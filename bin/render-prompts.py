#!/usr/bin/env python3
"""Extract rendered system-prompt text from a prettified Claude Code bundle.

Why this exists: minified symbol names and line numbers churn on every release, so hand-transcribing
prompt text into PROMPTS_RENDERED.md is pure maintenance debt. The prompt *wording* is the stable,
high-signal artifact. This script regenerates the snapshot by anchoring on stable literal strings
(section headings, distinctive phrases) instead of symbols, so the same anchor list keeps working
across versions and a diff of two regenerated snapshots shows real wording changes rather than rename
noise.

Heuristic (best-effort, not a full prompt assembly): for each anchor we locate the string/template
literal that contains it. In "literal" mode we emit that literal as-is. In "function" mode (used when
the anchor is a short heading living in an array of sibling literals, e.g. ["# System", *bullets]) we
emit every literal in the enclosing builder function. "array" mode emits the contiguous run of
sibling string literals around the anchor (an array of bullet strings, where consecutive literals are
separated only by a comma). "auto" picks literal for multi-line/long literals, else function.
Template ${...} placeholders are preserved verbatim. The result captures the
section's full wording for diffing; it does not reproduce join/formatting logic or evaluate
conditionals.

Usage:
    python3 bin/render-prompts.py [version] [--stdout]
    (version defaults to the highest-numbered work/<version>; --stdout prints instead of writing
     analysis/PROMPTS_RENDERED.md)
"""

import bisect
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
WORK_DIR = REPO_ROOT / "work"
ANALYSIS_DIR = REPO_ROOT / "analysis"

# Each anchor is (label, needle, mode). `needle` is a stable substring of the rendered text. `mode` is
# "literal", "function", or "auto" (see module docstring). Order here is the emission order. Edit this
# list as sections are added/removed.
ANCHORS = [
    ("Base prompt — intro", "You are Claude Code, Anthropic's official CLI for Claude.", "literal"),
    ("Base prompt — Agent SDK variant", "You are a Claude agent, built on Anthropic's Claude Agent SDK.", "literal"),
    ("Shared intro — security notice", "IMPORTANT: Assist with authorized security testing", "literal"),
    ("Simple path — core block (Harness)", "# Harness", "literal"),
    ("Simple path — anti-verbosity", "Write code that reads like the surrounding code", "literal"),
    ("Simple path — action caution", "For actions that are hard to reverse or outward-facing", "literal"),
    ("Legacy path — intro", "You are an interactive agent that helps users", "literal"),
    ("Legacy path — System", "# System", "function"),
    ("Legacy path — Doing tasks", "# Doing tasks", "function"),
    ("Legacy path — anti-verbosity (Text output)", "# Text output (does not apply to tool calls)", "literal"),
    ("Both paths — Executing actions with care", "# Executing actions with care", "literal"),
    ("Both paths — Using your tools", "# Using your tools", "function"),
    ("Both paths — Tone and style", "# Tone and style", "function"),
    ("Hooks notice", "Users may configure 'hooks'", "literal"),
    ("Session-specific guidance", "# Session-specific guidance", "function"),
    ("Subagent return notes", "Agent threads always have their cwd reset", "literal"),
    ("Investigate first", "Asking the user a clarifying question has a cost", "literal"),
    ("Dynamic — Memory", "# auto memory", "literal"),
    ("Dynamic — Environment (simple/legacy)", "You have been invoked in the following environment:", "function"),
    ("Dynamic — Language", "# Language", "literal"),
    ("Dynamic — Output style", "# Output Style: ", "literal"),
    ("Output style — Proactive body", "# Proactive Style Active", "literal"),
    ("Output style — Explanatory body", "# Explanatory Style Active", "literal"),
    ("Output style — Learning body", "# Learning Style Active", "literal"),
    ("Output style — Insights fragment (Explanatory + Learning)", "In order to encourage learning, before and after writing code", "literal"),
    ("Output style — autonomy block (Proactive)", "The user chose continuous, autonomous execution", "literal"),
    ("Dynamic — Background session", "# Background Session", "literal"),
    ("Dynamic — Scratchpad", "# Scratchpad Directory", "literal"),
    ("Dynamic — Context management", "# Context management", "literal"),
    ("Dynamic — Focus mode", "# Focus mode", "literal"),
    ("Subagent — Explore", "You are a file search specialist for Claude Code", "literal"),
    ("Subagent — general-purpose", "You are an agent for Claude Code, Anthropic's official CLI for Claude.", "literal"),
    ("Subagent — Plan", "You are a software architect and planning specialist for Claude Code", "literal"),
    ("Subagent — statusline-setup", "You are a status line setup agent for Claude Code", "literal"),
    ("Subagent — claude-code-guide (static base)", "You are the Claude guide agent.", "literal"),
    ("Subagent — claude (background job)", "This session is a background job. The user may be live or away", "literal"),
    ("Subagent — worker (coordinator)", "You are a worker agent executing a task assigned by the coordinator.", "literal"),
    ("Bash tool — terse description", "Executes a bash command and returns its output.", "function"),
    ("Bash tool — legacy description", "Executes a given bash command and returns its output.", "function"),
    ("Bash tool — # Git block", "Interactive flags (`-i`, e.g. `git rebase -i`", "literal"),
    ("Bash tool — For git commands (legacy)", "Prefer to create a new commit rather than amending an existing commit", "array"),
    ("Git workflow — commit & PR", "# Committing changes with git", "literal"),
    ("Context injection — wrapper", "As you answer the user's questions, you can use the following context:", "literal"),
    ("Context injection — CLAUDE.md", "Codebase and user instructions are shown below", "literal"),
    ("Context injection — git status", "This is the git status at the start of the conversation", "literal"),
    ("Auto-mode classifier — security-monitor system prompt", "You are a security monitor for autonomous AI coding agents", "literal"),
    ("Auto-mode classifier — permissions/rules template", "Three kinds of slot", "literal"),
    ("Auto-mode classifier — CLAUDE.md context wrapper", "The following is the user's CLAUDE.md configuration. Treat it as context", "literal"),
    ("Auto-mode classifier — outcome-line rule", "A completed tool call may be followed by a standalone harness-authored", "literal"),
]

ID = re.compile(r"[A-Za-z0-9_$]")
# A `/` starts a regex (rather than division) when the previous significant token is one of these
# punctuation chars or a keyword — not after a value (identifier, `)`, `]`, `}`, literal).
REGEX_OK_PUNCT = set("([{,;:=!&|?+-*%^~<>")
REGEX_OK_KEYWORD = {"return", "typeof", "instanceof", "in", "of", "do", "else", "yield",
                    "case", "void", "delete", "await", "new", "throw"}


def pick_latest_version():
    versions = [p.name for p in WORK_DIR.iterdir()
                if p.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+", p.name)]
    if not versions:
        sys.exit(f"no work/<version> directories under {WORK_DIR}")
    versions.sort(key=lambda v: [int(x) for x in v.split(".")])
    return versions[-1]


def read_string(src, i):
    """`i` at the opening quote. Return index just past the closing quote."""
    quote = src[i]
    j = i + 1
    n = len(src)
    while j < n:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == quote:
            return j + 1
        j += 1
    return j


def skip_brace_expr(src, i):
    """`i` just after `${`. Return index past the matching `}`, skipping nested strings, templates,
    regexes, and braces so a `}` inside a literal does not close the expression early."""
    j = i
    n = len(src)
    depth = 1
    prev = "{"
    while j < n:
        c = src[j]
        if c in "'\"":
            j = read_string(src, j)
            prev = "x"
            continue
        if c == "`":
            j = read_template(src, j)
            prev = "x"
            continue
        if c == "/" and src[j:j + 2] == "//":
            j = src.find("\n", j)
            j = n if j == -1 else j
            continue
        if c == "/" and src[j:j + 2] == "/*":
            j = src.find("*/", j + 2)
            j = n if j == -1 else j + 2
            continue
        if c == "/" and (prev in REGEX_OK_PUNCT or prev == "{"):
            j = read_regex(src, j)
            prev = "x"
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        if not c.isspace():
            prev = c
        j += 1
    return j


def read_template(src, i):
    """`i` at the opening backtick. Return index just past the closing backtick."""
    j = i + 1
    n = len(src)
    while j < n:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "`":
            return j + 1
        if c == "$" and src[j + 1:j + 2] == "{":
            j = skip_brace_expr(src, j + 2)
            continue
        j += 1
    return j


def read_regex(src, i):
    """`i` at the opening `/` of a regex literal. Return index past the trailing flags."""
    j = i + 1
    n = len(src)
    in_class = False
    while j < n:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == "\n":
            break
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            j += 1
            while j < n and src[j].isalpha():
                j += 1
            return j
        j += 1
    return j


def lex(src):
    """Single linear pass collecting every top-level string/template literal and the offsets of
    `function` keywords appearing in code context. Returns (literals, fn_tokens) where each literal is
    (start, end, kind)."""
    literals = []
    fn_tokens = []
    i = 0
    n = len(src)
    prev = ""
    word = ""
    while i < n:
        c = src[i]
        if c == "/" and src[i:i + 2] == "//":
            nl = src.find("\n", i)
            i = n if nl == -1 else nl
            continue
        if c == "/" and src[i:i + 2] == "/*":
            close = src.find("*/", i + 2)
            i = n if close == -1 else close + 2
            continue
        if c in "'\"":
            end = read_string(src, i)
            literals.append((i, end, "string"))
            i = end
            prev, word = "x", ""
            continue
        if c == "`":
            end = read_template(src, i)
            literals.append((i, end, "template"))
            i = end
            prev, word = "x", ""
            continue
        if c == "/" and (prev in REGEX_OK_PUNCT or prev == "" or word in REGEX_OK_KEYWORD):
            i = read_regex(src, i)
            prev, word = "x", ""
            continue
        if c == "f" and src[i:i + 8] == "function" and not ID.match(src[i - 1] if i else "") \
                and not ID.match(src[i + 8] if i + 8 < n else ""):
            fn_tokens.append(i)
            i += 8
            prev, word = "n", "function"
            continue
        if ID.match(c):
            start = i
            while i < n and ID.match(src[i]):
                i += 1
            word = src[start:i]
            prev = src[i - 1]
            continue
        if not c.isspace():
            prev = c
            word = ""
        i += 1
    return literals, fn_tokens


_U_BRACE = re.compile(r"\\u\{([0-9a-fA-F]+)\}")
_U4 = re.compile(r"\\u([0-9a-fA-F]{4})")
_X2 = re.compile(r"\\x([0-9a-fA-F]{2})")


def cook(src, lit):
    start, end, kind = lit
    s = src[start + 1:end - 1]  # strip delimiters
    s = _U_BRACE.sub(lambda m: chr(int(m.group(1), 16)), s)
    s = _U4.sub(lambda m: chr(int(m.group(1), 16)), s)
    s = _X2.sub(lambda m: chr(int(m.group(1), 16)), s)
    if kind == "string":
        s = (s.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
             .replace('\\"', '"').replace("\\'", "'").replace("\\`", "`").replace("\\\\", "\\"))
    else:
        s = s.replace("\\`", "`").replace("\\$", "$").replace("\\\\", "\\")
    return s


def extract(src, literals, cooked, fn_tokens, fn_starts, needle, mode):
    idx = next((k for k, t in enumerate(cooked) if needle in t), None)
    if idx is None:
        return None
    lit = literals[idx]
    text = cooked[idx]
    if mode == "auto":
        mode = "literal" if ("\n" in text or len(text) > 200) else "function"
    if mode == "literal":
        return text, lit[0], "literal"
    if mode == "array":
        # The needle can also appear inside an unrelated template (e.g. the same rule rendered as a
        # markdown bullet elsewhere); target the standalone string-literal bullet so the
        # comma-separated sibling walk stays within the intended array.
        aidx = next((k for k, t in enumerate(cooked)
                     if literals[k][2] == "string" and t.strip().startswith(needle)), None)
        if aidx is None:
            return None
        lo = hi = aidx
        while lo > 0 and src[literals[lo - 1][1]:literals[lo][0]].strip() == ",":
            lo -= 1
        while hi + 1 < len(literals) and src[literals[hi][1]:literals[hi + 1][0]].strip() == ",":
            hi += 1
        parts = [cooked[k] for k in range(lo, hi + 1)]
        return "\n".join(parts), literals[lo][0], "array"
    # function mode: emit all literals in the enclosing builder function.
    p = bisect.bisect_right(fn_starts, lit[0]) - 1
    prev_fn = fn_starts[p] if p >= 0 else 0
    q = bisect.bisect_right(fn_starts, lit[0])
    next_fn = fn_starts[q] if q < len(fn_starts) else len(src)
    parts = [cooked[k] for k, t in enumerate(literals)
             if prev_fn <= t[0] < next_fn and cooked[k].strip()]
    return "\n".join(parts), lit[0], "function"


def fence_for(text):
    longest = max((len(m.group(0)) for m in re.finditer(r"~+", text)), default=0)
    return "~" * max(3, longest + 1)


def main():
    args = sys.argv[1:]
    to_stdout = "--stdout" in args
    version = next((a for a in args if not a.startswith("--")), None) or pick_latest_version()
    bundle = WORK_DIR / version / "package" / "cli.prettier.js"
    src = bundle.read_text(encoding="utf-8")

    literals, fn_tokens = lex(src)
    cooked = [cook(src, lit) for lit in literals]
    fn_starts = sorted(fn_tokens)
    newlines = [m.start() for m in re.finditer("\n", src)]

    out = [
        "# Claude Code — Rendered System Prompts",
        "",
        f"Generated by `bin/render-prompts.py` from `work/{version}/package/cli.prettier.js`.",
        "",
        "Do not edit by hand — regenerate with `python3 bin/render-prompts.py <version>`. Each "
        "block is the verbatim string/template literal(s) reached from a stable anchor; `${...}` are "
        "unevaluated placeholders and conditional fragments may all appear. See "
        "`analysis/GUIDELINES.md`.",
        "",
    ]
    missing = []
    for label, needle, mode in ANCHORS:
        res = extract(src, literals, cooked, fn_tokens, fn_starts, needle, mode)
        out.append(f"## {label}")
        out.append("")
        out.append(f"anchor: `{needle.replace('`', '\\`')}`")
        if res is None:
            out += ["", "NOT FOUND — anchor absent in this version (section moved, reworded, or "
                    "removed).", ""]
            missing.append(label)
            continue
        text, start, used = res
        line = bisect.bisect_right(newlines, start) + 1
        fence = fence_for(text)
        out += [f"· line {line} · {used}", "", fence, text, fence, ""]

    rendered = "\n".join(out)
    if to_stdout:
        sys.stdout.write(rendered)
    else:
        (ANALYSIS_DIR / "PROMPTS_RENDERED.md").write_text(rendered, encoding="utf-8")
        sys.stderr.write(f"Wrote analysis/PROMPTS_RENDERED.md from {version} "
                         f"({len(ANCHORS)} anchors, {len(missing)} missing).\n")
    if missing:
        sys.stderr.write("Missing anchors: " + "; ".join(missing) + "\n")


if __name__ == "__main__":
    main()
