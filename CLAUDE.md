This repository analyzes the Claude Code source to answer questions about how it actually behaves.
The official Anthropic docs lag the product, so the source is the ground truth. Findings are written
down in `analysis/` so they don't have to be re-derived; Claude Code ships often, and nothing updates
these docs automatically, so keeping them current is part of the work.

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

1. Find prior research. Open `analysis/README.md` (the index) and look up the topic. It maps each
   doc to its scope, the version it was verified against, and stable strings to grep.

2. Pick the source. Use the latest local `work/<version>`. If the matching doc's Verified version is
   behind that, treat its version-specific specifics as suspect and re-check them.

3. Research the bundle. Grep the doc's landmark strings to relocate the behavior; use the
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

- `code-intel` MCP — structure-aware navigation of the bundle (configured in `.mcp.json`).
- `anthropic-docs` / `claude-code-docs` MCP — the published docs, for the "is this still current?"
  check.
- `bin/render-prompts.py <version>` — regenerates `analysis/PROMPTS_RENDERED.md` verbatim from
  a bundle.
- `bin/generate-transcript-schema.py` — evolves `analysis/schemas/transcript.schema.json` from real
  session JSONL under `~/.claude/projects/`.
- Skills: `prepare-for-patch-generation`, `match-code-patterns`, `prepare-library-versions`,
  `search-for-libraries`, `compare-library-signatures`, `port-patch`. Agent: `identify-library-version`.
- `mcp/expert-server.mjs` — exposes this repo to other projects as `ask_claude_code_expert`.

# Where things are

- `analysis/README.md` — index of all findings docs. Start here.
- `analysis/GUIDELINES.md` — how to write and update analysis docs.
- `analysis/schemas/` — JSON Schemas for Claude Code's own files (frontmatter, transcript).
- `patches/` — patch corpus, with `README.md` (per-patch semantics) and `PATCH_METHODOLOGY.md`
  (per-version regeneration workflow).
- `work/<version>/package/cli.prettier.js` — the prettified sources, one dir per version.
