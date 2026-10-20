# Claude Desktop Internals

Notes on how the macOS Claude Desktop app is laid out and what config files, environment variables,
and managed preferences influence its behavior. These notes track the build in the banner below;
update the banner and any drifted details when re-extracting a newer build.

| Field             | Value                                      |
|-------------------|--------------------------------------------|
| App version       | 1.26832.0                                  |
| Build commit      | 056ee2be623b207f6a4d24dfb1b2fb5a82db0ecf   |
| Build timestamp   | 2026-08-06T05:43:05Z                       |
| Build type        | prod                                       |
| Platform observed | darwin (macOS)                             |


## Document map

| File                                                | Covers                                                                             |
| --------------------------------------------------- | ---------------------------------------------------------------------------------- |
| [ARCHITECTURE](./ARCHITECTURE.md)                   | Process model, `app.asar` file tree, workers, native modules, IPC                  |
| [EXTRACTION](./EXTRACTION.md)                       | Unpacking, repacking/re-signing, re-verification recipes                           |
| [CONFIGURATION](./CONFIGURATION.md)                 | Config stores, preferences schema, enterprise/user layering                        |
| [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md)           | First-party vs third-party (`Claude-3p`), enterprise sources, org policy           |
| [ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md) | Main-process env vars; the bundled Claude Code surface                             |
| [MCP](./MCP.md)                                     | MCP SDK/protocol, server hosting, transports, `.dxt`/`.mcpb`                       |
| [MCP_APPS](./MCP_APPS.md)                           | MCP Apps (MCP-UI) support, including `updateModelContext`                          |
| [FEATURES](./FEATURES.md)                           | Feature codenames, Cowork/VM download control, `chillingSloth`                     |
| [COWORK_VM](./COWORK_VM.md)                         | `vm_bundles/` on disk: sparse images, guest filesystems, VM versioning and updates |
| [DEBUGGING](./DEBUGGING.md)                         | Main-process, renderer, and native debugging; CDP auth                             |
| [RESET_LIMITS](./RESET_LIMITS.md)                   | Usage-limit reset grants: the claude.ai endpoints that read and apply them         |

Every file in the set was re-verified against the banner build.


## Refreshing after an update

Re-run the extraction and the [re-verification recipes](./EXTRACTION.md) against the fresh build,
then update the banner and any drifted facts. Key things that move between builds:

- The bundle is code-split: `index.pre.js` is the entry point, alongside 203 `index.chunk-*.js`,
  130 `index2.chunk-*.js` and 14 entry-point files. Search the whole `.vite/build/` directory
  rather than one file or one chunk family. The count keeps growing — it was ~90 chunks two builds
  ago.
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
