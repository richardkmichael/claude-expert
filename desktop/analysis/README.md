# Claude Desktop Internals

Notes on how the macOS Claude Desktop app is laid out and what config files, environment variables,
and managed preferences influence its behavior. These notes track the build in the banner below;
update the banner and any drifted details when re-extracting a newer build.

| Field             | Value                                      |
|-------------------|--------------------------------------------|
| App version       | 1.22209.3                                  |
| Build commit      | babe11577dfefe3e209c06bd674628d862f0dbae   |
| Build timestamp   | 2026-07-19                                 |
| Build type        | prod                                       |
| Platform observed | darwin (macOS)                             |


## Document map

| File                                                 | Covers                                                        |
|------------------------------------------------------|---------------------------------------------------------------|
| [ARCHITECTURE](./ARCHITECTURE.md)                    | Process model, `app.asar` file tree, workers, native modules, IPC |
| [EXTRACTION](./EXTRACTION.md)                        | Unpacking, repacking/re-signing, re-verification recipes      |
| [CONFIGURATION](./CONFIGURATION.md)                  | Config stores, preferences schema, enterprise/user layering   |
| [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md)            | First-party vs third-party (`Claude-3p`), enterprise sources, org policy |
| [ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md)  | Main-process env vars; the bundled Claude Code surface        |
| [MCP](./MCP.md)                                      | MCP SDK/protocol, server hosting, transports, `.dxt`/`.mcpb`  |
| [MCP_APPS](./MCP_APPS.md)                            | MCP Apps (MCP-UI) support, including `updateModelContext`     |
| [FEATURES](./FEATURES.md)                            | Feature codenames, Cowork/VM download control, `chillingSloth`|
| [COWORK_VM](./COWORK_VM.md)                          | `vm_bundles/` on disk: sparse images, guest filesystems, VM versioning and updates |
| [DEBUGGING](./DEBUGGING.md)                          | Main-process, renderer, and native debugging; CDP auth        |

[COWORK_VM](./COWORK_VM.md) was verified against a newer build (1.26832.0) than the banner above;
it carries its own build note. The rest of the set still tracks 1.22209.3.


## Refreshing after an update

Re-run the extraction and the [re-verification recipes](./EXTRACTION.md) against the fresh build,
then update the banner and any drifted facts. Key things that move between builds:

- The bundle is code-split (a small `index.js` stub, a large `index.pre.js`, and ~90
  `index.chunk-*.js`), so search the whole `.vite/build/` directory, not one file.
- Minified identifiers and single-letter names change every build. Anchor on string literals and
  behavior instead; treat any identifier quoted in these notes as a snapshot illustration.
- The main app UI is the remotely-served `https://claude.ai` frontend loaded in a `WebContentsView`.
  Web-frontend features (for example the MCP Apps host) are not in this bundle and version-drift
  independently.


## Official Anthropic documentation

Anthropic does not publish a comprehensive reference for Claude Desktop's internals; these notes are
the gap-filler. Adjacent public docs:

- Download: <https://claude.com/download>
- Release notes: <https://docs.anthropic.com/en/release-notes/claude-apps>
- Claude Code desktop quickstart: <https://code.claude.com/docs/en/desktop-quickstart>
- Claude Code settings (env-var conventions): <https://code.claude.com/docs/en/settings>
- Desktop Extensions / one-click MCP install: <https://www.anthropic.com/engineering/desktop-extensions>
- Claude Cowork product page: <https://www.anthropic.com/product/claude-cowork>
