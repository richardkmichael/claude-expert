# TODO:

- Document ALL tool descriptions (the text Claude sees in the API) for ALL tools, since this
  influences:
  - When Claude decides to use the tool
  - HOW Claude uses it (what parameter values it generates)
  - Example: Agent tool description tells Claude to write "highly detailed task description"

# Claude Code Tools and Execution Architecture

Verified against: cli.prettier.js 2.1.296 (2026-10-14)

Scope note: the Built-in Tools section below is verified against 2.1.207, except the task list
gating under "Condition gates", which was re-checked at 2.1.296. Sections from
"Example Tool Description: Read" onward still carry 2.1.76-era line numbers and pasted code and
have not been re-checked — treat their specifics as suspect until retrofitted.

## Overview

Claude Code provides tools to the LLM via the Anthropic API's `tools` parameter. Each tool is a
function that can be called by the AI to perform specific actions. Tools are defined with JSON
schemas and implemented as JavaScript async generator functions.

## Official Documentation

https://code.claude.com/docs/en/settings.md#tools-available-to-claude


## Built-in Tools

A single registry function returns the built-in tool array. Entries fall into three shapes:

- Unconditional — listed in the array literal directly.
- Additive-gated — spread behind a predicate, e.g. the task tools.
- Subtractive — built unconditionally, then filtered out by an omit-set. Only `Glob` and `Grep`
  work this way, and only embedded search populates that set.

Registry membership is necessary but not sufficient. A second layer filters the constructed array
by each tool's own `isEnabled()`, so a tool can be in the registry and still absent from a session.
MCP tools (`mcp__<server>__<tool>`) and skill tools (`skill__…`) are added by separate paths,
not by this function.

Re-location: start from a tool-name literal, which survives minification, and walk outward to the
registry.

    rg -n 'var [A-Za-z_$0-9]+ = "Glob"[;,]'   # -> the name const for Glob
    rg -n '\b<that const>\b'                  # -> the registry (the array with the omit-set filter)

Expected shape: an array literal mixing bare identifiers, `...(pred() ? [x] : [])` spreads, and one
`...[glob, grep].filter((t) => !omitSet().has(t.name))`.

□ the array contains a subtractive filter for exactly Glob and Grep □ every other conditional
entry is an additive spread.

### File Operations

| Tool           | Condition                              |
| -------------- | -------------------------------------- |
| `Read`         | Always                                 |
| `Write`        | Always                                 |
| `Edit`         | Always                                 |
| `NotebookEdit` | Always                                 |
| `Glob`         | Omitted under embedded search          |
| `Grep`         | Omitted under embedded search          |

### Execution

| Tool         | Condition                                                      |
| ------------ | -------------------------------------------------------------- |
| `Bash`       | Shell is bash-capable                                          |
| `PowerShell` | `CLAUDE_CODE_USE_POWERSHELL_TOOL`, or Windows without git-bash |

### Web

| Tool        | Condition |
| ----------- | --------- |
| `WebFetch`  | Always    |
| `WebSearch` | Always    |

### Agent and Task Management

| Tool         | Condition       | Aliases                 |
| ------------ | --------------- | ----------------------- |
| `Agent`      | Always          | `Task`                  |
| `Skill`      | Always          |                         |
| `TaskCreate` | Task list tools |                         |
| `TaskGet`    | Task list tools |                         |
| `TaskUpdate` | Task list tools |                         |
| `TaskList`   | Task list tools |                         |
| `TaskStop`   | Always          | `KillShell`, `KillBash` |
| `TaskOutput` | Always          | see below               |

`Agent` is the primary name; `Task` is retained as an alias. `TaskStop` and `TaskOutput` replace
the former `KillShell` and `BashOutput` tools, keeping the old names as aliases. `TaskOutput`
carries four: `AgentOutputTool`, `BashOutputTool`, `AgentOutput`, `BashOutput`. It renders to the
user as "Task Output".

### Planning

| Tool            | Condition |
| --------------- | --------- |
| `EnterPlanMode` | Always    |
| `ExitPlanMode`  | Always    |

### Worktree

| Tool            | Condition                    |
| --------------- | ---------------------------- |
| `EnterWorktree` | Worktree mode (always true)  |
| `ExitWorktree`  | Worktree mode (always true)  |

### Collaboration

| Tool              | Condition | Aliases |
| ----------------- | --------- | ------- |
| `SendMessage`     | Always    |         |
| `SendUserMessage` | Always    | `Brief` |
| `SendUserFile`    | Always    |         |
| `EndConversation` | Always    |         |

`SendMessage` is no longer gated on a teams/swarm flag.

### Scheduling

| Tool             | Condition |
| ---------------- | --------- |
| `CronCreate`     | Always    |
| `CronDelete`     | Always    |
| `CronList`       | Always    |
| `ScheduleWakeup` | Always    |

### User Interaction

| Tool              | Condition |
| ----------------- | --------- |
| `AskUserQuestion` | Always    |

### MCP Integration

| Tool                      | Condition | Aliases                |
| ------------------------- | --------- | ---------------------- |
| `ListMcpResourcesTool`    | Always    | `ListMcpResources`     |
| `ReadMcpResourceTool`     | Always    | `ReadMcpResource`      |
| `ReadMcpResourceDirTool`  | Always    | `ReadMcpResourceDir`   |
| `WaitForMcpServers`       | Always    |                        |
| `SearchMcpRegistry`       | Always    |                        |
| `SuggestConnectors`       | Always    |                        |
| `ListConnectors`          | Always    |                        |

MCP servers also provide tools dynamically, named `mcp__<servername>__<toolname>`.

### Special Purpose

| Tool                       | Condition                                        |
| -------------------------- | ------------------------------------------------ |
| `TodoWrite`                | Legacy todo tool (see Condition gates)           |
| `LSP`                      | Always (gate is a literal — see Condition gates) |
| `ReportFindings`           | Always                                           |
| `REPL`                     | Always                                           |
| `Workflow`                 | Always (alias `RunWorkflow`)                     |
| `Monitor`                  | Always                                           |
| `Artifact`                 | Always                                           |
| `Projects`                 | Always                                           |
| `DesignSync`               | Always                                           |
| `ClaudeDesign`             | `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` unset |
| `PushNotification`         | Always                                           |
| `RemoteTrigger`            | Always                                           |
| `ShareOnboardingGuide`     | Always                                           |
| `ShowOnboardingRolePicker` | Always                                           |
| `ToolSearch`               | Tool search enabled                              |

Plugin and skill tools (`SearchPlugins`, `SearchSkills`, `SuggestPluginInstall`, `SuggestSkills`,
`ListPlugins`, `ListSkills`) are spread in as a group from a plugin-skill tool list.

`StructuredOutput` is not a registry entry. It is attached per-request when a caller forces
schema-constrained output, which is why the tool-lookup path treats it as expected-absent alongside
`mcp__`-prefixed names.

The registry array carries several permanently-`null` slots, each referenced only by its own `null`
assignment and its guarded spread. They contribute nothing in shipped builds.

### Condition gates

Gates are described by what drives them. Minified predicate names churn every release, so each gate
below names the env-var literal or behavioral string to relocate it by.

Embedded search — on unless the session opts out via the CLI, and the entrypoint is not
`local-agent` (the SDK carve-out). Anchor: `CLAUDE_CODE_ENTRYPOINT !== "local-agent"`.

Search-tools opt-in — true when `Glob` or `Grep` is named in `--tools` or `--allowedTools`. Turning
it on turns embedded search off. Anchor: `setSearchToolsOptIn`.

Bash-capable shell — true on any non-Windows platform; on Windows, only if git-bash is found, via
`CLAUDE_CODE_GIT_BASH_PATH` or the standard install locations. Anchor: `CLAUDE_CODE_GIT_BASH_PATH`.

Task list flavor — default on. Only `CLAUDE_CODE_ENABLE_TASKS` set to a false-y value turns it off.
When on, the session checklist is `TaskCreate` / `TaskGet` / `TaskUpdate` / `TaskList`. When off,
it is the single legacy `TodoWrite` tool. Anchor: `CLAUDE_CODE_ENABLE_TASKS`.

Todo tools available — a second gate, independent of the flavor. Neither `TodoWrite` nor the Task
tools are registered unless it passes. `TaskCreate` and its siblings require flavor on and this
gate; `TodoWrite` requires flavor off and this gate. It passes when any of these holds:

- The session is a background (`bg`) or job session.
- `--tools` or `--allowedTools` names any of `TodoWrite`, `TaskCreate`, `TaskGet`, `TaskUpdate`,
  `TaskList` (launch-time opt-in).
- The main-loop model is not resolved yet, or is a Bedrock `application-inference-profile` ID.
- The main-loop model is in a fixed list of older families: the Claude 3 and 3.5/3.7 models, Opus
  4.0 through 4.7, Sonnet 4.0 through 4.6, and Haiku 4.5. Later model families, such as the
  Claude 5 models, are not in the list.
- `CLAUDE_CODE_ENABLE_TODO_TOOLS` is set to a true-y value.

On a model outside the list, with no opt-in, the session has no checklist tool at all, and the
model has no task list to show. Anchors: `CLAUDE_CODE_ENABLE_TODO_TOOLS`, `"claude-haiku-4-5"`
(end of the model list), and the tool search hints `"manage the session task checklist"`
(`TodoWrite`) and `"create a task in the task list"` (`TaskCreate`). All five tools set
`shouldDefer`, so under tool search they appear by name until loaded. The `todoFeatureEnabled`
setting ("Enable the todo / task tracking panel") defaults to true.

The source carries no comment giving the reason for the model list. The published docs do: the
Agent SDK todo-tracking page (`/en/agent-sdk/todo-tracking`, "Model availability") says newer
models keep track of multi-step work without a written checklist, and the tool definitions and
reminders cost context. The same page says the default set applies from 2.1.268 and that a model ID
Claude Code does not recognize, such as a custom name behind an LLM gateway, is treated as outside
the list. Its opt-ins match the source: name a tool in `allowedTools` or `tools`, or set
`CLAUDE_CODE_ENABLE_TODO_TOOLS=1`. The opt-in variable first appears in the local bundles at 2.1.263.

Worktree mode — hardcoded true. Anchor: `isWorktreeModeEnabled`.

Tool search enabled — driven by `ENABLE_TOOL_SEARCH`, default on for first-party
`api.anthropic.com`. Vetoed by a non-first-party provider (Bedrock, Vertex, Foundry), by
`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`, or by a `hipaa` compliance taint delivered in the server
policy response — the last is org-side and not user-settable. Anchor: `ENABLE_TOOL_SEARCH`.

PowerShell tool — `CLAUDE_CODE_USE_POWERSHELL_TOOL` on non-Windows; on Windows, true unless
explicitly disabled or git-bash is present, with a Statsig gate as the fallback. Anchors:
`CLAUDE_CODE_USE_POWERSHELL_TOOL`, `tengu_cobalt_ridge`.

Two gates read as conditional but are not. The `LSP` gate and the first check of the embedded-search
gate both parse the literal string `"true"` through the env-truthiness helper, so they always pass.
Worktree mode returns true unconditionally. Treat all three as always-on until the literal changes.

The env-truthiness helper accepts `1`/`true`/`yes`/`on`; its false-y twin accepts `0`/`false`/`no`/
`off`. Both return false for unset, so they are not complements — that is how tri-state defaults are
expressed.

### Embedded search (Glob and Grep removal)

On a native build, Claude Code drops the `Glob` and `Grep` tools from the registry and routes file
search through the Bash tool instead. The shell snapshot injects `find`, `grep`, and `rg` functions
that re-exec the `claude` binary with a forced `argv[0]`, so one multi-call binary acts as bfs,
ugrep, or ripgrep. See `BASH_TOOL_EXECUTION.md` ("Search-tool wrappers") for the wrapper mechanics
and the pinned flag sets.

The omit-set is `{Glob, Grep}` when embedded search is on and the shell is bash-capable; otherwise
it is empty. Consequences worth knowing:

- The gate is consulted wherever tool lists are built, including subagent tool lists. A subagent
  whose definition names `Grep` or `Glob` still does not receive them — the frontmatter is not
  consulted for this. Built-in agent prompts branch on the same gate, telling the agent to use
  `` `find` ``/`` `grep` `` via Bash rather than the tools.
- The only way back is naming `Glob` or `Grep` in `--tools` or `--allowedTools` on the CLI. That
  sets the opt-in flag as a side effect, which turns embedded search off and restores both tools.
  There is no dedicated switch, no settings.json key, and no env var that reaches it — the sole
  writer is the CLI-flag parser.
- `EMBEDDED_SEARCH_TOOLS` does not control this. The name survives as an env-schema entry and is
  still parsed off `process.env`, but nothing reads the parsed value; the gate's own check is the
  folded literal `"true"`. Setting it has no effect.
- Windows without git-bash keeps `Glob` and `Grep`, because the omit-set also requires a
  bash-capable shell.

Re-location: `rg -n 'CLAUDE_CODE_ENTRYPOINT !== "local-agent"'` lands in the embedded-search gate;
`rg -n 'setSearchToolsOptIn'` lands on the opt-in setter, whose single call site is the
`--allowedTools` / `--tools` parser.

□ omit-set is exactly `{Glob, Grep}` □ opt-in has exactly one writer □ `EMBEDDED_SEARCH_TOOLS` has
exactly one occurrence (its schema declaration).

### Build-artifact caveat

The prettified bundle is extracted from a platform-specific native binary, and the build
constant-folds the platform accessor — in the darwin-arm64 artifact it returns the literal
`"macos"`. Every `=== "windows"` and `=== "wsl"` branch is therefore dead code in that artifact,
including the Windows halves of the bash-capable and PowerShell gates. Read those branches for
source semantics, but do not conclude from one artifact that a platform check is live or dead in
general; per-platform bundles differ.


## Tool descriptions

Tool descriptions are template literals assembled at module scope, with interpolations for
runtime-varying values. The Read tool's description is representative: it interpolates the default
line cap and the per-line truncation width, names the Bash tool through a variable rather than a
literal, and conditionally includes its PDF sentence behind a capability check.

Relocate any tool's description by grepping a distinctive sentence from it that cannot span an
interpolation boundary, for example `Results are returned using cat -n format`. The verbatim text of
every description is in `PROMPTS_RENDERED.md`; this doc does not duplicate it.

Tripwire: a description sentence that stops matching is either reworded or newly interpolated. Check
for the latter before recording the former as a change.

## Tool Execution

### How Tools Are Sent to Claude

Tools are sent as part of the Anthropic API request, in the `tools` array alongside `model`,
`messages`, `system` as an array of content blocks, `tool_choice` and `max_tokens`. See
`ANTHROPIC_API_USAGE.md` for the full request shape and how each field is built.

### Tool Approval System

Tools can be categorized as:
- No approval required — execute automatically
- Requires permission — user must approve each use
- Wildcard rules — pattern-based approval (e.g., `Bash(git:)`)

Example tools without approval requirement:
```
mcp__code-intel__, Bash(cat:), Bash(git restore:), Read, Edit, Grep, Glob
```

## The Agent/Task Tool and Subagents

Extracted to [TASK_TOOL_AND_SUBAGENTS.md](TASK_TOOL_AND_SUBAGENTS.md).

Covers: built-in agents (general-purpose, statusline-setup, Explore, Plan, claude-code-guide),
the team/swarm system (teammates, SendMessageTool, TeammateTool), task management tools
(TaskCreate/Update/Get/List), magic-docs agent, agent loading pipeline, system prompts, and
the Agent tool implementation.

## MCP Tools

MCP (Model Context Protocol) servers can provide additional tools dynamically.

### MCP Tool Naming

MCP tools are prefixed with `mcp__servername__`:
- `mcp__code-intel__find_symbol_by_name`
- `mcp__code-intel__get_code_context`
- `mcp__toolbox__find`

### MCP Tool Loading

MCP tools are:
1. Discovered from connected MCP servers
2. Transformed to Claude Code's tool format
3. Added to the tools array sent to the API
4. Available in both main session and subagents (unless filtered)

## Tool Permission Context

Every tool execution checks permissions. The context is not held separately: an accessor on the
tool-use context reads `toolPermissionContext` off the current app state each time it is called, so
a permission change made mid-session applies to the next tool call without re-plumbing.

Permission modes:
- `ask` — ask user for each tool use
- `auto` — execute approved tools automatically
- `plan` — planning mode (different prompts)

## Bash Tool

The Bash tool has special capabilities:
- Can run in foreground or background (`run_in_background: true`)
- Background processes get an ID
- Use `TaskOutput` (alias: `BashOutputTool`) to read output from background processes
- Use `TaskStop` (alias: `KillShell`) to terminate background processes

### Bash Tool Pattern Matching

Bash commands can be approved with patterns:
- `Bash(git:)` — all git commands
- `Bash(cat:)` — all cat commands
- `Bash(npm --silent pack:)` — specific npm commands

## Per-release facts

Verified against the local bundle named on each line.

- 2.1.207: `EMBEDDED_SEARCH_TOOLS` is vestigial. It remains an env-schema entry and is still parsed
  off `process.env`, but no code reads the parsed value; the gate's own flag check is the folded
  literal `"true"`. Setting the variable has no effect.
- 2.1.207: the only opt-out from embedded search is naming `Glob` or `Grep` in `--tools` or
  `--allowedTools`; the opt-in flag has exactly one writer, the CLI-flag parser.
- 2.1.207: `SendMessage` is unconditional — no longer gated on a teams/swarm flag. `TeamCreate` and
  `TeamDelete` name consts still exist but the registry does not return them.
- 2.1.207: `StructuredOutput` is not a registry entry; it is attached per-request for
  schema-constrained output.
- 2.1.207: registry additions since the 2.1.76 pass — `ReportFindings`, `REPL`, `Workflow`,
  `Monitor`, `Artifact`, `Projects`, `DesignSync`, `ClaudeDesign`, `PushNotification`,
  `RemoteTrigger`, `ScheduleWakeup`, `SendUserMessage`, `SendUserFile`, `EndConversation`,
  `WaitForMcpServers`, `ReadMcpResourceDirTool`, `SearchMcpRegistry`, `SuggestConnectors`,
  `ListConnectors`, `ShareOnboardingGuide`, `ShowOnboardingRolePicker`, `PowerShell`, and the
  plugin/skill tool group.

Attributed to release notes, not verified against a local bundle (earliest local version is 2.1.168,
which already has the behavior, so these introduction points cannot be bisected locally):

- 2.1.117: native builds moved file search into the Bash tool and dropped `Glob`/`Grep` from the
  registry.
- 2.1.162: naming `Glob`/`Grep` in `--tools` / `--allowedTools` restores the dedicated tools.

## Version history

- 2.1.296: the task-list gating in "Condition gates" matches this bundle. The polarity of
  `CLAUDE_CODE_ENABLE_TASKS` changed over time, so advice for older versions differs:
  - Up to 2.1.138: a true-y value enabled the Task tools, and an unset variable enabled them only in
    interactive sessions. Non-interactive (`-p`) and SDK sessions defaulted to `TodoWrite`.
  - 2.1.154 to 2.1.207: a true-y value selected `TodoWrite`. Unset enabled the Task tools in every
    mode.
  - 2.1.220 onward: only an explicit false-y value (`0`, `false`, `no`, `off`) selects `TodoWrite`.
    `CLAUDE_CODE_ENABLE_TASKS=1` therefore means the Task tools again.
  - The model gate first appears at 2.1.263, as a table of newer families plus a remote flag
    (`tengu_rosy_wren`). By 2.1.277 it is the fixed list of older models, with no remote flag.
  - `TaskStop` and `TaskOutput` have no flavor or model gate.
  - `CLAUDE_CODE_SESSION_KIND=bg` is one of the "background or job session" conditions that
    passes the second gate, and `CLAUDE_CODE_TASK_LIST_ID` selects which task list the tools use.
- 2.1.283: the task-list gating in "Condition gates" was re-checked against this bundle, and the
  gate and model list were spot-checked in the 2.1.285 binary. Earlier text in this doc listed
  `TodoWrite` as always registered and the task tools as gated only by `CLAUDE_CODE_ENABLE_TASKS`.
  Both were incomplete: a model-family list and `CLAUDE_CODE_ENABLE_TODO_TOOLS` gate the whole
  group, so sessions on newer model families have no checklist tool unless opted in.
