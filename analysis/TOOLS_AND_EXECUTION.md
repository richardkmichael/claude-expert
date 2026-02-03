# TODO:

- Update built-in tool list with those in official documentation but missing from this document
- What is the difference between the Bash and BashOutput tools?  The BashOutput tool is not in the
  official documentation, why?
- Why is there no parenthesized function name with BashOutput, TodoWrite and KillShell -- are they
  anonymous functions?  Same with List/ReadMcpResourceTool(s).
- Document ALL tool descriptions (the text Claude sees in the API) for ALL tools, since this
  influences:
  - When Claude decides to use the tool
  - HOW Claude uses it (what parameter values it generates)
  - Example: Task tool description tells Claude to write "highly detailed task description"

# Claude Code Tools and Execution Architecture

Version: 2.0.29

## Overview

Claude Code provides tools to the LLM via the Anthropic API's `tools` parameter. Each tool is a
function that can be called by the AI to perform specific actions. Tools are defined with JSON
schemas and implemented as JavaScript async generator functions.

## Official Documentation

https://code.claude.com/docs/en/settings.md#tools-available-to-claude


## Built-in Tools

TODO: rewrite these as a markdown table:
| Tool | Purpose | JavaScript reference | Built-in |

### File Operations
1. Read (H5) - Line 79935
2. Write (PJ) - Line 79964
3. Edit (B3) - Line 79963
4. NotebookEdit (bAA) - Line 79977

### Search and Discovery
5. Glob (dK) - Line 79873
6. Grep (aC) - Line 79894

### Command Execution
7. Bash (T4) - Line 78616
8. BashOutput - Line 449469
9. KillShell - Line 449268

### Web Operations
10. WebFetch (rC) - Line 79994
11. WebSearch (Ql) - Line 80013

### Agent and Task Management
12. Task (pI) - Line 79880 (launches subagents)
13. Skill ($N) - Line 433302

### User Interaction
14. TodoWrite - Line 205111
15. AskUserQuestion (t_) - Line 331271
16. SlashCommand (JS) - Line 433631

### MCP Integration
17. ListMcpResourcesTool - Line 284678
18. ReadMcpResourceTool - Line 284813

### Additional MCP Tools
- MCP servers can provide additional tools with names like `mcp__servername__toolname`
- These are dynamically loaded based on connected MCP servers

## Tool Execution

### Tool Definition

Each tool is defined with this structure.

TODO: Above, what "structure"? there is no structure here.

The actual minified code uses single-letter variable names (A, B, Q, I, G, Z, Y, J, etc.) and
minified function names throughout.

TODO: Fill in all missing tools; or remove -- redundant with tool names and line numbers above.  Ask user.

Tool Name Constants (Lines 79873-79977)
```javascript
[source fragment removed]
```

Example: Read Tool Description (Lines 79942-79961)
```javascript
[source fragment removed]
```

### How Tools Are Sent to Claude

Location: cli.prettier.js:460173

Tools are sent as part of the Anthropic API request:

```javascript
[source fragment removed]
```

### Tool Approval System

Location: cli.prettier.js:458727 (Function `Db6`)

Tools can be categorized as:
- No approval required - Execute automatically
- Requires permission - User must approve each use
- Wildcard rules - Pattern-based approval (e.g., `Bash(git:)`)

Example tools without approval requirement:
```
mcp__code-intel__, Bash(cat:), Bash(git restore:), Read, Edit, Grep, Glob
```

## The Task Tool and Subagents

Extracted to [TASK_TOOL_AND_SUBAGENTS.md](TASK_TOOL_AND_SUBAGENTS.md).

Covers: built-in agents (Bash, general-purpose, statusline-setup, Explore, Plan,
claude-code-guide), the team/swarm system (teammates, SendMessageTool, TeammateTool),
task management tools (TaskCreate/Update/Get/List), magic-docs agent, agent loading pipeline,
system prompts, and the Task tool implementation (Gd, CA1, execution flow).

## MCP Tools

MCP (Model Context Protocol) servers can provide additional tools dynamically.

### MCP Tool Naming

MCP tools are prefixed with `mcp__servername__`:
- `mcp__code-intel__find_symbol_by_name`
- `mcp__code-intel__get_code_context`
- `mcp__toolbox__find`

### MCP Tool Loading

Location: cli.prettier.js:284678-284813

MCP tools are:
1. Discovered from connected MCP servers
2. Transformed to Claude Code's tool format
3. Added to the tools array sent to the API
4. Available in both main session and subagents (unless filtered)

## Tool Permission Context

Location: cli.prettier.js:460891

Every tool execution checks permissions:

```javascript
[source fragment removed]
```

Permission modes:
- `ask` - Ask user for each tool use
- `auto` - Execute approved tools automatically
- `plan` - Planning mode (different prompts)

## Bash Tool

Location: Line 78616

The Bash tool is special:
- Can run in foreground or background (`run_in_background: true`)
- Background processes get an ID
- Use `BashOutput` to read output from background processes
- Use `KillShell` to terminate background processes

### Bash Tool Pattern Matching

Location: cli.prettier.js:466746

Bash commands can be approved with patterns:
- `Bash(git:)` - All git commands
- `Bash(cat:)` - All cat commands
- `Bash(npm --silent pack:)` - Specific npm commands

