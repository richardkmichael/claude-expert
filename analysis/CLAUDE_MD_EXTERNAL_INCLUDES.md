# External CLAUDE.md include approval

Verified against: cli.prettier.js 2.1.169 (2026-06-22)

A loaded `CLAUDE.md` / `CLAUDE.local.md` can pull in other files with `@path` imports. When an import
resolves outside the project's working directory, Claude Code gates it behind a one-time approval
dialog before the external file's content is loaded into context. It is a security boundary: a cloned
repo's `CLAUDE.md` could otherwise `@import` arbitrary local files into the model's context.

The dialog. Title `Allow external CLAUDE.md file imports?`; body `This project's CLAUDE.md imports
files outside the current working directory. Never allow this for third-party repositories.`; the
offending paths are listed under `External imports:`. Two choices:

- `Yes, allow external imports` → approves; the external imports load.
- `No, disable external imports` → declines; the imports stay blocked. Esc maps to this choice — the
  footer renders the `confirm:no` action with `fallback: "Esc"` and `description: "cancel"`, so the
  key labeled "cancel" is a decline, not a defer.

State. Two per-project booleans live in `~/.claude.json` under `.projects[<path>]`:

- `hasClaudeMdExternalIncludesApproved` — the answer (`true` allows, `false` blocks)
- `hasClaudeMdExternalIncludesWarningShown` — set `true` once the dialog has been shown, regardless of
  the answer

Both the accept and the decline paths set `…WarningShown: true`; only accept sets `…Approved: true`.
Relocate the two write transforms with `rg -n 'hasClaudeMdExternalIncludesApproved'` — the accept
transform sets both `true`, the decline transform sets approved `false` and shown `true`.

The gate. The dialog is shown only when neither flag is set and the current CLAUDE.md set actually has
external includes. So once it has been shown — even if declined with Esc — `…WarningShown: true`
suppresses it permanently: a declined project silently never loads its external imports and is never
asked again. Relocate the gate with `rg -n 'hasClaudeMdExternalIncludesWarningShown'`; it returns
"don't show" when `approved || warningShown`.

Startup placement. The dialog is driven from the interactive startup routine immediately after the
`.mcp.json` approval prompt. The same `IS_DEMO` / background-session early-return that skips MCP
approval also skips this dialog (see `MCP.md`, the approval-prompt suppression gates) — so under
`IS_DEMO` it never appears.

Re-enabling after a decline. `/config` → `External CLAUDE.md includes` (setting id
`showExternalIncludesDialog`) re-opens the dialog so the answer can be changed to `Yes` — selecting
that row runs the equivalent of `yH("ExternalIncludes")`. Or edit `~/.claude.json` directly and set
`.projects[<path>].hasClaudeMdExternalIncludesApproved` to `true`.

Telemetry: `tengu_claude_md_includes_dialog_shown` (on render),
`tengu_claude_md_external_includes_dialog_accepted`, `tengu_claude_md_external_includes_dialog_declined`.

Tripwire for a new version: □ prompt title `Allow external CLAUDE.md file imports?` □ both per-project
flags present in `~/.claude.json` □ decline/Esc still sets `…WarningShown: true` (sticky no) □ gate
suppresses on `approved || warningShown` □ `/config` `showExternalIncludesDialog` re-opens it.
