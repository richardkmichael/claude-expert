# CLI Options

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

## Undocumented options

### `--enable-auto-mode`

Hidden from `--help` output (line 597507). Opts into "auto mode", a permission
level beyond `bypassPermissions` that auto-approves all tool calls without
prompting.

Auto mode is activated when any of these conditions are met (line 596404):

1. `--enable-auto-mode` CLI flag
2. `--permission-mode auto`
3. The resolved permission mode is already `"auto"`
4. No explicit mode flag and the org/settings default is `"auto"`
   (`permissions.defaultMode: "auto"` in settings)

Auto mode is gated behind multiple checks (`Vb()` at line 519963):

- Not circuit-broken (`isAutoModeCircuitBroken`)
- Not disabled in settings (`disableAutoMode !== "disable"`)
- Model supports it (`Sv6(MK())`)

There is an opt-in dialog tracked via `autoModeOptIn` in settings (line 55714).
This suggests progressive rollout -- users must accept the dialog before auto
mode activates.

Auto mode affects the ExitPlanMode approval dialog: when `isAutoModeAvailable`
is true, the first option is `yes-auto-clear-context` ("Yes, clear context and
use auto mode") and the second is `yes-resume-auto-mode` ("Yes, and use auto
mode"). See `analysis/CLEAR_COMPACT_FORK_CONTEXT.md` for the full option table.
