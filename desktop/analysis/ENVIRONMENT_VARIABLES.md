# Environment Variables

Variables read by the Claude Desktop main process. Generic Node.js, OS, networking, terminal, and
cloud-detection variables are omitted. Use the [re-verification recipes](./EXTRACTION.md) to
enumerate everything a given build honors — note that many variables are reached through a
lazy-getter accessor map (`NAME:()=>...`), which a plain `process.env.NAME` grep misses.

The two enumeration methods err in opposite directions, so cross-check before documenting anything:

- `process.env.NAME` under-collects, missing everything behind the accessor map.
- The accessor-map pattern over-collects. That map also carries ordinary module constants in
  SCREAMING_CASE, so it yields non-variables — `DEFAULT_ARTIFACT_MCP_CALLS_PER_MINUTE:()=>30` is a
  literal, and `COWORK_MCP_SERVER`, `COWORK_CLI_EXPOSED_COMMANDS`, `COWORK_FORCE_ASK_TOOLS`,
  `COWORK_WIN32_LOG_DIR` and `COWORK_WIN32_DAEMON_LOG_SUBDIR` are exported constants, not
  environment variables, despite looking exactly like them.

A third category is variables Desktop *writes* into a child process rather than reads. Those are
noted where relevant rather than listed as inputs.

Two families dominate the raw enumeration but are not Desktop's own surface:

- `CLAUDE_CODE_*` (several hundred) and the provider/model `ANTHROPIC_*` set belong to the bundled
  Claude Code / Agent SDK subprocess, now inlined into this build. They are documented by Claude
  Code, not here. See [Bundled Claude Code](#bundled-claude-code).
- The `OPERON_*` family and the separate agent-skills "Operon" runtime are gone in this build (the
  `operon` sidebar mode is migrated away at read time). Treat any older `OPERON_*` reference as
  removed. Agent execution now runs through the Claude Code / Agent SDK path.


## Path and launch control

| Variable                                    | Effect                                                                                       |
|---------------------------------------------|----------------------------------------------------------------------------------------------|
| `CLAUDE_USER_DATA_DIR`                      | Sets `userData` and `logs` (`$VAL/Logs`). Bypasses the `-3p` suffix mechanism entirely. See [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md). |
| `CLAUDE_CDP_AUTH`                           | Required when launching with `--remote-debugging-port` / `--remote-debugging-pipe`. See [DEBUGGING](./DEBUGGING.md). |
| `CLAUDE_AI_URL`                             | Overrides the `https://claude.ai` frontend base URL. Honored unconditionally in `dev` builds; in prod only when the host ends in `.ant.dev` or is `localhost` and CDP auth passes. |
| `CLAUDE_DESKTOP_BACKGROUND_LAUNCH`          | Launches without taking focus. `"1"` or `"behind"` starts behind other windows; `"hidden"` starts with no window shown ("stealth relaunch"). |
| `CLAUDE_FORCE_HOST_LOOP`                    | `"1"` forces the agent loop to run on the host (only when the dev URL override is on).        |
| `CLAUDE_EXTRA_HEADERS_TOKEN`                | Signed token used to inject extra HTTP headers — internal dev/QA.                            |
| `CLAUDE_UPDATER_TOKEN`                      | Signed token consumed by the auto-updater path — internal dev/QA.                            |
| `CLAUDE_ENABLE_LOGGING`                     | Forces logging on in packaged builds (otherwise dev-only).                                   |
| `DESKTOP_LOG_LEVEL`                         | Main-process log level. Default `"info"` packaged, `"debug"` dev.                            |
| `CLAUDE_DESKTOP_LOCAL_FRAME_SHELL`          | `"1"` enables a local frame shell instead of the remote frontend — dev.                      |
| `CLAUDE_SECURESTORAGE_CONFIG_DIR`           | Override directory for secure-storage config.                                                |
| `CLAUDE_SIM_SANDBOX`                        | Dev only. `"0"` disables the simulator sandbox in unpackaged builds (packaged is always sandboxed). |


## Auth and OAuth

| Variable                            | Effect                                                                        |
|-------------------------------------|-------------------------------------------------------------------------------|
| `OAUTH_ENVIRONMENT`                 | Honored only when the dev URL override is active — selects an OAuth environment. |
| `CLAUDE_LOCAL_OAUTH_API_BASE`       | Local OAuth API base URL. Default `http://localhost:8000`.                    |
| `CLAUDE_LOCAL_OAUTH_APPS_BASE`      | Local OAuth apps base URL. Default `http://localhost:4000`.                   |
| `CLAUDE_LOCAL_OAUTH_CONSOLE_BASE`   | Local OAuth console base URL. Default `http://localhost:3000`.                |
| `CLAUDE_SESSION_INGRESS_TOKEN_FILE` | Path to a session-ingress-token file (internal default if unset).             |
| `CLAUDE_CUSTOM3P_REFRESH_FLOOR_MS`  | Floor for custom third-party credential refresh interval. Default `60000`.    |


## Cowork / VM

| Variable                  | Effect                                                                          |
|---------------------------|---------------------------------------------------------------------------------|
| `COWORK_PROFILE_TURNS`    | Number of turns to profile for Cowork session performance metrics.              |
| `COWORK_VM_DEBUG`         | Verbose VM debug output.                                                        |
| `COWORK_CU_ONLY`          | `"0"` disables computer-use-only mode; otherwise on (also gated by a feature flag). |
| `CU_MEMORY_TRACE_MINUTES` | Computer Use memory-trace duration in minutes. Default `3`.                     |

The `secureVmFeaturesEnabled` toggle that gates the VM image download is a preference, not an env
var — see [FEATURES](./FEATURES.md).


## Telemetry and debugging

| Variable                   | Effect                                                                    |
|----------------------------|---------------------------------------------------------------------------|
| `DO_NOT_TRACK`             | Standard opt-out — disables analytics if truthy.                          |
| `DISABLE_TELEMETRY`        | Disables product telemetry.                                              |
| `DISABLE_ERROR_REPORTING`  | Disables Sentry error reporting.                                         |
| `DEBUG`                    | Standard `debug` package switch.                                         |
| `DEBUG_SDK`                | Generic SDK debug logging.                                              |
| `DIAGNOSTICS`              | Enables in-app diagnostics surfaces.                                    |
| `TRACING_DUMP`             | Dumps transformed module bytecode to disk for tracing.                  |
| `TRACING_DUMP_DIR`         | Directory for `TRACING_DUMP` output. Defaults to the OS temp dir.       |
| `SENTRY_NAME`              | Sentry server-name override.                                            |
| `CLAUDE_E2E_PKCE_LOG`      | `"1"` enables the E2E PKCE logging harness. Also requires CDP auth to pass. |
| `CLAUDE_HARNESS_RESIZE`    | `"1"` selects test-harness window-resize behavior. Internal E2E use.    |
| `ELECTRON_ENABLE_LOGGING`  | Generic Electron switch — routes Chromium and main-process console to stdout. |

`CLAUDE_AVOID_READING_LOGING_ITEM_SETTINGS` (which carried a `LOGIN_ITEM` typo) is gone in this
build. The `getLoginItemSettings().wasOpenedAtLogin` probe it guarded is now unconditional.


## Office add-in

The bundle ships an Office 365 MCP server (`resources/office365-mcp/`) and an add-in bridge.

| Variable                          | Effect                                          |
|-----------------------------------|-------------------------------------------------|
| `OFFICE_ADDIN_DEV_ID`             | Dev add-in ID.                                  |
| `OFFICE_ADDIN_DEV_MANIFEST_PATH`  | Path to a development add-in manifest.          |


## Bundled Claude Code

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

The full `CLAUDE_CODE_*` family (several hundred variables) and the provider/model `ANTHROPIC_*` set
are honored by that subprocess and the Agent SDK it embeds — including provider routing
(`CLAUDE_CODE_USE_BEDROCK`, `_USE_VERTEX`, `_USE_FOUNDRY`, `_USE_MANTLE`, `_USE_ANTHROPIC_AWS`,
`_USE_ANTHROPIC_GOOGLE_CLOUD`), mTLS (`CLAUDE_CODE_CLIENT_CERT` / `_KEY` / `_KEY_PASSPHRASE`,
`CLAUDE_CODE_CERT_STORE`), OAuth overrides, and `CLAUDE_CONFIG_DIR` (the Code analogue of
`CLAUDE_USER_DATA_DIR`).

A few are set by Desktop when it spawns the subprocess rather than read from the environment, e.g.
`CLAUDE_CODE_ENTRYPOINT="local-agent"` and `CLAUDE_AGENT_SDK_VERSION`. Refer to Claude Code's own
settings documentation for that surface rather than treating it as Desktop configuration.

Others in the same write-only category: `CLAUDE_IMPORT_CONVERSATIONS="1"` (with a scratch
`CLAUDE_CONFIG_DIR`) when spawning the conversation importer, and
`CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` / `CLAUDE_COWORK_MEMORY_GUIDELINES`, injected into the guest
environment pointing at `/sessions/<name>/mnt/…` — see [COWORK_VM](./COWORK_VM.md) for that
filesystem.


## Version history

- 4.4212.0: Bundled Claude Code section re-checked. Desktop pins a Claude Code version in an
  embedded manifest and downloads it at runtime; it is not shipped inside the app bundle.
