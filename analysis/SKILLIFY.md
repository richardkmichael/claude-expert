# Skillify: Disabled Skill-Creation Feature in Claude Code

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)


## Overview

Skillify is a disabled built-in feature designed to capture an interactive session's repeatable
process and convert it into a reusable SKILL.md file. It conducts a multi-round interview with
the user, analyzing the session history to understand what was done, then generating a structured
skill definition file that can be invoked in future sessions.

The feature is fully implemented as a prompt template but is unreachable -- its setup function is
a no-op and it is never registered with the skill system. There is no mechanism (feature flags,
server-side config, CLI options) that could activate it at runtime.


## Why It's Not Accessible

The setup function `Xhq()` at line 557031 is a no-op:

```javascript
[source fragment removed]
```

It never calls the skill registration function `Bj()` (line 511141), so the Skillify prompt is
never registered as an invocable skill. Compare with active skills like `zhq()` (keybindings-help)
and `Ohq()` (debug), which call `Bj({name: ..., description: ..., ...})` to register themselves.

The prompt template variable `_Rz` (lines 557034-557168) is defined but never referenced anywhere
in the codebase. The template placeholders (`{{sessionMemory}}`, `{{userDescriptionBlock}}`,
`{{userMessages}}`) also appear nowhere else -- no template engine processes them.

The skill dispatcher `RCq()` at line 562636 calls `Xhq()` alongside all other skill setup
functions, but since `Xhq()` returns immediately, nothing happens:

```javascript
[source fragment removed]
```

The nine comma-operator calls execute for side effects only. After them, `claude-api` is
registered via a dynamic import pattern (the `registerClaudeApiSkill` destructuring). Finally,
`claude-in-chrome` is conditionally registered if `sN6()` returns truthy (Chrome extension
detected).


### Could It Be Gated by Feature Flags or Server-Side Config?

No. A thorough search confirms Skillify is unconditionally dead code:

- The `_Rz` variable is never read. A word-boundary search for `\b_Rz\b` returns only its
  definition at line 557034.
- The string "skillify" (case-insensitive) appears nowhere in the file except inside the `_Rz`
  prompt template text itself.
- `Xhq` is declared with `function` (not reassignable `var`/`let`), is never reassigned, and is
  never referenced as a string for dynamic lookup.
- The feature flag systems contain no Skillify-related flags.
- The `sN6()` gate in `RCq()` is specifically for Claude-in-Chrome, not for Skillify.

This is build-time disabled code whose artifacts survived minification because the bundler does
not eliminate side-effect-free variable declarations.


## The Skillify Prompt Template

Variable `_Rz`, lines 557034-557168. The prompt contains two kinds of `{{...}}` patterns:

Code-level template variables (require programmatic expansion before the prompt reaches the
model):
- `{{userDescriptionBlock}}` (line 557034) - user context / description of what to skillify
- `{{sessionMemory}}` (line 557042) - session memory summary injected from disk
- `{{userMessages}}` (line 557047) - extracted user messages from the conversation

Model-facing placeholders (literal text instructing the model what to write in the SKILL.md
output):
- `{{skill-name}}`, `{{one-line description}}`, `{{list of tool permission patterns...}}`,
  etc. (lines 557109-557118) - in the SKILL.md template the model fills in

### 4-Step Workflow

Step 1 -- Analyze the Session:
Before asking any questions, analyze the session to identify:
- What repeatable process was performed
- What the inputs/parameters were
- The distinct steps (in order)
- The success artifacts/criteria for each step
- Where the user corrected or steered the process
- What tools and permissions were needed
- What agents were used
- What the goals and success artifacts were

Step 2 -- Interview the User (4 rounds using AskUserQuestion):
- Round 1: Suggest a name, description, goals, and success criteria. Ask user to confirm.
- Round 2: Present high-level steps as a numbered list. Suggest arguments. Ask about inline vs
  forked execution. Ask where to save the skill: repo (`.claude/skills/<name>/SKILL.md`) or
  personal (`~/.claude/skills/<name>/SKILL.md`).
- Round 3: For each step, ask what it produces, what proves success, whether to pause for user
  confirmation, whether steps can run in parallel, execution mode (direct, Task agent, Teammate,
  human), and hard constraints/preferences.
- Round 4: Confirm invocation triggers and trigger phrases. Ask about gotchas.

Step 3 -- Write the SKILL.md:
Generate a SKILL.md file at the location chosen in Round 2 with this structure:
- YAML frontmatter (name, description, allowed-tools, when_to_use, argument-hint, arguments,
  context)
- Markdown body with sections: Inputs, Goal, Steps (each with required success criteria)
- Per-step annotations: Execution mode, Artifacts, Human checkpoint, Rules
- Step structure tips: concurrent sub-steps (3a, 3b), `[human]` tags, simplicity guidance
- Frontmatter rules: minimal permissions, fork vs inline, when_to_use with trigger phrases

Step 4 -- Confirm and Save:
Show the user the complete SKILL.md as a YAML code block, ask for final confirmation via
AskUserQuestion, write the file, and tell the user where it was saved and how to invoke it
(`/{{skill-name}} [arguments]`).

### Helper Functions

`wRz()` (lines 557021-557029) extracts user message text from the conversation history, filtering
to `type: "user"` messages and extracting text content. This would provide the `{{userMessages}}`
template data.


## How Skill Registration Works

`Bj()` at line 511141 is the skill registration function. It takes a config object and creates a
skill entry pushed to the `Nfq` array (line 511165):

```javascript
[source fragment removed]
```

`kfq()` (line 511167) returns the registered skills array. Active skills call `Bj()` in their
setup functions; disabled skills have no-op setup functions that never call `Bj()`.

Skills are slash commands. Registering `Bj({name: "skillify", ...})` creates `/skillify`.
User-defined skills work the same way: `.claude/skills/tmux/SKILL.md` becomes `/tmux`.
Bundled skills and skill-directory skills are both dispatched through the same slash-command
system.


## Session Memory Pipeline (Separate Feature)

The session memory pipeline generates the `summary.md` file that Skillify's `{{sessionMemory}}`
variable reads. It runs as a background LLM call that periodically summarizes the conversation
into a structured markdown file. See [SESSION_MEMORY_AND_SUMMARY.md](SESSION_MEMORY_AND_SUMMARY.md)
for full details.


## Skill Improvement Pipeline (Separate Feature)

The skill improvement pipeline detects user corrections during skill execution and suggests
updates to the existing skill definition.

`pCq()` at line 563132 is the detection pipeline entry point -- currently a no-op (empty
function body). The apply function `FCq()` at line 563133 is fully implemented: it reads the
existing SKILL.md, sends both the current content and proposed improvements to an LLM, gets back
updated content inside `<updated_file>` tags, and writes the result to disk. The UI component
`fgq()` at line 592376 handles the suggestion display and user response, logging
`tengu_skill_improvement_survey` telemetry events.

The detection side (`pCq`) is disabled as a no-op, but the apply mechanism and UI remain intact.
The app state `skillImprovement.suggestion` (line 453898) still exists in the state tree. When a
suggestion is present and the user accepts it, `FCq` is called to apply the improvements
(querySource: `"skill_improvement_apply"`, line 563183).


## All Built-in Skills in the Dispatcher

The dispatcher `RCq()` (line 562636) calls all setup functions, then dynamically registers the
claude-api skill, then conditionally registers claude-in-chrome:

| Function | Line   | Status      | Name/Purpose             | Prompt Variable         |
|----------|--------|-------------|--------------------------|-------------------------|
| `Ahq()`  | 555626 | Disabled    | Settings / Update Config | `uyz` + `myz` (555629+) |
| `zhq()`  | 556237 | Active      | keybindings-help         | inline (556237)          |
| `_hq()`  | 556460 | Disabled    | Verification             | `qRz` (556463)           |
| `Ohq()`  | 556715 | Active      | debug                    | inline (556715)          |
| `Mhq()`  | 556824 | Disabled    | (empty stub, no prompt)  | none                     |
| `Xhq()`  | 557031 | Disabled    | Skillify                 | `_Rz` (557034)           |
| `Whq()`  | 557173 | Disabled    | (empty stub, no prompt)  | none                     |
| `Zhq()`  | 557180 | Active      | simplify                 | `$Rz` (557202)           |
| `Vhq()`  | 557321 | Active      | batch                    | `HRz()` (557250)         |
| `URz()`  | 562599 | Active      | claude-api               | `Ehq` + docs (557361)    |
| `tSq()`  | 555588 | Conditional | claude-in-chrome         | inline (555588)          |

"Disabled" means the function is a no-op (`return;`) and never calls `Bj()`.
"Active" means the function calls `Bj()` to register the skill.
"Conditional" means `tSq()` only runs if `sN6()` returns truthy (Chrome extension detected).


### Active Skills

keybindings-help (`zhq`, line 556237): Helps users customize keyboard shortcuts. Registered with
`userInvocable: !1` (not directly invocable by users, auto-triggered). Uses `Read` tool only.

debug (`Ohq`, line 556715): Reads the session debug log to help diagnose issues. Registered with
`userInvocable: !0` and `disableModelInvocation: !0`. Uses `Read`, `Grep`, `Glob` tools.
Accepts an optional issue description argument.

simplify (`Zhq`, line 557180): Reviews changed code for reuse, quality, and efficiency. Runs
`git diff` to identify changes, then launches three parallel review agents (Code Reuse, Code
Quality, Efficiency) via the Agent tool. Aggregates findings and fixes issues directly.
Registered with `userInvocable: !0`.

batch (`Vhq`, line 557321): Orchestrates large-scale parallel changes across a codebase.
Requires a git repository. Operates in three phases: (1) research and plan in plan mode,
decomposing work into 5-30 independent units; (2) spawn background agents in isolated worktrees,
each creating a PR; (3) track progress with a status table. Registered with `userInvocable: !0`
and `disableModelInvocation: !0`. Constants: `Thq = 5` (min units), `vhq = 30` (max units).

claude-api (`URz`, line 562599): Helps build applications using the Claude API and Anthropic
SDKs. Contains comprehensive bundled documentation for Python, TypeScript, Java, Go, Ruby, C#,
PHP, and curl -- auto-detects project language from file extensions. Registered via dynamic
import in the dispatcher. Uses `Read`, `Grep`, `Glob`, `WebFetch` tools. Its `{{OPUS_ID}}` and
similar template variables are expanded by `ECq()` (line 562542) using the `TCq` model-name map
(line 562480), which maps `OPUS_ID` -> `"claude-opus-4-6"`, `SONNET_ID` -> `"claude-sonnet-4-6"`,
etc.

claude-in-chrome (`tSq`, line 555588): Browser automation via Chrome extension. Only registered
when `sN6()` (line 510581) detects the extension is available -- checks environment, config, and
the `tengu_chrome_auto_enable` feature flag. Uses `mcp__claude-in-chrome__*` tools.


### Disabled Skills with Prompts

Settings / Update Config (`Ahq`, prompt `uyz` at 555629 plus `myz` at 555719): Modifies Claude
Code configuration files. Includes comprehensive schema reference for permissions, hooks, env
vars, model settings, MCP servers, plugins, attribution, and spinner customization.

Verification (`_hq`, prompt `qRz`, line 556463): A verification specialist that checks whether
code changes actually work. Discovers project-specific "verifier" skills, creates verification
plans, delegates to verifier skills, and reports results.


### Disabled Empty Stubs

`Mhq()` (line 556824) and `Whq()` (line 557173) are no-op functions with no associated prompt
templates. They may have had content during development that was stripped before release, or they
may be reserved slots for future skills.

Near `Mhq` are utility functions: `Jhq()` (line 556806) generates random English-like text from
a common word list `jhq` (line 556830), and `wRz()` (line 557021) extracts user messages from
conversation history. Both are utility functions rather than skill prompts.


## Execution Model: Inline Skill, Not a Task/Subagent

The skill system has two execution paths, determined by the `context` field in `Bj()` registration:

Inline (no `context` or `context: undefined`): The prompt from `getPromptForCommand` is injected
as messages into the main conversation. The model then interacts with the user normally.
Multi-round interaction is inherent since the skill becomes part of the ongoing conversation
context.

Fork (`context: "fork"`): The prompt becomes the sole user message for a new sub-agent
conversation loop. The sub-agent gets its own messages array and tool context, runs to completion,
and results are summarized back.

Skillify's prompt is structured for inline execution:
- It describes a 4+ round AskUserQuestion interview requiring heavy user interaction
- It reads user responses and iterates ("for each round, iterate as much as needed")
- It asks the user for confirmation before saving the final SKILL.md
- The prompt itself refers to inline vs fork as options for the skills it creates, not for itself

None of the active bundled skills use `context: "fork"` or set `agent`. All are inline skills.


## Template Variable Expansion

The `{{...}}` patterns in `_Rz` are NOT all the same kind of variable. There is no general
`{{...}}` template expansion layer applied to all skill prompts. The `{{...}}` expansion
functions in the codebase are purpose-specific:

- `hYY` (line 288862): used for session memory note prompts (line 288876)
- `Pqz` (line 458380): used for Magic Doc update prompts (line 458397)
- `ECq` (line 562542): used for claude-api skill documentation (line 562547), expanding model
  names like `{{OPUS_ID}}` via the `TCq` map

All three use identical regex logic (`/\{\{(\w+)\}\}/g` replacement), but none is wired into the
general skill dispatch pipeline. No `{{...}}` processing occurs between `getPromptForCommand`
returning and the messages reaching the model.

Skill-directory skills (`.claude/skills/*/SKILL.md`) use a completely different variable system:
- `$arg_name` / `$ARGUMENTS[n]` / `$n` substitution via `pG6` (line 252086)
- `${CLAUDE_SESSION_ID}` replacement
- `` !`command` `` and ` ```! command ``` ` embedded bash execution

The three code-level template variables in `_Rz` (`{{sessionMemory}}`, `{{userMessages}}`,
`{{userDescriptionBlock}}`) would need programmatic expansion in `getPromptForCommand` before the
prompt reaches the model -- the model cannot fabricate session memory or conversation history.

The model-facing placeholders (`{{skill-name}}`, `{{one-line description}}`, etc. at lines
557109-557118) are literal instructional text telling the model what to write in the generated
SKILL.md. The model fills these in during Step 3 of the interview, after learning the skill name
and details from the user.


## Could It Be Enabled with a Patch?

Yes. The prompt template is complete; what's missing is the `Bj()` registration call and
expansion of the three code-level template variables. Registering `Bj({name: "skillify", ...})`
would create the `/skillify` slash command.

### What the patch would need

Replace the `Xhq()` no-op with a `Bj()` registration call. The `getPromptForCommand` function
must expand the three code-level variables before returning the prompt:

| Variable                   | Data source                                                   |
|----------------------------|---------------------------------------------------------------|
| `{{sessionMemory}}`        | Session summary from disk (same mechanism as session notes)   |
| `{{userMessages}}`         | `wRz(messages)` (line 557021) extracts user text from history |
| `{{userDescriptionBlock}}` | Constructed from the command arguments                        |

`getPromptForCommand` receives two parameters: `(args, toolUseContext)`. Active bundled skills
use the first parameter (`args`) and sometimes the second for `toolUseContext.messages`.

### Sketch of a minimal patch

```javascript
[source fragment removed]
```

The model-facing `{{skill-name}}` and similar placeholders in the SKILL.md template section are
left as-is -- the model interprets them as instructions for what to write.

### Complications

1. `hYY`, `wRz`, and the session memory reader are minified names that could shift between
   versions. A patch would need to reference the correct identifiers for the target version.

2. `contentLength` is hardcoded to `0` in `Bj()` for all bundled skills (line 511153). This
   differs from skill-directory skills which set it to the markdown content length. The `0` value
   is used only in telemetry and does not gate execution.

3. The `Jhq()` random text generator (line 556806) and word list `jhq` (line 556830) near `Mhq`
   have no obvious connection to Skillify's prompt. They may have been intended for generating
   example/placeholder content during the skill creation interview, or they may be unrelated dead
   code that happens to be in the same module.
