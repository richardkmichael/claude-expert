# Claude Code Git Usage in System Prompts

Source: `cli.prettier.js` 2.1.154 (`work/2.1.154/package/cli.prettier.js`)

## Key Finding

The git behavioral instructions are carried by the Bash tool's `description` field, not the main
system prompt. The exact content depends on which Bash-description variant the running model
receives, and that variant determines what survives the disable switch.

This means git instructions are invisible if you only examine the system prompt text; they are
embedded in the tool definition passed via the `tools` API parameter.

### Change since 2.1.104

Two things changed structurally:

- The Bash tool description now has two variants, selected per-model by `Dz()` (the "simple
  system prompt" decision). The terse variant `gU3()` is used for current models (Opus 4.8); the
  legacy variant `tWK()` is used for older models (Sonnet, Haiku, Opus ≤ 4.7).
- The git workflow text split into two functions: `UU3()` (the commit/PR workflow, formerly the
  bulk of `Wr4()`) and a new `FU3()` "# Git" block. Both are gated by the disable switch.

The behavioral consequence is the headline change: on the terse variant, the short three-rule git
block no longer survives the disable switch. In 2.1.104 the "For git commands:" block lived in the
ungated body of the Bash description and always survived. On Opus 4.8 that block is gone entirely;
the only git content in its Bash description is the gated `FU3()` "# Git" section, so disabling the
switch removes all git instructions from the Bash description. The legacy variant still carries an
ungated "For git commands:" block (see section 5).

## The Disable Switch -- `tD_()`

The switch function was renamed from `oR8()` to `tD_()` (line 261058) but the logic is unchanged:

```js
[source fragment removed]
```

The truthy/falsy helpers were also renamed (`F6` -> `xH` at line 1901, `q_` -> `VK` at line 1907):

```js
[source fragment removed]
```

When a section below says "When `tD_()` returns false", that means one of:

- `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` is set to a truthy value in the environment, OR
- `includeGitInstructions: false` is set in the user config.

## Bash Description Variant Selection -- `Dz()`

`Dz()` (defined at line 171072, called at line 520963) decides whether a model gets the terse
"simple system prompt" Bash description `gU3()` or the legacy `tWK()`:

```js
[source fragment removed]
```

`_45(H)` (line 171047) returns true for "legacy prompt" models: `claude-3-*`, any `haiku`, any
`sonnet`, and `claude-opus-4-0/4-1/4-5/4-6/4-7`. It returns false for `claude-opus-4-8`. `H45(H)`
(line 171028) is a client/feature-flag override (`simple_system_prompt`, `tengu_velvet_cascade`).

The practical mapping for a default install:

| Model                         | `Dz()` | Bash variant | Ungated git block?        |
|-------------------------------|--------|--------------|---------------------------|
| Opus 4.8                      | true   | `gU3()`      | No -- only gated `FU3()`  |
| Sonnet / Haiku / Opus ≤ 4.7   | false  | `tWK()`      | Yes -- "For git commands" |

`CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT` forces the choice either way.

## Where Git Appears in Prompt-Relevant Code

### 1. Terse Bash Description -- `gU3()` and its "# Git" block `FU3()`

`gU3()` (line 520934) is the Bash description for current models. Its only git content is the
output of `FU3()` (line 520909), appended at the end:

```js
[source fragment removed]
```

`FU3()` renders the "# Git" block:

```
# Git
- Interactive flags (`-i`, e.g. `git rebase -i`, `git add -i`) are not supported in this environment.
- Use the `gh` CLI for GitHub operations (PRs, issues, API).
- Commit or push only when the user asks. If on the default branch, branch first.
- End git commit messages with:
  [commit attribution from CSH()]
- End PR bodies with:
  [PR attribution from CSH()]
```

When `tD_()` returns false: `FU3()` returns an empty string at its first line, so nothing is
appended. On the terse variant this removes the entire git footprint from the Bash description --
there is no other git content in `gU3()`. This is the behavioral change from 2.1.104.

### 2. Legacy Bash Description -- `tWK()`, commit/PR workflow `UU3()`

`tWK()` (line 520962) is the Bash description for older models. It builds a longer instruction list
and appends the commit/PR workflow `UU3()` (line 520729, the rename of the old `Wr4()`):

```js
[source fragment removed]
```

`UU3()` contains the "Committing changes with git" workflow (with the full Git Safety Protocol),
the "Creating pull requests" workflow, and "Other common operations".

When `tD_()` returns false: `UU3()` returns an empty string at its first line, so the workflow and
Git Safety Protocol are removed. The short "For git commands:" block (section 5) still survives on
this variant.

### 3. Git Status Context Injection -- `oZ8()`

At conversation start the current git status is captured and injected into the first user message
as a `<system-reminder>` block. This is informational context only -- branch, changed files,
recent commits -- with no behavioral instructions.

`oZ8()` (defined at line 261089) produces:

```
gitStatus: This is the git status at the start of the conversation. Note that this status is a snapshot in time, and will not update during the conversation.
Current branch: [BRANCH]

Main branch (you will usually use this for PRs): [MAIN_BRANCH]

Git user: [USER]

Status:
[git status --short output]

Recent commits:
[git log --oneline -n 5]
```

The injection gate is at line 261168:

```js
[source fragment removed]
```

When `tD_()` returns false: `oZ8()` is not called and no `gitStatus:` block appears. Also skipped
for remote sessions when `CLAUDE_CODE_REMOTE` is set. When included, the git status portion is now
truncated at 2,000 characters (`rZ8 = 2000`, line 261069) rather than the previous 40k.

### 4. Plan / Explore Subagent Restrictions

The Explore agent (`pI5()`) and Plan agent (`gI5()`) system prompts enumerate safe vs forbidden
Bash commands. Lines 278404-278405 (and the Plan equivalent at 278504-278505):

```
- Use Bash ONLY for read-only operations (ls, git status, git log, git diff, find, grep, cat, head, tail)
- NEVER use Bash for: mkdir, touch, rm, cp, mv, git add, git commit, npm install, pip install, or any file creation/modification
```

These are in the subagent system prompts, not the main system prompt, and not the Bash tool
description. They are guardrails layered on top of a normal Bash tool: both agents keep Bash
(`disallowedTools` -- line 278438 / 278544 -- strip Agent, ExitPlanMode, Edit, Write, NotebookEdit,
but not Bash), so each still receives a full Bash description through the `tWK`/`gU3` path keyed on
its own model. Explore is pinned to `haiku` (line 278441), so it lands on legacy `tWK()` and its
Bash description carries the ungated "For git commands:" block plus, when the switch is on, the
full `UU3()` commit/PR workflow -- even though this system prompt simultaneously forbids `git
commit`. Plan uses `model: "inherit"` (line 278548), so it follows the parent's model.

When `tD_()` returns false: no effect on these system prompts. They are independent of `tD_()` and
still mention these git commands as examples.

### 5. Legacy Bash Description -- "For git commands:" Short Block

Inside `tWK()` at lines 520991-520995, array `$`, rendered under the header `"For git commands:"`
at line 521024:

```js
[source fragment removed]
```

When `tD_()` returns false: no effect on the legacy variant -- this block sits in the ungated body
of `tWK()`, above the `UU3()` append point. It is the primary piece of git guidance an older-model
session retains when the switch is set.

This block does NOT exist in the terse variant `gU3()`. On Opus 4.8 these three rules are not
present at all when the switch is set (and the differently-worded `FU3()` block is gone too).

`tWK()` also carries an ungated inline example at line 520985 ("if you need to run `git status` and
`git diff`, send a single message with two Bash tool calls in parallel") -- a command-chaining
pattern, not git-specific behavior.

### 6. PowerShell Tool Description -- `MDK()`

On Windows the Bash-equivalent tool description is built by `MDK()` (line 498514). It contains git
references inline:

- Line 498563: prohibition on `git rebase -i`, `git add -i` (interactive editors).
- Lines 498565-498574: single-quoted here-string commit-message example and the stop-parsing
  token (`git log --% --format=%H`).
- Lines 498606-498609: a "For git commands:" block mirroring the three rules from section 5.

When `tD_()` returns false: no effect. `MDK()`'s git content is hardcoded into the template
literal; its only conditional inputs (`AI3()`, `wI3()`) are background-task notes gated by
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, not `tD_()`. Windows users retain the short git block and
the PowerShell-specific examples even with the switch set. `MDK()` never includes the full
commit/PR workflow.

### 7. Sandbox / Deny-Rules Prompt

The user soft-deny rules (line 325888) list "Git Destructive" (force push, deleting remote
branches, rewriting remote history) and "Git Push to Default Branch" under destructive/irreversible
operations.

When `tD_()` returns false: no effect. The deny-rules prompt is not gated.

### 8. Auto-Memory Prompt

The auto-memory system prompt (line 171569, under "What NOT to save in memory") tells the model
that `git log` / `git blame` are authoritative for history and recent changes.

When `tD_()` returns false: no effect. The auto-memory prompt is not gated.

### 9. Slash-Command Prompts (on-demand only)

Built-in commit/PR slash commands embed their own "## Git Safety Protocol" -- e.g. `_n3()` at line
542380 (with `!`git status``/`!`git diff HEAD`` command substitution) and a second at line 543641.
These call `CSH()` directly and are not gated by `tD_()`, but they are only injected when the user
invokes the command, not part of the always-on context.

## Git Safety Protocol (inside `UU3()`)

The full protocol, rendered by `UU3()` starting at line 520740:

- NEVER update the git config
- NEVER run destructive git commands (push --force, reset --hard, checkout ., restore ., clean -f,
  branch -D) unless the user explicitly requests
- NEVER skip hooks (--no-verify, --no-gpg-sign, etc) unless the user explicitly requests
- NEVER run force push to main/master, warn the user if they request it
- CRITICAL: Always create NEW commits rather than amending, unless explicitly requested. Pre-commit
  hook failure means the commit didn't happen, so --amend would modify the wrong commit
- When staging files, prefer specific files by name rather than "git add -A" or "git add ."
- NEVER commit changes unless the user explicitly asks

When `tD_()` returns false: the entire protocol disappears along with the rest of `UU3()`. On the
legacy variant the short block in section 5 still covers destructive ops, hook-skipping, and
amend-vs-new-commit in condensed form. On the terse variant nothing survives.

## Commit Attribution -- `CSH()`

Attribution text is generated by `CSH()` (line 520558, the rename of the old `GS6()`), called from
both `UU3()` and `FU3()`. It is surface-dependent and configurable.

### Default (CLI and most surfaces)

Commit: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
PR footer: `[robot emoji] Generated with [Claude Code](https://claude.com/claude-code)`

The model name in the commit trailer is resolved dynamically: inside an internal Anthropic repo
(`GAH()`) the actual model name is used via `n78()`; otherwise `CSH()` falls back to the literal
`"Claude Opus 4.8"` (line 520571).

### Remote sessions (claude.ai/code)

If `CLAUDE_CODE_REMOTE_SESSION_ID` and `SESSION_INGRESS_URL` are available (and not localhost),
`CSH()` uses a session URL for both commit and PR attribution (lines 520559-520568). If no session
URL is available: empty strings (no attribution).

### User configuration overrides

Inside `CSH()` at lines 520575-520577:

- `config.attribution.commit` -- custom commit trailer string
- `config.attribution.pr` -- custom PR footer string
- `config.includeCoAuthoredBy === false` -- disables all attribution

When `tD_()` returns false: `CSH()` is unreachable from the Bash description path because its only
callers there (`UU3()`, `FU3()`) return empty. Attribution trailers are neither computed nor shown.

## What Remains When Git Instructions Are Disabled

With `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=true` (or `includeGitInstructions: false`), the gated
content -- the commit/PR workflow `UU3()`, the "# Git" block `FU3()`, and the `gitStatus:`
injection -- is removed. What the model still sees depends on the surface:

| Source                                  | Gated by `tD_()`? | Present when disabled?                |
|-----------------------------------------|-------------------|---------------------------------------|
| Terse Bash `gU3()` (Opus 4.8)           | yes (`FU3()`)     | No git content at all                 |
| Legacy Bash `tWK()` commit/PR workflow  | yes (`UU3()`)     | Removed                               |
| Legacy Bash "For git commands:" block   | no                | Yes (older models only)               |
| Legacy Bash inline parallel example     | no                | Yes (older models only)               |
| `gitStatus:` context injection          | yes               | Removed                               |
| Plan / Explore subagent restrictions    | no                | Yes (git command names as examples)   |
| PowerShell tool `MDK()` git block       | no                | Yes (Windows)                         |
| Sandbox / deny-rules ("Git Destructive")| no                | Yes                                   |
| Auto-memory ("git log / git blame")     | no                | Yes                                   |
| Commit/PR slash-command prompts         | no                | Only when the command is invoked      |

The headline: on a current-model session (Opus 4.8, terse `gU3()`), setting the switch removes
every git instruction from the Bash tool description -- including the three short rules that
survived in 2.1.104. The git guidance that persists lives elsewhere: subagent prompts, the Windows
PowerShell tool, the sandbox deny-rules, the auto-memory prompt, and on-demand slash commands. On
an older-model session (legacy `tWK()`), the three-rule "For git commands:" block additionally
survives in the Bash description.

## Subagents and the Model Axis

The disable switch and the variant selection are independent axes. `tD_()` is keyed on an env
var / config; `Dz()` is keyed on the model that renders the request. A subagent runs its own
request loop on its own model, so a subagent can land on a different Bash variant than the main
session -- and therefore on different git instructions.

The Bash description is rendered per-request and keyed on the request's model: `PG6(tool, {...,
model: T.model})` (line 663284) -> `yXO()` -> `tool.prompt({model})` -> `tWK(model)` (line 521673)
-> `if (Dz(model)) return gU3()` (line 520963). A subagent's effective model is resolved by `io()`
(line 324566) in precedence order: `CLAUDE_CODE_SUBAGENT_MODEL` env var, then the agent's
frontmatter `model`, then inherit-from-parent.

The consequence: a subagent whose frontmatter pins a non-Opus-4.8 model (Sonnet, Haiku, Opus ≤ 4.7)
and which includes the Bash tool receives the legacy `tWK()` variant. That variant carries the
three-rule "For git commands:" block in its ungated body, so the subagent loads that block even
when `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=true` would have stripped git entirely from an Opus 4.8
subagent.

| Subagent model        | Switch | Git in subagent Bash description                          |
|-----------------------|--------|-----------------------------------------------------------|
| Opus 4.8              | on     | None                                                      |
| Opus 4.8              | off    | Full `UU3()` workflow + Safety Protocol + `FU3()` block   |
| Sonnet / Haiku / ≤4.7 | on     | "For git commands:" three-rule block only                 |
| Sonnet / Haiku / ≤4.7 | off    | "For git commands:" block + full `UU3()` workflow         |

Two caveats. This applies only if the subagent actually has the Bash tool. The built-in
Explore/Plan agents do have it (their `disallowedTools` strip Edit/Write/Task but not Bash), so
they go through the same `tWK`/`gU3` path -- Explore on its pinned `haiku` model lands on legacy
`tWK()` and so carries the ungated "For git commands:" block. Their read-only behavior comes from
the system prompt (section 4), not from a trimmed Bash description. And the `gitStatus:` injection
(section 3) is part of the main session's first user message -- gated by `tD_()` and
model-independent -- so it does not factor into the subagent Bash description.

## Implications

### For reproducing the system prompt

The git instructions are only available if you include a Bash tool whose description carries the
`UU3()`/`FU3()` content (and, on the legacy variant, the short "For git commands:" block) in its
description. Reproducing the Claude Code experience via the Anthropic API directly requires either
embedding the git instructions in your Bash tool description, or moving them into your system
prompt text (which Claude Code does not do).

### For subagents

Subagents that include the Bash tool receive a full Bash description on the variant selected by
their own model -- see "Subagents and the Model Axis". The restriction on the built-in Explore/Plan
agents is not a trimmed Bash description: they keep Bash and only strip Edit/Write/Task via
`disallowedTools`, then add read-only language in their system prompt (section 4). The git workflow
text can therefore appear in their Bash description even though their system prompt forbids
mutations. The main agent's git instructions separately prohibit delegating commit and PR
operations to subagents.

### Entanglement

The Bash tool description is a single dynamically-generated string whose git content varies by:

- Model ID (selects `gU3()` vs `tWK()` via `Dz()`; also affects the Co-Authored-By name)
- Execution surface (`remote` vs others -- affects attribution format)
- Whether the repo is an internal Anthropic repo (affects model name resolution)
- User config (`attribution`, `includeCoAuthoredBy`, `includeGitInstructions`)
- `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` and `CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT` env vars
