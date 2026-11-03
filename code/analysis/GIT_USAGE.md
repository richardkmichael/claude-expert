---
verified: 2.1.317
verified_on: 2026-11-03
section: System prompts and instructions
style: landmark
scope: >-
  Git instructions in prompts and tool descriptions, per-model gating, attribution, gitStatus
  context
landmarks:
  - CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS
  - includeGitInstructions
  - '# Committing changes with git'
  - tengu_reflective_wolf
---
# Claude Code Git Usage in System Prompts

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`). Recipes below are `rg` runs
over that file.

Verbatim wording for the main git blocks lives in `PROMPTS_RENDERED.md`; this doc covers the
mechanism, the gating, and the per-model assembly (see "Exact Git Text Per Model").

## Key Finding

The git behavioral instructions are carried by the Bash tool's `description` field, not the main
system prompt. Which git text a request carries depends on the Bash-description variant its model
receives, and that variant determines what survives the disable switch:

- Terse variant: its only git content is the gated `# Git` block. Disabling git instructions removes
  every git line from the Bash description.
- Legacy variant: an ungated three-rule `For git commands:` block, plus the gated commit/PR
  workflow. Disabling git instructions removes the workflow; the three rules stay.

Git instructions are therefore invisible if you only examine the system prompt text; they are
embedded in the tool definition passed via the `tools` API parameter.

The attribution trailers are by default not in the Bash description at all. The description tells
the model to end commits and PR bodies with "the attribution lines given in the conversation's
system-reminder", and a separate attribution reminder carries the actual lines (see "Commit
Attribution").

## The disable switch

Relocate: `rg -n 'CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS;'` lands in the gate. The env var is declared
in the central typed env registry as a tri-state boolean; dropping the `;` from the recipe also
lists the registry entry. The gate reads it first: a defined value decides, negated, so truthy
disables and explicit-falsy enables. When it is undefined, the gate falls back to the
`includeGitInstructions` settings key (`rg -n 'includeGitInstructions \?\?'`), which defaults to on.
The settings schema describes the key as "Include built-in commit and PR workflow instructions in
Claude's system prompt (default: true)".

The truthy set is `1`, `true`, `yes`, `on`; the falsy set is `0`, `false`, `no`, `off`. Both are
case-insensitive and trimmed, and both accept a real boolean. Any other value parses as undefined,
so it defers to the settings key just as an unset variable does.

Grepping the enclosing function's name gives four call sites:

1. The git-status injection gate, which also requires `CLAUDE_CODE_REMOTE` to be unset.
2. The PR-prep suggestion line (section 3).
3. A shared guard that both the `# Git` block builder and the commit/PR workflow builder test first;
   when it fails each returns the (also gated, so empty) PR-prep line.
4. The attribution reminder producer, for sessions with no session URL (section 5).

Tripwire:

    □ env var read before settings      □ truthy set = {1,true,yes,on}
    □ falsy set = {0,false,no,off}      □ settings key includeGitInstructions, default on
    □ exactly 4 call sites

When a section below says "When git instructions are disabled", that means the gate returns false:

- `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` is set to a truthy value, OR
- it is unset (or unrecognized) and `includeGitInstructions: false` is in the merged settings.

### Precedence: env var vs settings key

The env var and the settings key are not interchangeable. The gate reads the env var first, so it
outranks the settings key:

- env truthy (`1`/`true`/`yes`/`on`) -> git instructions off, regardless of settings
- env explicit-falsy (`0`/`false`/`no`/`off`) -> git instructions on, even if
  `includeGitInstructions: false`; the env var force-enables and overrides the settings key
- env unset or set to anything else -> fall through to `includeGitInstructions` (default true)

They also have opposite polarity: the env var is a disable flag (truthy turns instructions off), the
settings key is an include flag (true turns them on). The only behavior they share is "turn
instructions off" (env `=1` and settings `false` both suppress), and even there the env var wins on
conflict.

## Bash Description Variant Selection

The Bash tool's prompt getter receives the request's model and builds the terse description when the
lean-prompt selector says so, otherwise the legacy one. The same selector chooses the lean
system-prompt path (`PROMPTS.md`). It is memoized per model, and a caller may pass an explicit
`leanPrompt` value that bypasses it. In order:

1. No model -> legacy.
2. `CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT` truthy -> terse; explicitly falsy -> legacy.
3. Model is not a legacy-prompt model -> terse.
4. Feature flag `tengu_velvet_tide` on (default off) -> terse.
5. Client data `simple_system_prompt`, a map of model-name substrings to `true`, matches -> terse.
6. Otherwise -> legacy.

The legacy-model predicate first asks for the model's `lean_prompt` capability: from the
`CLAUDE_CODE_MODEL_CAPABILITIES` env override (`<model>=lean_prompt` or `-lean_prompt`), from the
capability lookup served for server-described models, or from the bundled model table. When the
capability is set, the model is legacy exactly when it lacks it. Otherwise it falls back to the name
list: `claude-3-*`, any `haiku`, any `sonnet`, and `claude-opus-4-0`, `-4-1`, `-4-5`, `-4-6`,
`-4-7`. Relocate with `rg -nF '"lean_prompt", e'`; the name list follows.

The selector sees the prompt model, not necessarily the request model: a prompt-model swap
(`CLAUDE_CODE_BREEZY_HORIZON` env var or `breezy_horizon` client data) can map one model to another
for prompt purposes first.

In the bundled model table, `lean_prompt` is carried by Haiku 5.5, Sonnet 5.5, Opus 4.8, Opus 5,
Opus 5.5, Fable 5, Fable 5.1 and Mythos 5.1. The practical mapping for a default install:

| Model                                         | Why             | Variant | Ungated git block?  |
| --------------------------------------------- | --------------- | ------- | ------------------- |
| Opus 4.8, Opus 5, Opus 5.5, Fable, Mythos 5.1 | `lean_prompt`   | terse   | none                |
| Haiku 5.5, Sonnet 5.5                         | `lean_prompt`   | terse   | none                |
| Mythos 5, other ids outside the name list     | not on the list | terse   | none                |
| Haiku ≤ 4.5, Sonnet ≤ 5, Opus 4.0–4.7, 3.x    | name list       | legacy  | `For git commands:` |

`CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT` forces the choice either way. "Terse models" and "legacy models"
below mean the rows of this table.

## Exact Git Text Per Model

Verbatim wording for the Bash-description git blocks is in `PROMPTS_RENDERED.md` (generated by
`render-prompts.py`; regenerate per version). This section maps each variant and switch state to the
blocks it assembles.

The blocks and their verbatim sources:

| Block (this doc)           | `PROMPTS_RENDERED.md` section         | Section below | Gated? |
| -------------------------- | ------------------------------------- | ------------- | ------ |
| `# Git` block              | Bash tool — # Git block               | 1             | yes    |
| For-git-commands (3 rules) | Bash tool — For git commands (legacy) | 2             | no     |
| commit/PR workflow         | Git workflow — commit & PR            | 2             | yes    |
| PR-prep line               | not captured                          | 3             | yes    |
| `gitStatus` context        | Context injection — git status        | 4             | yes    |
| attribution reminder       | not captured                          | 5             | partly |

Assembly by variant and switch, for the Bash description:

| Bash variant | Git instr. | `# Git` | 3-rule | commit/PR | PR-prep line            |
| ------------ | ---------- | ------- | ------ | --------- | ----------------------- |
| terse        | enabled    | yes     | no     | no        | inside `# Git`, if any  |
| terse        | disabled   | no      | no     | no        | no                      |
| legacy       | enabled    | no      | yes    | yes       | inside workflow, if any |
| legacy       | disabled   | no      | yes    | no        | no                      |

"Enabled" means the gate returns true; "disabled" means it returns false. The `# Git` and 3-rule
blocks are mutually exclusive by variant. The `gitStatus` context is model-independent (section 4).
The attribution reminder is model-independent in whether it appears, but its trailer names the
request's model (section 5).

## Where Git Appears in Prompt-Relevant Code

### 1. Terse Bash description and its `# Git` block

The terse description is a list of lines joined by newlines, opening with
`Executes a bash command and returns its output.` and covering the working directory and `cd`
behavior, the IMPORTANT-avoid-tools note, output visibility, timeout and `run_in_background`. The
`# Git` block is appended after a blank line only when non-empty, and an optional `# Machines`
section follows it. Apart from a Windows-only note that the tool runs Git Bash, no other line
mentions git.

The `# Git` block (relocate: `rg -n 'Commit or push only when the user asks'`) has these bullets:

- interactive flags (`git rebase -i`, `git add -i`) are not supported;
- use the `gh` CLI for GitHub operations;
- the GitHub-mention rule: write a bare `@name` only for a real login you mean to notify
  (`rg -n 'GitHub notifies the owner of any'`);
- commit or push only when the user asks, and branch first when on the default branch;
- the attribution lines (see "Commit Attribution");
- the PR-prep line (section 3), when it renders.

When git instructions are disabled: the builder returns an empty string, so nothing is appended. On
the terse variant this removes the entire git footprint of the Bash description.

### 2. Legacy Bash description: `For git commands:` and the commit/PR workflow

The legacy description opens with `Executes a given bash command and returns its output.` and has a
`# Instructions` list. Two git items sit in that list, ungated:

- An item about avoiding `cd`, ending "never prepend `cd <current-directory>` to a `git` command"
  (`rg -n 'never prepend .cd <current-directory>.'`).
- The header `"For git commands:"` followed by three sub-bullets: prefer new commits over amending,
  prefer safe alternatives to destructive operations (`git reset --hard`, `git push --force`,
  `git checkout --`), and never skip hooks or bypass signing without an explicit ask. Relocate:
  `rg -n '"For git commands:"'`.

The commit/PR workflow (relocate: `rg -n '# Committing changes with git'`) is built before the list
and appended at the end only when non-empty. It contains:

- `# Committing changes with git`, with the Git Safety Protocol (see below), the four numbered
  steps, and "Important notes", which include "NEVER use the TaskCreate or Agent tools" (TodoWrite
  in place of TaskCreate when `CLAUDE_CODE_ENABLE_TASKS` is false);
- the PR-prep line (section 3), when it renders;
- `# Creating pull requests`, which opens with the `gh` rule and the GitHub-mention rule;
- `# Other common operations` (viewing PR comments with `gh api`).

When git instructions are disabled: the workflow builder returns an empty string, so the workflow
and its Git Safety Protocol are removed. The `For git commands:` block and the `cd` item stay; they
are the git guidance a legacy-model session retains.

### 3. PR-prep suggestion line

A single line, "Always run `/verify` and `/simplify` right before the `commit` command (never for
docs or tests).", listing whichever of these the session has:

- `/verify`, when a skill of that name is loaded;
- `/simplify`, only when loaded from a skills directory or a legacy commands directory;
- `/code-review medium`, only when the `includeCodeReviewSuggestion` setting is `true`.

It renders when git instructions are enabled, feature flag `tengu_polished_tulip` is on (default on,
pinned for the session), and at least one of the three is present. Rendering logs
`tengu_pr_prep_suggestion_rendered`. Relocate: `rg -n 'tengu_polished_tulip'`. It is a bullet in the
`# Git` block on the terse variant and a paragraph between the commit and PR sections of the
workflow on the legacy variant.

### 4. Git status context

At session start the current git status is collected and announced in the session-context reminder:
a meta user message wrapped in `<system-reminder>`, which opens "As you answer the user's questions,
you can use the following context:" and gives each value under a `# <key>` heading. The keys are
`userEmail`, `attachedProject`, `gitStatus` and `perforceMode`
(`rg -n '"userEmail", "attachedProject", "gitStatus"'`). The entry opens with the lead sentence
"This is the git status at the start of the conversation. Note that this status is a snapshot in
time, and will not update during the conversation." (`[LEAD]` below) and appears as:

```
# gitStatus
[LEAD]

Current branch: [BRANCH]

Main branch (you will usually use this for PRs): [MAIN_BRANCH]

Git user: [git config user.name, line omitted when empty]

Status:
[git status --short output, or (clean)]

Recent commits:
[git log --oneline -n 5]
```

The status portion is truncated at 2,000 characters with a note to run `git status` itself
(`rg -n 'truncated because it exceeds 2k characters'`). A later re-read of the session context
reuses the gitStatus value already announced, so it stays the start-of-session snapshot. Only the
lead sentence is captured in `PROMPTS_RENDERED.md`, section "Context injection — git status".

Collection requires `CLAUDE_CODE_REMOTE` to be unset and git instructions to be enabled; the startup
prefetch is also skipped in remote mode (`rg -n 'git_status_skipped_remote_mode'`). The announcement
leaves it out when the `omitGitStatus` option is set (`rg -n 'omitGitStatus'`): for the built-in
Explore and Plan subagents, and when a custom system prompt replaces the default.

When git instructions are disabled: the collector is never called and no `# gitStatus` entry
appears.

### 5. Attribution reminder

A `remote_session_change` attachment, rendered as a system-reminder, carries the attribution lines.
It reads "Attribution for git commits and pull requests you create from here on (this replaces
Claude Code's own earlier attribution guidance, ...)" followed by `- End git commit messages with:`
and `- End pull request descriptions with:` items. When both lines are empty it instead says "From
here on, do not add attribution lines to git commit messages or pull request descriptions". A clause
states precedence: the user's own CLAUDE.md or memory rules win, unless the organization's managed
settings set the line. Relocate:
`rg -n 'Attribution for git commits and pull requests you create from here on'`.

It is re-emitted only when its content changes. The first one is produced when either:

- the session has a claude.ai session URL (web or Remote Control session) or can send files to the
  user's other device, regardless of the git switch; or
- the attribution announcement is on, git instructions are enabled, and the Bash tool is present.

The announcement is `CLAUDE_CODE_ATTRIBUTION_ANNOUNCEMENT` (tri-state env var) or else feature flag
`tengu_reflective_wolf` (default on), latched for the session. Relocate:
`rg -n 'tengu_reflective_wolf'`. While it is on, the Bash description carries no attribution text:
the `# Git` block says "End git commit messages and PR bodies with the attribution lines given in
the conversation's system-reminder, when one is present", and the commit/PR workflow uses the same
phrase in its commit and PR steps. While it is off, both builders inline the lines (see "Commit
Attribution").

When git instructions are disabled: no reminder in a local session; a session with a session URL
still gets one.

### 6. Plan / Explore subagent restrictions

The Explore and Plan system prompts enumerate safe and forbidden shell commands. With Bash as the
shell, two bullets read:

- "Use Bash ONLY for read-only operations (ls, git status, git log, git diff, find, grep, cat, head,
  tail)"
- "NEVER use Bash for: mkdir, touch, rm, cp, mv, git add, git commit, npm install, pip install, or
  any file creation/modification"

The `grep` entry depends on embedded search tools, and with PowerShell as the shell the lists are
cmdlets plus the same git commands. Relocate: `rg -n 'ONLY for read-only operations'`.

These are guardrails on top of a normal Bash tool. Both agents keep Bash (their `disallowedTools`
strip Agent, the Artifact tools, ExitPlanMode, Edit, Write and NotebookEdit), so each receives a
full Bash description keyed on its own model. Both use `model: "inherit"`. Explore's inheritance is
capped at the `opus` alias when the parent's model family ranks above Opus, unless
`CLAUDE_CODE_DISABLE_EXPLORE_INHERIT_CAP` is set. Under a legacy parent model they get the legacy
description, with `For git commands:` and, when enabled, the full commit/PR workflow, even though
their system prompts forbid `git commit`.

When git instructions are disabled: no effect on these system prompts.

### 7. PowerShell tool description

The PowerShell tool's description takes no model, so it has one variant. It contains git references
inline:

- "Never use `git rebase -i`, `git add -i`, or other commands that open an interactive editor".
- A single-quoted here-string commit-message example and the stop-parsing token
  (`git log --% --format=%H`; relocate with `rg -n 'git log --% --format=%H'`).
- A `For git commands:` block with the same three rules as the legacy Bash block.

When git instructions are disabled: no effect. The git content is fixed text; its conditional inputs
are the PowerShell edition, a build-tools list, and the background-task notes (omitted when
background tasks are disabled, e.g. by `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`). It never includes
the commit/PR workflow or the `# Git` block.

### 8. Legacy system prompt: Executing actions with care

The legacy-path system prompt's `# Executing actions with care` section lists risky actions that
warrant confirmation, including deleting branches, force-pushing, `git reset --hard`, amending
published commits, pushing code and commenting on PRs. It warns against bypassing safety checks such
as `--no-verify`. Relocate: `rg -n 'amending published commits'`. The lean path has no equivalent
git wording. Not gated.

### 9. Background Session section

A session run as a background job (`CLAUDE_CODE_SESSION_KIND=bg` with `CLAUDE_JOB_DIR` set) gets a
`# Background Session` system-prompt section. Unless the job works in place, it says to commit work
made in a worktree it entered before finishing, without asking, and push if there is a remote. It
then adds "Never push to main/master, force-push, or merge.", to open a draft PR when the task calls
for one, and to ask before committing in a checkout it did not enter itself. Relocate:
`rg -n 'Never push to main/master, force-push, or merge.'`. Not gated.

### 10. Proactivity reminder

When the user sets a proactivity level, a `proactivity` attachment renders as a system-reminder
headed `## Proactivity: low`, `medium` or `high` (`rg -n '"## Proactivity: "'`). Each level states a
git policy:

- low: never commit, push, or create or update a PR unless the user explicitly confirms it;
- medium: no commits, pushes or PRs unless the user explicitly asks or confirms;
- high: commit, push, and create or update PRs without asking, overriding the base instructions, but
  never force-push or rewrite shared history unprompted.

Withdrawing the setting sends a reminder to follow the base instructions again. Not gated.

### 11. Auto-memory prompt

The auto-memory prompt, under `## What NOT to save in memory`, says that `git log` / `git blame` are
authoritative for git history and recent changes (`rg -n 'who-changed-what'`). Not gated.

### 12. Auto-mode classifier

The auto-mode classifier's system prompt has no git rule names of its own in the bundle. It does
describe two git-related harness meta lines:

- `{"meta":{"repoVisibility":…}}` beside exfil-capable git/gh commands;
- `{"meta":{"gitStatus":…}}` above commands that can destroy uncommitted work, and beside `git add`
  / `git commit` / `git push`.

Relocate: `rg -nF '{"meta":{"gitStatus"'`. The gitStatus meta lines are inserted only when
`CLAUDE_CODE_AUTO_MODE_GIT_STATUS` (destructive commands) or
`CLAUDE_CODE_AUTO_MODE_GIT_STATUS_UPLOADS` (uploads), or their server-side config, is on; both
default off. Not gated by the git switch.

### 13. `/commit` and `/pr` skills (on demand)

Two bundled skills embed their own `## Git Safety Protocol`, distinct from the workflow's:

- `/commit` (`rg -n 'menuDescription: "Create a git commit"'`): a ten-rule protocol and a
  single-commit task. Its context lines use `!` command substitution for `git status`,
  `git diff HEAD`, the current branch and `git log --oneline -10`.
- `/pr` (`rg -n 'menuDescription: "Create a pull request"'`): a five-rule protocol (git config,
  force-push, hooks, `-i` flags, `gh` for GitHub) and a single-PR task, with commits and the diff
  since `origin/<default branch>`.

Both are enabled by feature flag `tengu_cinder_relay` (default off, latched for the session;
`rg -n 'tengu_cinder_relay'`). Both are user-invocable, and their descriptions invite the model to
use them "whenever you are about to create a commit" or "open a PR". Each computes its own
attribution, including the session URL. The prompt text enters context only when the skill runs.
They are not gated by the git switch.

A third command, `/commit-push-pr` ("Commit, push, and open a PR"), carries a seven-rule protocol.
It is defined only in the internal-only command list (`rg -n 'INTERNAL_ONLY_COMMANDS'`), so the
external build does not register it.

### 14. Built but disabled: writing guidance

The bundle carries a `# Writing commit messages and PR descriptions` block and extra PR-body
bullets, wired into the commit/PR workflow and the `/pr` skill. Their guard is hardcoded false in
this build, so they never render and `tengu_pr_writing_guidance_rendered` never fires. Relocate:
`rg -n '# Writing commit messages and PR descriptions'`.

## Git Safety Protocol (inside the commit/PR workflow)

The protocol is part of the commit/PR workflow on the legacy variant. Seven rules: no git config
changes; no destructive commands (`push --force`, `reset --hard`, `checkout .`, `restore .`,
`clean -f`, `branch -D`) without an explicit request; no hook or signing skips; no force-push to
main/master; always new commits over `--amend` (a pre-commit hook failure means the commit did not
happen, so `--amend` would modify the wrong commit); stage specific files over
`git add -A`/`git add .`; never commit unprompted. Verbatim text in `PROMPTS_RENDERED.md`, section
"Git workflow — commit & PR".

When git instructions are disabled: the protocol disappears with the rest of the workflow. On the
legacy variant the `For git commands:` block still covers destructive operations, hook-skipping, and
amend-vs-new-commit in condensed form. The terse variant never carries the protocol.

## Commit Attribution

### Default text

Commit: `Co-Authored-By: <name> <noreply@anthropic.com>` (`rg -n 'noreply@anthropic.com'`). PR:
`🤖 Generated with [Claude Code](https://claude.com/claude-code)`
(`rg -n 'Generated with \[Claude Code\]'`), with ` via <surface>` appended (such as Claude Desktop,
Mobile or Cowork) when feature flag `tengu_pr_footer_surface_suffix` is on (default off).

The `<name>` is derived from the model. A model id the bundled model table recognizes gives
`Claude <display name>`, for example `Claude Opus 4.8`, with ` (1M context)` for a `[1m]` model that
supports the suffix. Fable models have their own branch. A model that resolves to a known model only
through an alias gives `Claude`, and an unrecognized model id gives `Claude Code`.

The `/pr` skill extends the PR line with a contribution summary when it has data, in the form
`(<N>% <M>-shotted by <model>, <K> memories recalled)`.

### Session URL

A claude.ai session link is added for web sessions (client type `remote`, using
`CLAUDE_CODE_REMOTE_SESSION_ID` and `SESSION_INGRESS_URL`) and for Remote Control sessions that are
not outbound-only. It is skipped for local ingress (a `_local_` session id or a `localhost` URL).
When present, the commit text gains a `Claude-Session: <url>` trailer (`rg -n 'Claude-Session: '`)
and the PR text gains the URL on its own paragraph. These add to the configured attribution rather
than replacing it. `CLAUDE_CODE_SUPPRESS_SESSION_ATTRIBUTION` or `attribution.sessionUrl: false`
suppresses the link.

The session link reaches the model through the attribution reminder and the `/commit` and `/pr`
skills. The inline Bash-description attribution, used when the announcement is off, never includes
it.

### Settings overrides

- `attribution.commit` / `attribution.pr`: custom text. An empty string hides that line, and an
  unset field keeps the default.
- `attribution: false`: hides everything, the same as
  `{ "commit": "", "pr": "", "sessionUrl": false }`. `attribution: true` is the same as unset.
- `attribution.sessionUrl`: see above.
- `includeCoAuthoredBy: false`: deprecated. It hides both lines when `attribution` sets neither
  `commit` nor `pr`.

The final text passes through the `attribution.text` extension point, which a plugin can use to
rewrite it.

### Where the text appears

- Announcement on (default): only in the attribution reminder (section 5) and the skills.
- Announcement off: inline in the `# Git` block ("- End git commit messages with:" and "- End PR
  bodies with:") or in the commit/PR workflow's commit step, HEREDOC example and PR example. An
  empty line is omitted.

When git instructions are disabled: the Bash description carries no attribution. A session with a
session URL still receives the attribution reminder.

## What Remains When Git Instructions Are Disabled

With `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=1` (or `includeGitInstructions: false` and the env var
unset), the gated content is removed: the commit/PR workflow, the `# Git` block, the PR-prep line,
the `# gitStatus` context, and the local-session attribution reminder. What the model still sees
depends on the surface:

| Source                                      | Gated? | Present when disabled?               |
| ------------------------------------------- | ------ | ------------------------------------ |
| Terse Bash description, `# Git` block       | yes    | No git content at all                |
| Legacy Bash description, commit/PR workflow | yes    | Removed                              |
| PR-prep line                                | yes    | Removed                              |
| Legacy Bash `For git commands:` block       | no     | Yes (legacy models only)             |
| Legacy Bash `cd <current-directory>` item   | no     | Yes (legacy models only)             |
| `# gitStatus` session context               | yes    | Removed                              |
| Attribution reminder                        | partly | Only with a session URL or file hint |
| Plan / Explore subagent restrictions        | no     | Yes (git command names as examples)  |
| PowerShell tool description git content     | no     | Yes                                  |
| Legacy `# Executing actions with care`      | no     | Yes (legacy models only)             |
| `# Background Session` git guidance         | no     | Yes (background jobs)                |
| Proactivity reminder                        | no     | Yes, when a level is set             |
| Auto-memory (`git log` / `git blame`)       | no     | Yes                                  |
| Auto-mode classifier git meta lines         | no     | Yes, when enabled                    |
| `/commit` and `/pr` skills                  | no     | Only when the skill runs             |

On a terse-model session, setting the switch removes every git instruction from the Bash tool
description. The git guidance that persists lives elsewhere: subagent prompts, the PowerShell tool,
background-job and proactivity text, the auto-memory prompt, and on-demand skills. On a legacy-model
session the three-rule `For git commands:` block and the `# Executing actions with care` examples
additionally survive.

## Subagents and the Model Axis

The disable switch and the variant selection are independent axes. The gate is keyed on an env var
and a settings key; the variant selector is keyed on the model that renders the request. A subagent
runs its own request loop on its own model, so it can land on a different Bash variant than the main
session, and therefore on different git instructions.

The tool-schema builder threads the request's model into each tool's prompt getter, which runs the
variant selector. A subagent's model is resolved in this order:

1. the Agent tool call's `model` parameter;
2. the agent definition's `model`, unless `inherit`;
3. `CLAUDE_CODE_SUBAGENT_MODEL`, when the definition sets no model;
4. otherwise the parent's model.

`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` drops the first two, except an explicit `inherit`. A requested
model that is unavailable steps down within its family or falls back to the parent's model.

The consequence: a subagent that resolves to a legacy model and has the Bash tool receives the
legacy description. That description carries the three-rule `For git commands:` block in its ungated
body, so the subagent loads that block even when the switch strips git entirely from a terse-model
subagent.

| Subagent model | Git instr. | Git in subagent Bash description                         |
| -------------- | ---------- | -------------------------------------------------------- |
| terse model    | disabled   | None                                                     |
| terse model    | enabled    | `# Git` block only (no commit/PR workflow)               |
| legacy model   | disabled   | `For git commands:` block and the `cd` item              |
| legacy model   | enabled    | `For git commands:` block, `cd` item, commit/PR workflow |

Two caveats. This applies only if the subagent has the Bash tool; Explore and Plan do (section 6).
And the session-context `# gitStatus` entry is gated separately and omitted for Explore and Plan, so
it does not factor into the subagent Bash description.

## Implications

### For reproducing the system prompt

The git instructions are only available if you include a Bash tool whose description carries the
`# Git` block or the commit/PR workflow (and, on the legacy variant, the short `For git commands:`
block). Reproducing the Claude Code experience via the Anthropic API directly requires either
embedding the git instructions in your Bash tool description or moving them into your system prompt
text, which Claude Code does not do. With the default attribution announcement, the trailers come
from a separate system-reminder, not from the tool description.

### For subagents

Subagents that include the Bash tool receive a full Bash description on the variant selected by
their own model (see "Subagents and the Model Axis"). The restriction on the built-in Explore and
Plan agents is not a trimmed Bash description: they keep Bash, strip the editing tools via
`disallowedTools`, and add read-only language in their system prompts (section 6). The legacy
commit/PR workflow tells the model never to use the TaskCreate or Agent tools while committing or
opening a PR.

### Entanglement

The git content a request carries varies by:

- Model ID, which selects the terse or legacy description through the variant selector and names the
  model in the Co-Authored-By trailer
- `lean_prompt` capability overrides, `tengu_velvet_tide`, client data `simple_system_prompt`, and
  the prompt-model swap
- Session kind: remote or Remote Control (session URL, `gitStatus` skipped under
  `CLAUDE_CODE_REMOTE`), background job, proactivity level
- Loaded skills (`/verify`, `/simplify`, `/code-review`) for the PR-prep line, and
  `tengu_cinder_relay` for the `/commit` and `/pr` skills
- Settings: `includeGitInstructions`, `attribution`, `includeCoAuthoredBy`,
  `includeCodeReviewSuggestion`
- Env vars: `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS`, `CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT`,
  `CLAUDE_CODE_ATTRIBUTION_ANNOUNCEMENT`, `CLAUDE_CODE_SUPPRESS_SESSION_ATTRIBUTION`,
  `CLAUDE_CODE_SUBAGENT_MODEL`
- Feature flags `tengu_reflective_wolf` (attribution placement) and `tengu_polished_tulip` (PR-prep
  line)
