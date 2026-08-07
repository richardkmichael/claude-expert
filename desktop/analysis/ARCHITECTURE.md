# Architecture

How the macOS Claude Desktop app is laid out: processes, the `app.asar` file tree, IPC, workers,
and native modules. See [README](./README.md) for the build banner and the rest of the doc set.


## Process model

Standard Electron two-process design.

- Main process (Node.js): manages windows, IPC, config, spawns MCP servers, handles OS
  integration, and hosts the bundled Claude Code / Agent SDK subprocess. Entry point is
  `.vite/build/index.pre.js` (the `main` field in `package.json`).
- Renderer process (Chromium): the native window chrome is a set of local bundles under
  `.vite/renderer/` (`main_window`, `about_window`, `buddy_window`, `find_in_page`,
  `local_exec_consent`, `quick_window`), but the actual Claude app is the remote `https://claude.ai`
  frontend loaded into a `WebContentsView`. Context bridges expose native capabilities to it.

The frontend base URL is the bare `https://claude.ai`. `CLAUDE_AI_URL` overrides it only in `dev`
builds, or in prod when the developer dev-URL override has been approved — see
[ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md).

The claude.ai frontend being remote is load-bearing for several features. Anything implemented in
the web frontend (for example the MCP Apps host — see [MCP_APPS](./MCP_APPS.md)) is not in this
bundle and version-drifts independently of the desktop shell.


## Main-process bundle

The main-process code is minified and split by Vite:

| File                        | Size    | Role                                                 |
|-----------------------------|---------|-------------------------------------------------------|
| `index.pre.js`              | ~4.6 MB | Main entry (`package.json` `main`); largest bundle    |
| `index.chunk-*.js`          | 203     | Code-split modules (deployment, env handling, UI IPC) |
| `index2.chunk-*.js`         | 130     | Second chunk family — Cowork/VM, OAuth, preferences   |
| `index.js`                  | ~236 KB | Aggregating module — `require`s ~100 chunks and re-exports |
| `mainView.js`               | ~233 KB | `WebContentsView` context bridge                      |
| `mainWindow.js`             | ~166 KB | Title bar and window chrome                           |
| `aboutWindow.js`            | ~143 KB | About dialog                                          |
| `quickWindow.js`            | ~143 KB | Spotlight / quick-entry window                        |
| `findInPage.js`             | ~142 KB | Find-in-page                                          |
| `buddy.js`                  | ~65 KB  | Hardware Buddy companion window                       |
| `computerUseWatchRecord.js` | ~6.5 KB | Computer Use recording UI                             |
| `watchRecordChooser.js`     | ~6.5 KB | Computer Use recording chooser                        |
| `computerUseTeach.js`       | ~6.5 KB | Computer Use teach-mode UI                            |
| `coworkArtifact.js`         | ~2.3 KB | Cowork artifact preview window                        |
| `localExecConsent.js`       | ~1.4 KB | Local-execution consent prompt                        |
| `claudePagePreview.js`      | ~725 B  | Page-preview window                                   |

That is 347 `.js` files directly under `.vite/build/`: 203 `index.chunk-*`, 130 `index2.chunk-*`,
and 14 entry points. Both chunk families matter — the Cowork VM code lives in `index.chunk-*` but
its warm-bundle and manifest helpers are `index2.chunk-*`, so a search restricted to one family
will miss things.

The single-`index.js`-holds-everything layout from older builds is gone; the bulk now lives in
`index.pre.js` plus the chunk set. `index.js` is no longer the ~800 B Sentry stub it was in
1.22209.3 — it has grown into a ~236 KB aggregator that pulls in roughly a hundred chunks and
re-exports them, though it still carries the Sentry-release preamble. To search minified JS, split
on separators first:

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
| `stall-sampler-worker/`    | Stall sampling (`stallSamplerWorker.js`)           |
| `transcript-search-worker/`| Transcript full-text search                        |

The older `sqlite-worker/` is gone; `file-index-worker/`, `heavy-work-worker/` and
`stall-sampler-worker/` are the recent additions, and PTY work moved into a dedicated `pty-host/`.


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
| `resources/github-mcp/`         | Bundled GitHub MCP server — a ~40 MB Go binary, the single largest file in the archive |
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
| `claude.internal.computerUse`| Computer Use                                     |
| `claude.internal.findInPage`| Find-in-page                                      |
| `claude.internal.localExecConsent`| Local-execution consent prompt              |
| `claude.skills`             | Agent skills                                      |
| `claude.hybrid`             | Hybrid local/remote agent surface                 |
| `claude.buddy`              | Hardware Buddy                                    |
| `claude.coworkArtifact`     | Cowork artifact preview                           |
| `claude.officeAddin`        | Office add-in bridge                              |
| `claude.simulator`          | iOS/Android simulator access                      |
