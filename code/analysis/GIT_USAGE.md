# Claude Code Git Usage in System Prompts

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)
Verified against: cli.prettier.js 2.1.154 (2026-07-24); gate and variant selection spot-checked
against 2.1.277 (2026-09-19), see Version history.

Verbatim wording for the git blocks lives in `PROMPTS_RENDERED.md`; this doc covers the mechanism
and the per-model assembly (see "Exact Git Text Per Model").

## Key Finding

The git behavioral instructions are carried by the Bash tool's `description` field, not the main
system prompt. The exact content depends on which Bash-description variant the running model
receives, and that variant determines what survives the disable switch.

This means git instructions are invisible if you only examine the system prompt text; they are
embedded in the tool definition passed via the `tools` API parameter.

### Change since 2.1.104

Two things changed structurally:

- The Bash tool description now has two variants, selected per model by the variant selector under the
  "simple system prompt" decision. The terse variant is used for current models (Opus 4.8); the legacy
  variant is used for older models (Sonnet, Haiku, Opus ≤ 4.7).
- The git workflow text split in two: a commit/PR workflow builder carrying the bulk of the old
  workflow, and a new `# Git` block. Both are gated by the disable switch.

The behavioral consequence is the headline change: on the terse variant, the short three-rule git
block no longer survives the disable switch. In 2.1.104 the "For git commands:" block lived in the
ungated body of the Bash description and always survived. On Opus 4.8 that block is gone entirely;
the only git content in its Bash description is the gated the `# Git` block builder "# Git" section,
so disabling the switch removes all git instructions from the Bash description. The legacy variant
still carries an ungated "For git commands:" block (see section 5).

## The disable switch

Relocate: `rg -n 'CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS'`. The enclosing function is the gate. It
reads the env var, treats a truthy value as "disabled", treats an explicitly falsy value as
"enabled", and otherwise falls back to the `includeGitInstructions` config key, which defaults to
on. Expect three call sites: the git-status injection, the commit/PR workflow builder, and the
`# Git` block builder.

The truthy set is `1`, `true`, `yes`, `on`; the falsy set is `0`, `false`, `no`, `off`. Both are
case-insensitive and trimmed, and both accept a real boolean. The distinction between "falsy" and
"absent" is what makes the config fallback reachable: only an undefined env var defers to config.

Tripwire:

    □ env var read before config      □ truthy set = {1,true,yes,on}
    □ falsy set = {0,false,no,off}    □ config key includeGitInstructions, default on
    □ exactly 3 call sites

When a section below says "When the git-instructions gate returns false", that means one of:

- `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` is set to a truthy value in the environment, OR
- `includeGitInstructions: false` is set in the user config.

### Precedence: env var vs config

The env var and the config key are not interchangeable. the git-instructions gate reads the env var
first, so it outranks the config; the config is consulted only when the env var is unset or holds an
unrecognized value.

- env truthy (`1`/`true`/`yes`/`on`) -> git instructions off, regardless of the config
- env explicit-falsy (`0`/`false`/`no`/`off`) -> git instructions on, even if
  `includeGitInstructions: false` -- the env var force-enables and overrides the config
- env unset or set to anything else -> fall through to `includeGitInstructions` (default true)

They also have opposite polarity: the env var is a disable flag (truthy turns instructions off),
the config is an include flag (truthy turns them on). The only behavior they share is "turn
instructions off" -- env `=1` and config `=false` both suppress -- and even there the env var wins
on conflict.

## Bash Description Variant Selection -- the variant selector

The variant selector decides whether a model gets the terse
"simple system prompt" Bash description the terse Bash description or the legacy:

It is memoized, and returns false when given no model at all. `CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT`
overrides everything: truthy forces terse, explicitly falsy forces legacy. Absent the override, a
model gets the terse variant when it is not a legacy-prompt model, or when a client or feature-flag
override says so.

A legacy-model predicate returns true for "legacy prompt" models: `claude-3-*`, any `haiku`, any
`sonnet`, and `claude-opus-4-0/4-1/4-5/4-6/4-7`. It returns false for `claude-opus-4-8`. `H45(H)`
is a client/feature-flag override, keyed on `simple_system_prompt`.

The practical mapping for a default install:

| Model                           | Variant selector | Bash variant   | Ungated git block?               |
| ------------------------------- | ---------------- | -------------- | -------------------------------- |
| Opus 4.8                        | true             | terse          | No, only the gated `# Git` block |
| Sonnet / Haiku / Opus ≤ 4.7     | false            | legacy         | Yes, "For git commands"          |

`CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT` forces the choice either way.

## Exact Git Text Per Model

Verbatim wording for every git block is in `PROMPTS_RENDERED.md` (generated by `render-prompts.py`;
regenerate per version). This section maps each model variant and switch state to the blocks it
assembles, so the exact text is one lookup away.

The blocks and their verbatim sources:

| Block (this doc)           | `PROMPTS_RENDERED.md` section         | Built by                   | Gated? |
| -------------------------- | ------------------------------------- | -------------------------- | ------ |
| `# Git` block              | Bash tool — # Git block               | `# Git` block builder      | yes    |
| For-git-commands (3 rules) | Bash tool — For git commands (legacy) | legacy Bash description    | no     |
| commit/PR workflow         | Git workflow — commit & PR            | commit/PR workflow builder | yes    |
| `gitStatus:` injection     | Context injection — git status        | git-status collector       | yes    |

The `gitStatus:` rendered section holds only the lead sentence; its full template (branch, status,
recent commits) is runtime-filled and shown under "Git Status Context Injection" below.

Assembly by model and switch:

| Model (Bash variant)           | Git instr. | `# Git` | 3-rule | commit/PR | `gitStatus:` |
| ------------------------------ | ---------- | ------- | ------ | --------- | ------------ |
| Opus 4.8 (terse)               | enabled    | yes     | no     | no        | yes          |
| Opus 4.8 (terse)               | disabled   | no      | no     | no        | no           |
| Sonnet / Haiku / ≤4.7 (legacy) | enabled    | no      | yes    | yes       | yes          |
| Sonnet / Haiku / ≤4.7 (legacy) | disabled   | no      | yes    | no        | no           |

"Git instr. enabled" means the gate returns true: env var unset or explicitly falsy, config not
false. "Disabled" means it returns false. The `# Git` and 3-rule blocks are mutually exclusive by
variant: the terse variant carries only `# Git`, the legacy variant only the 3-rule block plus the
commit/PR workflow. The `gitStatus:` injection is model-independent and additionally suppressed by
`CLAUDE_CODE_REMOTE`.

Two git surfaces sit outside this matrix and are not yet captured verbatim in `PROMPTS_RENDERED.md`:
the Windows PowerShell tool description, which hardcodes its own ungated git block, and the
commit/PR slash commands, which embed a Git Safety Protocol injected only when invoked. Both are
detailed in "Where Git Appears" below.

## Where Git Appears in Prompt-Relevant Code

### 1. Terse Bash description and its `# Git` block

The terse Bash description is the one used for current models. Its only git content is the output of
the `# Git` block builder, appended at the end:

The description is assembled as a list of sections joined by newlines, opening with
`Executes a bash command and returns its output.` and covering working directory, the
IMPORTANT-avoid-tools note, timeout, `run_in_background` and sandbox. The `# Git` block is spread in
at the end only when it is non-empty.

the `# Git` block builder renders the "# Git" block -- four bullets: interactive-flag restriction,
use `gh` for GitHub operations, commit/push only when asked (branch off the default first), and the
commit/PR attribution trailers filled by the attribution helper. Verbatim text in
`PROMPTS_RENDERED.md`, section "Bash tool — # Git block".

When the git-instructions gate returns false: the `# Git` block builder returns an empty string at
its first line, so nothing is appended. On the terse variant this removes the entire git footprint
from the Bash description -- there is no other git content in the terse Bash description. This is
the behavioral change from 2.1.104.

### 2. Legacy Bash description and the commit/PR workflow

The legacy Bash description is the one used for older models. It builds a longer instruction list
and appends the commit/PR workflow builder:

The workflow is built first and spread in at the end only when non-empty, exactly as the `# Git`
block is on the terse variant. The short `For git commands:` block sits inline in the middle of the
list and is not gated at all (see section 5).

the commit/PR workflow builder contains the "Committing changes with git" workflow (with the full
Git Safety Protocol), the "Creating pull requests" workflow, and "Other common operations".

When the git-instructions gate returns false: the commit/PR workflow builder returns an empty string
at its first line, so the workflow and Git Safety Protocol are removed. The short "For git
commands:" block (section 5) still survives on this variant.

### 3. Git Status Context Injection -- the git-status collector

At conversation start the current git status is captured and injected into the first user message
as a `<system-reminder>` block. This is informational context only -- branch, changed files,
recent commits -- with no behavioral instructions.

The git-status collector produces the block below. Only its lead sentence is captured in
`PROMPTS_RENDERED.md` section "Context injection — git status"; the rest is runtime-filled (the
array uses a spread, so the renderer stops at the first interpolated line):

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

Relocate the injection gate by grepping `CLAUDE_CODE_REMOTE` near the git-status collector. The
block is collected only when the remote flag is falsy and the git-instructions gate is on;
otherwise the collector is never called.

When the git-instructions gate returns false: the git-status collector is not called and no
`gitStatus:` block appears. Also skipped for remote sessions when `CLAUDE_CODE_REMOTE` is set. When
included, the git status portion is now truncated at 2,000 characters rather than the previous 40k.

### 4. Plan / Explore Subagent Restrictions

The Explore agent and Plan agent system prompts enumerate safe vs forbidden
Bash commands, with an equivalent block in the Plan agent:

```
- Use Bash ONLY for read-only operations (ls, git status, git log, git diff, find, grep, cat, head, tail)
- NEVER use Bash for: mkdir, touch, rm, cp, mv, git add, git commit, npm install, pip install, or any file creation/modification
```

These are in the subagent system prompts, not the main system prompt, and not the Bash tool
description. They are guardrails layered on top of a normal Bash tool: both agents keep Bash
(`disallowedTools` strips Agent, ExitPlanMode, Edit, Write, NotebookEdit, but not Bash), so each
still receives a full Bash description through the `tWK`/`gU3` path keyed on its own model. Explore
is pinned to `haiku`, so it lands on the legacy Bash description and its Bash description carries
the ungated "For git commands:" block plus, when the switch is on, the full the commit/PR workflow
builder commit/PR workflow -- even though this system prompt simultaneously forbids `git commit`.
Plan uses `model: "inherit"`, so it follows the parent's model.

When the git-instructions gate returns false: no effect on these system prompts. They are
independent of the git-instructions gate and still mention these git commands as examples.

### 5. Legacy Bash Description -- "For git commands:" Short Block

Inside the legacy Bash description, rendered under the header `"For git commands:"`
Three rules: prefer new commits over amend, prefer safe alternatives to destructive
operations, and never skip hooks or signing without an explicit ask. Verbatim text in
`PROMPTS_RENDERED.md`, section "Bash tool — For git commands (legacy)".

When the git-instructions gate returns false: no effect on the legacy variant -- this block sits in
the ungated body of the legacy Bash description, above the commit/PR workflow builder's append
point. It is the primary piece of git guidance an older-model session retains when the switch is
set.

This block does not exist in the terse variant. On Opus 4.8 these three rules are not present at all
when the switch is set, and the differently-worded `# Git` block is gone too.

The legacy Bash description also carries an ungated inline example ("if you need to run `git status`
and `git diff`, send a single message with two Bash tool calls in parallel") -- a command-chaining
pattern, not git-specific behavior.

### 6. PowerShell Tool Description -- the PowerShell tool description

On Windows the Bash-equivalent tool description is built by the PowerShell tool description. It
contains git references inline:

- A prohibition on `git rebase -i` and `git add -i`, being interactive editors.
- A single-quoted here-string commit-message example and the stop-parsing
  token (`git log --% --format=%H`).
- A "For git commands:" block mirroring the three rules from section 5.

When the git-instructions gate returns false: no effect. the PowerShell tool description's git
content is hardcoded into the template literal; its only conditional inputs are background-task
notes gated by `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, not the git-instructions gate. Windows users
retain the short git block and the PowerShell-specific examples even with the switch set. the
PowerShell tool description never includes the full commit/PR workflow.

### 7. Sandbox / Deny-Rules Prompt

The user soft-deny rules list "Git Destructive" (force push, deleting remote
branches, rewriting remote history) and "Git Push to Default Branch" under destructive/irreversible
operations.

When the git-instructions gate returns false: no effect. The deny-rules prompt is not gated.

### 8. Auto-Memory Prompt

The auto-memory system prompt, under "What NOT to save in memory", tells the model
that `git log` / `git blame` are authoritative for history and recent changes.

When the git-instructions gate returns false: no effect. The auto-memory prompt is not gated.

### 9. Slash-Command Prompts (on-demand only)

Two built-in slash commands embed their own "## Git Safety Protocol", condensed and distinct from
the commit/PR workflow builder's: `/commit` ("Create a git commit") and `/commit-push-pr` ("Commit,
push, and open a PR"). Both use `!`git status``/`!`git diff HEAD`` command substitution and call the
attribution helper for attribution. They are not gated by the git-instructions gate but are injected
only when the user runs the command, so they never appear in the always-on context. Not captured in
`PROMPTS_RENDERED.md`.

## Git Safety Protocol (inside the commit/PR workflow builder)

The protocol is part of the commit/PR workflow rendered by the commit/PR workflow builder. Seven
rules: no config changes; no destructive commands without explicit request; no hook or signing
skips; no force-push to main/master; always new commits over `--amend` (a pre-commit hook failure
means the commit did not happen, so `--amend` would modify the wrong commit); stage specific files
over `git add -A`/`git add .`; never commit unprompted. Verbatim text in `PROMPTS_RENDERED.md`,
section "Git workflow — commit & PR".

When the git-instructions gate returns false: the entire protocol disappears along with the rest of
the commit/PR workflow builder. On the legacy variant the short block in section 5 still covers
destructive ops, hook-skipping, and amend-vs-new-commit in condensed form. On the terse variant
nothing survives.

## Commit Attribution -- the attribution helper

Attribution text is generated by the attribution helper, called from both the commit/PR workflow
builder and the `# Git` block builder. It is surface-dependent and configurable.

### Default (CLI and most surfaces)

Commit: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
PR footer: `[robot emoji] Generated with [Claude Code](https://claude.com/claude-code)`

The model name in the commit trailer is resolved dynamically: inside an internal Anthropic repo
the actual model name is used; otherwise the attribution helper falls back to a hardcoded model-name
literal.

### Remote sessions (claude.ai/code)

If `CLAUDE_CODE_REMOTE_SESSION_ID` and `SESSION_INGRESS_URL` are available (and not localhost),
the attribution helper uses a session URL for both commit and PR attribution. If no session
URL is available: empty strings (no attribution).

### User configuration overrides

Inside the attribution helper:

- `config.attribution.commit` -- custom commit trailer string
- `config.attribution.pr` -- custom PR footer string
- `config.includeCoAuthoredBy === false` -- disables all attribution

When the git-instructions gate returns false: the attribution helper is unreachable from the Bash
description path because its only callers there (the commit/PR workflow builder, the `# Git` block
builder) return empty. Attribution trailers are neither computed nor shown.

## What Remains When Git Instructions Are Disabled

With `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=true` (or `includeGitInstructions: false`), the gated
content, being the commit/PR workflow, the `# Git` block and the `gitStatus:` injection, is
removed. What the model still sees depends on
the surface:

| Source                                                     | Gated by the git-instructions gate?  | Present when disabled?                  |
| ---------------------------------------------------------- | ------------------------------------ | --------------------------------------- |
| Terse Bash the terse Bash description (Opus 4.8)           | yes (the `# Git` block builder)      | No git content at all                   |
| Legacy Bash the legacy Bash description commit/PR workflow | yes (the commit/PR workflow builder) | Removed                                 |
| Legacy Bash "For git commands:" block                      | no                                   | Yes (older models only)                 |
| Legacy Bash inline parallel example                        | no                                   | Yes (older models only)                 |
| `gitStatus:` context injection                             | yes                                  | Removed                                 |
| Plan / Explore subagent restrictions                       | no                                   | Yes (git command names as examples)     |
| PowerShell tool the PowerShell tool description git block  | no                                   | Yes (Windows)                           |
| Sandbox / deny-rules ("Git Destructive")                   | no                                   | Yes                                     |
| Auto-memory ("git log / git blame")                        | no                                   | Yes                                     |
| Commit/PR slash-command prompts                            | no                                   | Only when the command is invoked        |

The headline: on a current-model session (Opus 4.8, terse), setting the switch removes
every git instruction from the Bash tool description -- including the three short rules that
survived in 2.1.104. The git guidance that persists lives elsewhere: subagent prompts, the Windows
PowerShell tool, the sandbox deny-rules, the auto-memory prompt, and on-demand slash commands. On
an older-model session (legacy), the three-rule "For git commands:" block additionally
survives in the Bash description.

## Subagents and the Model Axis

The disable switch and the variant selection are independent axes. the git-instructions gate is
keyed on an env var / config; the variant selector is keyed on the model that renders the request. A
subagent runs its own request loop on its own model, so a subagent can land on a different Bash
variant than the main session -- and therefore on different git instructions.

The Bash description is rendered per-request and keyed on the request's model: `PG6(tool, {..., the
subagent's model is threaded into the tool-schema builder, which calls the tool's prompt getter with
that model, which runs the variant selector and returns the terse or legacy description accordingly.
A subagent's effective model is resolved in precedence order: `CLAUDE_CODE_SUBAGENT_MODEL` env var,
then the agent's frontmatter `model`, then inherit-from-parent.

The consequence: a subagent whose frontmatter pins a non-Opus-4.8 model (Sonnet, Haiku, Opus ≤ 4.7)
and which includes the Bash tool receives the legacy variant. That variant carries the
three-rule "For git commands:" block in its ungated body, so the subagent loads that block even
when `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=true` would have stripped git entirely from an Opus 4.8
subagent.

| Subagent model          | Switch   | Git in subagent Bash description                                                          |
| ----------------------- | -------- | ----------------------------------------------------------------------------------------- |
| Opus 4.8                | on       | None                                                                                      |
| Opus 4.8                | off      | the `# Git` block builder "# Git" block only (no the commit/PR workflow builder workflow) |
| Sonnet / Haiku / ≤4.7   | on       | "For git commands:" three-rule block only                                                 |
| Sonnet / Haiku / ≤4.7   | off      | "For git commands:" block + full the commit/PR workflow builder workflow                  |

Two caveats. This applies only if the subagent actually has the Bash tool. The built-in Explore/Plan
agents do have it (their `disallowedTools` strip Edit/Write/Task but not Bash), so they go through
the same `tWK`/`gU3` path -- Explore on its pinned `haiku` model lands on legacy the legacy Bash
description and so carries the ungated "For git commands:" block. Their read-only behavior comes
from the system prompt (section 4), not from a trimmed Bash description. And the `gitStatus:`
injection (section 3) is part of the main session's first user message -- gated by the
git-instructions gate and model-independent -- so it does not factor into the subagent Bash
description.

## Implications

### For reproducing the system prompt

The git instructions are only available if you include a Bash tool whose description carries the the
commit/PR workflow builder/the `# Git` block builder content (and, on the legacy variant, the short
"For git commands:" block) in its description. Reproducing the Claude Code experience via the
Anthropic API directly requires either embedding the git instructions in your Bash tool description,
or moving them into your system prompt text (which Claude Code does not do).

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

- Model ID, which selects the terse or legacy description through the variant selector and also
  affects the Co-Authored-By name
- Execution surface, `remote` versus others, which affects attribution format
- Whether the repo is an internal Anthropic repo, which affects model name resolution
- User config (`attribution`, `includeCoAuthoredBy`, `includeGitInstructions`)
- `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` and `CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT` env vars

## Version history

- 2.1.104: the terse Bash description still carried git content outside the gated `# Git` block.
- 2.1.154: the terse variant's entire git footprint is the gated `# Git` block, so disabling the
  switch removes git instructions from it completely. Git status injection truncated at 2,000
  characters, down from 40k.
- 2.1.277: the gate reads the env var through a central typed env accessor declared as a tri-state
  boolean, so the call site reduces to "defined value decides, negated; undefined falls back to
  config". The truthy and falsy token sets are unchanged and still live in shared helpers. The
  `tengu_velvet_cascade` flag is gone from the bundle; `simple_system_prompt` remains. Relocate the
  gate by grepping `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` and reading the enclosing function, or
  `triBool` for the env declaration.
