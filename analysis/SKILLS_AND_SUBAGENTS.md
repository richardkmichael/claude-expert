# Skills and Subagent Integration

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)
Verified against: cli.prettier.js 2.1.76 (2026-06-06); the headline `allowed-tools` preload gap and
the permission-merge shape re-checked against 2.1.277 (2026-09-19), see Version history.

See also: [Task Tool and Subagents](TASK_TOOL_AND_SUBAGENTS.md),
[Markdown Frontmatter](MARKDOWN_FRONTMATTER.md)

## Overview

Skills (`.claude/skills/*/SKILL.md`) can declare `allowed-tools:` in their YAML frontmatter to
auto-permit specific tools without user approval.  When a skill is invoked directly in the main
session (`/my-skill`), this works as expected.  When a subagent references a skill via its YAML
`skills:` field, the `allowed-tools` are not applied — the user is prompted for permission.

This document traces the three code paths that load skills and shows exactly where the
`allowed-tools` permission grant occurs (or doesn't).


## Two Axes of Tool Control: Availability vs Permission

Agent and skill YAML frontmatter use different keywords that operate on different axes, which
makes the system difficult to intuit.

### Axis 1: Tool Availability (Agent Frontmatter)

Agent YAML (`.claude/agents/*.md`) uses `tools:` and `disallowedTools:` to control which tools
the subagent can see and call at all.  These are enforced by a filter that reduces
the tool list before the subagent starts.

| Field              | Effect                                       | Example                      |
| ------------------ | -------------------------------------------- | ---------------------------- |
| `tools:`           | Whitelist: only these tools are available    | `tools: [Read, Grep, Glob]`  |
| `disallowedTools:` | Blacklist: these tools are removed           | `disallowedTools: [Edit]`    |

If `tools:` is `["*"]` or omitted, all tools are available (minus any `disallowedTools`).
An unavailable tool cannot be called at all — the subagent doesn't even see it.

### Axis 2: Tool Permission (Skill Frontmatter)

Skill YAML (`.claude/skills/*/SKILL.md`) uses `allowed-tools:` to control which tools are
auto-permitted without user approval.  The tool must still be available (axis 1); this only
affects whether the user is prompted before the tool executes.

| Field              | Effect                                       | Example                                 |
| ------------------ | -------------------------------------------- | --------------------------------------- |
| `allowed-tools:`   | Auto-permit: no user approval prompt needed  | `allowed-tools: Bash(git diff:*), Read` |
| (no counterpart)   | There is no `disallowed-tools:` for skills   |                                         |

### Naming Confusion

The naming is inconsistent across the two systems:

| Concept            | Agent keyword      | Skill keyword      | Syntax       |
| ------------------ | ------------------ | ------------------ | ------------ |
| Tool whitelist     | `tools:`           | (none)             | camelCase    |
| Tool blacklist     | `disallowedTools:` | (none)             | camelCase    |
| Auto-permit        | (none)             | `allowed-tools:`   | kebab-case   |
| Auto-deny          | (none)             | (none)             |              |

- Agent keywords use camelCase: `tools`, `disallowedTools`
- Skill keywords use kebab-case: `allowed-tools`
- "tools" (agent) means "available to call" — not "permitted without asking"
- "allowed-tools" (skill) means "permitted without asking" — not "available to call"
- There is no `disallowed-tools` counterpart in skill frontmatter
- There is no `allowed-tools` counterpart in agent frontmatter

A subagent that references a skill (`skills: [my-skill]`) must contend with both axes: the
agent's `tools:` determines what tools are available; the skill's `allowed-tools:` determines
which of those are auto-permitted.  Except that, as documented below, the skill's
`allowed-tools:` is not actually applied in this context.


## Skill Execution Context

### The `context:` and `agent:` Frontmatter Fields

Skill YAML frontmatter supports two fields that control execution:

| Field       | Values           | Effect                                                    |
| ----------- | ---------------- | --------------------------------------------------------- |
| `context:`  | `fork` or absent | `fork`: run in an isolated subagent; absent: run inline   |
| `agent:`    | agent type name  | Which agent definition runs the forked subagent           |

The `agent:` field only has effect when `context: fork` is present.  Without `context: fork`,
the `agent:` field is parsed and stored on the skill object but never read by any execution path.

Both the direct invocation path and the Skill tool path check only `context === "fork"`. The
non-fork path calls the prompt slash-command processor, which does not reference
`A.agent`.

### Three Execution Modes

| Frontmatter                        | Execution mode           | Conversation context        | Agent type used           |
| ---------------------------------- | ------------------------ | --------------------------- | ------------------------- |
| (neither field)                    | Inline in main session   | Full conversation history   | Main session (none)       |
| `context: fork` only               | Isolated subagent        | Skill content only          | `general-purpose`         |
| `context: fork` + `agent: Explore` | Isolated subagent        | Skill content only          | `Explore`                 |
| `agent: Explore` only (no fork)    | Inline in main session   | Full conversation history   | `agent:` ignored          |

### What "Fork" Means (and Doesn't Mean)

The name `context: fork` is misleading.  It does not fork the conversation — the subagent does
not receive any of the current conversation history.  "Fork" means "fork execution" — spawn a
separate subagent process that runs independently.

This is a naming collision with the `/fork` command, which does the opposite: `/fork` duplicates
the entire conversation transcript into a new JSONL session file and switches to it, preserving
all history (see [Context Ops](CLEAR_COMPACT_FORK_CONTEXT.md)).  The two uses of "fork" are
unrelated.

The subagent receives:

- The skill's rendered content as a single user message (the only `promptMessages`)
- The selected agent definition's system prompt
- The skill's `allowed-tools` propagated by wrapping `getAppState`
- Tool availability determined by the agent definition's `tools:`/`disallowedTools:`
- All tools from the main session (via `availableTools: K.options.tools`) unless the agent
  definition restricts them

The subagent does NOT receive:

- The current conversation history
- The main session's system prompt
- Any prior tool results or assistant messages

### The `forkContextMessages` Mechanism

The subagent loop supports a `forkContextMessages` parameter that, when provided, prepends
conversation history to the subagent's initial messages. Relocate by grepping
`forkContextMessages`.

The initial message array is the filtered fork context followed by the prompt messages. Passing
fork context also switches the file-state seed: with fork context the subagent inherits the
parent's read-file state, without it the subagent starts from an empty one.

The filter removes orphaned `tool_use` blocks, meaning assistant messages carrying a `tool_use` id
with no matching `tool_result` in the user messages. Without that step a forked subagent would open
on a malformed conversation.

This mechanism exists and is used by other callers:

| Caller                      | Passes `forkContextMessages`         |
| --------------------------- | ------------------------------------ |
| Agent tool                  | Conditionally, the parent's messages |
| Context packager            | The current context's messages       |
| Skill fork, direct `/skill` | Not passed                           |
| Skill fork, Skill tool      | Not passed                           |

Neither skill fork entry point passes `forkContextMessages`.  The parent's
`toolUseContext.messages` does flow through the spread (`{ ...K, getAppState: $ }`) but is
overridden when the child context is created: the child takes the computed message array when one
is supplied and falls back to the parent's only when it is not. For a skill fork that computed array
is the fork context plus the prompt messages, which is to say the prompt messages alone.


## Skill Object Construction

### Parsing `allowed-tools` from Frontmatter

Relocate by grepping `allowed-tools`.

The parser accepts a string or an array of strings, normalizes the result, and distinguishes three
outcomes: `null` when the field is absent, an empty array when it is present but yields nothing,
and the normalized list otherwise. A list containing `*` collapses to exactly `["*"]`.

A non-string member of an array is dropped rather than coerced or rejected.

The distinction between absent and empty matters only inside the parser: its wrapper folds `null`
into an empty array, so every downstream consumer sees a list. Tracing a bug through this code
means knowing which of the two you are looking at.

### The skill object

Skills are loaded from `SKILL.md` files and constructed by a factory taking a named-argument
object: skill name, markdown content, the parsed `allowedTools` list, and the rest of the
frontmatter.

It returns a command object of type `prompt`, carrying the name and the `allowedTools` list, whose
`getPromptForCommand` resolves the template and injects `allowedTools` into the app state the skill
body sees. See "Template Resolution" below.

Relocate by grepping `getPromptForCommand`; the factory is the enclosing function.

### Skill Loading Pipeline

Skills are loaded from two directory patterns and one plugin source:

| Source                           |
| -------------------------------- |
| `.claude/skills/*/SKILL.md`      |
| `.claude/commands/*.md`, legacy  |
| Plugin skills                    |

All three paths extract `allowed-tools` from frontmatter through the same parser and pass the
result to the skill factory.

### Template Variables

The skill's `getPromptForCommand` method resolves template variables and performs substitutions
before returning the rendered content.  Two built-in template variables are available in SKILL.md:

| Variable               | Value                          |
| ---------------------- | ------------------------------ |
| `${CLAUDE_SKILL_DIR}`  | Absolute path to skill's dir   |
| `${CLAUDE_SESSION_ID}` | Current session UUID           |

`CLAUDE_SKILL_DIR` resolves to the skill's directory (e.g., `.claude/skills/my-skill`).  On
Windows, backslashes are normalized to forward slashes.  This lets SKILL.md reference companion
files (scripts, templates, data) relative to the skill's own location.  The substitution occurs
in both the standard skill path and the plugin skill path.

`CLAUDE_SESSION_ID` resolves to the session UUID.

### Template Resolution and `getPromptForCommand`

The method also creates a modified `getAppState` that includes the skill's `allowedTools` in the
`alwaysAllowRules.command` array, but that modification is scoped to the template resolver.

Resolution runs in a fixed order on the markdown body:

1. Argument substitution, filling the skill's invocation arguments.
2. `${CLAUDE_SKILL_DIR}` replaced with the skill's base directory, when one exists. On Windows the
   path is converted to forward slashes first, so a skill body can interpolate it into a command
   without escaping.
3. `${CLAUDE_SESSION_ID}` replaced with the session UUID.
4. The template resolver runs over the result, given a context whose `getAppState` is wrapped.

The wrapper is a shallow spread of the real app state with one substitution: inside
`toolPermissionContext.alwaysAllowRules`, the `command` list is replaced by the skill's
`allowedTools`. Everything else passes through unchanged.

The resolved text is returned as a single text block.

The modified `getAppState` is used only by the template resolver. The caller of
`getPromptForCommand` receives only the resolved text content — the `allowedTools` injection does
not propagate to the caller's permission context.


## Code Path 1: Direct Skill Invocation (`/my-skill`)

`allowed-tools`: applied

When a user invokes `/my-skill` in the main session, the Skill tool's `call` method processes it.

### Flow

```
User types /my-skill
  → Skill tool call
    → prompt slash-command processor
      → skill.getPromptForCommand        — prompt content
      → normalize skill.allowedTools
      → append a command_permissions message carrying the list
      → return { messages, allowedTools }
    ← Skill tool receives the result
      → read allowedTools off it
      → contextModifier merges them into alwaysAllowRules.command
```

### The prompt slash-command processor

Relocate by grepping `command_permissions`.

It calls the skill's `getPromptForCommand` for the prompt content, normalizes
`skill.allowedTools ?? []` through the same list normalizer the frontmatter parser uses, and appends
a `command_permissions` message carrying the normalized list and the model.

It returns the messages, a `shouldQuery` flag, and the same `allowedTools` list, so the caller
receives the permission grant as data rather than having it applied behind its back.

### Key Code: Skill Tool `contextModifier`

The Skill tool's `call` method applies the `allowedTools` by wrapping the tool-use context before
the skill body runs. At 2.1.76 the wrapper was named `contextModifier`; that name is gone by
2.1.277. Relocate by grepping `alwaysAllowRules` and looking for the merge into its `command` list.

When the list is empty the context is passed through untouched. Otherwise the modifier wraps
`getAppState`, and the wrapper returns the real app state with one substitution: inside
`toolPermissionContext.alwaysAllowRules`, the `command` list becomes the de-duplicated union of the
existing entries and the skill's `allowedTools`.

That union is the difference from the template-resolution wrapper described earlier, which replaces
the list outright. Here the skill's grants are added to what the session already allows.

This is what makes the tools auto-permitted for the remainder of the skill's execution in the main
session.


## Code Path 2: Forked Skill Execution (`context: fork`)

`allowed-tools`: applied

When a skill has `context: fork` in its frontmatter, it runs in a separate subagent with an
isolated context (see "Skill Execution Context" above).  The fork path handles `allowed-tools`
correctly.

There are two entry points for forked skills:

| Entry point          | Function                                       | Trigger                                     | Location     |
| -------------------- | ---------------------------------------------- | ------------------------------------------- | ------------ |
| Direct `/skill`      | User types `/skill` at the prompt              |                                             |              |
| Skill tool           | Model calls the Skill tool with a forked skill |                                             |              |

Both prepare the fork context, then run the subagent loop.

### Flow

```
Either entry point
  → prepare fork context
    → skill.getPromptForCommand          — prompt content
    → normalize skill.allowedTools
    → wrap getAppState with those tools
    → select agent definition            — agent: field, else general-purpose
    → promptMessages = one user message holding the skill content
  ← returns { modifiedGetAppState, baseAgent, promptMessages, skillContent }
  → subagent loop
      promptMessages                     — skill content only, no conversation history
      toolUseContext with the wrapped getAppState
      availableTools                     — inherits the main session's tool list
                                         — note: no forkContextMessages passed
```

### Preparing the fork context

Relocate by grepping `No agent available for forked execution`, the error thrown when agent
selection finds nothing.

The preparation step resolves the skill's prompt content, flattening the returned blocks to their
text and joining with newlines, normalizes `allowedTools`, wraps `getAppState` with those tools,
selects a base agent, and builds the initial message list as a single user message holding the
rendered skill content.

It returns the skill content, the wrapped `getAppState`, the base agent, and those prompt messages.

The `promptMessages` array contains only one user message: the rendered skill content.  No
conversation history is included. Both callers pass it to the subagent loop without
`forkContextMessages`, so the subagent starts with a clean context.

### Wrapping getAppState with the allowed tools

An empty list returns the original accessor untouched, so the wrap is skipped entirely rather than
producing an identity wrapper.

Otherwise it returns an accessor that reads the real app state and substitutes one field: inside
`toolPermissionContext.alwaysAllowRules`, `command` becomes the de-duplicated union of the existing
entries and the skill's list. This is the same merge the Skill tool's `contextModifier` performs,
for the fork path instead of the main session.

The wrapped `getAppState` is passed to the subagent loop, so the forked subagent inherits
the skill's tool permissions.

### Agent Type Selection for Forked Skills

The fork path selects which agent definition to run the skill under, from the skill's `agent:`
frontmatter field, searched against the active agent definitions.

Fallback chain: specified agent type → `general-purpose` → first available agent.

This means a skill can declare `agent: Explore` to run in a read-only Explore subagent, or leave
the field unset to get the full-tool-access `general-purpose` agent.

### Tool Availability in Forked Skills

Both callers pass the main session's tool list through as `availableTools`, so the subagent starts
from the same set. The agent definition's `tools:` and `disallowedTools:` then narrow it, filtered
inside the subagent loop.


## Code Path 3: Subagent Skill Preloading (`skills:` in Agent YAML)

`allowed-tools`: NOT applied

When a subagent YAML file (`.claude/agents/*.md`) includes `skills: [my-skill]`, the skills are
preloaded at the start of the agent execution function.

### Flow

```
Agent tool call
  → agent execution function
    → read the agent's skills list
    → for each skill:
        find the skill among the available commands
        resolve it to a skill object
        skill.getPromptForCommand("")    — prompt content ONLY
        format the skill-loading metadata tags
        push a user message with metadata plus content
    ← skills loaded as prompt content only
    ← NO allowedTools extraction
    ← NO permission context modification
```

### Subagent skill preloading

Relocate by grepping `Preloaded skill`, the debug line emitted per skill.

For each name in the agent's `skills:` list the loader resolves the skill object and skips it with a
warning when the resolved command is not prompt-based. It then renders each surviving skill by
calling `getPromptForCommand` with empty arguments, formats the skill-loading metadata tags, and
pushes a user message whose first content block is the metadata and whose remaining blocks are the
rendered skill content.

The resolved skill object carries `allowedTools`, exactly as on the other two paths.

The preload path never reads that property and never modifies the permission context.

### Skill Metadata Tags

When skill content is injected into the conversation as a user message, a metadata string is
prepended as a separate text content block.  The metadata contains XML tags that are not
consumed by the model — they are parsed back out by Claude Code's own JavaScript for UI
rendering, prompt extraction, and conversation compaction.

The tag names are `command-name`, `command-message` and `command-args`, defined as constants and
interpolated into the metadata strings. Grep a tag name rather than a full rendered line: the
surrounding text is assembled from those constants, so the complete tag never appears as a literal.

Two metadata formats exist:

Direct `/skill` invocation:

```xml
<command-message>skill-name</command-message>
<command-name>/skill-name</command-name>
<command-args>user arguments</command-args>
```

Preloaded or non-user-invocable skills, formatted by `formatSkillLoadingMetadata`:

```xml
<command-message>skill-name</command-message>
<command-name>skill-name</command-name>
<skill-format>true</skill-format>
```

A dispatcher chooses between the two formats. A skill whose `userInvocable` is not explicitly false
gets the `/name` format. A skill loaded from `skills` or from a plugin gets the skill format.
Anything else falls back to `/name`.

The subagent preload path calls the skill formatter directly, bypassing that dispatcher.

| Aspect          | Direct invocation              | Preloaded / non-invocable         |
| --------------- | ------------------------------ | --------------------------------- |
| `command-name`  | `/skill-name` (with `/`)       | `skill-name` (no `/`)             |
| Extra tag       | `<command-args>` (if present)  | `<skill-format>true`              |

These tags are sent to the Anthropic API as part of user message content — the model sees them.
There is no system prompt instruction explaining them, but the model processes them as structured
context about what is happening in the conversation (e.g., "a skill named X was invoked").  Claude
Code's JavaScript also parses them client-side with a general-purpose XML tag extractor, for UI
rendering and bookkeeping:

| Consumer                       | Location                                           | Purpose                                          |
| ------------------------------ | -------------------------------------------------- | ------------------------------------------------ |
| UI message rendering           | Display `Skill(name)` vs `/name args` in terminal  |                                                  |
| UI message rendering, alt path | Same distinction in the alternate renderer         |                                                  |
| Prompt summary extraction      | Label compact summaries, e.g. the ctrl+o view      |                                                  |
| Conversation compaction        | Label what a user message was during summarization |                                                  |

The tags serve dual purpose: they provide the model with structured context about skill
invocations (as part of the user message content sent to the API), and they provide the
client-side TUI with rendering hints.  The `<skill-format>true` tag switches the UI between
`Skill(name)` and `/name args` display styles.  The leading `/` in `<command-name>`
distinguishes user-invoked from preloaded in the summary extractors.

Note: skill content messages are marked `isMeta: true`, which sets `isSynthetic: true` on the
API-facing message. However, `isSynthetic` does not
filter the message from API calls — it is a round-trip flag preserved through serialization.
Both the metadata tags and the skill content are sent to the model.

### Why This Is a Gap, Not Intentional Scoping

The `getAppState` wrapping in the agent execution function is intentionally restrictive for
subagents. The subagent's own `getAppState` wrapper controls what permission state it inherits:

1. It reads the parent's `getAppState()` each call (to pick up CLI-arg or global permissions)
2. It applies the agent's `permissionMode` (e.g., `dontAsk`, `acceptEdits`)
3. When `allowedTools` is explicitly provided, it replaces session-level
   rules — it doesn't merge with the parent's session grants

This means subagents don't inherit the main session's "always allow" grants (e.g., a user
pressing "always allow" for `Bash(git:*)` in the main session doesn't carry into subagents).
This is intentional.

Separately, the `getPromptForCommand` method's `getAppState` wrapping is also
intentionally scoped — it injects `allowedTools` into the template resolver's context so that
template variables can be resolved based on available permissions.  This does not propagate to
the caller.

But the absence of `allowedTools` extraction in the preload path is a gap, not a consequence of
either scoping design.  Both the direct invocation and fork paths explicitly read
`skill.allowedTools` and apply it; the preload path simply does not. The subagent's `getAppState`
wrapper already
has a mechanism for accepting `allowedTools`:

### What Would Need to Change

The subagent builds its own `getAppState` wrapper, and that wrapper already handles an
`allowedTools` argument when the agent execution function receives one: it replaces
`alwaysAllowRules` with the parent's `cliArg` entries plus the passed list as the session entries.

That argument is only passed by the in-process teammate runner. The Agent tool's invocation of the
agent execution function does not set it.

There is also an ordering problem. The wrapper is built before the skill preloading loop runs, and
the argument it checks is supplied by the caller rather than computed inside the function, so by the
time a preloaded skill's `allowedTools` are known the wrapper already exists.

To fix this, the skill preloading code could:

1. Collect `allowedTools` from each preloaded skill
2. Re-wrap the `getAppState` accessor after the loop, merging the collected list the same way the
   fork path's wrapper does.

Rebuilding the accessor after preloading is the shape the fork path already uses, so the fix is
structural rather than novel.

## Comparison Table

| Step                            | Direct (`/skill`)                        | Fork (`context: fork`)   | Subagent preload       |
| ------------------------------- | ---------------------------------------- | ------------------------ | ---------------------- |
| Execution context               | Inline in main session                   | Isolated subagent        | Inside parent subagent |
| Conversation history included   | Yes (full)                               | No (skill content only)  | No (agent context)     |
| `agent:` field used             | Ignored                                  | Yes (selects agent)      | N/A                    |
| Get prompt content              | Prompt slash-command processor           | Fork preparation         | Preload loop           |
| Read `allowedTools` from skill  | Yes                                      | Yes                      | Not done               |
| Normalize the list              | Yes                                      | Yes                      | Not done               |
| Inject into permission context  | Skill tool `contextModifier`             | Fork `getAppState` wrap  | Not done               |
| `forkContextMessages` passed    | N/A (inline)                             | Not passed               | N/A                    |
| Tools auto-permitted            | Yes                                      | Yes                      | No                     |


## Bundled Skills

Bundled skills are hardcoded into the bundle and registered through a factory function. Unlike
user-defined skills loaded from `.claude/skills/*/SKILL.md`, they carry `source: "built-in"` and
have no disk file. Relocate by grepping `built-in`.

### Registration

The factory creates skill objects and pushes them into a module-level array, which a collector
returns as a copy. An initialization function calls each bundled skill's registration in sequence at
startup.

### Bundled Skill Inventory

| Name               | Invocable | allowed-tools                      | disableModel | Line   |
| ------------------ | --------- | ---------------------------------- | ------------ | ------ |
| `claude-in-chrome` | yes       | `mcp__claude-in-chrome__*`         | no           | 547511 |
| `keybindings-help` | no        | `Read`                             | no           | 548165 |
| `debug`            | yes       | `Read`, `Grep`, `Glob`             | yes          | 548643 |
| `simplify`         | yes       | (none)                             | no           | 549123 |
| `batch`            | yes       | (none)                             | yes          | 549265 |
| `loop`             | yes       | (none)                             | no           | 549363 |
| `claude-api`       | yes       | `Read`, `Grep`, `Glob`, `WebFetch` | no           | 555890 |

Column notes:
- Invocable: whether the skill can be invoked by the user via `/name`.  Non-invocable skills
  are only triggered automatically by the model.
- `disableModel`: when `true`, the model will not auto-trigger the skill — it can only be
  invoked explicitly by the user via `/name`.

### Skill Descriptions

`claude-in-chrome` — browser automation via Chrome DevTools MCP tools.  Conditionally enabled
only when the Chrome extension is available. On invocation, instructs the model to
call `mcp__claude-in-chrome__tabs_context_mcp` first.

`keybindings-help` — help for customizing keyboard shortcuts and `~/.claude/keybindings.json`.
Not user-invocable; auto-triggered when the model detects keybinding questions.

`debug` — enables debug logging for the current session and helps diagnose issues.  Reads
session debug log files.  Argument hint: `[issue description]`.

`simplify` — reviews changed code (via `git diff`) for reuse, quality, and efficiency, then
fixes issues found.  Launches three parallel review agents internally.

`batch` — parallel work orchestration for large-scale mechanical changes across many files
(migrations, refactors, bulk renames).  Uses worktrees and PR creation.
Argument hint: `<instruction>`.

`loop` — schedules a recurring prompt or slash command on an interval.  Parses
`[interval] <prompt>` and uses `CronCreate` to schedule it.  Conditionally enabled (`VR`)
based on cron support.  Argument hint: `[interval] <prompt>`.

`claude-api` — helps build apps with the Claude API or Anthropic SDK.  Auto-detects project
language and provides SDK documentation.  Triggered when code imports `anthropic`,
`@anthropic-ai/sdk`, or `claude_agent_sdk`.

### Differences from User-Defined Skills

| Aspect                   | User-defined                              | Bundled                                  |
| ------------------------ | ----------------------------------------- | ---------------------------------------- |
| Source                   | `.claude/skills/*/SKILL.md` on disk       | Embedded in cli.prettier.js              |
| `source` property        | `"userSettings"` or `"projectSettings"`   | `"built-in"`                             |
| Factory function         | Skill factory                             | Bundled-skill factory                    |
| `disableModelInvocation` | Not supported in frontmatter              | Supported (`batch`, `debug` use it)      |
| Conditional enable       | Always enabled if file exists             | Can be gated by runtime checks           |
| `progressMessage`        | From frontmatter                          | Hardcoded to `"running"`                 |


## Plugin Skill: `security-review`

`security-review` is a plugin skill and is not registered
via the bundled-skill factory.


## How `alwaysAllowRules.command` Works

The `alwaysAllowRules` object in `toolPermissionContext` has multiple sources:

| Source    | Where Set                                    | Scope                 |
| --------- | -------------------------------------------- | --------------------- |
| `cliArg`  | CLI `--allowed-tools` flag                   | Entire session        |
| `session` | Session-level grants (user presses "always") | Entire session        |
| `command` | Skill `allowed-tools` frontmatter            | While skill is active |

When a tool permission check occurs, all three arrays are merged and checked for matching patterns.
The `command` source is the one set by skill `allowed-tools`.

The pattern syntax supports:
- Simple tool names: `Read`, `Edit`, `Bash`
- Parameterized patterns: `Bash(git diff:*)`, `Bash(npm run:*)`
- These are parsed by the shared list normalizer, which handles parenthesized arguments and
  comma/space separation


## Workaround

Since `allowed-tools` from skills is not applied in the subagent preload path, users who need
tools auto-permitted for a subagent cannot rely on the skill's `allowed-tools`.

Note: agent YAML frontmatter has `tools:` (which tools are available) and `disallowedTools:`
(which tools are excluded), but these control tool availability, not auto-permission.  There is
no `allowed-tools:` field in agent YAML.

Options for auto-permitting tools in subagents:

1. Use the `--allowed-tools` CLI flag when launching Claude Code
2. Grant tool permissions when prompted (they persist in session rules)
3. Pre-approve specific tool patterns in `settings.json` under `permissions.allow`

## Version history

- 2.1.76: three paths, of which the subagent preload path does not apply `allowed-tools`. The
  permission merge is written inline at each call site, and a skill's grants persist for the
  remainder of its execution.
- 2.1.277 spot-check. The gap is unchanged: the preload loop resolves each skill object, renders it
  and pushes it as a user message, and never reads `allowedTools`. Everything around it moved:
  - The `contextModifier` name is gone. The merge is now a pair of pure helpers, one for
    `alwaysAllowRules.command` and one for `alwaysDenyRules.command`, each a no-op on an empty list.
  - The prompt slash-command processor returns `disallowedTools` and `effort` alongside
    `allowedTools`, so a skill can now deny as well as grant.
  - Skill permissions are explicitly reset after the skill's turn unless the caller passes
    `skipSkillPermissionReset`. Grants are torn down rather than persisting, which contradicts the
    2.1.76 description above.
  - A `pollEventDeliveryGuard` clears `alwaysAllowRules.command` outright for poll-event delivery.
  - The preload loop gained three more skip conditions, each logging its own warning: not a
    prompt-based skill, disabled by policy, and an account-synced skill while skills sync is off.
  - Preloaded skills are rendered in parallel, with `isSkillPreload` set in the options, and carry a
    `promptShellHandOff` channel for commands handed to a shell.

  The rest of this doc has not been re-verified against 2.1.277. Treat its specifics as 2.1.76
  facts.
