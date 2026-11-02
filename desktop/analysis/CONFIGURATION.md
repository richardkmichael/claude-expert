# Configuration

The on-disk config stores, the user-preferences schema, and how enterprise config layers over user
preferences. For how deployment mode and the enterprise sources are selected and resolved, see
[DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md).

User data root: `~/Library/Application Support/Claude/` (or `Claude-3p/` in third-party deployment
mode — see [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md)).


## The two on-disk stores

### `config.json` (Electron Store)

Low-level app state written by `electron-store` (store name `config`): dark mode, window and
quick-window state, OAuth token caches (`oauth:tokenCache`, `oauth:tokenCacheV2`), updater
bookkeeping, assorted feature toggles, and the Desktop Extension allowlist cache. The allowlist keys
are kept per organization: `dxt:allowlistEnabled:<org-uuid>`, `dxt:allowlistCache:<org-uuid>` (a
`safeStorage`-encrypted blob) and `dxt:allowlistLastUpdated:<org-uuid>`, alongside unsuffixed
`dxt:allowlistEnabled`, `dxt:allowlistCache` and `dxt:allowlistLastUpdated`.

### `claude_desktop_config.json` (Desktop config)

User-facing configuration. Top-level fields in the schema (relocate with
`rg -n 'isCoworkVmDebugLoggingEnabled: ' "$EX/.vite/build/"`, the object that ends in
`preferences:`):

- `mcpServers` — MCP server definitions (see [MCP](./MCP.md)).
- `preferences` — the feature/UI toggles below (a nested object).
- `deploymentMode` (`"1p"` / `"3p"`) — see [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md). The copy that
  decides the mode is the one in the third-party store's file
  (`Claude-3p/claude_desktop_config.json`).
- `claudeAiUrl`, `globalShortcut`, `features`, `chromiumFlags`.
- Hardware acceleration: `isHardwareAccelerationDisabled`, `isHardwareAccelerationAutoDisabled`,
  `isHardwareAccelerationAutoDisableNoticePending`.
- Debugging and runtime: `isCoworkSdkDebuggingEnabled`, `isCoworkVmDebugLoggingEnabled`,
  `isUsingBuiltInNodeForMcp`.
- Desktop Extensions: `isDxtAutoUpdatesEnabled`, `dxtMaxTotalSizeMB`.
- Cowork: `coworkUserFilesPath` (and `coworkUserFilesPathUncRedirectedFrom`),
  `coworkManagedDirsDeferredSince`, `coworkManagedDirsDeferrals`.
- Third-party bootstrap cache: `lastServedBootstrapPartial` / `lastServedBootstrapHost`,
  `lastProbedBootstrapPartial` / `lastProbedBootstrapHost`, `lastRemoteBootstrapPartial` /
  `lastRemoteBootstrapHost`, `lastRemoteDisableEssentialTelemetry` /
  `lastRemoteDisableEssentialTelemetryHost`, `hybridIdentity`, `sessionHostLicense`.

The resolved enterprise config is not persisted in this file; it is rebuilt at each launch from its
sources.


## User preferences schema

Feature toggles and UI settings, nested under `preferences` in `claude_desktop_config.json`. All
entries are optional; defaults apply at read time. The schema is a zod object in the main-process
bundle, with a parallel defaults object (same key set) in the same chunk. 131 top-level keys in
build 4.4212.0, grouped by area (use the [re-verification recipe](./EXTRACTION.md) for the
authoritative set of a given build):

Entry points, shortcuts, and notifications:

```
menuBarEnabled, legacyQuickEntryEnabled,
chromeExtensionEnabled, chromeExtension,
quickEntryShortcut, quickEntryDictationShortcut, dictationShortcut, dockBounceEnabled,
notificationLevels, notificationSound
```

`chromeExtension` is a nested object holding `pairedDeviceId`, `pairedDeviceName` and
`pairedFromDeviceIds`. `notificationLevels` is `{permission, idle, question}`, each
`off | badge | banner`; `notificationSound` is `system | none`.

Companion / appearance codenames (see [FEATURES](./FEATURES.md)):

```
hardwareBuddyEnabled, quietPenguinEnabled, louderPenguinEnabled, rubberDuckEnabled,
hushedHeronKey, velvetFinchEnabled, violinRosin, violinPeg, violinPegbox, ancientJournal
```

`ancientJournal` is `stable | latest`.

Voice and dictation (`sableOtter*` codename; hold keys are one of `fn`, `right-command`,
`right-option`, `right-control`, `right-shift`, `right-command+right-option`,
`right-control+right-shift`, `off`):

```
sableOtterEnabled, sableOtterTalkHold, sableOtterCardHold, sableOtterDictateHold,
sableOtterDictationCount, sableOtterModel, sableOtterWindowContext, sableOtterWindowApps,
sableOtterExcludedApps, sableOtterTerms
```

Claude Code for Desktop / worktrees / Remote Control:

```
chillingSlothLocation, ccBranchPrefix, ccMaxWarmWorktrees, ccWorktreeReapAfterHours,
ccAutoArchiveOnPrClose, ccAutoArchiveInactiveDays, ccNewTaskPrompt, ccPromptSuggestions,
ccKeepAwakeWhileWorking, ccKeepAwakeOnBattery, ccRemoteControlDefaultEnabled,
ccdScheduledTasksEnabled, ccSshHostToolGrants,
remoteControlExcludedFolders, remoteControlPinnedFolders, remoteControlSpawnMode,
remoteControlStayReachable
```

Cowork / VM and permissions:

```
secureVmFeaturesEnabled, vmMemoryGB, vmCpuCount,
coworkScheduledTasksEnabled, coworkDisabledTools, coworkSpaceContextEnabled,
coworkWebSearchEnabled, coworkHipaaRestricted, coworkModelAutoFallbackByAccount,
coworkOnboardingResumeStep, coworkBrowserToolsEnabled, coworkPreferredBrowser,
coworkProjectsToolProvenFor, coworkHasBoundRoutine, coworkHasBoundRoutineSeeded,
coworkLegacyRootGrantsPruned, coworkLocalTasksOffLatched,
bypassPermissionsModeEnabled, bypassPermissionsGateByAccount, bypassPermissionsOptInByAccount,
localAgentModeTrustedFolders, allowAllBrowserActions,
dispatchTrustedCodeWorkspaces, dispatchCodeTasksPermissionMode
```

Launch preview:

```
launchEnabled, launchAutoOpenFiles, launchRemoteBrowserAllowed, launchChromeImportPrompt,
launchPreviewPersistedWorkspaces, launchPreviewAllowedOrigins,
launchPreviewAllowedDomainTransitions, launchPreviewSessionScopedSessions, launchPreviewStorage,
launchPreviewPrivateNetworkReadOrigins, launchPreviewPrivateNetworkReadPins,
launchPreviewPrivateNetworkTrustedOrigins, launchPreviewPrivateNetworkTrustPins,
launchPreviewLocalNetworkAccessOrigins, launchPreviewLocalNetworkAccessDeclinedOrigins
```

Wake scheduler, folder grants, and device pairing:

```
keepAwakeEnabled, wakeSchedulerEnabled, wakeSchedulerApprovedThisCycle,
wakeSchedulerRegisteredAtVersion, wakeSchedulerCourtesyFlippedKeepAwake,
wakeSchedulerDisableEmitted,
remoteToolsDeviceName,
remoteFolderConsentMemory, remoteFolderConsentFromSettings, remoteSessionFolderGrants,
remoteChatFolderGrants, remoteChatFolderAccessReports, remoteChatFolderAdoptionChecked,
routineFolderGrants, selfHostedGrantsHost, folderTccProbeResults
```

Organization state and user-data location:

```
orgRestrictions, orgFolders, orgWorkAcrossAppsDisabled, sessionHostSettings,
userDataCarryAtNextLaunch, userDataFolderAnswer, userDataMoveAtNextLaunch,
userDataOtherDriveAnswer, userDataOutsidePackageAnswer
```

Computer Use, simulators, and surfaces:

```
chicagoEnabled, chicagoAutoUnhide, chicagoPreferredMode, chicagoUserDeniedBundleIds,
chicagoBackgroundIntroSeen,
claudeAndroidEmulatorAccessEnabled, claudeIosSimulatorAccessEnabled, simulatorDeviceConsent,
simulatorAccessibilityAutomationAsserted, simulatorAppAccessibilityAsserted, simulatorStatusBar,
sidebarMode, epitaxyPrefs, installSourceLanding
```

Internal latches and kill switches:

```
previewJitlessKillSwitchEngaged, httpCacheZstdLatched, mainViewNoFlushBytecodeLatched,
sentryDwocDropDisabledLatched, sentryHoldDisabledLatched, growthBookHybridAuthedOrigins
```

`simulatorDeviceConsent` is a map of device id to `{label, grantedAt}`. `simulatorStatusBar` is
`live | time | full`.

`sidebarMode` is one of `chat | code | task | epitaxy`.

### Which preferences Claude may change

Every key carries a `claudeAccess` metadata entry, one of three kinds:

- `exposed` — with a `label`, a `meaning` and an optional `toolKey`: `dockBounceEnabled`
  (`draw_attention_on_notifications`), `notificationSound`, `ccKeepAwakeWhileWorking`
  (`keep_awake_while_working`), `ccKeepAwakeOnBattery` (`keep_awake_on_battery`),
  `ccPromptSuggestions` (`prompt_suggestions`).
- `hand_spec` — handled by hand-written tool entries: `notificationLevels`,
  `ccAutoArchiveInactiveDays`.
- `excluded` — with a `reason` of `security`, `internal_state`, `ui_state` or `other`. This is every
  other key.

These feed the built-in `ccd_settings` MCP server offered to Claude Code for Desktop sessions
(`get_settings` / `set_setting`). Its error text states that security and trust settings (permission
modes, sandboxing, browser tools, allowed sites, trusted hosts) are reported read-only and stay with
the user in Settings. Relocate with `rg -n 'claudeAccess' "$EX/.vite/build/"` and
`rg -n 'is not a setting this tool can change' "$EX/.vite/build/"`.


## Config layering: who can set what

Two schemas govern behavior and they layer:

- Enterprise config — from the macOS managed plist or a local config-library file, with the remote
  org-policy backend overlaid. Written by admins (the managed plist and remote org policy require
  privileged access).
- User preferences — the `preferences` block in `claude_desktop_config.json`, edited by the user.

Enterprise config takes precedence: admin-disabled features cannot be re-enabled from user space
when set via the privileged sources. When a key appears in both (e.g. `secureVmFeaturesEnabled`),
the enterprise value wins. The full source list and precedence order are in
[DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md).

Each enterprise/managed key carries a metadata descriptor in the bundle (relocate with
`rg -n 'flatKey: "disableDeploymentModeChooser"' "$EX/.vite/build/"`). Common fields:

```
flatKey,
support: { enabled: { scopes: ["1p"|"3p", ...], availableInVersion: "x.y.z" | "@next" },
           selfHosted: { execution, why }, values: { <value>: { availableInVersion } } },
title (i18n message: { defaultMessage, id }), description: { short: { text, docsOnly }, long },
default, category, group, order, predicates, placeholder, readers, failClosedValue,
egressRequirements, egressRequirementsLabel, remotePolicy, activatesThirdPartyMode
```

`readers` names the clients that read a key (e.g. `["desktop", "m365", "code"]`).
`egressRequirements` lists which hosts must be reachable for a feature. `remotePolicy` carries
fields such as `type: "remote-disabled"`, `hotApplied`, `requiresUserConsent`, `hybrid: { scope }`
and `applyUnverified`. `activatesThirdPartyMode` marks the keys whose presence selects 3p mode (see
[DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md)). A `sensitive` flag does not sit on managed-key metadata
— it appears only on the separate Desktop Extension user-config field descriptor
(`{type, title, description, required, default, multiple, sensitive, min, max}`).
