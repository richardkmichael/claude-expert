This directory is for exploring the operation of Claude Desktop, a macOS app. Paths below are
relative to `desktop/`. Repository-wide conventions, including commit subjects and how to search a
bundle, are in the root `CLAUDE.md`.

## The source

- The app's own code ships in `/Applications/Claude.app/Contents/Resources/app.asar`. Only the
  installed build is available: Claude Desktop updates itself, and older builds are not
  downloadable.
- The `prepare-claude-desktop-source` skill extracts the installed build into
  `work/<app-version>/app` and formats its code. It writes `work/<app-version>/manifest.json` with
  the build info and the Claude Code version the build pins. Running it again for a prepared build
  only prints the manifest.
- Claude Desktop runs Claude Code as a separate process. It does not ship it in the bundle. It
  downloads the pinned version at runtime (see `analysis/ARCHITECTURE.md`, "Claude Code
  subprocess").
- `bin/asar-search.py <needle>` lists the files inside `app.asar` that contain a string, without
  extracting it.

## Answering a question about Claude Desktop

1. Prepare the source. Run the `prepare-claude-desktop-source` skill and read the manifest it
   prints.

2. Find prior research. Open `analysis/README.md` and look up the topic. Its document map gives each
   doc's Verified build. If that is behind the installed build, treat the doc's build-specific
   details as suspect and re-check them.

3. Research the extracted code under `work/<app-version>/app/`, mostly `.vite/build/`. Search with
   `rg` (see the root `CLAUDE.md`), and anchor on string literals and behavior, not minified names.

4. For anything about the Claude Code that Desktop runs, research the version the manifest pins
   (`claudeCode.version`), not the newest one in `../code/work/`. Run the
   `prepare-claude-code-source` skill if `../code/work/<version>/` is missing, and follow
   `../code/CLAUDE.md`.

5. Record what you found:

   - Desktop findings go in `analysis/`. Restamp the doc's Verified build in the document map in the
     same commit. Use `*` when only some sections were re-checked, and say which in the doc's
     Version history.
   - Claude Code findings go in `../code/analysis/`, following `../code/CLAUDE.md`. Its stamps only
     move forward, so a check against an older pinned version adds a Version history line instead of
     lowering the stamp.
   - Commit Desktop findings with the subject `(desktop <version>) analysis: <description>`, where
     `<version>` is the app build analyzed.

## Model Context Protocol functionality

Areas of interest are MCP Server integration: Claude Desktop support of MCP and MCP Apps

- MCP Specification is available via the `mcp-specification` tool
- "MCP Apps" is an extension specification to the MCP Specification, it descriptions GUI components inside Claude Desktop
  - ~/src/modelcontextprotocol/ext-apps/main/specification/
  - ~/src/modelcontextprotocol/ext-apps/main/docs/patterns.md

We build MCP servers with FastMCP and Prefab which are MCP frameworks in Python:

- Documentation available for both via tools: `fastmcp_documentation` and `prefab_documentation`
  - ~/src/fastmcp/fastmcp/main
  - ~/src/fastmcp/prefab/main
- Important: prefab bundles the MCP Apps SDK in its renderer
  - ~/src/fastmcp/prefab/main/renderer
