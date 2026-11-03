---
verified: 2.1.316
verified_on: 2026-11-02
section: Tools, skills, and execution
style: landmark
scope: Live `propose_skills` skill proposals; dead Skillify prompt
landmarks:
  - propose_skills
  - CLAUDE_CODE_SKILL_PROPOSALS
  - '# Skillify'
---
# Skill Proposals, and the Dead Skillify Prompt

Two things answer the question "does Claude Code ever notice a repeated procedure and offer to turn
it into a skill":

- `propose_skills`: a registered tool whose purpose is surfacing recurring multi-step procedures as
  skill proposals. It is live, but only in remote, Cowork or explicitly opted-in sessions.
- Skillify: a complete prompt for interviewing the user and writing a SKILL.md from what the session
  just did. Its registration function is a no-op, its prompt function is never called, and nothing
  (flag, env var, server config) can reach it.

`propose_skills` is the discovery-and-offer flow; Skillify is an interview-and-author flow. Both
ship in the binary, one live and one dead. For how skills load and register in general, see
`SKILLS.md`. The public docs mention neither.

## `propose_skills`

Anchors:

- tool name `"propose_skills"`, exported as `ProposeSkillsTool`
- prompt opening `Surface recurring multi-step procedures from this session as skill proposals.`
- tool description `Show the user a review card of proposed skills to save`
- search hint `propose skills from recurring procedures for the user to review and save`
- input-schema field description `memory file paths where this procedure was observed`
- telemetry `tengu_propose_skills` (with `proposal_count` and `improvement_count`),
  `tengu_propose_skills_read_check`, `tengu_propose_skills_kept_lines`

What it is: a render-only, read-only tool. Calling it shows the user a review card; it writes
nothing and creates nothing, and its result tells the model
`Shown <n> skill proposal(s) to the user for review.` and not to wait. The user saves from the card.
Up to three proposals per call, each `kind: "new"` or `kind: "improvement"` (an improvement needs a
`target`), each carrying a complete `skillMd`: a saved proposal replaces the target skill's whole
SKILL.md, never a partial edit. An `evidence` field takes memory file paths where the procedure was
observed, which is how a procedure recurring across sessions, not just within one, becomes visible.

When the model is told to call it, from the tool prompt:

> Call once with all proposals (max 3). Use it when the user asks to turn a workflow or procedure
> into a skill, or when the same multi-step procedure has recurred and a skill would clearly save
> future work. Do not call it for one-off tasks, and do not re-propose skills the user has already
> seen.

That second clause is the discovery step. It is model judgment on the conversation plus memory
evidence. There is no background detector, no counter, and no cross-session mining job; the only
machinery is the tool's availability and that instruction.

Guardrails:

- Input validation refuses an `improvement` whose target SKILL.md has not been read in full, or
  whose copy on disk is newer than the copy read: `Existing SKILL.md not read in full yet for …`,
  `SKILL.md on disk is newer than the copy read for …`, with the reminder that a saved proposal
  replaces the whole file.
- An `improvement` can target only one of the user's own skills, including one they uploaded to
  claude.ai that the session lists as a plugin skill. Another plugin's skill, or a built-in one,
  must be proposed as `kind: "new"` under a name of its own, with a description saying when to use
  it instead of the original.
- A `new` proposal whose name is already one of the user's skills is refused with a pointer to
  propose an `improvement` instead.

There is no other skill-improvement pipeline: `tengu_skill_improvement_survey`, `skillImprovement`
and `<updated_file>` return no hits. `kind: "improvement"` is the only path that updates an existing
skill from a session.

### Gating

From the tool's `isEnabled`, in order:

| Condition                                                                    | Result                                               |
| ---------------------------------------------------------------------------- | ---------------------------------------------------- |
| `CLAUDE_CODE_CHILD_SESSION` or `CLAUDECODE` set                              | off                                                  |
| Diskless session on the `remote_cowork` surface                              | `CLAUDE_CODE_SYNC_SKILLS` and skills sync not vetoed |
| Entrypoint not `remote_cowork` and no `CLAUDE_CODE_SKILL_PROPOSALS`          | off                                                  |
| No `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE`, unless diskless with both env vars | off                                                  |
| `CLAUDE_CODE_ENVIRONMENT_KIND` set without `CLAUDE_CODE_SKILL_PROPOSALS`     | off                                                  |
| `CLAUDE_CODE_SKILL_PROPOSALS` set                                            | on, unless skills sync is vetoed                     |
| Otherwise                                                                    | `CLAUDE_CODE_SYNC_SKILLS` and not vetoed             |

The `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE` check sits ahead of every override, so in a local terminal
session the tool is off even with `CLAUDE_CODE_SKILL_PROPOSALS` set. The remote-session launcher
injects that variable (`rg -n 'CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE: "'`), and a helper classifies
its presence as the `env_ccr` environment. The only path that needs neither it nor the
`remote_cowork` entrypoint is a diskless session with both `CLAUDE_CODE_SKILL_PROPOSALS` and
`CLAUDE_CODE_SYNC_SKILLS` set.

### How the system prompt routes skill saving

A `# Saving skills` block picks one of four variants by which tool the session actually has, keyed
`save_tool` (a `save_skill` tool), `propose_tool` (`propose_skills`), `send_file` (a file-sending
tool), or `no_save_tool`. Relocate with `rg -n '# Saving skills'`. The block is emitted only when
the entrypoint is `remote_cowork` or `remote_cowork_trigger`, on related hosted surfaces, or with
`CLAUDE_CODE_SKILL_PROPOSALS` set. The `propose_tool` variant makes the proposal the deliverable:

> When the user wants a skill added or updated, the proposal is the deliverable — draft the content
> any way that helps, then propose it; don't send them a SKILL.md or a packaged skill file to save
> themselves.

The variants warn that skill files on disk, including synced copies of account skills, are a
read-only cache: editing them does not change the user's saved skill. Every variant ends with the
exception for plugin skills: when the session has the `cowork-plugin` skill, customize those through
it.

## Skillify

### Locating it

`rg -n -i 'skillify' work/<version>/package/cli.prettier.js` returns exactly one hit: the opening
line of the prompt template, a returned template literal starting with the heading `# Skillify`
followed immediately by `{{userDescriptionBlock}}`. The second line is
`You are capturing this session's repeatable process as a reusable skill.`

The enclosing function is the prompt getter. The no-op registration function is the next
`function <name>() { return; }` after the template's closing backtick.

To confirm the prompt is unreachable, scope the search to the enclosing bun module, because minified
names are two characters long and collide across modules:

```bash
# find the module banner above the hit, and the next banner below it
rg -n '^// ==== bun module:' work/<version>/package/cli.prettier.js
sed -n '<start>,<end>p' work/<version>/package/cli.prettier.js > /tmp/mod.js
rg -n '\b<promptFnName>\b' /tmp/mod.js   # expect: the definition only
rg -n '\b<setupFnName>\b'  /tmp/mod.js   # expect: the definition, plus one initializer call
```

The prompt getter has exactly one occurrence, its own `function` line. The registration function has
two: its definition and one call in the bundled-skill initializer's comma-operator list
(`rg -n 'bundledSkillsInitialized'`).

### Why it is unreachable

Bundled skills register by calling the bundled-skill registrar (see `SKILLS.md`). Registering under
a name is what creates the `/<name>` command and the model-invocable skill. Skillify's registration
function never calls the registrar: its body is `return;`. Nothing else in the module references the
prompt getter, so the template is never read either.

This is not a runtime gate. The function takes no arguments, checks no flag, and is declared with
`function`, not a reassignable binding, so no feature flag, server-side config or env var can switch
it on. It is build-time-disabled code whose string constant survives minification.

Skillify is one of several such slots. The skills module holds four `function <name>() { return; }`
no-ops that the initializer calls. Two sit right after a complete but unreferenced prompt string:
Skillify, and a `/stuck` session diagnostic (anchor `diagnose frozen/slow Claude Code sessions`,
likewise never read; the source spells its dash as a `\u2014` escape, so search the text after it).
The other two have no prompt beside them. The initializer also calls three functions with an empty
body. Re-derive the `return;` set with the multiline search
`rg -U 'function [A-Za-z_$]+\(\) \{\n  return;\n\}'` over the extracted module, then check what
precedes each one.

### What the prompt does

A four-step, four-round flow, all user-facing and all inline:

1. Analyze the session: what repeatable process ran, its inputs, its ordered steps, the success
   artifact for each step ("not just 'writing code,' but 'an open PR with CI fully passing'"), where
   the user corrected or steered, which tools, permissions and agents were used.
2. Interview the user with `AskUserQuestion` only, never plain text, iterating per round:
   - Round 1: proposed name, description, goals, success criteria.
   - Round 2: numbered high-level steps, suggested arguments, inline versus forked execution, and
     save location: `.claude/skills/<name>/SKILL.md` (this repo) or
     `~/.claude/skills/<name>/SKILL.md` (personal).
   - Round 3: per step, what it produces that later steps need, what proves success, whether to
     pause before irreversible actions, what can run in parallel, execution mode (`Direct`,
     `Task agent`, `Teammate`, `[human]`), hard constraints.
   - Round 4: when the skill should be invoked, trigger phrases, remaining gotchas.
3. Write the SKILL.md: frontmatter (`name`, `description`, `allowed-tools`, `when_to_use`,
   `argument-hint`, `arguments`, `context`) plus a body of Inputs, Goal and Steps, each step
   carrying a required Success criteria and optional Execution, Artifacts, Human checkpoint and
   Rules annotations. Concurrent sub-steps are numbered `3a`, `3b`.
4. Confirm and save: show the complete SKILL.md as a yaml block, confirm via `AskUserQuestion`,
   write the file, report where it went and that it is invoked as `/<name> [arguments]`.

Skillify starts from the user having already decided: it is invoked, it does not volunteer. The
noticing step is the model reading the conversation in Step 1, not a detector.

The template has one code-level placeholder, `{{userDescriptionBlock}}`. The session itself is the
source material:

> Review the conversation above — it is your source material. Pay particular attention to the user's
> messages (how they steered and corrected the process) and the tools/commands that were actually
> used.

The `{{skill-name}}`, `{{one-line description}}` and similar placeholders in the SKILL.md template
are model-facing instructional text that the model fills in while writing. Check with
`rg -o '\{\{(sessionMemory|userMessages|userDescriptionBlock)\}\}'`; expect one hit.

There is no general `{{...}}` expansion layer for skill prompts. The `/\{\{(\w+)\}\}/g` replacement
in the bundle is purpose-specific: the `claude-api` skill's `SKILL_MODEL_VARS` map. Disk skills use
the substitutions in the public docs (`$ARGUMENTS`, `$name`, `${CLAUDE_*}`) and `` !`command` ``
injection.

### Enabling it with a patch

Feasible. Replace the no-op with a call to the bundled-skill registrar, supplying
`name: "skillify"`, a `whenToUse`, and a `getPromptForCommand` that returns the template with
`{{userDescriptionBlock}}` substituted from the command arguments. The prompt reads the conversation
directly, so nothing else needs wiring.

The registrar lives in a different bun module from the prompt getter, so the patch must import it by
following the module's `import` and `export` lists; both names are minified and shift every release.

## What the adjacent features do, and do not, do

| Feature                          | Anchor                                                         | Discovery?                                                                  |
| -------------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `/skill-doctor`                  | `Show which loaded skills are unused and costing context`      | No: reports on already-loaded skills                                        |
| `skill-creator` plugin           | `/init` recommends `/plugin install skill-creator@…`           | No: authors and evals a skill already decided on; not shipped in the binary |
| `/init` Phase 6                  | `## Phase 6: Suggest and create skills`                        | Partly: suggests skills from repo structure and an interview                |
| `SuggestSkills` / `SearchSkills` | `SuggestSkills`, `Use ListSkills for skills they already have` | No: recommends existing catalog skills to install                           |
| `propose_skills`                 | `Surface recurring multi-step procedures from this session`    | Yes, the only one                                                           |

Skill-related telemetry, for orientation, includes `tengu_propose_skills`, `tengu_skill_authored`,
`tengu_skill_loaded`, `tengu_skill_file_changed`, `tengu_skill_tool_invocation`,
`tengu_dynamic_skills_changed` and `tengu_skills_sync_*`. Enumerate with
`rg -o 'tengu_[a-z0-9_]*skill[a-z0-9_]*' | sort -u`.

## Related

- `SKILLS.md`: skill sources, registration, filters, execution paths and `allowed-tools`.
- `SESSION_MEMORY_AND_SUMMARY.md`: the session memory pipeline.
- `MEMORY_SYSTEM.md`: the memory files `propose_skills` cites as evidence.
