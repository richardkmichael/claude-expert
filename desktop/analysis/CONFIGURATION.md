# Configuration

The on-disk config stores, the user-preferences schema, and how enterprise config layers over user
preferences. For how deployment mode and the enterprise sources are selected and resolved, see
[DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md).

User data root: `~/Library/Application Support/Claude/` (or `Claude-3p/` in third-party deployment
mode — see [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md)).


## The two on-disk stores

### `config.json` (Electron Store)

Low-level app state written by `electron-store` (store name `config`): dark mode, window state,
OAuth tokens, assorted feature toggles, and the Desktop Extension allowlist cache
(`dxt:allowlistEnabled`, `dxt:allowlistCache`, `dxt:allowlistLastUpdated`).

### `claude_desktop_config.json` (Desktop config)

User-facing configuration. Top-level fields in the schema:

- `mcpServers` — MCP server definitions (see [MCP](./MCP.md)).
- `preferences` — the feature/UI toggles below (a nested object).
- `deploymentMode` (`"1p"` / `"3p"`) and `awaitingSignIn` — see
  [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md).
- `managedConfig` — cached copy of the resolved enterprise config.
- `features`, hardware-acceleration toggles (`isHardwareAccelerationDisabled` and related),
  `isUsingBuiltInNodeForMcp`, `isCoworkSdkDebuggingEnabled`.
- Desktop Extensions: `isDxtAutoUpdatesEnabled`, `dxtMaxTotalSizeMB`.
- `coworkUserFilesPath` (and `coworkUserFilesPathUncRedirectedFrom`).


## User preferences schema

Feature toggles and UI settings, nested under `preferences` in `claude_desktop_config.json`. All
entries are optional; defaults apply at read time. The schema is a zod object in the main-process
bundle, with a parallel defaults object in a different chunk. 68 top-level keys in build 1.26832.0,
grouped by area (use the [re-verification recipe](./EXTRACTION.md) for the authoritative set of a
given build):

Entry points and shortcuts:

```
menuBarEnabled, legacyQuickEntryEnabled,
chromeExtensionEnabled, chromeExtension,
quickEntryShortcut, quickEntryDictationShortcut, dockBounceEnabled,
notificationLevels, notificationSound
```

`chromeExtension` is now a nested object holding `pairedDeviceId`, `pairedDeviceName` and
`pairedFromDeviceIds`, which were top-level keys in 1.22209.3.
`chromeExtensionInstallDialogDismissed` is gone. `notificationLevels` is
`{permission, idle, question}`, each `off | badge | banner`; `notificationSound` is
`system | none`.

Companion / appearance codenames (see [FEATURES](./FEATURES.md)):

```
hardwareBuddyEnabled,
plushRaccoonEnabled, plushRaccoonOption1, plushRaccoonOption2, plushRaccoonOption3,
quietPenguinEnabled, louderPenguinEnabled, floatingPenguinEnabled
```

Claude Code for Desktop / worktrees:

```
chillingSlothLocation, ccBranchPrefix, ccMaxWarmWorktrees, ccWorktreeReapAfterHours,
ccAutoArchiveOnPrClose, ccRemoteControlDefaultEnabled, ccdScheduledTasksEnabled
```

Cowork / VM and permissions:

```
secureVmFeaturesEnabled, vmMemoryGB, vmCpuCount,
coworkScheduledTasksEnabled, coworkDisabledTools, coworkSpaceContextEnabled,
coworkWebSearchEnabled, coworkHipaaRestricted, coworkModelAutoFallbackByAccount,
coworkOnboardingResumeStep,
bypassPermissionsModeEnabled, bypassPermissionsGateByAccount, bypassPermissionsOptInByAccount,
localAgentModeTrustedFolders, allowAllBrowserActions,
dispatchTrustedCodeWorkspaces, dispatchCodeTasksPermissionMode
```

Launch preview, wake scheduler, and device pairing:

```
launchEnabled, launchPreviewPersistedWorkspaces, launchPreviewAllowedOrigins,
launchPreviewAllowedDomainTransitions, launchPreviewSessionScopedSessions, launchPreviewStorage,
keepAwakeEnabled, wakeSchedulerEnabled, wakeSchedulerApprovedThisCycle,
wakeSchedulerRegisteredAtVersion, wakeSchedulerCourtesyFlippedKeepAwake, wakeSchedulerDisableEmitted,
remoteToolsDeviceName,
remoteFolderConsentMemory, remoteSessionFolderGrants, folderTccProbeResults
```

Computer Use, simulators, and surfaces:

```
chicagoEnabled, chicagoAutoUnhide, chicagoPreferredMode, chicagoUserDeniedBundleIds,
claudeAndroidEmulatorAccessEnabled, claudeIosSimulatorAccessEnabled, simulatorDeviceConsent,
sidebarMode, epitaxyPrefs, installSourceLanding, previewJitlessKillSwitchEngaged
```

`simulatorDeviceConsent` is a map of device id to `{label, grantedAt}`.

`sidebarMode` is one of `chat | code | task | epitaxy`. The former `operon` value is migrated away
at read time, and the older `sparkleHedgehog*` and `operon*` preference keys are gone.


## Config layering: who can set what

Two schemas govern behavior and they layer:

- Enterprise config — from the macOS managed plist, a local config-library file, and the remote
  org-policy backend; cached on disk as `managedConfig`. Written by admins (the managed plist and
  remote org policy require privileged access).
- User preferences — the `preferences` block in `claude_desktop_config.json`, edited by the user.

Enterprise config takes precedence: admin-disabled features cannot be re-enabled from user space
when set via the privileged sources. When a key appears in both (e.g. `secureVmFeaturesEnabled`),
the enterprise value wins. The full source list and precedence order are in
[DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md).

Each enterprise/managed key carries a metadata descriptor in the bundle:

```
flatKey, support: { enabled: { scopes: ["1p"|"3p"|"3p-bootstrap"], availableInVersion: "x.y.z" } },
title, description: { short: { text, docsOnly } }, default, category, group, label, order,
predicates, egressRequirements, egressRequirementsLabel, remotePolicy
```

`support.enabled.availableInVersion` replaces the older `appMin` field. `egressRequirements` (which
hosts must be reachable for a feature) is still present. `legacyAlias` is gone. A `sensitive` flag
no longer sits on managed-key metadata — it now appears only on the separate MCP/config field
descriptor (`{type, title, description, required, default, multiple, sensitive}`).
