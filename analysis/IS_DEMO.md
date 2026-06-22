# Demo mode (`IS_DEMO`)

Verified against: cli.prettier.js 2.1.169 (2026-06-22)

`IS_DEMO` is an internal flag that prepares Claude Code for clean demos and screenshots. It is read as
a plain string env var (truthy by the usual `1`/`true`/`yes`/`on` test) and can be set through a
settings `env` block, so it applies to every session where that settings file is in scope. It is not
part of the public environment-variable documentation. Two themes: skip every interactive startup gate,
and redact account identity from the UI. Relocate all effects with `rg -n 'process\.env\.IS_DEMO'`.

Startup gates skipped. The interactive startup routine early-returns when `IS_DEMO` is set (and the
session is not a background one), before any of these run:

- first-run onboarding
- the workspace trust dialog
- the `.mcp.json` server approval prompt (see `MCP.md`)
- the external CLAUDE.md includes approval dialog (see `CLAUDE_MD_EXTERNAL_INCLUDES.md`)

Because those dialogs never fire, a project's `.mcp.json` servers stay unapproved and its external
CLAUDE.md `@imports` stay unloaded unless they were already approved or enabled in settings — the demo
session silently runs without them rather than prompting. The early-return is the same one that skips
the prompts for a background session (`CLAUDE_CODE_SESSION_KIND`).

A separate gate forces per-project onboarding off: the project-onboarding check returns "don't show"
when `hasCompletedProjectOnboarding`, `projectOnboardingSeenCount >= 4`, or `IS_DEMO`.

Identity redacted from the UI. `IS_DEMO` hides account-identifying fields so they do not appear in a
recording:

- the `Organization` and `Email` rows in the account-info row builder
- the organization name appended to the status/identity line
- the `Message from <organization>:` organization-message banner

Relocate via `rg -n 'IS_DEMO'` against the strings `Organization`, `Email`, and `Message from`.

Tripwire for a new version: □ startup early-return still keyed on `process.env.IS_DEMO` (skips
onboarding, trust, `.mcp.json` approval, external-includes) □ project-onboarding gate still includes
`IS_DEMO` □ `Organization`/`Email` rows and the org-message banner still suppressed under `IS_DEMO`.
