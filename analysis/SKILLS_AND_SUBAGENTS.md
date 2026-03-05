# Skills and Subagent Integration

Version: 2.1.69

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
the subagent can see and call at all.  These are enforced by `Ki()` (line 291138) which filters
the tool list before the subagent starts.

| Field              | Effect                                       | Example                      |
| ------------------ | -------------------------------------------- | ---------------------------- |
| `tools:`           | Whitelist: only these tools are available     | `tools: [Read, Grep, Glob]` |
| `disallowedTools:` | Blacklist: these tools are removed            | `disallowedTools: [Edit]`   |

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


## Skill Object Construction

### Parsing `allowed-tools` from Frontmatter

Location: cli.prettier.js:532591

The `Tkq()` function parses the `allowed-tools` frontmatter field.  It handles string and array
input, normalizing via `ti()`.  Returns `null` for missing values.  The wrapper `Zx()` (line
532608) converts `null` to `[]`:

```javascript
[source fragment removed]
```

### The Skill Object (`f54`)

Location: cli.prettier.js:252173

Skills are loaded from `SKILL.md` files and constructed by `f54()`.  The `allowed-tools` value
becomes the `allowedTools` property on the returned object:

```javascript
[source fragment removed]
```

### Skill Loading Pipeline

Skills are loaded from two directory patterns and one plugin source:

| Source                             | Loader function | Location    |
| --------------------------------- | --------------- | ----------- |
| `.claude/skills/*/SKILL.md`       | `_Q6()`         | Line 252259 |
| `.claude/commands/*.md` (legacy)  | `Ro9()`         | Line 252377 |
| Plugin skills                     | `eE8()`         | Line 283562 |

All three paths extract `allowed-tools` from frontmatter via `Zx()` and pass it to `f54()`.

### Template Variables

Location: cli.prettier.js:252222

The skill's `getPromptForCommand` method resolves template variables and performs substitutions
before returning the rendered content.  Two built-in template variables are available in SKILL.md:

| Variable               | Value                          | Added in |
| ---------------------- | ------------------------------ | -------- |
| `${CLAUDE_SKILL_DIR}`  | Absolute path to skill's dir   | 2.1.69   |
| `${CLAUDE_SESSION_ID}` | Current session UUID           | ≤2.1.63  |

`CLAUDE_SKILL_DIR` resolves to the skill's directory (e.g., `.claude/skills/my-skill`).  On
Windows, backslashes are normalized to forward slashes.  This lets SKILL.md reference companion
files (scripts, templates, data) relative to the skill's own location.  The substitution occurs
in both the standard skill path (`f54`, line 252230) and the plugin skill path (line 283274).

`CLAUDE_SESSION_ID` resolves to the session UUID via `i1()`.

### Template Resolution and `getPromptForCommand`

The method also creates a modified `getAppState` that includes the skill's `allowedTools` in the
`alwaysAllowRules.command` array, but this modification is scoped to the `gg()` template resolver:

```javascript
[source fragment removed]
```

The modified `getAppState` is only used by `gg()` for template resolution.  The caller of
`getPromptForCommand` receives only the resolved text content — the `allowedTools` injection does
not propagate to the caller's permission context.


## Code Path 1: Direct Skill Invocation (`/my-skill`)

`allowed-tools`: applied

When a user invokes `/my-skill` in the main session, the Skill tool's `call` method processes it.

### Flow

```
User types /my-skill
  → Skill tool call()                    [line 420026]
    → He4()                              [line 404951]
      → skill.getPromptForCommand()      [line 404952]  — get prompt content
      → ti(skill.allowedTools ?? [])     [line 404973]  — parse allowed tools
      → i4({ type: "command_permissions", allowedTools: J })
                                         [line 404991]  — attach permissions
      → return { messages, allowedTools: J }
                                         [line 405011]  — return to caller
    ← Skill tool receives result
      → J.allowedTools                   [line 420038]  — extract allowed tools
      → contextModifier()               [line 420098]  — inject into permission context
```

### Key Code: `He4` (Process Prompt Slash Command)

Location: cli.prettier.js:404951

```javascript
[source fragment removed]
```

### Key Code: Skill Tool `contextModifier`

Location: cli.prettier.js:420098

The Skill tool's `call` method applies the `allowedTools` via a `contextModifier` that wraps
`getAppState` to add the tools to `alwaysAllowRules.command`:

```javascript
[source fragment removed]
```

This is what makes the tools auto-permitted for the remainder of the skill's execution in the main
session.


## Code Path 2: Forked Skill Execution (`context: fork`)

`allowed-tools`: applied

When a skill has `context: fork` in its frontmatter, it runs in a separate subagent.  The fork
path handles `allowed-tools` correctly.

### Flow

```
Skill tool call()                        [line 420026]
  → skill has context === "fork"
    → mrY()                              [line 419765]
      → mN1()                           [line 453308]
        → skill.getPromptForCommand()    [line 453309]  — get prompt content
        → ti(skill.allowedTools ?? [])   [line 453313]  — parse allowed tools
        → f7z(getAppState, w)            [line 453314]  — wrap getAppState
      ← returns { modifiedGetAppState, baseAgent, promptMessages }
      → gS({ toolUseContext: { getAppState: modifiedGetAppState } })
                                         [line 419789]  — launch subagent
```

### Key Code: `f7z` (Wrap getAppState with Allowed Tools)

Location: cli.prettier.js:453287

```javascript
[source fragment removed]
```

The wrapped `getAppState` is passed to `gS` (the subagent loop), so the forked subagent inherits
the skill's tool permissions.


## Code Path 3: Subagent Skill Preloading (`skills:` in Agent YAML)

`allowed-tools`: NOT applied

When a subagent YAML file (`.claude/agents/*.md`) includes `skills: [my-skill]`, the skills are
preloaded at the start of the agent execution function.

### Flow

```
Agent tool call()                        [line 420026]
  → agent execution function             [line 405117]
    → A.skills ?? []                     [line 405195]  — read skills list
    → for each skill:
        ccY(name, commands, agent)       [line 405200]  — find skill
        Tb(name, commands)              [line 405208]  — resolve skill object
        skill.getPromptForCommand("", K) [line 405222]  — get prompt content ONLY
        y6(name, progressMessage)       [line 405224]  — wrap with metadata tags
        V.push(Y8({ content: [...] }))  [line 405225]  — add as user message
    ← skills loaded as prompt content only
    ← NO allowedTools extraction
    ← NO permission context modification
```

### Key Code: Subagent Skill Preloading

Location: cli.prettier.js:405195

```javascript
[source fragment removed]
```

The code:

1. Finds and resolves each skill object (which has `allowedTools` on it)
2. Calls `getPromptForCommand` to get the rendered markdown content
3. Wraps the content with `<command-name>` / `<command-message>` metadata tags
4. Pushes it as a user message into the subagent's prompt

But it never reads `z6.allowedTools` and never modifies the permission context.

### Skill Metadata Tags

When skill content is injected into the conversation as a user message, a metadata string is
prepended as a separate text content block.  The metadata contains XML tags that are not
consumed by the model — they are parsed back out by Claude Code's own JavaScript for UI
rendering, prompt extraction, and conversation compaction.

Tag name constants (line 54273):

```javascript
[source fragment removed]
```

Two metadata formats exist:

`we4` (line 404928) — direct `/skill` invocation:

```xml
<command-message>skill-name</command-message>
<command-name>/skill-name</command-name>
<command-args>user arguments</command-args>
```

`Oe4` / `formatSkillLoadingMetadata` (line 404920) — preloaded or non-user-invocable skills:

```xml
<command-message>skill-name</command-message>
<command-name>skill-name</command-name>
<skill-format>true</skill-format>
```

The dispatch logic in `BcY` (line 404936) chooses the format:

```javascript
[source fragment removed]
```

The subagent preload path (line 405224) calls `Oe4` directly, bypassing `BcY`.

| Aspect          | Direct invocation (`we4`)      | Preloaded / non-invocable (`Oe4`) |
| --------------- | ------------------------------ | --------------------------------- |
| `command-name`  | `/skill-name` (with `/`)       | `skill-name` (no `/`)             |
| Extra tag       | `<command-args>` (if present)  | `<skill-format>true`              |

These tags are sent to the Anthropic API as part of user message content — the model sees them.
There is no system prompt instruction explaining them, but the model processes them as
structured context about what is happening in the conversation (e.g., "a skill named X was
invoked").  Claude Code's JavaScript also parses them client-side using `t4()` (line 533178),
a general-purpose XML tag extractor, for UI rendering and bookkeeping:

| Consumer                       | Location     | Purpose                                         |
| ------------------------------ | ------------ | ------------------------------------------------ |
| UI message rendering           | Line 394058  | Display `Skill(name)` vs `/name args` in terminal |
| UI message rendering (alt)     | Line 567215  | Same distinction in alternate render path         |
| Prompt summary extraction      | Line 535976  | Label compact summaries (e.g., for ctrl+o view)   |
| Conversation compaction        | Line 601277  | Label what a user message was during summarization |

The tags serve dual purpose: they provide the model with structured context about skill
invocations (as part of the user message content sent to the API), and they provide the
client-side TUI with rendering hints.  The `<skill-format>true` tag switches the UI between
`Skill(name)` and `/name args` display styles.  The leading `/` in `<command-name>`
distinguishes user-invoked from preloaded in the summary extractors.

Note: skill content messages are marked `isMeta: true` (line 404989), which sets
`isSynthetic: true` on the API-facing message (line 409807).  However, `isSynthetic` does not
filter the message from API calls — it is a round-trip flag preserved through serialization.
Both the metadata tags and the skill content are sent to the model.

### Why This Is a Gap, Not Intentional Scoping

The `getAppState` wrapping in the agent execution function is intentionally restrictive for
subagents.  The `m` wrapper (line 405148) controls what permission state the subagent inherits:

1. It reads the parent's `getAppState()` each call (to pick up CLI-arg or global permissions)
2. It applies the agent's `permissionMode` (e.g., `dontAsk`, `acceptEdits`)
3. When `allowedTools` is explicitly provided (the `D` parameter), it replaces session-level
   rules — it doesn't merge with the parent's session grants

This means subagents don't inherit the main session's "always allow" grants (e.g., a user
pressing "always allow" for `Bash(git:*)` in the main session doesn't carry into subagents).
This is intentional.

Separately, the `getPromptForCommand` method's `getAppState` wrapping (line 252238) is also
intentionally scoped — it injects `allowedTools` into the template resolver's context so that
template variables can be resolved based on available permissions.  This does not propagate to
the caller.

But the absence of `allowedTools` extraction in the preload path is a gap, not a consequence of
either scoping design.  Both the direct invocation and fork paths explicitly read
`skill.allowedTools` and apply it — the preload path simply doesn't.  The `m` wrapper already
has a mechanism for accepting `allowedTools`:

### What Would Need to Change

The subagent's `getAppState` function `m` is defined at line 405148.  This function
already handles `allowedTools` if passed as the `D` parameter to the agent execution function:

```javascript
[source fragment removed]
```

However, the `allowedTools` parameter `D` is only passed by the in-process teammate runner and
is not set by the Agent tool's invocation of the agent execution function.

There is also a code ordering issue.  The `m` wrapper is defined at line 405148, and the skill
preloading loop runs at line 405195 — after `m` is already created.  The `D` parameter that `m`
checks is passed in when the function is called by its callers, not determined inside it.

To fix this, the skill preloading code could:

1. Collect `allowedTools` from each preloaded skill
2. Re-wrap `m` after the skill loop using `f7z()` or equivalent:

```javascript
[source fragment removed]
```

This would be analogous to what `mN1` (the fork path) does at line 453314.


## Comparison Table

| Step                            | Direct (`/skill`)      | Fork (`context: fork`)   | Subagent preload       |
| ------------------------------- | ---------------------- | ------------------------ | ---------------------- |
| Get prompt content              | `He4` line 404952      | `mN1` line 453309        | loop at line 405222    |
| Read `allowedTools` from skill  | `He4` line 404973      | `mN1` line 453313        | Not done               |
| Parse with `ti()`              | `He4` line 404973      | `mN1` line 453313        | Not done               |
| Inject into permission context  | Skill tool line 420098 (contextModifier) | `f7z` line 453314 | Not done               |
| Tools auto-permitted            | Yes                    | Yes                      | No                     |


## Bundled Skill: `security-review` (Special Case)

Location: cli.prettier.js:498973

The bundled `security-review` skill uses a third pattern.  Its `getPromptWhileMarketplaceIsPrivate`
method manually reads `allowed-tools` from the embedded SKILL.md frontmatter and injects them into
`getAppState` during template resolution:

```javascript
[source fragment removed]
```

This is a one-off implementation that bypasses the standard skill loading pipeline.  The `uN6`
factory creates a bundled skill with its own prompt-fetching logic rather than using `f54`.


## How `alwaysAllowRules.command` Works

The `alwaysAllowRules` object in `toolPermissionContext` has multiple sources:

| Source    | Where Set                                    | Scope                |
| --------- | -------------------------------------------- | -------------------- |
| `cliArg`  | CLI `--allowed-tools` flag                   | Entire session       |
| `session` | Session-level grants (user presses "always") | Entire session       |
| `command` | Skill `allowed-tools` frontmatter            | While skill is active |

When a tool permission check occurs, all three arrays are merged and checked for matching patterns.
The `command` source is the one set by skill `allowed-tools`.

The pattern syntax supports:
- Simple tool names: `Read`, `Edit`, `Bash`
- Parameterized patterns: `Bash(git diff:*)`, `Bash(npm run:*)`
- These are parsed by `ti()` (line 532435) which handles parenthesized arguments and
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
