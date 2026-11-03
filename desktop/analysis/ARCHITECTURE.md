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

### How a Code session launches it

A Code session is driven through the Agent SDK inlined in the main-process bundle. Desktop builds
the SDK options object and the SDK's process transport turns it into an argv. Desktop's log lines
carry a `[CCD]` prefix, and the options builder logs as `[LocalSessionManager]`.

#### Binary

The binary is always a downloaded Claude Code, resolved in this order (relocate with
`rg -n 'LOCAL OVERRIDE' .vite/build` and the `desktop_ccd_binary_resolved` telemetry event, whose
`resolution` field names the outcome):

1. `pinned_version`: a resumed session pinned to the version it started on, if still installed.
2. `local_override`: a binary set through `initLocalBinary`, logged as
   `[CCD] LOCAL OVERRIDE: Using local binary at …`. Nothing in the production build calls it.
3. `preseed_in_place`: a copy shipped inside the package. Only MSIX (Windows Store) installs have
   one. The MSIX check is a constant `false` on macOS.
4. `required_version`: the build's pinned version under `claude-code/<version>/`.
5. `fallback_version`: any other installed version, while the pinned one downloads.

A `claude` on `PATH` is never used, and no preference or setting points Code sessions at another
binary. Desktop logs the result as `Using Claude Code binary at: <path>`. The executable is
`claude.app/Contents/MacOS/claude` inside the user-owned install directory. Before a spawn, Desktop
checks only that it is executable and that the `.verified` marker holds the manifest checksum. It
does not re-hash the file. If macOS kills the process at exec, Desktop removes that version's
`.verified` marker and downloads it again. Relocate with `rg -n "verified marker" .vite/build`.

A second launcher hook, the "host CLI launcher" (`Starting it through the host CLI launcher at:`),
is wired into the spawn path, but the module that would set its path is an empty stub in production
builds, so it never activates.

#### Managed launcher

An organization can put a launcher program in front of the binary. Two conditions must both hold:

- The Desktop enterprise config key `claudeCodeProcessWrapperEnabled` is `true` (1p since 2.16120.0,
  3p since 2.7032.0, visibility `public-undocumented`). See
  [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md#enterprise-config-sources) for where enterprise config
  comes from.
- The Managed tier of Claude Code settings (`managed-settings.json`, see
  [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md#settings-resolution-tiers)) sets `processWrapper`, or
  `env.CLAUDE_CODE_PROCESS_WRAPPER`, which wins when both are set. User, project, and local settings
  are not consulted.

The value is an argv: either a JSON array of strings or a whitespace-split string with double-quote
quoting. An unquoted shell metacharacter (semicolon, pipe, ampersand, dollar sign, parenthesis,
backtick, or angle bracket) is rejected, because the value is an argv, not a shell command. The
first element must be an absolute path to an executable regular file, must not be Claude Code's own
path, and must not end in `.js`, `.mjs`, `.ts`, `.tsx` or `.jsx`. Desktop then spawns the launcher
with its own arguments, then the Claude Code path, then the SDK arguments, and logs
`[CCD] Claude Code launches go through the organization's launcher …`. A refused value fails the
start with `the launcher program your organization configured cannot be used on this computer` and
logs `[CCD] Managed launcher (processWrapper / …) refused: …`. On a launcher spawn, Desktop removes
the in-process OAuth token callbacks from the SDK options.

On macOS the enterprise config key can come from the user-writable local config library, so that
half needs no administrator. `processWrapper` cannot. Desktop reads it from the `Managed` tier of
the bundled SDK's settings resolver, whose sources are the server-managed settings (not fetched for
Max and Pro accounts), the Claude Code managed plist, and
`/Library/Application Support/ClaudeCode/managed-settings.json` at a fixed path. All of those are
root-owned or organization-delivered.

The launcher sees the full argv, so it can add CLI flags, which no other route allows. Relocate with
`rg -n 'claudeCodeProcessWrapperEnabled' .vite/build` and `rg -n 'Managed launcher' .vite/build`.

#### Arguments

There is no setting or preference for extra CLI arguments. The SDK transport always passes
`--output-format stream-json --verbose --input-format stream-json`. From the options Desktop sets it
adds, as applicable: `--thinking=adaptive`, `--effort`, `--model`, `--permission-prompt-tool=stdio`
(Desktop answers permission prompts through `canUseTool`), `--resume`, `--allowedTools`,
`--disallowedTools`, `--setting-sources user,project,local`, `--permission-mode`,
`--allow-dangerously-skip-permissions`, `--include-partial-messages`, `--add-dir`, `--plugin-dir`,
`--session-id`, and `--managed-settings <json>` (Desktop's resolved managed settings). Desktop's own
`extraArgs` add `--replay-user-messages` and usually `--thinking-display summarized`.

Desktop never sets the SDK `channels` option, so `--channels` is never passed, and neither is
`--dangerously-load-development-channels`. Desktop does not call the SDK's `enableChannel()` (the
`channel_enable` control request) either. Relocate the argv builder with
`rg -n 'Spawning Claude Code' .vite/build` and the options builder with
`rg -n 'settingSources: \["user", "project", "local"\]' .vite/build`.

#### Environment

The Code-session environment starts from Desktop's own `process.env`, then layers in order:

- the user's Code environment variables (below);
- `PATH` from the login shell;
- host-authored keys: `CLAUDE_CODE_ENTRYPOINT` (`claude-desktop`, or `claude-desktop-3p`),
  `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_DESKTOP_APP_VERSION`,
  `CLAUDE_CODE_SUBSCRIPTION_TYPE`, `CLAUDE_CODE_RATE_LIMIT_TIER`, and blanked `ANTHROPIC_API_KEY`,
  `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_CUSTOM_HEADERS`;
- `DISABLE_MICROCOMPACT=1`, `NODE_USE_SYSTEM_CA=1`, `CLAUDE_CODE_TERMINAL_MCP_TOOLS`,
  `MCP_SERVER_CONNECTION_BATCH_SIZE` (unless already set), `CLAUDE_CODE_EAGER_FLUSH=1`,
  `CLAUDE_CODE_EMIT_STARTUP_TIMING=1`, and `CLAUDE_CODE_HOST_SESSION_ID`.

The user's Code environment variables are edited in the app and reach the main process over the
`LocalSessionEnvironment` IPC namespace (`get`, `save`, `getScoped`, `saveScoped`, `removeScoped`).
They are stored `safeStorage`-encrypted in `ccd-environment-config.json` under the app data
directory: `envVars` holds the global set and `scopedEnvVars` holds per-account, per-scope sets. The
editor rejects `PATH`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_CUSTOM_HEADERS`, `ANTHROPIC_BASE_URL`, `DISABLE_AUTOUPDATER` and
a few `CLAUDE_CODE_*` display switches, and the stored set always drops
`CLAUDE_CODE_PROCESS_WRAPPER`, `CLAUDE_CODE_SIMPLE` and `CLAUDE_AGENT_SDK_MCP_NO_PREFIX`. Relocate
with `rg -n 'ccd-environment-config' .vite/build`.

Because the CLI runs with `--setting-sources user,project,local`, the `env` key of
`~/.claude/settings.json` and of project settings also applies inside the session.

#### Channel messages

A channel can register only through `--channels plugin:<name>@<marketplace>` or `enableChannel()`
when Claude Code runs headless (see `../code/analysis/MCP.md`, "Headless sessions"), and Desktop
supplies neither. A managed launcher can append `--channels`. Desktop's message handler recognizes a
CLI-started turn whose user message has `origin.kind` `channel`: it marks the session as steered
from outside the app and reports the turn origin in `desktop_ccd_cli_started_turn_result`. Relocate
with `rg -n '"slack-ping"' .vite/build`. How the remote claude.ai frontend displays such a message
is not in this bundle.


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
