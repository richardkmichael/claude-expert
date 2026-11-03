# Claude Desktop Internals

Notes on how the macOS Claude Desktop app is laid out and what config files, environment variables,
and managed preferences influence its behavior.

Each doc records the build it was last verified against in its YAML frontmatter (`verified`,
`verified_on`, `scope`). The document map below is generated from that frontmatter by
`../../bin/analysis-index.py`: never edit it by hand. When the installed build is newer, treat a
doc's build-specific details as suspect and re-check them. Docs are brought up to date when a
question needs them, not all at once, so their builds differ. A doc describes only the build it is
stamped with, and a stamp only moves forward.

## Document map

<!-- analysis-index -->

| File                                                | Covers                                                                             | Verified |
| --------------------------------------------------- | ---------------------------------------------------------------------------------- | -------- |
| [ARCHITECTURE](./ARCHITECTURE.md)                   | Product surfaces, process model, Claude Code subprocess, file tree, workers, IPC   | 4.4212.0 |
| [CONFIGURATION](./CONFIGURATION.md)                 | Config stores, preferences schema, enterprise/user layering                        | 4.4212.0 |
| [COWORK_VM](./COWORK_VM.md)                         | Where Cowork runs (device or cloud); the local VM's `vm_bundles/`, images, updates | 4.4212.0 |
| [DEBUGGING](./DEBUGGING.md)                         | Main-process, renderer, and native debugging; CDP auth                             | 4.4212.0 |
| [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md)           | First-party vs third-party (`Claude-3p`), enterprise sources, org policy           | 4.4212.0 |
| [ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md) | Main-process env vars; the bundled Claude Code surface                             | 4.4212.0 |
| [EXTRACTION](./EXTRACTION.md)                       | Unpacking, repacking/re-signing, re-verification recipes                           | 4.4212.0 |
| [FEATURES](./FEATURES.md)                           | Feature codenames, Cowork/VM download control, `chillingSloth`                     | 4.4212.0 |
| [LAUNCH_PREVIEW](./LAUNCH_PREVIEW.md)               | Code-session Browser pane: `.claude/launch.json`, element picker, preview network  | 4.4212.0 |
| [MCP](./MCP.md)                                     | MCP SDK/protocol, server hosting, transports, `.dxt`/`.mcpb`                       | 4.4212.0 |
| [MCP_APPS](./MCP_APPS.md)                           | MCP Apps (MCP-UI) support, including `updateModelContext`                          | 4.4212.0 |
| [RESET_LIMITS](./RESET_LIMITS.md)                   | Usage-limit reset grants: the claude.ai endpoints that read and apply them         | 4.4212.0 |

<!-- /analysis-index -->

## Refreshing after an update

Run the `prepare-claude-desktop-source` skill to extract the fresh build, and run the
[re-verification recipes](./EXTRACTION.md) against it. Then update any drifted facts, restamp the
frontmatter of each doc you re-checked in full, and regenerate the document map. Key things that
move between builds:

- The bundle is code-split, and the split changes between builds. `manifest.json` records the split
  for each prepared build. Search the whole `.vite/build/` directory rather than one file or one
  chunk family.
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
- Desktop Extensions / one-click MCP install:
  <https://www.anthropic.com/engineering/desktop-extensions>
- Claude Cowork product page: <https://www.anthropic.com/product/claude-cowork>
