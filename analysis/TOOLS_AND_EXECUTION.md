# TODO:

- Document ALL tool descriptions (the text Claude sees in the API) for ALL tools, since this
  influences:
  - When Claude decides to use the tool
  - HOW Claude uses it (what parameter values it generates)
  - Example: Agent tool description tells Claude to write "highly detailed task description"

# Claude Code Tools and Execution Architecture

Version: 2.1.74

## Overview

Claude Code provides tools to the LLM via the Anthropic API's `tools` parameter. Each tool is a
function that can be called by the AI to perform specific actions. Tools are defined with JSON
schemas and implemented as JavaScript async generator functions.

## Official Documentation

https://code.claude.com/docs/en/settings.md#tools-available-to-claude


## Built-in Tools

Tool registration function: `xg()` at cli.prettier.js:439329.

Tools are returned as an array.  Some are always present; others are gated by condition functions
(see [Condition Functions](#condition-functions) below).

### File Operations

| Tool           | Var   | Def line | Condition               |
| -------------- | ----- | -------- | ----------------------- |
| `Read`         | `$4`  | 239985   | Always                  |
| `Write`        | `tK`  | 413889   | Always                  |
| `Edit`         | `o4`  | 514895   | Always                  |
| `Glob`         | `rY`  | 414782   | `!l$()` (not embedded search) |
| `Grep`         | `W9`  | 414416   | `!l$()` (not embedded search) |
| `NotebookEdit` | `RJ`  | 415134   | Always                  |

### Execution

| Tool   | Var  | Def line | Condition |
| ------ | ---- | -------- | --------- |
| `Bash` | `U7` | 518603   | Always    |

### Web

| Tool        | Var   | Def line | Condition |
| ----------- | ----- | -------- | --------- |
| `WebFetch`  | `aO`  | 431458   | Always    |
| `WebSearch` | `sT`  | 432598   | Always    |

### Agent and Task Management

| Tool         | Var   | Def line | Condition | Aliases                              |
| ------------ | ----- | -------- | --------- | ------------------------------------ |
| `Agent`      | `d4`  | 406209   | Always    | `Task`                               |
| `Skill`      | `oH`  | 407430   | Always    |                                      |
| `TaskCreate` | `rL`  | 436359   | `i$()`    |                                      |
| `TaskGet`    | `Bt`  | 436490   | `i$()`    |                                      |
| `TaskUpdate` | `Rk`  | 436711   | `i$()`    |                                      |
| `TaskList`   | `gt`  | 436994   | `i$()`    |                                      |
| `TaskStop`   | `lS`  | 431765   | Always    | `KillShell`                          |
| `TaskOutput` | `iS`  | 432266   | Always    | `AgentOutputTool`, `BashOutputTool`  |

`Agent` was renamed from `Task` in 2.1.69; the old name is retained as an alias.
`TaskStop` and `TaskOutput` replace the former `KillShell` and `BashOutput` tools (aliases kept).

### Planning

| Tool            | Var   | Def line | Condition |
| --------------- | ----- | -------- | --------- |
| `EnterPlanMode` | `ut`  | 435181   | Always    |
| `ExitPlanMode`  | `Lk`  | 433038   | Always    |

### Worktree

| Tool            | Var    | Def line | Condition                   |
| --------------- | ------ | -------- | --------------------------- |
| `EnterWorktree` | `F01`  | 435326   | `XT6()` (always true in 2.1.74) |
| `ExitWorktree`  | `p01`  | 435550   | `XT6()` (always true in 2.1.74) |

### Collaboration

| Tool          | Var    | Def line | Condition        |
| ------------- | ------ | -------- | ---------------- |
| `SendMessage` | `_I`   | 439222   | `eA()` (teams)   |
| `TeamCreate`  | `EI`   | 438375   | `eA()` (teams)   |
| `TeamDelete`  | `q96`  | 438551   | `eA()` (teams)   |

### Scheduling

| Tool         | Var    | Def line | Condition |
| ------------ | ------ | -------- | --------- |
| `CronCreate` | `NR`   | 437508   | Always    |
| `CronDelete` | `nd`   | 437615   | Always    |
| `CronList`   | `UW6`  | 437713   | Always    |

### User Interaction

| Tool              | Var   | Def line | Condition |
| ----------------- | ----- | -------- | --------- |
| `AskUserQuestion` | `bw`  | 433414   | Always    |

### MCP Integration

| Tool                   | Var    | Def line | Condition |
| ---------------------- | ------ | -------- | --------- |
| `ListMcpResourcesTool` | `gl6`  | 434774   | Always    |
| `ReadMcpResourceTool`  | —      | 434934   | Always    |

MCP servers can also provide additional tools dynamically, with names like
`mcp__servername__toolname`.

### Special Purpose

| Tool               | Var   | Def line | Condition              |
| ------------------ | ----- | -------- | ---------------------- |
| `TodoWrite`        | `Fm`  | 221915   | Always                 |
| `LSP`              | `Bl6` | 434489   | Always                 |
| `StructuredOutput` | `oM`  | 280460   | Always                 |
| `ToolSearch`       | `Ev`  | 240425   | `YI()` (tier/flag)     |

### Condition Functions

| Function | Variable / env var                          | Meaning                               |
| -------- | ------------------------------------------- | ------------------------------------- |
| `l$()`   | `EMBEDDED_SEARCH_TOOLS` + non-SDK entrypoint | Embedded search mode (omits Glob/Grep) |
| `i$()`   | `CLAUDE_CODE_ENABLE_TASKS` or non-simple    | Tasks enabled                         |
| `eA()`   | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` + flag | Teams/swarm enabled                  |
| `XT6()`  | (none — always `true`)                      | Worktree mode enabled                 |
| `YI()`   | `ENABLE_TOOL_SEARCH` + subscription tier    | ToolSearch available                  |

The `xg()` array also includes several `null`-initialized slots (`z4q`, `_4q`, `w4q`, `Bk1`,
`gk1`, `Fk1`, `pk1`, etc.) that are never assigned in static code — these are plugin extension
points for dynamically registered tools.


## Example Tool Description: Read

Location: cli.prettier.js (near line 239985)

```javascript
[source fragment removed]
```


## Tool Execution

### How Tools Are Sent to Claude

Tools are sent as part of the Anthropic API request:

```javascript
[source fragment removed]
```

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

Every tool execution checks permissions:

```javascript
[source fragment removed]
```

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
