This repository analyzes two Anthropic products from the code they ship, to answer questions about
how they actually behave:

| Path       | Product                       | Instructions        |
| ---------- | ----------------------------- | ------------------- |
| `code/`    | Claude Code, the CLI          | `code/CLAUDE.md`    |
| `desktop/` | Claude Desktop, the macOS app | `desktop/CLAUDE.md` |

The published docs lag both products, so the shipped code is the ground truth. Findings are written
down so they don't have to be re-derived. Nothing updates them automatically: a doc is brought up to
date when a question needs it, so keeping the docs current is part of answering.

Before researching a product, read its `CLAUDE.md`. A session started at the repository root loads a
subdirectory's `CLAUDE.md` only after it reads a file in that subdirectory.

Claude Desktop downloads a pinned Claude Code version and runs it as a separate process. Questions
about that Claude Code are answered from `code/`.

This repo also runs as an MCP server other projects can consult instead of `/add-dir`-ing it in:
`mcp/claude-expert.mjs` exposes `ask_claude_code_expert` and `ask_claude_desktop_expert`, each
backed by a nested headless Claude session started in its product's subdirectory. See
`mcp/README.md` for registration and design.

# Documenting findings

When you confirm, correct, or discover behavior, update the product's docs in the same session. A
question answered from the source but not written back is research lost. Each product's `CLAUDE.md`
gives its procedure. Common to both:

- Anchor on version-stable strings: literal prompt and UI strings, telemetry event names, env vars,
  config keys, tool names, and the behavioral logic itself. Never anchor on minified symbol names,
  line numbers, or pasted code, which churn every release. In place of a line number, give a grep
  relocation recipe plus the expected shape.
- Record the version a doc was checked against in its YAML frontmatter (`verified`, `verified_on`).
  The stamp covers the whole doc: move it forward only after checking every claim in the doc against
  the new version.
- The index tables in each product's `analysis/README.md` are generated from that frontmatter. After
  adding a doc or changing its frontmatter, run `bin/analysis-index.py` and commit the README with
  the doc. Never edit the tables by hand.
- A doc describes the current state of the version it is stamped with, and nothing else. When a
  claim no longer holds, rewrite or delete it. Do not keep history: no "in earlier versions", no
  "was renamed from", no Version history sections or dated appendices. Git history records how a doc
  changed.
- A version stamp only moves forward. A doc keeps describing the version it is stamped with. When
  you check an older version and it differs, report that in your answer; do not write it into the
  doc.

# Commit subjects

```
(<product> <version>) <kind>: <description>
```

- product: `code`, `desktop`, or `repo` for a change that serves both products or the repository
  itself. The product is what the change is about, not where the file lives.
- version: the product version the change was checked against. Only on a commit about one version,
  usually `analysis`. Omit it otherwise, as in `(code) skills: ...`.
- kind: `analysis`, `bin`, `skills`, `mcp`, `patches` or `docs`. `docs` also covers `CLAUDE.md`,
  READMEs, and config files such as `.mcp.json` and `.gitignore`.

```
(code 2.1.316) analysis: Document project config discovery from a subdirectory
(desktop 1.26832.0) analysis: Update environment variables for 1.26832.0
(repo) docs: Move the desktop MCP servers into the root .mcp.json
```

# Searching shipped code

- Search a bundle with `rg`, never `grep`. In the Bash tool, `grep` is a shell function that runs
  the ugrep built into the `claude` binary (`type grep` shows the function; `grep --version` reports
  ugrep). ugrep slows down in proportion to a bounded repetition such as `[^"]{0,90}`, with or
  without an alternation after it: over the 70 MB `cli.prettier.js` such a pattern runs for tens of
  seconds or more, where `rg` takes a fraction of a second, and `-U` does not help. Use `rg` for
  every bundle scan; keep `grep` to fixed strings (`-F`).
- When you grep a raw artifact instead — a native binary, or minified JS with no line breaks (e.g.
  to bisect versions without prettifying) — match for presence, not lines: `grep -aqF` (true/false
  via exit code), `-ac` (count), or `-ao` (just the matched substring). Bare line output dumps a
  multi-KB line or binary bytes; `-a` treats the file as text so the match isn't skipped.
- A zero-hit grep does not prove absence. Strings the product renders are often assembled from
  parts, so the rendered text never appears as one literal — a heading built as `` `## ${CONST}` ``
  will not match a search for the full heading, and neither will text interpolated from a hoisted
  variable or split across a concatenation. Before concluding a feature was removed, search a
  distinctive substring that cannot span an interpolation boundary, then follow the constant or
  variable to its use site. Reserve "absent" for when that shorter search also comes back empty.
