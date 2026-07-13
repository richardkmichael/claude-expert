# Auto Mode and the Bash Command Classifier

Verified against: cli.prettier.js 2.1.198 (2026-07-02)

Two independent "classifiers" gate what a Bash command is allowed to do. They are easy to conflate,
so this doc separates them:

1. The destructive-command classifier — a deterministic regex table (`B4i`/`o6e`/`Zce`). It labels a
   command with a `category`, a human `warning`, and a refined "target". It makes no allow/deny
   decision; it feeds telemetry and the auto-mode allowlist.
2. The auto-mode security classifier — an LLM ("You are a security monitor for autonomous AI coding
   agents.") that reads the conversation transcript and returns `<block>yes|no</block>`. This is the
   one that actually blocks `git commit --amend`, `git reset --hard`, `terraform destroy`, and the
   rest when the session is in auto mode.

The 2.1.183 changelog line about amend/reset/clean/stash and `*destroy` being blocked describes
rules inside classifier 2, not classifier 1.

Every `rg -n '…'` recipe below targets the prettified bundle: `work/<version>/package/cli.prettier.js`
(e.g. `work/2.1.198/package/cli.prettier.js`). Classifier 2 only runs in auto mode — `Pgc` is true
only for `mode === "auto"` (or `plan` with auto active). In default/acceptEdits/bypassPermissions an
"ask" decision goes to the normal user permission prompt and this classifier never runs, so the amend
block below cannot occur outside auto mode.

## Layer 1: the destructive-command classifier (regex table)

Relocation: `rg -n 'git_commit_amend|Note: may rewrite the last commit'`. The enclosing module builds
an array of `{pattern, category, warning}` entries (minified `i5d`). `B4i(command)` truncates to the
first 10k chars, walks the table, and returns the first match (or null); `r6e` returns just the
`category`, `$4i` just the `warning`.

The category set is version-stable — grep any of these to relocate the table:

| category                | example trigger                          | warning fragment                          |
| ----------------------- | ---------------------------------------- | ----------------------------------------- |
| `git_reset_hard`        | `git reset --hard`                       | may discard uncommitted changes           |
| `git_force_push`        | `git push --force` / `-f`                | may overwrite remote history              |
| `git_clean_force`       | `git clean -f` (not `-n`/`--dry-run`)    | may permanently delete untracked files    |
| `git_checkout_dot`      | `git checkout -- .`                      | may discard all working tree changes      |
| `git_restore_dot`       | `git restore .`                          | may discard all working tree changes      |
| `git_stash_drop`        | `git stash drop` / `clear`               | may permanently remove stashed changes    |
| `git_branch_force_delete`| `git branch -D` / `--delete --force`    | may force-delete a branch                 |
| `git_no_verify`         | `git commit/push/merge --no-verify`      | may skip safety hooks                     |
| `git_commit_amend`      | `git commit … --amend`                   | may rewrite the last commit               |
| `rm_recursive_force`    | `rm -rf`                                 | may recursively force-remove files        |
| `rm_recursive`          | `rm -r`                                  | may recursively remove files              |
| `rm_force`              | `rm -f`                                  | may force-remove files                    |
| `sql_drop_truncate`     | `DROP/TRUNCATE TABLE`                    | may drop or truncate database objects     |
| `sql_delete_from`       | `DELETE FROM <table>`                    | may delete all rows from a database table |
| `kubectl_delete`        | `kubectl delete`                         | may delete Kubernetes resources           |
| `terraform_destroy`     | `terraform destroy`                      | may destroy Terraform infrastructure      |

Two follow-up refiners turn a category into a finer "target", used only for telemetry:

- `o6e(command, category)` handles the git set (the `g5d` Set: force_push, reset_hard,
  branch_force_delete, commit_amend). For `git_commit_amend` it returns `no_edit` (`--no-edit`),
  `with_message` (`-m`/`--message`), or `interactive`. For `git_reset_hard` it returns `bare`,
  `head_relative`, `remote_ref`, or `other`. For force-push/branch-delete it returns `main_like` vs
  `feature` (via the protected-branch regex — `main|master|develop|trunk|release*|prod*|staging`).
- `Zce(command, cwd, category)` handles the `rm`/PowerShell-remove set (`u5d`) and returns whether
  the deletion targets are `cwd`, `tmp`, `outside_cwd`, `mixed`, or `unknown`.

Where the labels go: `rg -n 'git_destructive_target|destructive_category|destructive_target_scope'`.
Every hit is a telemetry payload (`tengu_bash_tool_command_executed`, `_command_failed`, and the
permission-grant/deny events) or the auto-mode allowlist check. Tripwire: none of these call sites
returns an allow/deny; the label is metadata only. If a future version routes a category straight to
a deny, that is a real behavior change worth recording.

## Layer 2: the auto-mode security classifier (LLM)

### When it can run at all

Auto mode is a permission mode (`mode: "auto"`) parallel to `default`/`acceptEdits`/`plan`/
`bypassPermissions`. Availability is gated by four things — relocate with `rg -n 'auto mode is
unavailable for your plan|CLAUDE_CODE_ENABLE_AUTO_MODE'`:

- Settings: `disableAutoMode: "disable"` (top-level or under `permissions`) forces it off.
- Circuit breaker: `isAutoModeCircuitBroken()` (set from the `tengu_auto_mode_config.enabled ===
  "disabled"` gate). Surfaced to the user as "auto mode is unavailable for your plan".
- Provider opt-in: non-first-party providers require `CLAUDE_CODE_ENABLE_AUTO_MODE=1`.
- Model support: the current model must be in the auto-mode-capable set.

`tengu_auto_mode_config` (a feature-gate/GB blob) carries most tuning: `enabled`
(`enabled`/`disabled`/`opt-in`), `twoStageClassifier` (`fast`/`thinking`/both), model overrides,
`maxRetries`, `priorAssistantContext`, `jsonlTranscript`, `outcomeVisibility`.

### Where it sits in the permission pipeline

Relocate with `rg -n 'Skipping auto mode classifier|Auto mode classifier blocked action'`. For each
tool call in auto mode:

1. A per-tool "allowlist" short-circuit (`isAutoModeAllowlistedTool`) skips the classifier for
   provably safe tools/commands. Bash `git commit --amend` is not allowlisted.
2. Otherwise the classifier core (`ASt`) runs, returning `{shouldBlock, reason, …}`.
3. `shouldBlock` true → deny with `decisionReason {type:"classifier", classifier:"auto-mode",
   reason}`; the agent sees the reason plus "run with --debug for details". Blocked-and-unavailable
   are distinguished (see fail-closed below).

The classifier is invoked identically from the main loop and from inside subagents; the difference
is entirely in what transcript it is handed (next section).

Runtime shape — this is the point most mental models get wrong. The classifier is a second,
independent `/v1/messages` call the CLI makes client-side, between the main model emitting a
`tool_use` and the CLI executing it. It is not the agent reconsidering its own move. Two calls per
gated tool use:

- Call 1 (main turn): system = the agent's own system prompt; messages = the agent's real turns;
  output = assistant text + the `tool_use` to run.
- Call 2 (classifier): system = the security-monitor prompt (`sQn`) + rule template; messages = the
  conversation rendered to text and wrapped in `<transcript>…</transcript>` with the pending action
  appended as the last entry; `querySource: "auto_mode"`, usually a different (classifier) model;
  output = `<block>yes|no</block>` + `<reason>`.

`ASt`/`FSm` build Call 2: `Dyl` renders each history entry to text, they are concatenated into one
`<transcript>` block (not replayed as real alternating turns), and the pending tool call is pushed
last. `block=yes` → the CLI denies the tool call (the agent gets a blocked tool_result, surfaced as
`automode-blocked`); `block=no` → the CLI runs the command. Because Call 2 carries its own system
prompt and only the rendered transcript, the agent's own system prompt from Call 1 (e.g. a custom
subagent definition) never reaches the classifier.

### What the classifier is told

System prompt: `rg -n 'You are a security monitor for autonomous AI coding agents'` (minified
`sQn`). It defines HARD BLOCK (security boundaries, never cleared by user intent), SOFT BLOCK
(destructive/irreversible, clearable by explicit user intent), ALLOW exceptions, the User Intent
Rule (10 numbered rules), Evaluation Rules, Classification Process, and the `<block>`/`<reason>`
Output Format. The verbatim text is generated into `PROMPTS_RENDERED.md` (anchors "Auto-mode
classifier — …"); regenerate with `python3 bin/render-prompts.py <version>`.

Input framing (inside the system prompt): the conversation is wrapped in `<transcript>` and the
action to judge is "the agent's most recent action (the last entry in the transcript)". The last
message is the pending tool call; everything before it is context/evidence.

Rule-template population (`ISm`, minified). The `sQn` body is a scaffold with placeholders; the CLI
fills them per call:

- `<permissions_template>` ← the big rules template (`rg -n 'Three kinds of slot'`, minified `uyl`,
  parsed to `IPo`) when `bSt()` is true (default); when false it becomes empty (`dSm`, `""`).
- The four `<user_*_rules_to_replace>` blocks — `allow`, `soft_deny`, `hard_deny`, `environment` —
  are each replaced by `TSt(custom, defaultText)`. The name is literal: the user's configured rules
  *replace* the built-in defaults for that block. `custom` comes from the `autoMode` key in settings,
  merged by `Qte()` across `gPs` = `userSettings`, `localSettings`, `flagSettings`, `policySettings`.
  The checked-in project `.claude/settings.json` is deliberately absent from that list, so a cloned
  repo cannot weaken the classifier — only `~/.claude/settings.json`, `.claude/settings.local.json`,
  `--settings`, or managed policy feed it. Each key (`autoMode.{allow,soft_deny,hard_deny,environment}`)
  is an array of rule strings. With no custom rules the default block text stays. With custom rules the
  defaults are dropped unless the array includes the sentinel `"$defaults"`, which splices the built-in
  block back in at that position (so `["$defaults", "…my rule…"]` appends; `["…my rule…"]` replaces).
  `$defaults` is atomic: `ySt` re-inserts the whole default block once (even if several scopes repeat
  the sentinel), with no per-rule granularity — there is no way to keep `$defaults` and drop a single
  default rule. To edit or remove one default rule you omit `$defaults` and re-list the rest of that
  block yourself (pull the exact text with `claude auto-mode defaults | jq -r '.soft_deny[]'` — a real
  CLI subcommand), which forks the block and forgoes future default additions. `soft_deny`/`hard_deny`
  only tighten (they add block rules); to *relax* a soft block, add an `autoMode.allow` exception
  rather than editing `soft_deny`, since an ALLOW exception clears a matching SOFT BLOCK.
- `<settings_deny_rules>` ← a note derived from the permission-context `alwaysDenyRules` (`EPo`),
  telling the classifier to catch tool-switching around those deny rules.
- `<cross_session_messages_rule>` ← `""` in single-session use (populated only in multi-session).

The classifier request payload (Call 2), built by `ASt`/`FSm` — it is not "just the command and the
security prompt":

- `system` = the assembled `sQn` prompt above, plus a "## Session Context" note with the resolved
  user identity (`kSm()`), cache-controlled.
- `messages` = at most two user messages: (1) an optional message carrying the user's `CLAUDE.md`
  (`wSm()` — "The following is the user's CLAUDE.md configuration…"; omitted when there is none). The
  wrapper weighs CLAUDE.md as intent only when it explicitly authorizes the SPECIFIC action under
  review — same operation, same target; it names generic grants ("be autonomous", "don't ask", "I
  trust you") and states they are not authorization and must not lower the block threshold. So a
  standing CLAUDE.md line cannot clear a per-target rule like Git Destructive, whose target (which
  commit) varies per action. Then (2) one user message whose content is the whole loop transcript
  rendered to text and wrapped
  in `<transcript>…</transcript>` with the pending tool call appended as the final entry, followed by
  a short stage-specific instruction suffix (`OSm`/`LSm`).
- There are no assistant-role messages and no real turn structure — the history is quoted evidence
  text (tool calls as `Name {json}`, user/assistant turns, `outcome` lines), not replayed turns.

Transcript construction: `Hyl(messages, includePriorAssistant, recordTelemetry)` (minified) turns the
loop's messages into classifier-format entries. Genuine user turns are counted only when they have no
`origin` (teammate/peer/channel/task-notification messages are tagged and do not count as user
intent). Tool calls and their `outcome` lines are always included; assistant prose text is included
only when `includePriorAssistant` is set.

`includePriorAssistant` = `!isSubagentLoop && priorAssistantContext`. `priorAssistantContext`
(env `CLAUDE_CODE_AUTO_MODE_PRIOR_ASSISTANT_CONTEXT`, or `tengu_auto_mode_config`) defaults off, so
by default assistant prose is excluded everywhere and the flag matters only when explicitly enabled —
in which case it is still forced off inside subagents.

### Decision, staging, fail-closed

Parse: `rg -n '<block>|Blocked by fast classifier'`. The model must emit `<block>yes</block>` or
`<block>no</block>` (`vPo` reads the first match; `<thinking>` is stripped first) and a `<reason>`.
Two stages (`twoStageClassifier`): a `fast` stage-1 pass can allow immediately on `no`; ambiguous or
risky cases escalate to a `thinking` stage-2 pass.

Fail-closed outcomes (`rg -n 'automode-blocked|automode-unavailable|automode-parsing-error'`):

- `automode-blocked` — the classifier actively denied.
- `automode-unavailable` — classifier unreachable; the call is held back fail-closed with retry
  guidance ("Auto mode could not evaluate this action…"). Not a policy decision.
- `automode-parsing-error` — response unparseable; also held back fail-closed.
- Transcript too long: for the Agent tool specifically the action is allowed; otherwise it falls back
  to a normal permission prompt (or denies in headless `dontAsk`).

Outcome telemetry: `tengu_auto_mode_decision` (decision allowed/blocked/unavailable) and
`tengu_auto_mode_outcome` (classifier success/error/parse_failure), plus per-stage token/cost fields.

### Classifier model

The classifier call does not hardcode a model. It is resolved by `Eyl`/`Fyl` (`rg -n 'modelByMainModel'`)
in this precedence, keyed off the current main-loop model:

1. `tengu_auto_mode_config.modelByMainModel[mainModel]` (with a `[1m]` long-context variant lookup).
2. else `tengu_auto_mode_config.model` (a fixed override).
3. else, for certain model classes, a default derived by `x1t` — `ANTHROPIC_DEFAULT_OPUS_MODEL`, else
   the resolved default Opus model (`opus48`), with a `[1m]` variant when the main model is
   long-context.
4. else the main-loop model itself.

So the concrete model id comes from the server-pushed `tengu_auto_mode_config`; absent that config it
heads toward the default Opus model or reuses the main model. Both two-stage passes (fast, thinking)
use the same model; a separate `fallbackModelByModel` model is tried if the primary is unavailable
and time remains. Note: the env var `CLAUDE_CODE_AUTO_MODE_MODEL` is declared in the env schema but
has no read site in this version — it does not override the classifier model.

### Environment variables

All auto-mode env vars override the matching `tengu_auto_mode_config` key when set (env → GB config →
default). Relocate with `rg -n 'CLAUDE_CODE_AUTO_MODE'`.

| Env var                                        | Effect on the classifier                                                  | Default |
| ---------------------------------------------- | ------------------------------------------------------------------------- | ------- |
| `CLAUDE_CODE_ENABLE_AUTO_MODE`                 | Opt-in required for non-first-party providers before auto mode is offered | off     |
| `CLAUDE_CODE_AUTO_MODE_TEMPERATURE`            | Classifier sampling temperature (`byl`)                                   | 1       |
| `CLAUDE_CODE_AUTO_MODE_PRIOR_ASSISTANT_CONTEXT`| Include prior assistant prose + the "referent" prompt note (`cSm`)        | off     |
| `CLAUDE_CODE_AUTO_MODE_SIBLING_CONTEXT`        | Include same-turn sibling tool_uses in the transcript (`b7o`/`Hhf`)       | off     |
| `CLAUDE_CODE_AUTO_MODE_OUTCOME_CODES`          | Emit `outcome`/`id` codes in the rendered transcript (`_1e`)              | off     |
| `CLAUDE_CODE_AUTO_MODE_EDIT_REMOVAL`           | Add the "EDIT REMOVALS" evaluation rule (`SGe`)                           | off     |
| `CLAUDE_CODE_AUTO_MODE_EDIT_REMOVAL_CAP`       | Cap on shown removed-edit text (`x8t`)                                    | 3000    |
| `CLAUDE_CODE_CHILD_SESSION`                    | Forces `isSubagentLoop` true (transcript treated as a subagent's)         | unset   |
| `ANTHROPIC_DEFAULT_OPUS_MODEL`                 | Feeds the default classifier-model derivation (`x1t`)                     | unset   |

Two more are declared in the env schema but have no read site in this version, so they are inert:
`CLAUDE_CODE_AUTO_MODE_MODEL` (string) and `CLAUDE_CODE_AUTO_MODE_EXTERNAL_PERMISSIONS` (bool).
Separate, related surfaces: `CLAUDE_CHROME_CLASSIFIER_FLOOR` / `CLAUDE_PREVIEW_CLASSIFIER_FLOOR`
force the classifier floor for Chrome-MCP / preview tools (a different auto-mode path, not the git
gate). Tripwire: if a later version wires `CLAUDE_CODE_AUTO_MODE_MODEL` into `Fyl`, that is a real
change — re-check the read site.

## Subagents and the classifier

`isSubagentLoop` is computed by `x3e(agentId)` — relocate with `rg -n 'isSubagentLoop'`. It is true
when any of: an `agentId` is present (a Task/Agent-tool subagent), `isTeammate()`, or
`CLAUDE_CODE_CHILD_SESSION` is set.

The load-bearing fact: a subagent evaluates the classifier against its own isolated message history,
which begins at the delegation prompt. A fresh (non-fork) subagent seeds its messages as a single
plain `{role:"user"}` message holding the task prompt, with no `origin` and no parent messages
prepended (parent messages are carried over only for `subagent_type:"fork"`). So the classifier's
"this session" is the subagent's transcript, not the whole run. Anything the parent agent did before
delegating — including a `git commit` — is invisible to the subagent's classifier.

Two secondary effects for subagents: `includePriorAssistant` is forced off (assistant prose stripped,
already the default), and the system-prompt variant that treats prior assistant prose as the likely
referent for a bare "ok"/"yes" is omitted.

## Why `git commit --amend` gets blocked in the git-wright subagent (the 2.1.183 change)

The relevant SOFT BLOCK rule — `rg -n 'Git Destructive'` in the bundle — reads (paraphrased from the
verbatim template):

> `git commit --amend` is blocked when the commit being rewritten is not the agent's own unpushed
> work: either no prior `git commit` is visible (HEAD pre-dates the session), or a `git push` of the
> current branch is visible after the most recent commit. Clears when the user asked to
> amend/reword/fixup, or when it is a message-only reword (`--amend -m …`, nothing newly staged) of a
> commit the agent visibly created this session.

Combine that with subagent transcript isolation and the failure is mechanical:

- git-wright's classifier sees only the subagent transcript: the delegation prompt plus git-wright's
  own tool calls. A commit the main agent made before delegating does not appear.
- If git-wright is asked to amend that pre-existing commit, "no prior `git commit` is visible" holds
  from the classifier's vantage → the rule reads it as rewriting a commit that "pre-dates the
  session" → SOFT BLOCK.
- The clearing paths do not fire: the delegation prompt (git-wright's only "user" message) typically
  says "commit"/"clean up history", not literally "amend/reword/fixup"; and there is no prior
  `git commit` by git-wright in-transcript to satisfy "a commit the agent visibly created this
  session".

The block is genuinely absent when git-wright makes the commit itself and then amends it in the same
run — that `git commit` is in its own transcript, so the rule's precondition ("not the agent's own
unpushed work") is false and the amend is allowed. The problem is amending a commit that predates the
subagent.

Ways to clear it, ranked by reliability:

- Take the amend out of auto mode. The classifier only runs in auto mode; a normal permission prompt
  (or existing allow rules) governs the amend otherwise. Most reliable and needs no change to how the
  work is delegated.
- Edit the classifier's rules through `autoMode` settings — the supported config surface, and the only
  lever that changes the rule itself instead of arguing intent past it. Relaxing a soft block goes in
  `autoMode.allow` (the exception list), not `soft_deny` (the block list — an "X is allowed…" entry
  there is inert, and the default Git Destructive rule kept by `$defaults` keeps firing). Word the
  exception authorship-agnostically: a carve-out about "the agent's own commits" is useless here, since
  the blocked case is rewriting commits that predate the subagent or that others authored. A working
  shape is `["$defaults", "Git History Cleanup: arbitrarily rewriting git history with rebase or amend
  is permitted, including sequence and commit message subject/body."]`, which clears the amend/local-
  rebase block. It does not by itself clear the force-push that publishing a rewrite of an already-
  pushed branch needs: the ALLOW intro says exceptions do not extend "to force-pushing over commits the
  agent didn't author," so name force-push explicitly if the publish step is needed, and expect it to
  still be judged strictly on shared/default branches. For a deterministic removal instead of an
  LLM-judged exception, fork `autoMode.soft_deny` (omit `$defaults`, re-list the block without Git
  Destructive's rewrite clause). Two hard limits on any such rule: it is read for every gated call
  regardless of which agent triggered it (merged from user/local/flag/policy settings by `Qte()`, never
  the checked-in project `.claude/settings.json`), so it applies to every agent in that settings scope,
  not git-wright alone; and it cannot name the agent — the classifier input carries no agent name or
  type (Session Context `kSm` is user identity only, the entry renderer `Pyl`/`Dyl` labels entries by
  role and content type, and the agent definition never reaches the classifier), so "git-wright" binds
  to nothing. The only git-wright-specific text the classifier sees is the delegation prompt (its first
  user message); keying a rule off a phrase that always appears there is the closest handle, and it is
  brittle. Put the rule in `~/.claude/settings.json` (all projects) or `.claude/settings.local.json`
  (this project); base wording on `claude auto-mode defaults`.
- Let git-wright create the commit it will amend, so the `git commit` sits in git-wright's own
  transcript and the rule's precondition ("not the agent's own unpushed work") is false. Reliable
  when the workflow allows it; it does not help when the job is to amend a pre-existing commit.
- Make the delegation prompt name the action ("amend the last commit to fix X"). The subagent's task
  prompt is its only user turn, so an explicit, targeted amend request there is read as user intent
  and can satisfy "the user asked to amend". This is the weakest lever, for three reasons. It is
  composed by the parent agent when it calls the Agent tool, not authored directly by the human, so
  you can only nudge the wording. A standing capability grant ("you are permitted to amend previous
  commits") is generic pre-authorization, which the classifier is explicitly instructed to discount
  ("Generic encouragement … is not authorization"); a specific request naming the target is the
  stronger form. And the pass/fail is a non-deterministic LLM judgment regardless.

  Putting the grant in the git-wright agent definition (`git-wright.md`) does nothing: the definition
  becomes the subagent's `systemPrompt` (P4 runs `EF({ messages, systemPrompt })` with the definition
  in `systemPrompt`, separate from `messages`), and the classifier builds its `<transcript>` from
  `messages` only while using its own security-monitor system prompt. It never sees the agent
  definition. Subagent assistant prose is stripped too, so git-wright cannot self-justify in prose. A
blanket grant in `CLAUDE.md` (`git-wright may rewrite all history`) does reach the classifier — it is
`messages[0]` via `wSm()` — but the wrapper counts CLAUDE.md as intent only when it names the specific
operation and target, and is told to discount generic grants, so it is ignored for the same reason a
standing authorization is.

This is a design consequence, not a bug in the classifier: the classifier deliberately trusts only
what it can see in the transcript it is given, and a subagent's transcript is scoped to the subagent.

## Tripwire checklist (re-verify against a new bundle)

- □ `B4i`/`i5d` table still returns `{pattern, category, warning}` and makes no allow/deny decision.
- □ `git_commit_amend` category and "may rewrite the last commit" warning still present.
- □ `o6e` for `git_commit_amend` still returns `no_edit`/`with_message`/`interactive` (telemetry
  only).
- □ System prompt still opens "You are a security monitor for autonomous AI coding agents."
- □ Decision still parsed from `<block>yes|no</block>`; `<transcript>` still wraps the evidence.
- □ `isSubagentLoop` still true for agentId present / teammate / `CLAUDE_CODE_CHILD_SESSION`.
- □ Non-fork subagent still seeds messages from the task prompt only (no parent messages).
- □ "Git Destructive" amend rule still clears on explicit amend/reword/fixup request or an
  agent-visible session commit.
- □ `autoMode` still merges from `gPs` = `userSettings`/`localSettings`/`flagSettings`/`policySettings`
  only (checked-in `projectSettings` excluded); `$defaults` still atomic (`ySt` splices once); the
  classifier input still carries no agent name/type (Session Context = user identity only).

## Dated appendix

- 2.1.183: SOFT BLOCK rules tightened. `git reset --hard`, `git checkout -- .`, `git clean -fd`,
  `git stash drop` blocked when the user did not ask to discard local work; `git commit --amend`
  blocked when the commit was not made by the agent this session; `terraform/pulumi/cdk destroy`
  blocked unless the user named the specific stack. In subagents "this session" is the subagent's own
  transcript, which is why git-wright amends of pre-delegation commits began being blocked.
- 2.1.198: verified. Two-stage classifier (fast/thinking), `<block>`/`<reason>` parse,
  `tengu_auto_mode_config` tuning, `isSubagentLoop` via `x3e`, transcript isolation for non-fork
  subagents all as described above. Rule-config surface documented:
  `autoMode.{allow,soft_deny,hard_deny,environment}` merged by `Qte()` over `gPs`
  (`userSettings`/`localSettings`/`flagSettings`/`policySettings`, checked-in project settings
  excluded), `$defaults` atomic splice via `ySt`/`TSt`, the `claude auto-mode defaults` CLI, no
  agent-name/type in the classifier input, and the CLAUDE.md intent wrapper (weighed only on a specific
  operation+target match; generic grants discounted). The `claude auto-mode` command exposes
  `defaults`/`config`/`critique` subcommands, and `autoMode.classifyAllShell` (read over `gPs`) routes
  every shell command through the classifier. The official reference page
  `code.claude.com/docs/en/auto-mode-config` matches the source on scopes (project settings excluded),
  the `$defaults` splice, and the `hard_deny` > `soft_deny` > `allow` > explicit-intent precedence; it
  does not spell out the CLAUDE.md wrapper's generic-grant discount (it gives only the tightening
  example "never force push") or the absence of any agent-name signal.
