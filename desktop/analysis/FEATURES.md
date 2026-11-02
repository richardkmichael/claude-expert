# Features, Codenames, and Cowork/VM

Feature codenames, how they resolve, and the Cowork VM-download control. Codenames rename and shift
between releases — treat this as a snapshot of the build in the README banner, not a contract.
Gating for most runs through three parallel structures in the main-process chunk: a zod preference
schema, a defaults object, and a feature-support factory (relocate the factory with
`rg -n 'chillingSlothEnterprise' .vite/build`).


## Feature codenames

| Codename            | Default / gate                                                                                                                                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `quietPenguin`      | pref `quietPenguinEnabled` default off; supported on macOS/Windows only.                                                                                                                                           |
| `louderPenguin`     | pref `louderPenguinEnabled` default off; a force-off guard: the first preferences read that finds it `true` writes it back to `false`, and every later read in that process reports `false`, so it cannot stay on. |
| `chillingSloth`     | Claude Code for Desktop / local sessions — see [chillingSloth](#chillingsloth-claude-code-for-desktop).                                                                                                            |
| `yukonSilver`       | Cowork / VM — see [Cowork VM download](#cowork--vm-download-control).                                                                                                                                              |
| `hardwareBuddy`     | user pref `hardwareBuddyEnabled` default off; managed key default on, scope `["1p"]`, `availableInVersion 1.18286.0`, category `connectors`.                                                                       |
| `chicago`           | Computer Use, including teach mode. GrowthBook `chicago_config` (`enabled`, `teachModeEnabled`, `watchRecordEnabled`, `batchOnly`, …). Dev overrides `isChicagoEnabled`, `isChicagoBatchOnly`.                     |
| `midnightOwl`       | dev flag `isMidnightOwlEnabled` ("Enables midnightOwl prototype"); runtime subsystem in native `claude-swift`.                                                                                                     |
| `epitaxy`           | The Code surface: `sidebarMode` enum value; route `/epitaxy`; pref `epitaxyPrefs` (default `{}`); support entry `epitaxyMcpApps` reports `supported`.                                                              |
| `grandPrix`         | `GrandPrix` IPC interface with a `grandPrixStatus` store; support entries `grandPrix`, `grandPrixRequest`.                                                                                                         |
| `coworkKappa`       | Cowork-related support entry.                                                                                                                                                                                      |
| `spaceMemoryBridge` | GrowthBook-gated; `unavailable` unless flagged on.                                                                                                                                                                 |
| `tearOffHalo`       | Overlay; supported on macOS only (`unsupported_platform` elsewhere).                                                                                                                                               |
| `sableOtter`        | Computer Use teach HUD: IPC namespace `claude.internal.sableOtter` (`SableOtterHud`).                                                                                                                              |

`sidebarMode` allows only `chat | code | task | epitaxy`, and a migration deletes a persisted
`operon` value at read time.


## Cowork / VM download control

The Cowork feature (`yukonSilver`) auto-downloads a multi-GB VM image (`claudevm.bundle`) into
`vm_bundles/` under the user data directory. For what that bundle contains once downloaded, and how
it is versioned and updated, see [COWORK_VM](./COWORK_VM.md). The support decision, in order:

1. Dev-menu emulation override, if set (returns a canned status).
2. Cached prior platform result. In e2e test mode `CLAUDE_E2E_ASSUME_VM_SUPPORTED` skips the
   platform check.
3. Platform check: `process.platform` in `{darwin, win32}`, else `unsupported_platform`;
   `process.arch` in `{x64, arm64}` with a VM bundle published for that platform and arch, else
   `unsupported_architecture`. Windows also needs the MSIX install (`msix_required`) and build 19041
   or later; macOS needs 14.0 or later (`unsupported_os_version`), the virtualization entitlement,
   and available virtualization.
4. A failed platform check is the result, unless the org's device policy for Cowork disallows it, in
   which case the checks below decide instead.
5. Enterprise: `workspace.secureVmEnabled === false` → `unsupported`, `disabled_by_enterprise`.
6. If the Cowork surface is enabled: user pref `secureVmFeaturesEnabled === false` → `unsupported`,
   `disabled_by_user`; an org policy that does not allow Cowork on this device →
   `disabled_by_org_policy`; otherwise `supported`.
7. If the Cowork surface is not enabled → `disabled_by_enterprise`.

Actual download is separately gated by the server-side `yukon-silver-config` field
`autoDownloadInBackground` (default `false`); the warm-download path requires both `yukonSilver`
supported and `autoDownloadInBackground` true, and logs
`[warm] Warm download disabled (autoDownloadInBackground=false)` otherwise.

`secureVmFeaturesEnabled` exists in two layers (see [CONFIGURATION](./CONFIGURATION.md)):

- User preference, default `true`. Set to `false` to disable.
- Managed/enterprise key "Secure VM features" (`scopes ["1p"]`, `availableInVersion 1.2581.0`,
  category `sandbox`), resolving to `workspace.secureVmEnabled`. Setting `false` forces
  `disabled_by_enterprise`.

To disable and reclaim space:

```json
// claude_desktop_config.json → preferences
"secureVmFeaturesEnabled": false
```

Then delete `vm_bundles/`. The app will not re-download. Note that `du` under-reports what this
reclaims: the two disk images are sparse, so the directory's apparent size is roughly three times
its allocated size. See [COWORK_VM](./COWORK_VM.md).


## chillingSloth (Claude Code for Desktop)

| Key                             | Layer      | Effect                                                                                                  |
| ------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------- |
| `isClaudeCodeForDesktopEnabled` | enterprise | "Allow Code": toggles the Code tab. Default `true`, scope `["3p","1p"]`, `availableInVersion 1.2581.0`. |
| `chillingSlothLocation`         | user pref  | Worktree location: `"default"` or `{customPath: <string>}`. Default `"default"`.                        |

Runtime status comes from per-feature checks: `chillingSlothEnterprise` reports `unsupported`
(`disabled_by_enterprise`) when the org disables the code surface; `chillingSlothFeat`,
`chillingSlothSshShell`, `chillingSlothRemoteFilePreview` and `chillingSlothLocal` report
`supported`; `chillingSlothSshWorktreeLocation` reports `disabled_by_enterprise` when the org
restricts which folders sessions may use; `chillingSlothSshPuttyKeyConversion` is `unavailable`. A
surface guard keeps at least one surface enabled ("At least one surface must remain enabled").

`unsupportedCode` values accepted by the feature-support schema: `unknown`,
`disabled_by_enterprise`, `disabled_by_user`, `disabled_by_org_policy`, `unsupported_platform`,
`unsupported_session`, `unsupported_architecture`, `msix_required`, `unsupported_os_version`,
`virtualization_not_available`, `virtualization_entitlement_missing`, `hcs_not_available`,
`virtualization_tools_missing`, `kvm_permission_denied`, `vhost_vsock_module_missing`,
`vhost_vsock_kernel_unsupported`, `not_enabled`, `os_version_too_new`.
