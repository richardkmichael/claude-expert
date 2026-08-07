# Architecture

How the macOS Claude Desktop app is laid out: processes, the `app.asar` file tree, IPC, workers,
and native modules. See [README](./README.md) for the build banner and the rest of the doc set.


## Process model

Standard Electron two-process design.

- Main process (Node.js): manages windows, IPC, config, spawns MCP servers, handles OS
  integration, and hosts the bundled Claude Code / Agent SDK subprocess. Entry point is
  `.vite/build/index.pre.js` (the `main` field in `package.json`).
- Renderer process (Chromium): the native window chrome is a local bundle under
  `.vite/renderer/main_window/`, but the actual Claude app is the remote `https://claude.ai/new`
  frontend loaded into a `WebContentsView`. Context bridges expose native capabilities to it.

The claude.ai frontend being remote is load-bearing for several features. Anything implemented in
the web frontend (for example the MCP Apps host — see [MCP_APPS](./MCP_APPS.md)) is not in this
bundle and version-drifts independently of the desktop shell.


## Main-process bundle

The main-process code is minified and split by Vite:

| File                   | Size    | Role                                                     |
|------------------------|---------|----------------------------------------------------------|
| `index.pre.js`         | ~4.6 MB | Main entry (`package.json` `main`); largest bundle       |
| `index.js`             | ~800 B  | Sentry-release stub; `require`s the bootstrap chunk      |
| `index.chunk-*.js`     | ~90     | Code-split modules (deployment, env handling, UI IPC)    |
| `mainWindow.js`        | ~176 KB | Title bar and window chrome                              |
| `mainView.js`          | ~231 KB | `WebContentsView` context bridge                         |
| `quickWindow.js`       | ~153 KB | Spotlight / quick-entry window                           |
| `aboutWindow.js`       | ~153 KB | About dialog                                             |
| `findInPage.js`        | ~151 KB | Find-in-page                                             |
| `buddy.js`             | ~70 KB  | Hardware Buddy companion window                          |
| `coworkArtifact.js`    | ~3 KB   | Cowork artifact preview window                           |
| `claudePagePreview.js` | ~1 KB   | Page-preview window                                      |
| `computerUseTeach.js`  | ~1 KB   | Computer Use teach-mode UI                               |
| `computerUseWatchRecord.js`, `watchRecordChooser.js` | ~1 KB | Computer Use recording UI       |

The single-`index.js`-holds-everything layout from older builds is gone; the bulk now lives in
`index.pre.js` plus the chunk set. To search minified JS, split on separators first:

```bash
tr ';' '\n' < index.pre.js | grep "searchTerm"
tr ',' '\n' < index.pre.js | grep -B2 -A2 "searchTerm"
```

Because the code is split, grep across the whole directory rather than one file:

```bash
grep -rl "searchTerm" .vite/build/*.js
```


## Workers

Under `.vite/build/`, each in its own subdirectory:

| Worker                     | Purpose                                            |
|----------------------------|----------------------------------------------------|
| `mcp-runtime/`             | MCP server hosting — see [MCP](./MCP.md)           |
| `pty-host/`                | PTY host process for terminal sessions             |
| `file-index-worker/`       | File indexing                                      |
| `heavy-work-worker/`       | Offloaded CPU-heavy work                           |
| `shell-path-worker/`       | Shell `PATH` extraction                            |
| `transcript-search-worker/`| Transcript full-text search                        |

The older `sqlite-worker/` is gone; `file-index-worker/` and `heavy-work-worker/` are new, and PTY
work moved into a dedicated `pty-host/`.


## Native modules and bundled resources

Native code (compiled Mach-O `.node`) lives under `node_modules/`:

| Path                                                  | Purpose                              |
|-------------------------------------------------------|--------------------------------------|
| `@ant/claude-native/claude-native-binding.node`       | Native OS integrations               |
| `@ant/claude-swift/build/Release/swift_addon.node`    | macOS Swift interop                  |
| `@ant/claude-swift/build/Release/computer_use.node`   | Computer Use native support          |
| `node-pty/prebuilds/darwin-{x64,arm64}/pty.node`      | PTY for terminal sessions            |

The top-level `resources/` directory ships auxiliary payloads:

| Path                            | Purpose                                                     |
|---------------------------------|-------------------------------------------------------------|
| `resources/office365-mcp/`      | Bundled Office 365 MCP server (`msal-node-runtime.node`)    |
| `resources/bundled-skills/`     | Agent skills shipped with the app                           |

The MCP SDK is inlined into the main-process bundle by Vite; there is no separate `node_modules`
entry for `@modelcontextprotocol/sdk`.


## IPC

Renderer-to-main IPC uses a custom channel-name format:

```
$eipc_message$_{uuid}_$_{namespace}_$_{component}_$_{method}
```

Observed namespaces:

| Namespace                   | Area                                              |
|-----------------------------|---------------------------------------------------|
| `claude.web`                | Main web-app interface (auth, filesystem, sessions, extensions) |
| `claude.settings`           | Desktop config (AppConfig, MCP, shortcuts, extensions)          |
| `claude.internal.ui`        | Native UI (title bar, about, quick window)        |
| `claude.internal.findInPage`| Find-in-page                                      |
| `claude.skills`             | Agent skills                                      |
| `claude.hybrid`             | Hybrid local/remote agent surface                 |
| `claude.buddy`              | Hardware Buddy                                    |
| `claude.coworkArtifact`     | Cowork artifact preview                           |
| `claude.officeAddin`        | Office add-in bridge                              |
| `claude.simulator`          | iOS/Android simulator access                      |
