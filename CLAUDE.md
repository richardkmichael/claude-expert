This repository analyzes the Claude Code source to answer questions about how it actually behaves.
The official Anthropic docs lag the product, so the source is the ground truth. Findings are written
down in `analysis/` so they don't have to be re-derived; Claude Code ships often, and nothing updates
these docs automatically, so keeping them current is part of the work.

This repo also runs as an MCP server other projects can consult instead of `/add-dir`-ing it in:
`mcp/expert-server.mjs` exposes one tool, `ask_claude_code_expert`, backed by a nested headless
Claude session rooted here. See `mcp/README.md` for registration and design.

# The source

- `cli.prettier.js` is Claude Code. For versions <= 2.1.116 it is a minified Node.js application
  shipped via npm; for >= 2.1.117 it is the JavaScript extracted from a bun-compiled native binary.
  Either way the prettified form lives at `work/<version>/package/cli.prettier.js`.
- It is self-contained: no `package.json`, lock file, or `node_modules` — all dependencies are
  bundled inline.
- The original unminified source is not available.
- Latest local version: `ls work/ | sort -V | tail -1`. If the version asked about isn't present,
  the `prepare-for-patch-generation` skill downloads and prettifies it.

# Answering a question about Claude Code

0. First consult the `@claude-code-guide` subagent with the question.  This may reveal additional
   strings to help search the source code, or clarify behaviours and findings from the source code.

1. Find prior research. Open `analysis/README.md` (the index) and look up the topic. It maps each
   doc to its scope, the version it was verified against, and stable strings to grep.

2. Pick the source. Use the latest local `work/<version>`. If the matching doc's Verified version is
   behind that, treat its version-specific specifics as suspect and re-check them.

3. Research the bundle. Search the doc's landmark strings with `rg` (not `grep` — see Research
   tooling) to relocate the behavior; use the
   `code-intel` MCP for structure-aware navigation and `bin/render-prompts.py` for prompt
   text. App and library code are interleaved in the bun-compiled bundle, so anchor on
   app-specific strings (`tengu_*`, prompt literals, tool names, `CLAUDE_CODE_*` env vars) — these
   do not appear inside third-party libraries.

4. Cross-check the official docs when the question is whether documented behavior is current. The
   `anthropic-docs` and `claude-code-docs` MCP servers hold the published docs; drift between those
   and the source is the reason this repo exists. Report the drift in your answer.

5. Record what you found (see below). A question answered from the source but not written back is
   research lost.

# Documenting findings

When you confirm, correct, or discover behavior, update the docs in the same session:

- Update the matching `analysis/` doc, or add a new one, in the landmark style: anchor on
  version-stable strings (literal prompt/UI strings, `tengu_*` names, env vars, config keys, tool
  names, behavioral logic) — never on minified symbol names, line numbers, or pasted code, which
  churn every release. Replace line numbers with a grep relocation recipe plus the expected shape.
- Restamp the doc's verified version and bump its row in `analysis/README.md` in the same commit.
- If the doc was `legacy` style, retrofit the section you touched instead of leaving line-number
  anchors behind.
- Commit with a scoped subject: `(analysis:<version>) short description`, where `<version>` is the
  `cli.prettier.js` version analyzed.

Full methodology, including the version-stamp and update procedure: `analysis/GUIDELINES.md`.

# Research tooling

- Search the bundle with `rg`, never `grep`. In the Bash tool, `grep` is bundled `ugrep` dispatched
  busybox-style from the `claude` binary itself (argv-switched — not installed on the machine, and it
  presents only as `grep`, so you cannot detect it). It catastrophically backtracks on bounded
  quantifier + alternation patterns (`[^"]{0,90}(a|b|c)…`) over the 25MB `cli.prettier.js` and hangs.
  `rg` uses a DFA and stays fast — use it for every bundle scan; restrict `grep` to fixed strings (`-F`).
- When you grep a raw artifact instead — a native binary, or minified JS with no line breaks (e.g. to
  bisect versions without prettifying) — match for presence, not lines: `grep -aqF` (true/false via exit
  code), `-ac` (count), or `-ao` (just the matched substring). Bare line output dumps a multi-KB line or
  binary bytes; `-a` treats the file as text so the match isn't skipped.
- A zero-hit grep does not prove absence. Strings the product renders are often assembled from parts,
  so the rendered text never appears as one literal — a heading built as `` `## ${CONST}` `` will not
  match a search for the full heading, and neither will text interpolated from a hoisted variable or
  split across a concatenation. Before concluding a feature was removed, search a distinctive
  substring that cannot span an interpolation boundary, then follow the constant or variable to its
  use site. Reserve "absent" for when that shorter search also comes back empty.
- `code-intel` MCP — structure-aware navigation of the bundle (configured in `.mcp.json`).
- `anthropic-docs` / `claude-code-docs` MCP — the published docs, for the "is this still current?"
  check.
- `bin/render-prompts.py <version>` — regenerates `analysis/PROMPTS_RENDERED.md` verbatim from
  a bundle.
- `bin/generate-transcript-schema.py` — evolves `analysis/schemas/transcript.schema.json` from real
  session JSONL under `~/.claude/projects/`.
- Skills: `prepare-for-patch-generation`, `match-code-patterns`, `port-patch`.
- `mcp/expert-server.mjs` — exposes this repo to other projects as `ask_claude_code_expert`.

# Where things are

- `analysis/README.md` — index of all findings docs. Start here.
- `analysis/GUIDELINES.md` — how to write and update analysis docs.
- `analysis/schemas/` — JSON Schemas for Claude Code's own files (frontmatter, transcript).
- `patches/README.md` — patch corpus index: the per-patch catalog (`PATCHES.md`) and the
  regeneration workflow (`METHODOLOGY.md`).
- `work/<version>/package/cli.prettier.js` — the prettified sources, one dir per version.
- `mcp/README.md` — this repo's own MCP server (`ask_claude_code_expert`): register it in another
  project to query this repo's Claude Code knowledge without leaving that project's context.
