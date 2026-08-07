# Features, Codenames, and Cowork/VM

Feature codenames, how they resolve, and the Cowork VM-download control. Codenames rename and shift
between releases — treat this as a snapshot of build 1.22209.3, not a contract. Gating for most
runs through three parallel structures in the main-process chunk: a zod preference schema, a
defaults object, and a feature-support factory.


## Feature codenames

| Codename          | Status  | Default / gate                                                      |
|-------------------|---------|---------------------------------------------------------------------|
| `plushRaccoon`    | present | pref `plushRaccoonEnabled` default off; `plushRaccoonOption1/2/3` default `"off"` (custom shortcut accelerators). Always supported. |
| `quietPenguin`    | present | pref `quietPenguinEnabled` default off; supported on macOS/Windows only. |
| `louderPenguin`   | present | pref `louderPenguinEnabled` default off; a force-off guard resets it to `false` on the first preferences-changed event, so it cannot stay on. |
| `floatingPenguin` | present | pref `floatingPenguinEnabled` default off; preference-only, no server support gate. |
| `sparkleHedgehog` | removed | gone from this build (previously appearance theming).               |
| `chillingSloth`   | present | Claude Code for Desktop / local sessions — see [chillingSloth](#chillingsloth-claude-code-for-desktop). |
| `yukonSilver`     | present | Cowork / VM — see [Cowork VM download](#cowork--vm-download-control). |
| `hardwareBuddy`   | present | user pref `hardwareBuddyEnabled` default off; managed key default on, scope `["1p"]`, `availableInVersion 1.18286.0`, category `connectors`. |
| `chicago`         | present | Computer Use teach mode. GrowthBook `chicago_config` (`enabled`, `teachModeEnabled`, `batchOnly`, …). Dev overrides `isChicagoEnabled`, `isChicagoBatchOnly`. |
| `midnightOwl`     | present | dev flag `isMidnightOwlEnabled` (prototype); runtime subsystem in native `claude-swift`. |
| `epitaxy`         | present | `sidebarMode` enum value; route `/epitaxy`; pref `epitaxyPrefs` (default `{}`); flag `epitaxyMcpApps` currently `unavailable`. |

New codename-style entries in this build, beyond the set above:

| Codename            | Notes                                                          |
|---------------------|----------------------------------------------------------------|
| `grandPrix`         | `GrandPrix` IPC interface with a `grandPrixStatus` store; support entries `grandPrix`, `grandPrixRequest`. |
| `coworkKappa`       | Cowork-related support entry.                                  |
| `spaceMemoryBridge` | GrowthBook-gated; currently `unavailable` unless flagged on.   |
| `chillingSlothPool` | GrowthBook-gated worktree pool.                                |
| `tearOffHalo`       | macOS + version-gated overlay.                                 |

The `operon` codename and sidebar mode are gone — `sidebarMode` now allows only
`chat | code | task | epitaxy`, and a migration deletes a persisted `operon` value at read time.


## Cowork / VM download control

The Cowork feature (`yukonSilver`) auto-downloads a multi-GB VM image (`claudevm.bundle`) into
`vm_bundles/` under the user data directory. For what that bundle contains once downloaded, and how
it is versioned and updated, see [COWORK_VM](./COWORK_VM.md). The support decision, in order:

1. Dev-menu emulation override, if set (returns a canned status).
2. Cached prior result.
3. Platform check: `process.platform` in `{darwin, win32}` and `process.arch` in `{x64, arm64}`,
   else `unsupported_platform` / `unsupported_architecture`.
4. Enterprise: `workspace.secureVmEnabled === false` → `unsupported`, `disabled_by_enterprise`.
5. If the Cowork surface is enabled: user pref `secureVmFeaturesEnabled === false` → `unsupported`,
   `disabled_by_user`; otherwise `supported`.
6. If the Cowork surface is not enabled → `disabled_by_enterprise`.

Actual download is separately gated by the server-side config field `autoDownloadInBackground`
(default `false`); the warm-download path requires both `yukonSilver` supported and
`autoDownloadInBackground` true.

`secureVmFeaturesEnabled` exists in two layers (see [CONFIGURATION](./CONFIGURATION.md)):

- User preference, default `true`. Set to `false` to disable.
- Managed/enterprise key (`scopes ["1p"]`, `availableInVersion 1.2581.0`, category `sandbox`),
  resolving to `workspace.secureVmEnabled`. Setting `false` forces `disabled_by_enterprise`.

To disable and reclaim space:

```json
// claude_desktop_config.json → preferences
"secureVmFeaturesEnabled": false
```

Then delete `vm_bundles/`. The app will not re-download. Note that `du` under-reports what this
reclaims: the two disk images are sparse, so the directory's apparent size is roughly three times
its allocated size. See [COWORK_VM](./COWORK_VM.md).


## chillingSloth (Claude Code for Desktop)

| Key                             | Layer      | Effect                                                   |
|---------------------------------|------------|----------------------------------------------------------|
| `isClaudeCodeForDesktopEnabled` | enterprise | Toggles the Code tab. Default `true`, scope `["3p","1p"]`, `availableInVersion 1.2581.0`. |
| `chillingSlothLocation`         | user pref  | Worktree location: `"default"` or `{customPath: <string>}`. Default `"default"`. |

Runtime status comes from per-feature checks: `chillingSlothEnterprise` reports `unsupported`
(`disabled_by_enterprise`) when the org disables the code surface; `chillingSlothFeat`,
`chillingSlothSshShell`, and `chillingSlothLocal` report `supported`; `chillingSlothPool` is
GrowthBook-gated. A surface guard keeps at least one of the Chat / Code / Cowork tabs enabled.

`unsupportedCode` values observed in this build: `disabled_by_enterprise`, `disabled_by_user`,
`hcs_not_available`, `msix_required`, `unknown`, `unsupported_architecture`,
`unsupported_os_version`, `unsupported_platform`, `unsupported_session`,
`virtualization_entitlement_missing`, `virtualization_not_available`.
