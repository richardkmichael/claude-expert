# Environment Variables

Variables read by the Claude Desktop main process. Generic Node.js, OS, networking, terminal, and
cloud-detection variables are omitted. Use the [re-verification recipes](./EXTRACTION.md) to
enumerate everything a given build honors — note that many variables are reached through a
lazy-getter accessor map (`NAME:()=>...`), which a plain `process.env.NAME` grep misses.

The two enumeration methods err in opposite directions, so cross-check before documenting anything:

- `process.env.NAME` under-collects, missing everything behind the accessor map.
- The accessor-map pattern over-collects. That map also carries ordinary module constants in
  SCREAMING_CASE, so it yields non-variables — `CU_SUPPORTED_PLATFORMS`, `DESKTOP_OAUTH_CONFIGS`,
  `COWORK_OAUTH_CONFIGS`, `DESKTOP_3P_BASE_PROMPT` and `DESKTOP_MANAGED_CONFIG_POLICY_PATH` are
  exported constants, not environment variables, despite looking exactly like them.

A third category is variables Desktop *writes* into a child process rather than reads. Those are
noted where relevant rather than listed as inputs.

One family dominates the raw enumeration but is not Desktop's own surface: `CLAUDE_CODE_*` (several
hundred) and the provider/model `ANTHROPIC_*` set. They belong to Claude Code, which Desktop runs as
a separate, runtime-downloaded process, and to the TypeScript Agent SDK
(`@anthropic-ai/claude-agent-sdk`) that drives it. The SDK is inlined into the main-process bundle,
together with the env-var accessor maps it shares with Claude Code; the Claude Code CLI itself is
not. They are documented by Claude Code, not here. See [Bundled Claude Code](#bundled-claude-code).

Some variables below are read only inside that inlined SDK code (the chunks that carry the
`@anthropic-ai/claude-agent-sdk` package-name literal and the `CLAUDE_CODE_*` accessor maps), not by
Desktop's own modules; their rows say so.


## Path and launch control

| Variable                           | Effect                                                                                                                                                                             |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CLAUDE_USER_DATA_DIR`             | Sets `userData` and `logs` (`$VAL/Logs`). Bypasses the `-3p` suffix mechanism entirely. See [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md).                                             |
| `CLAUDE_CDP_AUTH`                  | Required when launching with `--remote-debugging-port` / `--remote-debugging-pipe`. See [DEBUGGING](./DEBUGGING.md).                                                               |
| `CLAUDE_AI_URL`                    | Overrides the `https://claude.ai` frontend base URL. Honored unconditionally in `dev` builds; in prod only when the host ends in `.ant.dev` or is `localhost` and CDP auth passes. |
| `CLAUDE_DESKTOP_BACKGROUND_LAUNCH` | Launches without taking focus. `"1"` or `"behind"` starts behind other windows; `"hidden"` starts with no window shown ("stealth relaunch"). Honored only when CDP auth passes.    |
| `CLAUDE_FORCE_HOST_LOOP`           | `"1"` forces the agent loop to run on the host (only when the dev URL override is on).                                                                                             |
| `CLAUDE_EXTRA_HEADERS_TOKEN`       | Signed token used to inject extra HTTP headers — internal dev/QA.                                                                                                                  |
| `CLAUDE_UPDATER_TOKEN`             | Signed token consumed by the auto-updater path — internal dev/QA.                                                                                                                  |
| `CLAUDE_ENABLE_LOGGING`            | Forces logging on in packaged builds (otherwise dev-only).                                                                                                                         |
| `DESKTOP_LOG_LEVEL`                | Main-process log level. Default `"info"` packaged, `"debug"` dev.                                                                                                                  |
| `CLAUDE_DESKTOP_LOCAL_FRAME_SHELL` | `"1"` enables a local frame shell instead of the remote frontend — dev.                                                                                                            |
| `CLAUDE_SECURESTORAGE_CONFIG_DIR`  | Override directory for secure-storage config. Read only by the inlined Agent SDK code.                                                                                             |
| `CLAUDE_SIM_SANDBOX`               | Dev only. `"0"` disables the simulator sandbox in unpackaged builds (packaged is always sandboxed).                                                                                |
| `CLAUDE_SIM_TOUCH_SERIAL`          | Dev only. `"1"` forces serial (rather than ordered) simulator touch dispatch for iOS in unpackaged builds.                                                                         |


## Auth and OAuth

| Variable                            | Effect                                                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `OAUTH_ENVIRONMENT`                 | Honored only when the dev URL override is active — selects an OAuth environment.                       |
| `CLAUDE_LOCAL_OAUTH_API_BASE`       | Local OAuth API base URL. Default `http://localhost:8000`. Inlined Agent SDK code only.                |
| `CLAUDE_LOCAL_OAUTH_APPS_BASE`      | Local OAuth apps base URL. Default `http://localhost:4000`. Inlined Agent SDK code only.               |
| `CLAUDE_LOCAL_OAUTH_CONSOLE_BASE`   | Local OAuth console base URL. Default `http://localhost:3000`. Inlined Agent SDK code only.            |
| `CLAUDE_SESSION_INGRESS_TOKEN_FILE` | Path to a session-ingress-token file (internal well-known path if unset). Inlined Agent SDK code only. |
| `CLAUDE_CUSTOM3P_REFRESH_FLOOR_MS`  | Floor for custom third-party credential refresh interval. Default `60000`.                             |


## Cowork / VM

| Variable                  | Effect                                                                                                              |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `COWORK_PROFILE_TURNS`    | When set (any value), records a V8 CPU profile of each Cowork turn into a `traces` folder under the logs directory. |
| `COWORK_VM_DEBUG`         | Verbose VM debug output.                                                                                            |
| `COWORK_CU_ONLY`          | `"0"` disables computer-use-only mode; otherwise on (also gated by a feature flag).                                 |
| `CU_MEMORY_TRACE_MINUTES` | Computer Use memory-trace duration in minutes. Default `3`.                                                         |

The `secureVmFeaturesEnabled` toggle that gates the VM image download is a preference, not an env
var — see [FEATURES](./FEATURES.md).


## Telemetry and debugging

| Variable                  | Effect                                                                                                                                                                                                                                            |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DO_NOT_TRACK`            | Inlined Agent SDK code only: truthy selects its `no-telemetry` mode, as does `DISABLE_TELEMETRY`.                                                                                                                                                 |
| `DISABLE_TELEMETRY`       | On third-party (`3p`) deployments, forwarded from Desktop's environment into the Claude Code subprocess. Desktop also writes `DISABLE_TELEMETRY="1"` into that environment when the third-party `disableNonessentialTelemetry` config key is set. |
| `DISABLE_ERROR_REPORTING` | On `3p` deployments, forwarded into the Claude Code subprocess. Desktop writes `"1"` when `disableEssentialTelemetry` is set.                                                                                                                     |
| `DEBUG`                   | Standard `debug` package switch; also parsed by the main-process logger.                                                                                                                                                                          |
| `DEBUG_SDK`               | Inlined Agent SDK code only: turns on SDK debug logging from launch, like `DEBUG` or `--debug`.                                                                                                                                                   |
| `SENTRY_NAME`             | Sentry server-name override.                                                                                                                                                                                                                      |
| `CLAUDE_E2E_PKCE_LOG`     | `"1"` enables the E2E PKCE logging harness. Also requires CDP auth to pass.                                                                                                                                                                       |
| `CLAUDE_HARNESS_RESIZE`   | `"1"` selects test-harness window-resize behavior. Internal E2E use.                                                                                                                                                                              |


## Office add-in

The bundle ships an Office 365 MCP server (`resources/office365-mcp/`) and an add-in bridge.

| Variable                         | Effect                                                                                                                                                                   |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `OFFICE_ADDIN_DEV_ID`            | Dev add-in ID. Referenced, but the value is discarded: it has no effect in this build.                                                                                   |
| `OFFICE_ADDIN_DEV_MANIFEST_PATH` | Path to a development add-in manifest (fallback `~/code/office-agent/public/manifest-dev.xml`). Referenced, but the result is discarded: it has no effect in this build. |


## Bundled Claude Code

How Desktop gets and runs Claude Code is in
[ARCHITECTURE](./ARCHITECTURE.md#claude-code-subprocess).

The full `CLAUDE_CODE_*` family (several hundred variables) and the provider/model `ANTHROPIC_*` set
are honored by that subprocess and by the Agent SDK that drives it — including provider routing
(`CLAUDE_CODE_USE_BEDROCK`, `_USE_VERTEX`, `_USE_FOUNDRY`, `_USE_MANTLE`, `_USE_ANTHROPIC_AWS`,
`_USE_ANTHROPIC_GOOGLE_CLOUD`), mTLS (`CLAUDE_CODE_CLIENT_CERT` / `_KEY` / `_KEY_PASSPHRASE`,
`CLAUDE_CODE_CERT_STORE`), OAuth overrides, and `CLAUDE_CONFIG_DIR` (the Code analogue of
`CLAUDE_USER_DATA_DIR`).

A few are set by Desktop when it spawns the subprocess rather than read from the environment, e.g.
`CLAUDE_CODE_ENTRYPOINT` (`claude-desktop`, or `claude-desktop-3p` on third-party deployments, for
Code sessions; `local-agent` for Cowork sessions run on the host) and `CLAUDE_AGENT_SDK_VERSION`
(the inlined SDK stamps its own version, `0.3.309` here, matching the pinned Claude Code `2.1.309`).
The full Code-session environment, and the user-editable variables layered into it, are in
[ARCHITECTURE](./ARCHITECTURE.md#environment). Refer to Claude Code's own settings documentation for
that surface rather than treating it as Desktop configuration.

Others in the same write-only category: `CLAUDE_IMPORT_CONVERSATIONS="1"` (with a scratch
`CLAUDE_CONFIG_DIR`) when spawning the conversation importer, and
`CLAUDE_COWORK_MEMORY_PATH_OVERRIDE`, `CLAUDE_COWORK_MEMORY_GUIDELINES` (feature-flag gated),
`CLAUDE_COWORK_MEMORY_INDEX_CONTENT` and `CLAUDE_COWORK_MEMORY_EXTRA_GUIDELINES`, injected into the
guest environment pointing at `/sessions/<name>/mnt/…` — see [COWORK_VM](./COWORK_VM.md) for that
filesystem.
