# Architecture

How the macOS Claude Desktop app is laid out: product surfaces, processes, the `app.asar` file tree,
IPC, workers, and native modules. See [README](./README.md) for the build banner and the rest of the
doc set.


## Product surfaces

The visible UI is mostly the remote claude.ai frontend (see [Process model](#process-model)), so tab
and sidebar labels are largely not in this bundle. What the main process does encode:

- Surface modes. The persisted preference `sidebarMode` is one of `chat | code | task | epitaxy`
  (default `chat`); a stored `operon` value is deleted when config is read. On a cold launch it
  picks the first route: `code` and `epitaxy` open `/epitaxy`, `task` opens `/task/new`, anything
  else opens `/`. The launch telemetry names those routes `"/": "root"`, `"/new": "new_chat"`,
  `"/task/new": "cowork"`, `"/epitaxy": "code"`. A URL classifier maps `/cowork`, `/local_sessions`,
  `/task`, `/scheduled-task` and `/cowork-artifact` to `cowork`; `/`, `/new`, `/chat` and `/chats`
  to `chat`; and the Code routes to `code`. So internally Cowork is `task` and Code is `epitaxy`.
  Relocate with `rg -n 'storedSidebarMode' .vite/build`.
- Code. The Code surface is Claude Code run as a subprocess (see
  [Claude Code subprocess](#claude-code-subprocess)). It also opens in its own window titled "Code".
- Home. Bundle evidence for a unified Home that holds both Chat and Cowork: the 3p policy key
  `desktopHome` (title "Desktop home", values `standard | simple | no-vm | off`) grants surfaces per
  value (`standard`: chat, file analysis and Cowork; `simple`: no Cowork; `no-vm`: chat only; `off`:
  none). Its `surfaceGrantsReason` reads "The unified view replaces this setting." Feature-support
  keys `desktopHome` and `chatTab` exist alongside. The label "Home" and the Home tab layout are not
  in this bundle. User-reported: two main tabs, Home and Code; in Home you start a conversation and
  pick Chat or Cowork when sending.
- Cowork, local and cloud. Both paths are in this build. The local VM is fully present: VM bundle
  download into `vm_bundles/`, the `yukonSilver` support gate, and VM error and cleanup strings
  ("Delete Cowork VM Bundle and Restart…") — see [FEATURES](./FEATURES.md) and
  [COWORK_VM](./COWORK_VM.md). Cloud sessions are also present: UI strings such as "A cloud session
  is using “{folderName}” on this computer" and "Let Claude use the Browser on this computer from
  cloud sessions?", the entrypoints `remote_cowork` / `remote_cowork_trigger`, and a scheduled-task
  migration to remote triggers (telemetry `cowork_scheduled_tasks_auto_migrated`,
  `cowork_space_migration_outcome`; its config defaults to `enabled: false` and is turned on by
  server-side config). An org policy can refuse Cowork on the device ("Your organization doesn't
  allow Cowork tasks on this computer", unsupported code `disabled_by_org_policy`). Which path a
  given account uses is decided server-side, so this bundle cannot confirm the user report that
  Cowork has moved to the cloud.

Home sidebar items (user-reported list: Search, Projects, Artifacts, Scheduled tasks, Dispatch,
Design):

- Search: A `/search` path in the deep-link handler; no sidebar logic. Otherwise user-reported only.
- Projects: A `project` deep link opens `/project/<uuid>`, or `/projects` without an id;
  feature-support key `projects`.
- Artifacts: Support keys `coworkArtifacts`, `coworkArtifactPopout`, `artifactsPane`; a Cowork
  artifact window (`coworkArtifact.js`, route `/cowork-artifact`). No "Artifacts" sidebar label in
  the bundle.
- Scheduled tasks: Cowork route `/scheduled-task`; Code routines under the Code route's
  `/scheduled`.
- Dispatch: A persistent agent conversation with its own MCP tools (`start_task`, `start_code_task`,
  `send_message`, `list_sessions`, `read_transcript`, `list_projects`, `list_code_workspaces`,
  `set_agent_name`). It starts Cowork child tasks and Code sessions, and its greeting says it can be
  controlled "from your phone … go to the Dispatch tab". Default sidebar label "Dispatch".
- Design: A separate window titled "Design" (`designWindow.js`, support key `claudeDesignWindow`,
  IPC `claude.designPdf` for PDF export).

The newer projects feature the user reports (separate from Projects) cannot be identified from the
bundle with certainty. The only candidate is the "space": Dispatch's `list_projects` tool lists
spaces ("Use list_projects to see available spaces"), and there are a deep-link route `space`, a
`spaceId` on Cowork sessions, and support keys `coworkRemoteSessionSpaces` and `spaceMemoryBridge`.


## Process model

Standard Electron two-process design.

- Main process (Node.js): manages windows, IPC, config, spawns MCP servers, handles OS integration,
  and runs the Claude Code / Agent SDK subprocess (see
  [Claude Code subprocess](#claude-code-subprocess)). Entry point is `.vite/build/index.pre.js` (the
  `main` field in `package.json`).
- Renderer process (Chromium): the native window chrome is a set of local bundles under
  `.vite/renderer/` (`main_window`, `about_window`, `buddy_window`, `file_viewer`, `find_in_page`,
  `local_exec_consent`, `quick_window`), but the actual Claude app is the remote `https://claude.ai`
  frontend loaded into a `WebContentsView`. Context bridges expose native capabilities to it.

The frontend base URL is the bare `https://claude.ai`. `CLAUDE_AI_URL` overrides it only in `dev`
builds, or in prod when the developer dev-URL override has been approved — see
[ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md).

The exception is custom third-party (3p) mode, which serves a bundled copy of the web frontend from
a second archive, `Contents/Resources/ion-dist.asar` (~190 MB, ~4,600 files), at the origin
`app://localhost`. Relocate with `rg -n 'ion-dist' .vite/build`; see
[DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md).

The claude.ai frontend being remote is load-bearing for several features. Anything implemented in
the web frontend (for example the MCP Apps host — see [MCP_APPS](./MCP_APPS.md)) is not in this
bundle and version-drifts independently of the desktop shell.


## Main-process bundle

The main-process code is minified and code-split by Vite. Sizes are as shipped in `app.asar`; the
formatted copies under `desktop/work/<app-version>/app` are larger.

| File                        | Size    | Role                                                                           |
| --------------------------- | ------- | ------------------------------------------------------------------------------ |
| `index.pre.js`              | ~1.0 MB | Main entry (`package.json` `main`): early guards, then `require("./index.js")` |
| `index.js`                  | ~640 B  | Sentry-release preamble that `require`s the two eager chunks                   |
| `index.chunk-*.js`          | 496     | Code-split modules, ~21.8 MB in total; one ~6.8 MB chunk holds most of the app |
| `mainView.js`               | ~268 KB | `WebContentsView` context bridge                                               |
| `mainWindow.js`             | ~89 KB  | Title bar and window chrome                                                    |
| `aboutWindow.js`            | ~87 KB  | About dialog                                                                   |
| `quickWindow.js`            | ~87 KB  | Spotlight / quick-entry window                                                 |
| `findInPage.js`             | ~87 KB  | Find-in-page                                                                   |
| `artifactShell.js`          | ~5.5 KB | Artifact shell bridge (`claude.artifactShell`)                                 |
| `computerUseTeach.js`       | ~5.2 KB | Computer Use teach-mode UI                                                     |
| `buddy.js`                  | ~4.5 KB | Hardware Buddy companion window                                                |
| `computerUseWatchRecord.js` | ~3.7 KB | Computer Use recording UI                                                      |
| `watchRecordChooser.js`     | ~3.7 KB | Computer Use recording chooser                                                 |
| `coworkArtifact.js`         | ~2.7 KB | Cowork artifact preview window                                                 |
| `claudePagePreview.js`      | ~1.9 KB | Page-preview window                                                            |
| `designWindow.js`           | ~1.5 KB | Design window (`claude.designPdf`)                                             |
| `localExecConsent.js`       | ~1.4 KB | Local-execution consent prompt                                                 |

That is 512 `.js` files directly under `.vite/build/`: 496 `index.chunk-*` and 16 entry points.
There is one chunk family. Chunk names are content hashes and change every build.

`app.asar` also ships `compile-cache/`, V8 code-cache files (`<file>.arm64.jsc`) for `index.js` and
its two eager chunks.

Because the code is split, search the whole directory rather than one file. The prepared copy is
formatted one statement per line, so `rg` line output is usable directly:

```bash
rg -n 'searchTerm' desktop/work/<app-version>/app/.vite/build
rg -l 'searchTerm' desktop/work/<app-version>/app/.vite/build     # which chunk
```


## Workers

Under `.vite/build/`, each in its own subdirectory:

| Worker                      | Purpose                                                                            |
| --------------------------- | ---------------------------------------------------------------------------------- |
| `mcp-runtime/`              | MCP server hosting (`nodeHost.js`, `directMcpHost.js`) — see [MCP](./MCP.md)       |
| `pty-host/`                 | PTY host process for terminal sessions                                             |
| `file-index-worker/`        | File indexing                                                                      |
| `frame-local-worker/`       | "Claude Desktop Typed Artifact Service"; bundles Cloudflare `HTMLRewriter` as wasm |
| `heavy-work-worker/`        | Offloaded CPU-heavy work                                                           |
| `shell-path-worker/`        | Shell `PATH` extraction                                                            |
| `stall-sampler-worker/`     | Stall sampling (`stallSamplerWorker.js`)                                           |
| `transcript-search-worker/` | Transcript full-text search                                                        |


## Native modules and bundled resources

Native code (compiled Mach-O `.node`, arm64 in this install) lives under `node_modules/` and is
unpacked to `app.asar.unpacked/`:

| Path                                                | Purpose                                         |
| --------------------------------------------------- | ----------------------------------------------- |
| `@ant/claude-native/claude-native-binding.node`     | Native OS integrations                          |
| `@ant/claude-swift/build/Release/swift_addon.node`  | macOS Swift interop                             |
| `@ant/claude-swift/build/Release/computer_use.node` | Computer Use native support                     |
| `node-pty/build/Release/pty.node`                   | PTY for terminal sessions (with `spawn-helper`) |

The only other `node_modules` entries are the JavaScript packages `agent-base` and `ws`.

The top-level `resources/` directory ships auxiliary payloads:

| Path                               | Purpose                                                                                                                   |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `resources/office365-mcp/`         | Bundled Office 365 MCP server (`office365-mcp-stdio.mjs`, `msal-node-runtime.node`, `libmsalruntime_arm64.dylib`)         |
| `resources/github-mcp/`            | Bundled GitHub MCP server — a ~24 MB Go binary, the single largest file in the app payload                                |
| `resources/bundled-skills/`        | Agent skills shipped with the app (`docx`, `pptx`, `xlsx`, `pdf`, `pdf-reading`, `frontend-design`, plus `manifest.json`) |
| `resources/artifact-libs/`         | Chart.js, Grid.js and Mermaid builds for artifacts                                                                        |
| `resources/i18n/`                  | Desktop-shell UI string tables, one JSON per locale                                                                       |
| `resources/quick-actions/`         | A macOS Automator workflow (`document.wflow`)                                                                             |
| `resources/claude-browser-shim.js` | Shell/Node polyglot that routes `http(s)` URL opens through `CLAUDE_BROWSER_BRIDGE`                                       |

The MCP SDK is inlined into the main-process bundle by Vite; there is no separate `node_modules`
entry for `@modelcontextprotocol/sdk`.


## Claude Code subprocess

Claude Desktop runs Claude Code (the CLI) out of process for the Code sidebar. It does not ship the
CLI inside the app bundle. Each Desktop build pins one Claude Code version in an embedded manifest
and downloads that version at runtime into
`~/Library/Application Support/Claude/claude-code/<version>/<checksum-prefix>/claude.app`, a macOS
app wrapper around the `claude` binary, next to a `.verified` file holding the bundle's SHA-256.
Earlier downloaded versions stay beside it. The Cowork VM gets a separate Linux build of the same
version at `claude-code-vm/<version>/claude`, with the version recorded in
`claude-code-vm/.sdk-version`.

Relocate the pin with `rg -n 'manifestSignatureEnforcement' .vite/build`. It is a `JSON.parse('…')`
literal shaped
`{"version", "manifest": {"version", "manifestSignatureEnforcement", "commit", "buildDate", "platforms": {"darwin-arm64": {…, "bundle": {"checksum"}}, …}}}`.
The `prepare-claude-desktop-source` skill reads it into `manifest.json` as `claudeCode`. Build
4.4212.0 pins Claude Code 2.1.309, and the checksum prefix in its download path matches the
manifest's `darwin-arm64` bundle checksum.

The env vars that subprocess honors are in
[ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md#bundled-claude-code).


## IPC

Renderer-to-main IPC uses a custom channel-name format:

```
$eipc_message$_{uuid}_$_{namespace}_$_{component}_$_{method}
```

Two channel UUIDs are in use. Enumerate namespaces with
`rg -oN --no-filename '_\$_claude\.[a-zA-Z.]+_\$_' .vite/build | sort -u`. Observed namespaces:

| Namespace                          | Area                                                            |
| ---------------------------------- | --------------------------------------------------------------- |
| `claude.web`                       | Main web-app interface (auth, filesystem, sessions, extensions) |
| `claude.settings`                  | Desktop config (AppConfig, MCP, shortcuts, extensions)          |
| `claude.internal.ui`               | Native UI (title bar, about, quick window)                      |
| `claude.internal.computerUse`      | Computer Use                                                    |
| `claude.internal.sableOtter`       | Computer Use teach HUD (`SableOtterHud`)                        |
| `claude.internal.findInPage`       | Find-in-page                                                    |
| `claude.internal.localExecConsent` | Local-execution consent prompt                                  |
| `claude.skills`                    | Agent skills                                                    |
| `claude.hybrid`                    | Hybrid local/remote agent surface                               |
| `claude.buddy`                     | Hardware Buddy                                                  |
| `claude.coworkArtifact`            | Cowork artifact preview                                         |
| `claude.artifactShell`             | Artifact shell                                                  |
| `claude.designPdf`                 | Design window PDF export (`DesignPdf.printFrameToPdf`)          |
| `claude.engineSurface`             | Engine surface bridge in `mainView.js`                          |
| `claude.windowVibrancy`            | Window vibrancy in `mainView.js`                                |
| `claude.telemetry`                 | Telemetry bridge in `mainView.js`                               |
| `claude.officeAddin`               | Office add-in bridge                                            |
| `claude.simulator`                 | iOS/Android simulator access                                    |
