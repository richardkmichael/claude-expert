# Environment Variables

Variables read by the Claude Desktop main process. Generic Node.js, OS, networking, terminal, and
cloud-detection variables are omitted. Use the [re-verification recipes](./EXTRACTION.md) to
enumerate everything a given build honors — note that many variables are reached through a
lazy-getter accessor map (`NAME:()=>...`), which a plain `process.env.NAME` grep misses.

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
| `CLAUDE_AI_URL`                             | Enables the dev URL override if host ends in `.ant.dev` and CDP auth passes.                 |
| `CLAUDE_AVOID_READING_LOGING_ITEM_SETTINGS` | (sic — a `LOGIN_ITEM` typo in the source) Skips `getLoginItemSettings().wasOpenedAtLogin` detection on macOS. Exact-string lookup, so the misspelling must be used as-is. |
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
| `ELECTRON_ENABLE_LOGGING`  | Generic Electron switch — routes Chromium and main-process console to stdout. |


## Office add-in

The bundle ships an Office 365 MCP server (`resources/office365-mcp/`) and an add-in bridge.

| Variable                          | Effect                                          |
|-----------------------------------|-------------------------------------------------|
| `OFFICE_ADDIN_DEV_ID`             | Dev add-in ID.                                  |
| `OFFICE_ADDIN_DEV_MANIFEST_PATH`  | Path to a development add-in manifest.          |


## Bundled Claude Code

Claude Code (CLI) is bundled inside Claude Desktop and runs out-of-process for the Code sidebar.
The full `CLAUDE_CODE_*` family (several hundred variables) and the provider/model `ANTHROPIC_*`
set are honored by that subprocess and the Agent SDK it embeds — including provider routing
(`CLAUDE_CODE_USE_BEDROCK`, `_USE_VERTEX`, `_USE_FOUNDRY`, `_USE_MANTLE`, `_USE_ANTHROPIC_AWS`,
`_USE_ANTHROPIC_GOOGLE_CLOUD`), mTLS (`CLAUDE_CODE_CLIENT_CERT` / `_KEY` / `_KEY_PASSPHRASE`,
`CLAUDE_CODE_CERT_STORE`), OAuth overrides, and `CLAUDE_CONFIG_DIR` (the Code analogue of
`CLAUDE_USER_DATA_DIR`).

A few are set by Desktop when it spawns the subprocess rather than read from the environment, e.g.
`CLAUDE_CODE_ENTRYPOINT="local-agent"` and `CLAUDE_AGENT_SDK_VERSION`. Refer to Claude Code's own
settings documentation for that surface rather than treating it as Desktop configuration.
