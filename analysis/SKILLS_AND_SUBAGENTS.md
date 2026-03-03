# Skills and Subagent Integration

Version: 2.1.63

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
the subagent can see and call at all.  These are enforced by `_l()` (line 299240) which filters
the tool list before the subagent starts.

| Field             | Effect                                       | Example                      |
| ----------------- | -------------------------------------------- | ---------------------------- |
| `tools:`          | Whitelist: only these tools are available     | `tools: [Read, Grep, Glob]` |
| `disallowedTools:` | Blacklist: these tools are removed           | `disallowedTools: [Edit]`   |

If `tools:` is `["*"]` or omitted, all tools are available (minus any `disallowedTools`).
An unavailable tool cannot be called at all — the subagent doesn't even see it.

### Axis 2: Tool Permission (Skill Frontmatter)

Skill YAML (`.claude/skills/*/SKILL.md`) uses `allowed-tools:` to control which tools are
auto-permitted without user approval.  The tool must still be available (axis 1); this only
affects whether the user is prompted before the tool executes.

| Field             | Effect                                       | Example                                 |
| ----------------- | -------------------------------------------- | --------------------------------------- |
| `allowed-tools:`  | Auto-permit: no user approval prompt needed  | `allowed-tools: Bash(git diff:*), Read` |
| (no counterpart)  | There is no `disallowed-tools:` for skills   |                                         |

### Naming Confusion

The naming is inconsistent across the two systems:

| Concept           | Agent keyword      | Skill keyword     | Syntax       |
| ----------------- | ------------------ | ----------------- | ------------ |
| Tool whitelist    | `tools:`           | (none)            | camelCase    |
| Tool blacklist    | `disallowedTools:` | (none)            | camelCase    |
| Auto-permit       | (none)             | `allowed-tools:`  | kebab-case   |
| Auto-deny         | (none)             | (none)            |              |

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

Location: cli.prettier.js:518237

The `pI()` function parses the `allowed-tools` frontmatter field.  It delegates to `BPq()` which
splits comma/space-separated tool patterns, returning `null` for missing values (converted to `[]`
by `pI`).

```javascript
[source fragment removed]
```

### The Skill Object (`ew4`)

Location: cli.prettier.js:273576

Skills are loaded from `SKILL.md` files and constructed by `ew4()`.  The `allowed-tools` value
becomes the `allowedTools` property on the returned object:

```javascript
[source fragment removed]
```

### Skill Loading Pipeline

Skills are loaded from two directory patterns and one plugin source:

| Source                            | Loader function | Location    |
| -------------------------------- | --------------- | ----------- |
| `.claude/skills/*/SKILL.md`      | `sF6()`         | Line 273661 |
| `.claude/commands/*.md` (legacy) | (inline)        | Line 273780 |
| Plugin skills                    | `fJ4()`         | Line 293557 |

All three paths extract `allowed-tools` from frontmatter via `pI()` and pass it to `ew4()`.

### Template Resolution and `getPromptForCommand`

Location: cli.prettier.js:273627

The skill's `getPromptForCommand` method resolves template variables in the SKILL.md content.  It
creates a modified `getAppState` that includes the skill's `allowedTools` in the
`alwaysAllowRules.command` array, but this modification is scoped to the `nB()` template resolver:

```javascript
[source fragment removed]
```

The modified `getAppState` is only used by `nB()` for template resolution.  The caller of
`getPromptForCommand` receives only the resolved text content — the `allowedTools` injection does
not propagate to the caller's permission context.


## Code Path 1: Direct Skill Invocation (`/my-skill`)

`allowed-tools`: applied

When a user invokes `/my-skill` in the main session, the Skill tool's `call` method processes it.

### Flow

```
User types /my-skill
  → Skill tool call()                    [line 421584]
    → Cr4()                              [line 407119]
      → Sr4()                            [line 407128]
        → skill.getPromptForCommand()    [line 407129]  — get prompt content
        → Ai(skill.allowedTools ?? [])   [line 407151]  — parse allowed tools
        → wq({ type: "command_permissions", allowedTools: J })
                                         [line 407169]  — attach permissions
        → return { messages, allowedTools: J }
                                         [line 407189]  — return to caller
    ← Skill tool receives result
      → j.allowedTools                   [line 421593]  — extract allowed tools
      → contextModifier()               [line 421654]  — inject into permission context
```

### Key Code: `Sr4` (Process Prompt Slash Command)

Location: cli.prettier.js:407128

```javascript
[source fragment removed]
```

### Key Code: Skill Tool `contextModifier`

Location: cli.prettier.js:421654

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
Skill tool call()                        [line 421584]
  → skill has context === "fork"
    → VUY()                              [line 421322]
      → JN1()                            [line 454804]
        → skill.getPromptForCommand()    [line 454805]  — get prompt content
        → Ai(skill.allowedTools ?? [])   [line 454809]  — parse allowed tools
        → YtY(getAppState, w)            [line 454810]  — wrap getAppState
      ← returns { modifiedGetAppState, baseAgent, promptMessages }
      → jC({ toolUseContext: { getAppState: modifiedGetAppState } })
                                         [line 421346]  — launch subagent
```

### Key Code: `YtY` (Wrap getAppState with Allowed Tools)

Location: cli.prettier.js:454783

```javascript
[source fragment removed]
```

The wrapped `getAppState` is passed to `jC` (the subagent loop), so the forked subagent inherits
the skill's tool permissions.


## Code Path 3: Subagent Skill Preloading (`skills:` in Agent YAML)

`allowed-tools`: NOT applied

When a subagent YAML file (`.claude/agents/*.md`) includes `skills: [my-skill]`, the skills are
preloaded at the start of the `jC` function (the core agent execution loop).

### Flow

```
Agent tool call()                        [line 420471]
  → jC()                                [line 407293]  — core agent loop
    → A.skills ?? []                     [line 407371]  — read skills list
    → for each skill:
        UgY(name, commands, agent)       [line 407376]  — find skill
        mx(name, commands)               [line 407384]  — resolve skill object
        skill.getPromptForCommand("", K) [line 407395]  — get prompt content ONLY
        nI8(name, progressMessage)       [line 407397]  — wrap with metadata tags
        N.push(K8({ content: [...] }))   [line 407398]  — add as user message
    ← skills loaded as prompt content only
    ← NO allowedTools extraction
    ← NO permission context modification
```

### Key Code: Subagent Skill Preloading

Location: cli.prettier.js:407371

```javascript
[source fragment removed]
```

The code:

1. Finds and resolves each skill object (which has `allowedTools` on it)
2. Calls `getPromptForCommand` to get the rendered markdown content
3. Wraps the content with `<command-name>` / `<command-message>` metadata tags
4. Pushes it as a user message into the subagent's prompt

But it never reads `v6.allowedTools` and never modifies the permission context.

### Why This Is a Gap, Not Intentional Scoping

The `getAppState` wrapping in `jC` is intentionally restrictive for subagents.  The `I` wrapper
(line 407325) controls what permission state the subagent inherits:

1. It reads the parent's `getAppState()` each call (to pick up CLI-arg or global permissions)
2. It applies the agent's `permissionMode` (e.g., `dontAsk`, `acceptEdits`)
3. When `allowedTools` is explicitly provided, it replaces session-level rules — it doesn't
   merge with the parent's session grants

This means subagents don't inherit the main session's "always allow" grants (e.g., a user
pressing "always allow" for `Bash(git:*)` in the main session doesn't carry into subagents).
This is intentional.

Separately, the `getPromptForCommand` method's `getAppState` wrapping (line 273640) is also
intentionally scoped — it injects `allowedTools` into the template resolver's context so that
template variables can be resolved based on available permissions.  This does not propagate to
the caller.

But the absence of `allowedTools` extraction in the preload path is a gap, not a consequence of
either scoping design.  Both the direct invocation and fork paths explicitly read
`skill.allowedTools` and apply it — the preload path simply doesn't.  The `I` wrapper already
has a mechanism for accepting `allowedTools`:

### What Would Need to Change

The subagent's `getAppState` function `I` is defined at line 407325 in `jC`.  This function
already handles `allowedTools` if passed as the `X` parameter to `jC`:

```javascript
[source fragment removed]
```

However, the `allowedTools` parameter `X` is only passed by the in-process teammate runner (line
415265) and is not set by the Agent tool's invocation of `jC` (line 420729).

There is also a code ordering issue.  The `I` wrapper is defined at line 407325, and the skill
preloading loop runs at line 407371 — after `I` is already created.  The `X` parameter that `I`
checks is passed in when `jC` is called by its callers, not determined inside `jC`.

To fix this, the skill preloading code could:

1. Collect `allowedTools` from each preloaded skill
2. Re-wrap `I` after the skill loop using `YtY()` or equivalent:

```javascript
[source fragment removed]
```

This would be analogous to what `JN1` (the fork path) does at line 454810.


## Comparison Table

| Step                            | Direct (`/skill`)    | Fork (`context: fork`) | Subagent preload     |
| ------------------------------- | -------------------- | ---------------------- | -------------------- |
| Get prompt content              | `Sr4` line 407129    | `JN1` line 454805      | `jC` line 407395     |
| Read `allowedTools` from skill  | `Sr4` line 407151    | `JN1` line 454809      | Not done             |
| Parse with `Ai()`              | `Sr4` line 407151    | `JN1` line 454809      | Not done             |
| Inject into permission context  | Skill tool line 421654 (contextModifier) | `YtY` line 454810 | Not done  |
| Tools auto-permitted            | Yes                  | Yes                    | No                   |


## Bundled Skill: `security-review` (Special Case)

Location: cli.prettier.js:495863

The bundled `security-review` skill uses a third pattern.  Its `getPromptWhileMarketplaceIsPrivate`
method manually reads `allowed-tools` from the embedded SKILL.md frontmatter and injects them into
`getAppState` during template resolution:

```javascript
[source fragment removed]
```

This is a one-off implementation that bypasses the standard skill loading pipeline.  The `pN6`
factory creates a bundled skill with its own prompt-fetching logic rather than using `ew4`.


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
- These are parsed by `Ai()` (line 518063) which handles parenthesized arguments and
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
