# Claude Desktop App Internals

These notes have been split into topic files under [`analysis/`](./analysis/). Start at
[`analysis/README.md`](./analysis/README.md).

| Topic                                                          | File                                              |
|----------------------------------------------------------------|---------------------------------------------------|
| Process model, file tree, IPC, native modules                  | [ARCHITECTURE](./analysis/ARCHITECTURE.md)        |
| Unpacking, repacking, re-verification recipes                  | [EXTRACTION](./analysis/EXTRACTION.md)            |
| Config stores, preferences, enterprise/user layering           | [CONFIGURATION](./analysis/CONFIGURATION.md)      |
| First-party vs third-party, enterprise sources, org policy     | [DEPLOYMENT_MODES](./analysis/DEPLOYMENT_MODES.md)|
| Environment variables                                          | [ENVIRONMENT_VARIABLES](./analysis/ENVIRONMENT_VARIABLES.md) |
| MCP SDK/protocol, server hosting, `.dxt`/`.mcpb`               | [MCP](./analysis/MCP.md)                          |
| MCP Apps (MCP-UI) support, including `updateModelContext`      | [MCP_APPS](./analysis/MCP_APPS.md)                |
| Feature codenames, Cowork/VM download control                  | [FEATURES](./analysis/FEATURES.md)                |
| `vm_bundles/` on disk: sparse images, guest FSes, VM updates   | [COWORK_VM](./analysis/COWORK_VM.md)              |
| Main-process, renderer, and native debugging                   | [DEBUGGING](./analysis/DEBUGGING.md)              |
