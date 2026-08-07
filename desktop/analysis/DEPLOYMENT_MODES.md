# Deployment Modes and Enterprise Config

First-party vs third-party deployment, the `Claude-3p` data directory, where enterprise config comes
from, and how the managed-settings tiers resolve. Minified identifiers below are snapshot
illustrations for this build — anchor on the string literals and behavior.


## First-party (1p) vs third-party (3p)

- 1p (default): connects to Anthropic's hosted services (claude.ai). User data lives at
  `~/Library/Application Support/Claude/`.
- 3p (enterprise / customer-deployed): connects to a configured inference provider or bootstrap URL.
  User data lives at `~/Library/Application Support/Claude-3p/`.

The `-3p` suffix is applied by the userData path function in `index.pre.js`:

```js
// constants: pD = "-3p", Cm = "Claude-3p"
function On() {
  // if CLAUDE_USER_DATA_DIR is set, use userData as-is (no suffix)
  if (process.env.CLAUDE_USER_DATA_DIR) return app.getPath("userData");
  // on Windows, %LOCALAPPDATA%\Claude-3p
  if (process.platform === "win32" && process.env.LOCALAPPDATA)
    return join(process.env.LOCALAPPDATA, Cm);
  // otherwise append -3p to the default userData dir (idempotently)
  const g = app.getPath("userData");
  return g.endsWith(pD) ? g : `${g}${pD}`;
}
```


## How the mode is selected

Re-evaluated at every launch. The resolver returns 3p when an inference/bootstrap backend is
configured and the app is not pinned to 1p:

```js
function AsA(g) {   // a backend is configured
  return g.inference !== undefined ||
         (g.bootstrap?.url !== undefined && g.bootstrap.enabled !== false);
}
function It(g) {    // true => 3p
  return AsA(g) &&
    (g.authentication?.disableClaudeAiSignIn === true || persistedDeploymentMode() !== "1p");
}
```

| Backend configured (`AsA`)? | `disableClaudeAiSignIn`? | Persisted `deploymentMode` | Mode |
|-----------------------------|--------------------------|----------------------------|------|
| no                          | —                        | —                          | 1p   |
| yes                         | true                     | —                          | 3p   |
| yes                         | false / unset            | `"1p"`                     | 1p   |
| yes                         | false / unset            | `"3p"` or unset            | 3p   |

Mapping from older builds:

- The old "`inferenceProvider` set?" input is now an `inference` block or a `bootstrap.url`.
- The old `disableDeploymentModeChooser` admin override is now
  `authentication.disableClaudeAiSignIn`. The old name survives only as that key's legacy `flatKey`
  alias (scope `["3p"]`, `availableInVersion 1.3834.0`, remote-disabled).
- The persisted `deploymentMode` still lives in `claude_desktop_config.json` (top level, with
  `awaitingSignIn`).

When a backend is configured and sign-in is not disabled, a first-launch chooser writes
`deploymentMode` into the JSON; later launches read it back.


## CLAUDE_USER_DATA_DIR

If set, the app uses the path verbatim (`userData` = the value, `logs` = `<dir>/Logs`) and the
entire `-3p` suffix mechanism and legacy migration are skipped. Which mode it then runs in depends
on the contents of `$CLAUDE_USER_DATA_DIR/claude_desktop_config.json`. Without the env var,
`Claude/` and `Claude-3p/` are independent stores selected per launch.

Using this to run separate profiles (personal/work) also gives each profile its own Cowork VM
bundle, since `vm_bundles/` resolves off `userData`. The bundle cannot be shared between profiles:
both disk images are read-write, and the machine identity files are per-VM — so each profile costs
another several GB. See [COWORK_VM](./COWORK_VM.md).


## Enterprise config sources

Read and merged in priority order:

1. macOS managed plist, read key-by-key via `@ant/claude-native`:
   - `/Library/Managed Preferences/com.anthropic.claudefordesktop.plist`
   - `/Library/Managed Preferences/<username>/com.anthropic.claudefordesktop.plist`
2. Local config-library file under the user data dir (`configLibrary/<appliedId>.json`).
3. Remote org-policy backend (1p only) — overlays onto the above. See below.

The resolved managed config is cached on disk as `managedConfig` in `claude_desktop_config.json`,
and handed to the renderer as `window.desktopEnterpriseConfig` via a
`--desktop-enterprise-config=<JSON>` switch on each window. If the managed plist is present but
invalid, local settings are disabled entirely ("managedUnusable").

Two points that differ from older builds:

- There is no `enterpriseConfig` JSON block anymore; the on-disk field is `managedConfig`.
- The Windows registry path `SOFTWARE\Policies\Claude` appears only in the ADMX/MDM admin-template
  generator, not in any runtime reader. In this build the Desktop managed tier is read only from the
  macOS plist. (The `SOFTWARE\Policies\ClaudeCode` registry reads belong to the separate bundled
  Claude Code CLI settings system, not Desktop.)


## How org policy is retrieved (1p mode)

The remote managed-settings overlay is fetched by `loadRemoteManagedSettings`, using
`electron.net.fetch`:

- Endpoint: `${apiHost}/api/claude_code/settings` (the Desktop surface and the bundled Claude Code
  subprocess consume the same managed-settings shape, so the path is shared).
- Headers: `Authorization: Bearer <oauth-token>`, `anthropic-beta: oauth-2025-04-20`.
- Gating: skipped unless `getDeploymentMode().hasOrgPolicyBackend()` is true (1p only) and the
  GrowthBook flag `2216901299` is enabled. Also skipped with no active org (`no_org`), no OAuth
  token (`no_token`), or a `max` / `pro` subscription tier (`tier_skip`).
- Responses: `404` and `204` are treated as empty settings and success; other non-2xx is
  `http_error`. On success the body's `.settings` object is stored in memory. 10-second timeout.
- An org switch invalidates the cache so the next call re-fetches.


## Settings resolution tiers

The merged managed-settings resolver (shared with the bundled Claude Code) ranks tiers, highest
authority first: `Managed`, then `User`, then `Project` / `ProjectLocal`.

The Managed-tier settings file is located at (env override `CLAUDE_CODE_MANAGED_SETTINGS_PATH`):

| Platform | Path                                                                      |
|----------|---------------------------------------------------------------------------|
| macOS    | `/Library/Application Support/ClaudeCode/managed-settings.json`            |
| Windows  | `C:\Program Files\ClaudeCode\...` preferred, falling back to `C:\ProgramData\ClaudeCode\...` |
| Linux    | `/etc/claude-code/managed-settings.json`                                  |

Two safety checks guard `permissions.defaultMode`:

- The elevated modes `bypassPermissions`, `auto`, and `dontAsk` may not be set from the `Project` or
  `ProjectLocal` tiers — repo-committed settings cannot default to an elevated mode. Such settings
  are rejected with a warning.
- On Windows, an elevated `defaultMode` from a Managed file located under `C:\ProgramData\` is
  rejected because that directory is user-writable; elevation is honored only from the admin-only
  `C:\Program Files\ClaudeCode` location.
