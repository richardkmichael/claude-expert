Claude Code analysis. Paths below are relative to `code/`. Repository-wide conventions, including
commit subjects and how to search a bundle, are in the root `CLAUDE.md`.

# The source

- `cli.prettier.js` is Claude Code. For versions up to 2.1.116 it is a minified Node.js application
  shipped via npm; from 2.1.117 it is the JavaScript extracted from a bun-compiled native binary.
  Either way the prettified form lives at `work/<version>/package/cli.prettier.js`.
- A bun-compiled binary embeds several JavaScript modules, so `cli.prettier.js` is their
  concatenation in the binary's own order, each preceded by a `// ==== bun module: <name> ====`
  banner naming the module a match came from. Chunk names are content hashes and change every
  release, so read a banner to orient yourself, never as a landmark.
- How the application is distributed across those modules changed at 2.1.242. Up to 2.1.241 it is
  one multi-megabyte `cli` module alongside a handful of vendor bundles (mermaid, highlight.js,
  Chart.js) and native-addon shims. From 2.1.242 it is split across a thousand-odd `chunk-<hash>.js`
  modules behind a small `cli` entry module, and cross-module references resolve through the
  `import`/`export` lists at each module's edges. Extracting only the entry module of a split binary
  yields a stub of a few hundred lines, not the application.
- It is self-contained: no `package.json`, lock file, or `node_modules` — all dependencies are
  bundled inline.
- The original unminified source is not available.
- Latest local version: `ls work/ | sort -V | tail -1`. If the version asked about isn't present,
  the `prepare-claude-code-source` skill downloads and prettifies it.

# Answering a question about Claude Code

0. If a `claude-code-guide` subagent is available, consult it first with the question. It may reveal
   additional strings to search for, or clarify behaviors and findings from the source code.

1. Find prior research. Open `analysis/README.md` (the index) and look up the topic. It maps each
   doc to its scope, the version it was verified against, and stable strings to grep.

2. Pick the source. Use the version the question names; otherwise the latest local `work/<version>`.
   If the matching doc's Verified version is behind that, treat its version-specific details as
   suspect and re-check them.

3. Research the bundle. Search the doc's landmark strings with `rg` (not `grep` — see the root
   `CLAUDE.md`) to relocate the behavior; use `bin/render-prompts.py` for prompt text. App and
   library code are interleaved in the bun-compiled bundle, so anchor on app-specific strings
   (`tengu_*`, prompt literals, tool names, `CLAUDE_CODE_*` env vars) — these do not appear inside
   third-party libraries.

4. Cross-check the official docs when the question is whether documented behavior is current. The
   `claude-code-docs` MCP server holds the published docs; drift between those and the source is the
   reason this repo exists. Report the drift in your answer.

5. Record what you found (see below). A question answered from the source but not written back is
   research lost.

# Documenting findings

Update the matching `analysis/` doc, or add a new one, following the root `CLAUDE.md`'s "Documenting
findings" rules. In addition:

- Restamp the doc's verified version and bump its row in `analysis/README.md` in the same commit.
- If the doc was `legacy` style, retrofit the section you touched instead of leaving line-number
  anchors behind.
- Commit with the subject `(code <version>) analysis: <description>`, where `<version>` is the
  `cli.prettier.js` version analyzed.

Full methodology, including the version-stamp and update procedure: `analysis/GUIDELINES.md`.

# Research tooling

- `claude-code-docs` MCP — the published docs, for the "is this still current?" check.
- `bin/render-prompts.py <version>` — regenerates `analysis/PROMPTS_RENDERED.md` verbatim from a
  bundle.
- `bin/generate-transcript-schema.py` — evolves `analysis/schemas/transcript.schema.json` from real
  session JSONL under `~/.claude/projects/`.
- Skills, in the repository root's `.claude/skills/`: `prepare-claude-code-source`,
  `match-code-patterns`, `port-patch`.

# Where things are

- `analysis/README.md` — index of all findings docs. Start here.
- `analysis/GUIDELINES.md` — how to write and update analysis docs.
- `analysis/schemas/` — JSON Schemas for Claude Code's own files (frontmatter, transcript).
- `patches/README.md` — patch corpus index: the per-patch catalog (`PATCHES.md`) and the
  regeneration workflow (`METHODOLOGY.md`).
- `work/<version>/package/cli.prettier.js` — the prettified sources, one dir per version.
