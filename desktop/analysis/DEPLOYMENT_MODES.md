# Deployment Modes and Enterprise Config

First-party vs third-party deployment, the `Claude-3p` data directory, where enterprise config comes
from, and how the managed-settings tiers resolve. Anchor on the string literals and behavior below;
the bundle's minified names change every build.


## First-party (1p) vs third-party (3p)

- 1p (default): connects to Anthropic's hosted services (claude.ai). User data lives at
  `~/Library/Application Support/Claude/`.
- 3p (enterprise / customer-deployed): connects to a configured inference provider, bootstrap URL or
  self-hosted backend. User data lives at `~/Library/Application Support/Claude-3p/`.

The `-3p` suffix is applied by the 3p userData path function, in both `index.pre.js` and the main
chunk (relocate with `` rg -n -- '= "-3p"|`-3p`' "$EX/.vite/build/" ``, next to the
`claude_desktop_config.json` constant). Its logic:

1. If `CLAUDE_USER_DATA_DIR` is set, return `userData` as-is (no suffix).
2. On Windows with `LOCALAPPDATA` set, return `%LOCALAPPDATA%\Claude-3p`.
3. Otherwise append `-3p` to the default `userData` dir (idempotently: a path already ending in
   `-3p` is returned unchanged).


## How the mode is selected

Re-evaluated at every launch. The resolver returns 3p when a third-party backend is configured and
the app is not pinned to 1p.

A backend counts as configured when any of these holds:

- An `inference` block is set (the `inferenceProvider` key's `activatesThirdPartyMode`).
- `bootstrap.url` is set and `bootstrap.enabled !== false` (the `bootstrapUrl` key's
  `activatesThirdPartyMode`).
- A `selfHosted` block is set.
- A managed key that would activate 3p mode is present but unreadable.

When the result is 3p the resolver also reports why (the Reason column):

| Backend? | `disableClaudeAiSignIn` | Persisted mode  | Mode | Reason                          |
| -------- | ----------------------- | --------------- | ---- | ------------------------------- |
| no       | —                       | —               | 1p   | —                               |
| yes      | true                    | —               | 3p   | `chooser-disabled`              |
| yes      | false / unset           | `"1p"`          | 1p   | —                               |
| yes      | false / unset           | `"3p"` or unset | 3p   | `hybrid-pointer` or `persisted` |

`hybrid-pointer` is reported when `bootstrap.url` points at an Anthropic host (`config.claude.com`,
`api.anthropic.com`, `api.claude.ai`, or their staging counterparts); otherwise `persisted`.
Relocate with `rg -n '"chooser-disabled"' "$EX/.vite/build/"`.

The admin override is `authentication.disableClaudeAiSignIn`, whose flat (plist) key is
`disableDeploymentModeChooser` (scope `["3p"]`, `availableInVersion 1.3834.0`,
`remotePolicy: { hybrid: { scope: "excluded" }, applyUnverified: true }`).

The persisted `deploymentMode` is a top-level field of the 3p store's `claude_desktop_config.json`
(`Claude-3p/`, or `$CLAUDE_USER_DATA_DIR` when that is set). When a backend is configured and
sign-in is not disabled, a first-launch chooser writes `deploymentMode` into that file (logged as
`[custom-3p] deploymentMode written`); later launches read it back.


## CLAUDE_USER_DATA_DIR

If set, the app uses the path verbatim (`userData` = the value, `logs` = `<dir>/Logs`) and the
entire `-3p` suffix mechanism and legacy migration are skipped. Which mode it then runs in depends
on the contents of `$CLAUDE_USER_DATA_DIR/claude_desktop_config.json`. Without the env var,
`Claude/` and `Claude-3p/` are independent stores selected per launch.

Using this to run separate profiles (personal/work) also gives each profile its own Cowork VM
bundle, since `vm_bundles/` resolves off `userData`. The bundle cannot be shared between profiles:
both disk images are read-write, and the machine identity files are per-VM — so each profile costs
another several GB. See [COWORK_VM](./COWORK_VM.md).

### Setting it per-bundle via LSEnvironment

The variable has to be in the environment at launch, which a Finder or Dock click does not provide.
Two ways around that: a wrapper that exports it and calls `open -n -a Claude`, or baking it into a
copy of the bundle via `LSEnvironment`.

`LSEnvironment` is a documented `Info.plist` dict that LaunchServices injects on every launch it
mediates. Claude Desktop already ships one:

```
LSEnvironment = { MallocNanoZone = 0 }
```

That single entry is Chromium's and must be preserved — a clone recipe that removes the dict and
re-inserts a fresh one drops it. Merge into the existing dict instead of replacing it.

Properties worth knowing, from a peer session's testing on a 1.25927.0 clone (not re-verified here
beyond the shipped plist above):

- Per-bundle, not per-process; applied by LaunchServices only, so it does not apply when the binary
  is exec'd directly.
- Values are literal — no `~` or `$VAR` expansion — so paths must be absolute and fixed at build
  time, making the resulting bundle machine-specific.
- It overrides the inherited environment rather than defaulting beneath it.
- `lsregister -f <bundle>` is required after editing; LaunchServices caches `Info.plist`.
- A `DYLD_*` key makes the launch fail outright under hardened runtime.

Cloning the bundle to carry this has costs beyond the scope of these notes — a new
`CFBundleIdentifier` resets TCC state, the auto-updater stops working, and the team-scoped
`keychain-access-groups` cannot be re-claimed ad-hoc, which disables passkey, hardware-key and Entra
sign-in. See [COWORK_VM](./COWORK_VM.md#entitlements) for the signing constraints.


## Enterprise config sources

Two device-side sources, used one at a time, with a served overlay on top:

1. macOS managed plist. The native module's `readPlistValue(<path>, <key>)` reads each known key
   from these files by path, not through CFPreferences:

   - `/Library/Managed Preferences/com.anthropic.claudefordesktop.plist` (machine scope)
   - `/Library/Managed Preferences/<username>/com.anthropic.claudefordesktop.plist` (user scope)

   Both are root-owned locations. The user preferences domain
   (`defaults write com.anthropic.claudefordesktop …`, stored in `~/Library/Preferences`) is never
   read as enterprise config. `CLAUDE_E2E_MANAGED_PLIST` replaces the plist path, but only when the
   e2e test hooks are on, which takes an Anthropic-signed `CLAUDE_CDP_AUTH` token (see
   [DEBUGGING](./DEBUGGING.md)). Relocate with `rg -n 'CLAUDE_E2E_MANAGED_PLIST' .vite/build`.
2. Local config-library file, read only when no managed plist is present:
   `configLibrary/<appliedId>.json` under the 3p data dir
   (`~/Library/Application Support/Claude-3p/`, user-owned), where `configLibrary/_meta.json` holds
   `appliedId` (a UUID) or a `hybridPointer` bootstrap URL, which supplies the config instead. It is
   read in 1p mode too: only keys that configure a third-party backend switch the app to 3p, and the
   resolver keeps every key whose `support.enabled` scopes include the current mode. A key valid in
   1p, such as `claudeCodeProcessWrapperEnabled`, therefore takes effect from this user-writable
   file. The "Configure Third-Party Inference…" window edits it. Its menu item is shown when
   `developer_settings.json` sets `allowDevTools` (see [DEBUGGING](./DEBUGGING.md)). Relocate with
   `rg -n 'Failed to read config library' .vite/build`.
3. Served overlay: the config a bootstrap server returns, applied by the custom-3p bootstrap code
   (logged with a `[custom-3p]` prefix). Keys with `remotePolicy.hotApplied` apply without a
   relaunch. A claude.ai sign-in without a bootstrap server has no served overlay.

The resolved source is reported as `managed`, `local` or `none`. It is rebuilt at each launch and
not persisted. A renderer-facing subset (org-login restrictions, telemetry switches, banner and
similar, plus `deploymentMode` and `appVersion`) is passed to each window on a
`--desktop-managed-config=<JSON>` switch and exposed as `window.desktopManagedConfig` (also as
`desktopEnterpriseConfig` and `desktopTelemetryConfig`). If the managed plist is present but
invalid, local settings are disabled entirely ("managedUnusable"; logged as
`[managedConfig] Managed configuration is invalid; local settings are disabled until it is fixed.`).

The Desktop managed tier is read only from the macOS plist. The Windows registry path
`HKLM\SOFTWARE\Policies\Claude` appears in the ADMX/MDM admin-template generator and in diagnostic
text about the Windows VM service, which reads `coworkEDRIntegration` and
`coworkEDRIntegrationVendor` from it itself; the app has no runtime reader for it. (The
`SOFTWARE\Policies\ClaudeCode` registry reads belong to the bundled Claude Agent SDK's settings
code, not Desktop.)


## How org policy is retrieved (1p mode)

The remote managed-settings overlay is fetched by `loadRemoteManagedSettings`, using
`electron.net.fetch`:

- Endpoint: `${apiHost}/api/claude_code/settings` (the Desktop surface and the bundled Claude Code
  subprocess consume the same managed-settings shape, so the path is shared).
- Headers: `Authorization: Bearer <oauth-token>`, `anthropic-beta: oauth-2025-04-20`.
- Gating: skipped unless `getDeploymentMode().hasOrgPolicyBackend()` is true (1p only). Also skipped
  with no active org (`no_org`), no OAuth token (`no_token`), or a `max` / `pro` subscription tier
  (`tier_skip`; `refetchRemoteManagedSettingsBypassingTierSkip` overrides it).
- Responses: `404` and `204` are treated as empty settings and success; other non-2xx is
  `http_error` (a `401` also invalidates the OAuth token once). On success the body's `.settings`
  object is stored in memory. 10-second timeout; failures retry with backoff from 15 seconds, capped
  at 60 seconds. Each attempt except `no_org` logs `desktop_ccd_remote_managed_settings_fetch` with
  its outcome.
- A second path, `askRemoteManagedSettings`, revalidates with `If-None-Match` on the body's
  `checksum` and accepts `304`.
- An org switch invalidates the cache so the next call re-fetches.


## Settings resolution tiers

The settings resolver for Claude Code for Desktop sessions stacks tiers in the order `User`,
`Project`, `ProjectLocal`, `Managed`; a later tier overrides an earlier one, so `Managed` wins and
`ProjectLocal` beats `Project` beats `User`. The `Managed` tier comes from the bundled Claude Agent
SDK's `resolveSettings`, fed with the remote managed settings above. Relocate with
`rg -n '\[SettingsResolver\]' "$EX/.vite/build/"`.

The Managed-tier settings file is `managed-settings.json` in the directory below. The bundled SDK's
resolver uses this path unconditionally. Desktop's own reader of `managed-settings.json`, used for
example for `enabledPlugins`, honors `CLAUDE_CODE_MANAGED_SETTINGS_PATH` in place of the directory,
but the `Managed` tier does not:

| Platform | Directory                                                                         |
| -------- | --------------------------------------------------------------------------------- |
| macOS    | `/Library/Application Support/ClaudeCode`                                         |
| Windows  | `C:\Program Files\ClaudeCode` if it exists, otherwise `C:\ProgramData\ClaudeCode` |
| Linux    | `/etc/claude-code`                                                                |

Two safety checks guard `permissions.defaultMode`:

- The elevated modes `bypassPermissions`, `auto`, and `dontAsk` may not be set from the `Project` or
  `ProjectLocal` tiers — repo-committed settings cannot default to an elevated mode. Such settings
  are rejected with a warning.
- On Windows, an elevated `defaultMode` from a Managed file located under `C:\ProgramData\` is
  rejected because that directory is user-writable; elevation is honored only from the admin-only
  `C:\Program Files\ClaudeCode` location.

`remoteControlAtStartup` is guarded the same way: ignored from `Project` / `ProjectLocal` ("only
user or managed settings can auto-enable Remote Control") and from a Managed file under
`C:\ProgramData\`.


## Managed settings passed to Claude Code

For each Code session, Desktop derives a Claude Code managed-settings object from its own enterprise
config and sets it as the SDK `managedSettings` option. The SDK serializes it with `JSON.stringify`
and adds `--managed-settings <json>`, so the value is always inline JSON, never a path. When the
object is empty the option is unset and the flag is absent, which is the usual case for a personal
1p account with no enterprise config. Claude Code treats the value as the SDK parent tier, under its
own admin sources; see [MANAGED_SETTINGS_PARENT](../../code/analysis/MANAGED_SETTINGS_PARENT.md).

The builder reads two inputs:

- The resolved Desktop enterprise config described in
  [Enterprise config sources](#enterprise-config-sources): the managed plist, else the local config
  library, plus the remote tier. The resolver deletes every key whose `support.enabled` scopes do
  not include the current mode, so a 3p-only key never reaches the builder in 1p mode.
- The organization's allowed folders, delivered by a GrowthBook feature override and cached as the
  `orgFolders` app preference. They replace `allowedWorkspaceFolders` while they are fresh, in 1p
  mode only, and only when the device does not set `allowedWorkspaceFolders` itself.

It does not read Claude Code's `managed-settings.json`, the `/api/claude_code/settings` overlay, or
user settings. The key set is a fixed mapping, so no enterprise key passes an arbitrary Claude Code
setting through.

| Claude Code key                                                                        | Mode | Desktop source                                                                    |
| -------------------------------------------------------------------------------------- | ---- | --------------------------------------------------------------------------------- |
| `permissions.deny`                                                                     | both | `disabledBuiltinTools`; deny rules for read-only `allowedWorkspaceFolders` roots  |
| `permissions.ask`                                                                      | both | `builtinToolPolicy` entries other than `allow`                                    |
| `permissions.ask` / `deny` (`mcp__…` rules)                                            | both | `managedMcpServers` tool policy for directly connected servers; 3p plugin servers |
| `permissions.allow` (`WebFetch(domain:…)`)                                             | 3p   | `coworkEgressAllowedHosts` without `*`                                            |
| `permissions.disableBypassPermissionsMode`                                             | 3p   | `disableBypassPermissionsMode`                                                    |
| `permissions.blockReadsOutsideWorkingDirectories`, `permissions.additionalDirectories` | both | `blockReadsOutsideWorkingDirectories`, on Claude Code 2.1.257 or later            |
| `sandbox.filesystem.allowRead`, `allowManagedReadPathsOnly`                            | both | `allowedWorkspaceFolders`, or the organization's allowed folders                  |
| `sandbox.network.allowedDomains`, `allowManagedDomainsOnly`                            | 3p   | `coworkEgressAllowedHosts` without `*`                                            |
| `sandbox.enabled`, `allowUnsandboxedCommands: false`, `failIfUnavailable`              | both | set with either sandbox block above                                               |
| `forceLoginOrgUUID`                                                                    | 1p   | `forceLoginOrgUUID`                                                               |
| `availableModels`, `enforceAvailableModels: false`, `modelPricing`, `modelPicker`      | 3p   | the models list, when Desktop manages provider routing                            |
| `env.ENABLE_TOOL_SEARCH: "force"`                                                      | 3p   | `toolSearchEnabled` on a gateway provider that supports host tool search          |
| `disableAutoMode: "disable"`                                                           | 3p   | `autoModeEnabled` off for the Code surface                                        |
| `strictPluginOnlyCustomization`, `allowedMcpServers`, `allowManagedMcpServersOnly`     | 3p   | `allowedPluginMcpServers`, `managedMcpServers`, `isLocalDevMcpEnabled: false`     |
| `deniedMcpServers`                                                                     | 3p   | `deniedPluginMcpServers`                                                          |
| `disableClaudeAiConnectors: true`                                                      | 3p   | always                                                                            |
| `strictKnownMarketplaces`                                                              | 3p   | `userPluginMarketplacesEnabled: false`                                            |

After the builder, the spawn path adds `Edit`/`Write`/`MultiEdit`/`NotebookEdit` deny rules,
`additionalDirectories` and `sandbox.filesystem.denyWrite` for plugin directories outside the
session's folders when `blockReadsOutsideWorkingDirectories` is set. It drops
`blockReadsOutsideWorkingDirectories` and `strictKnownMarketplaces` for a Claude Code it cannot show
to be new enough (logged as `[sandbox] blockReadsOutsideWorkingDirectories left off for this spawn`
and `[plugins] marketplace allowlist left off for this spawn`).

A non-root user can change this value only through the enterprise config. With no managed plist, the
local config library under `~/Library/Application Support/Claude-3p/configLibrary/` is a
user-writable source, and its 1p-scoped keys (`disabledBuiltinTools`, `builtinToolPolicy`,
`allowedWorkspaceFolders`, `blockReadsOutsideWorkingDirectories`, `forceLoginOrgUUID`,
`managedMcpServers`) reach the object in 1p mode. Every key the mapping produces in 1p mode narrows
what the session may do. Files under `~/Library/Application Support/Claude/` contribute only the
cached `orgFolders` preference.

Relocate the builder with `rg -n 'organizationsMarksInSight' "$EX/.vite/build/"` (the call site in
the Code session start, next to `managedSettings:`), the key mapping with
`rg -n 'egressAllowedDomains' "$EX/.vite/build/"`, and the SDK argv with
`rg -n '"--managed-settings"' "$EX/.vite/build/"`.
