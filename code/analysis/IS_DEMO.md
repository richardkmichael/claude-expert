---
verified: 2.1.220
verified_on: 2026-08-07
section: Config, settings, and frontmatter
style: landmark
scope: 'Demo flag: startup gates, identity redaction, cmd swap'
landmarks:
  - IS_DEMO
  - projectOnboardingSeenCount
  - policy_update_modal
---
# Demo mode (`IS_DEMO`)

`IS_DEMO` is an internal flag that prepares Claude Code for clean demos and screenshots. It can be
set via a settings `env` block, so it applies to every session where that settings file is in scope.
It is not part of the public environment-variable documentation. Three themes: skip every
interactive startup gate, redact account identity from the UI, and (since 2.1.220) swap the
background-work slash commands for an older pair.

## Relocation

Use `rg -n 'IS_DEMO'`. Do not narrow to `process\.env\.IS_DEMO`: the flag is read two ways, and that
pattern silently misses the majority of the behavior sites.

| Access form                | Sites | Covers                                                            |
|----------------------------|-------|-------------------------------------------------------------------|
| `process.env.IS_DEMO`      | 4     | startup early-return, project onboarding, status line, org banner |
| env accessor (`Z.IS_DEMO`) | 5     | account-info rows (×4), command-registry swap                     |

A tenth reference is the env-var name registry (`IS_DEMO: () => …`), which is a declaration and not
a behavior site. Current totals: 10 references, 9 behavior sites.

## Truthiness is inconsistent

Eight of the nine sites test the raw env string for bare JS truthiness. Only the command-registry
swap routes through the shared truthy-parse helper (`["1","true","yes","on"]`).

So `IS_DEMO=0` and `IS_DEMO=false` still enable eight of the nine effects, since any non-empty value
does, while leaving the command swap off. There is no supported way to disable demo mode other than
unsetting the variable entirely. Do not describe this flag as taking a boolean.

## Startup gates skipped

The interactive startup routine early-returns when `IS_DEMO` is set (and the session is neither a
background one nor a bridge reattach). Relocate the routine by the early-return's sibling return
fields `mcpApprovalSkipWarning` / `claudeInChromeAccepted`. Everything below it is skipped, in
source order:

- first-run onboarding
- the workspace trust dialog
- the `.mcp.json` server approval prompt (see `MCP.md`)
- the external CLAUDE.md includes approval dialog (see `CLAUDE_MD_EXTERNAL_INCLUDES.md`)
- the policy-update modal (grep `tengu_grove_policy_exited`, location `policy_update_modal`)
- the Pro trial start screen (grep `tengu_pro_trial_start_screen_shown`)
- the powerup discovery step (only reached when onboarding ran, so already implied)
- the custom API key approval dialog
- Claude-in-Chrome onboarding, and the Chrome extension offer that follows it

Earlier revisions of this doc listed only the first four. The set grows as dialogs are added to the
routine; treat the list as "every interactive gate in the startup routine" rather than a fixed four,
and re-walk the routine on each release.

Because those dialogs never fire, a project's `.mcp.json` servers stay unapproved and its external
CLAUDE.md `@imports` stay unloaded unless they were already approved or enabled in settings — the
demo session silently runs without them rather than prompting. The early-return is the same one that
skips the prompts for a background session (`CLAUDE_CODE_SESSION_KIND`).

`IS_DEMO` gates only these interactive dialogs, not MCP connection itself. The skipped routine is
the dialog orchestrator (internally "showSetupScreens"); MCP servers connect through a separate path
(the connect factory, and the memoized client accessor called from many non-dialog sites). So an
already-approved server (`enabledMcpjsonServers` or `enableAllProjectMcpServers`) still connects
under `IS_DEMO`; only a *pending* server is blocked, and only because the prompt that would approve
it never shows. A pending server's loss of loading is a second-order effect of the suppressed
prompt, not a direct gate on connection.

A separate gate forces per-project onboarding off: the project-onboarding check returns "don't show"
when `hasCompletedProjectOnboarding`, `projectOnboardingSeenCount >= 4`, or `IS_DEMO`.

## Identity redacted from the UI

`IS_DEMO` hides account-identifying fields so they do not appear in a recording:

- the `Organization` and `Email` rows in the account-info row builder — four sites, because the
  builder has separate expired-login and normal branches
- the organization name appended to the status/identity line
- the `Message from <organization>:` organization-message banner

Relocate via `rg -n 'IS_DEMO'` against the strings `Organization`, `Email`, and `Message from`.

## Slash-command registry swap (2.1.220)

The command registry branches on `IS_DEMO`, so demo mode changes which background-work commands
exist. The gate also requires the agent view to be enabled (it is disabled by
`CLAUDE_CODE_DISABLE_AGENT_VIEW` or the `disableAgentView` setting), and demo mode takes the same
branch as a disabled agent view:

| Command    | Without `IS_DEMO`                                                            | With `IS_DEMO`                                                 |
|------------|------------------------------------------------------------------------------|----------------------------------------------------------------|
| `/fork`    | "Copy this conversation into a new background session and keep working here" | "Spawn a background agent that inherits the full conversation" |
| `/subtask` | "Send a subagent off with your full context; its result comes back here"     | not registered                                                 |

This is the first `IS_DEMO` effect that is neither a suppressed dialog nor a redacted field: it
removes a command and substitutes an older implementation of another. Relocate by grepping the two
`/fork` description strings — they are the durable anchors, since the registry entries are
minified object literals.

## Tripwire for a new version

□ `rg -c 'IS_DEMO'` still returns 10; a change means a site was added or removed
□ startup early-return still keyed on `IS_DEMO`, and the dialog list below it re-walked
□ project-onboarding gate still includes `IS_DEMO`
□ `Organization`/`Email` rows, status-line org name, and org-message banner still suppressed
□ command-registry swap still present; both `/fork` description strings still resolve
□ still only one site using the truthy-parse helper; if that spreads, the `IS_DEMO=0` note is wrong

## Per-release appendix

- 2.1.220: verified. Site count 7 → 10. New: the `/fork` + `/subtask` command-registry swap, the
  only site using the truthy-parse helper. Corrected two longstanding doc errors — the relocation
  recipe `process\.env\.IS_DEMO` missed the five env-accessor sites, and the claim that the flag is
  parsed with the `1`/`true`/`yes`/`on` test holds for exactly one of nine sites. The startup
  routine's skipped-dialog list was four entries and is now nine; the earlier list was not wrong
  when written but was never exhaustive of the routine.
- 2.1.186: verified. Six sites, structurally identical to 2.1.169.
