# Skillify, and the Skill-Proposal Path That Replaced It

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)
Verified: 2.1.277

Two separate things answer the question "does Claude Code ever notice a repeated procedure and
offer to turn it into a skill":

- Skillify — a complete prompt for interviewing the user and writing a SKILL.md from what the
  session just did. It has never shipped enabled. Its setup function is a no-op, its prompt function
  is never called, and nothing (flag, env var, server config) can reach it.
- `propose_skills` — a registered tool whose whole purpose is surfacing recurring multi-step
  procedures as skill proposals. It is real and live, but gated to remote (cloud) sessions.

Skillify is the interview-and-author flow. `propose_skills` is the discovery-and-offer flow. They
are not the same feature, and one did not literally replace the other in the code: Skillify's dead
code is still shipped alongside the live tool.


## Skillify

### Locating it

`rg -n -i 'skillify' work/<version>/package/cli.prettier.js` returns exactly one hit in every
version checked (2.1.119 through 2.1.277): the opening line of the prompt template, a returned
template literal starting with the heading `# Skillify` followed immediately by the
`{{userDescriptionBlock}}` placeholder.

The enclosing function is the prompt getter. The no-op setup function is the next
`function <name>() { return; }` immediately after the template's closing backtick.

To confirm the prompt is unreachable, scope the search to the enclosing bun module rather than the
whole bundle — minified names are two characters long and collide across modules:

```bash
# find the module banner above the hit, and the next banner below it
rg -n '^// ==== bun module:' work/<version>/package/cli.prettier.js
sed -n '<start>,<end>p' work/<version>/package/cli.prettier.js > /tmp/mod.js
rg -n '\b<promptFnName>\b' /tmp/mod.js   # expect: the definition only
rg -n '\b<setupFnName>\b'  /tmp/mod.js   # expect: the definition, plus one dispatcher call
```

At 2.1.277 the prompt getter has exactly one occurrence — its own `function` line. The setup
function has two: its definition and one call inside the skill dispatcher's comma-operator list.

### Why it is unreachable

Bundled skills register by calling a registration helper (find it with
`rg -n 'source: "bundled"'`; the object it builds carries `loadedFrom: "bundled"`,
`contentLength: 0`, `userInvocable`, `disableModelInvocation`, `context`, `agent`,
`getPromptForCommand`, and an `isEnabled` gate). Registering under a name is what creates the
`/<name>` slash command; skill-directory skills (`.claude/skills/<name>/SKILL.md`) reach the same
dispatch through a different loader.

Skillify's setup function never calls that helper — its body is `return;`. So no slash command, no
model-invocable skill, no entry in the skill list. Nothing else in the module references the prompt
getter, so the template is never read either.

This is not a runtime gate. The setup takes no arguments, checks no flag, and is declared with
`function` (not a reassignable binding), so there is no feature flag, server-side config, or env var
that could switch it on. It is build-time-disabled code whose string constant survives minification.

Skillify is one of several such slots. At 2.1.277 the skills module holds four `function <name>() {
return; }` no-ops that the dispatcher calls. Two of them sit immediately after a complete but
unreferenced prompt string, making the pairing legible: Skillify, and a `/stuck` session diagnostic
(anchor: `# /stuck — diagnose frozen/slow Claude Code sessions`, likewise defined and never read).
The other two have no prompt attached at all. The count and membership churn; re-derive them with
the multiline search `rg -U 'function [A-Za-z_$]+\(\) \{\n  return;\n\}'` over the extracted module,
then check what precedes each one.

### What the prompt does

Anchor on `You are capturing this session's repeatable process as a reusable skill.`

A four-step, four-round flow, all user-facing and all inline:

1. Analyze the session — what repeatable process ran, its inputs, its ordered steps, the success
   artifact for each step ("not just 'writing code,' but 'an open PR with CI fully passing'"), where
   the user corrected or steered, which tools/permissions/agents were used.
2. Interview the user with `AskUserQuestion` only, never plain text, iterating per round:
   - Round 1: proposed name, description, goals, success criteria.
   - Round 2: numbered high-level steps, suggested arguments, inline vs forked execution, and save
     location — `.claude/skills/<name>/SKILL.md` (repo) or `~/.claude/skills/<name>/SKILL.md`
     (personal).
   - Round 3: per step — what it produces that later steps need, what proves success, whether to
     pause for confirmation before irreversible actions, what can run in parallel, execution mode
     (`Direct`, `Task agent`, `Teammate`, `[human]`), hard constraints.
   - Round 4: when the skill should be invoked, trigger phrases, remaining gotchas.
3. Write the SKILL.md — frontmatter (`name`, `description`, `allowed-tools`, `when_to_use`,
   `argument-hint`, `arguments`, `context`) plus a body of Inputs / Goal / Steps, each step carrying
   a required Success criteria and optional Execution / Artifacts / Human checkpoint / Rules
   annotations. Concurrent sub-steps are numbered `3a`, `3b`.
4. Confirm and save — show the complete SKILL.md as a yaml block, confirm via `AskUserQuestion`,
   write the file, report where it went and that it is invoked as `/<name> [arguments]`.

So yes: Skillify is squarely about turning what the session just did into a skill. But it starts
from the user having already decided — it is invoked, it does not volunteer. The noticing step is
the model reading the conversation in Step 1, not a detector that fires on its own.

### The prompt lost its session-history plumbing

At 2.1.76 the template carried three code-level placeholders needing programmatic expansion:
`{{userDescriptionBlock}}`, `{{sessionMemory}}`, and `{{userMessages}}`, the last fed by a helper
that filtered conversation history to `type: "user"` messages.

Only `{{userDescriptionBlock}}` survives. `{{sessionMemory}}` and `{{userMessages}}` are absent from
every locally held bundle from 2.1.119 onward, so they were dropped somewhere in 2.1.77–2.1.119. In
their place the prompt now says:

> Review the conversation above — it is your source material. Pay particular attention to the user's
> messages (how they steered and corrected the process) and the tools/commands that were actually
> used.

The remaining `{{skill-name}}`, `{{one-line description}}` and similar placeholders in the SKILL.md
template are model-facing instructional text, not variables — the model fills them in while writing.
Check with `rg -o '\{\{(sessionMemory|userMessages|userDescriptionBlock)\}\}'`; expect one hit.

There is still no general `{{...}}` expansion layer for skill prompts. The `/\{\{(\w+)\}\}/g`
replacement helpers in the bundle are purpose-specific (the `claude-api` skill's model-id map is
one). Skill-directory skills use a different substitution system entirely: `$arg_name`,
`$ARGUMENTS[n]`, `$n`, `${CLAUDE_SESSION_ID}`, and embedded `` !`command` `` execution.

### Enabling it with a patch

Still feasible, and simpler than it was at 2.1.76. Replace the no-op setup with a call to the
bundled-skill registration helper, supplying `name: "skillify"`, a `whenToUse`, and a
`getPromptForCommand` that returns the template with `{{userDescriptionBlock}}` substituted from the
command arguments. The session-history variables no longer need wiring — the prompt reads the
conversation directly.

Complications: the registration helper and the prompt getter are minified names that shift every
release, and from 2.1.242 they may live in different bun modules, so the patch must follow the
module's `import`/`export` edges rather than assume a single scope.


## `propose_skills` — the live discovery path

Introduced between 2.1.207 and 2.1.220 (absent in every local bundle up to 2.1.207, present from
2.1.220 on). Anchors:

- tool name string `"propose_skills"`, exported as `ProposeSkillsTool`
- `Surface recurring multi-step procedures from this session as skill proposals.`
- search hint `propose skills from recurring procedures for the user to review and save`
- input-schema field description `memory file paths where this procedure was observed`
- telemetry `tengu_propose_skills` with `proposal_count` and `improvement_count`

What it is: a render-only tool. Calling it shows the user a review card; it writes nothing and
creates nothing. The user saves from the card. Up to three proposals per call, each
`kind: "new"` or `kind: "improvement"`, each carrying a complete `skillMd` — a saved proposal
replaces the target skill's whole SKILL.md, never a partial edit. An `evidence` field takes memory
file paths where the procedure was observed, which is how a procedure recurring across sessions
rather than within one becomes visible.

When the model is told to call it, from the tool prompt:

> Use it when the user asks to turn a workflow or procedure into a skill, or when the same
> multi-step procedure has recurred and a skill would clearly save future work. Do not call it for
> one-off tasks, and do not re-propose skills the user has already seen.

That second clause is the discovery step. It is model-driven judgment on the conversation plus
memory evidence — there is no background detector, no counter, no cross-session mining job. The only
machinery is the tool's availability and that instruction.

Guardrails worth knowing: `validateInput` refuses an `improvement` whose target SKILL.md has not
been read in full, or whose on-disk copy is newer than the copy in context, with a message that a
saved proposal replaces the file entirely. An `improvement` can only target one of the user's own
skills — a plugin skill or a bundled one must be proposed as a new skill under a different name,
with a description saying when to use it instead of the original.

### Gating

From the tool's `isEnabled`, in order:

| Condition                                                                | Effect                                         |
| ------------------------------------------------------------------------ | ---------------------------------------------- |
| an internal suppression check                                            | off                                            |
| neither an account-sync predicate nor `CLAUDE_CODE_SKILL_PROPOSALS`      | off                                            |
| `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE` unset                              | off                                            |
| `CLAUDE_CODE_ENVIRONMENT_KIND` set without `CLAUDE_CODE_SKILL_PROPOSALS` | off                                            |
| otherwise                                                                | on, unless a further per-session check refuses |

The `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE` check is unconditional and sits ahead of every override
path, so the tool is off in a local terminal session even with `CLAUDE_CODE_SKILL_PROPOSALS` set.
That variable is injected by the remote-session launcher (find it via
`rg -n 'CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE: "'`), and a helper classifies its presence as the
`env_ccr` environment. Claude Code on the web and cloud sessions get this tool; the CLI on a laptop
does not.

### How the system prompt routes skill saving

A `# Saving skills` block picks one of four variants by which tool the session actually has,
keyed `save_tool` / `propose_tool` / `send_file` / `no_save_tool`. Relocate with
`rg -n '# Saving skills'`. The `propose_tool` variant makes the proposal itself the deliverable:

> When the user wants a skill added or updated, the proposal is the deliverable — draft the content
> any way that helps, then propose it; don't send them a SKILL.md or a packaged skill file to save
> themselves.

All four variants carry the same warning that skill files on disk, including synced copies of
account skills, are a read-only cache: editing them does not change the user's saved skill.


## What the adjacent features do, and do not, do

| Feature                          | Anchor                                                          | Discovery?                                                                                |
| -------------------------------- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `/skill-doctor`                  | `Show which loaded skills are unused and costing context`       | No — reports on already-loaded skills                                                     |
| `skill-creator` skill            | shipped skill, authors and evals a skill already decided on     | No                                                                                        |
| `/init` Phase 6                  | `## Phase 6: Suggest and create skills`                         | Partly — suggests skills from repo structure and an interview, not from observed behavior |
| `SuggestSkills` / `SearchSkills` | `SuggestSkills`, `Use ListSkills for skills they already have`  | No — recommends existing catalog skills to install                                        |
| `propose_skills`                 | `Surface recurring multi-step procedures from this session`     | Yes — the only one                                                                        |

Skill-related telemetry in 2.1.277, for orientation: `tengu_propose_skills`, `tengu_skill_authored`,
`tengu_skill_loaded`, `tengu_skill_file_changed`, `tengu_skill_tool_invocation`,
`tengu_dynamic_skills_changed`, `tengu_skills_sync_*`, `tengu_doctor_command`. Enumerate with
`rg -o 'tengu_[a-z0-9_]*skill[a-z0-9_]*' | sort -u`.


## Removed: the skill-improvement pipeline

At 2.1.76 a separate pipeline detected user corrections during skill execution and offered to update
the existing SKILL.md: a disabled no-op detector, a working apply function that round-tripped the
SKILL.md through an LLM and read back `<updated_file>` tags, a `skillImprovement.suggestion` entry
in the app state tree, and a UI component logging `tengu_skill_improvement_survey`.

All of it is gone. `tengu_skill_improvement_survey`, `skillImprovement`, `skill_improvement` and
`<updated_file>` return zero hits in every locally held bundle from 2.1.119 onward, so it was
removed in 2.1.77–2.1.119. Its function is now served, for remote sessions only, by `propose_skills`
with `kind: "improvement"`.


## Version history

| Versions          | Skillify                                                                                      | Discovery path                          |
| ----------------- | --------------------------------------------------------------------------------------------- | --------------------------------------- |
| 2.1.76            | Dead prompt with `{{sessionMemory}}` + `{{userMessages}}`; skill-improvement pipeline present | none                                    |
| 2.1.119 – 2.1.207 | Dead prompt trimmed to `{{userDescriptionBlock}}`; improvement pipeline removed               | none                                    |
| 2.1.220 – 2.1.277 | Unchanged dead prompt                                                                         | `propose_skills`, remote sessions only  |


## Related

- [SKILLS_AND_SUBAGENTS.md](SKILLS_AND_SUBAGENTS.md) — skill `allowed-tools` and where grants apply
- [SESSION_MEMORY_AND_SUMMARY.md](SESSION_MEMORY_AND_SUMMARY.md) — the `summary.md` pipeline that
  Skillify's removed `{{sessionMemory}}` variable once read
- [MEMORY_SYSTEM.md](MEMORY_SYSTEM.md) — the memory files `propose_skills` cites as evidence
