# Claude Code Tools and Execution Architecture

Version: 2.0.29

## Overview

Claude Code provides tools to the LLM via the Anthropic API's `tools` parameter. Each tool is a
function that can be called by the AI to perform specific actions. Tools are defined with JSON
schemas and implemented as JavaScript async generator functions.

## Complete List of Built-in Tools

### File Operations
1. **Read** (H5) - Line 79935
2. **Write** (PJ) - Line 79964
3. **Edit** (B3) - Line 79963
4. **NotebookEdit** (bAA) - Line 79977

### Search and Discovery
5. **Glob** (dK) - Line 79873
6. **Grep** (aC) - Line 79894

### Command Execution
7. **Bash** (T4) - Line 78616
8. **BashOutput** - Line 449469
9. **KillShell** - Line 449268

### Web Operations
10. **WebFetch** (rC) - Line 79994
11. **WebSearch** (Ql) - Line 80013

### Agent and Task Management
12. **Task** (pI) - Line 79880 (launches subagents)
13. **Skill** ($N) - Line 433302

### User Interaction
14. **TodoWrite** - Line 205111
15. **AskUserQuestion** (t_) - Line 331271
16. **SlashCommand** (JS) - Line 433631

### MCP Integration
17. **ListMcpResourcesTool** - Line 284678
18. **ReadMcpResourceTool** - Line 284813

### Additional MCP Tools
- MCP servers can provide additional tools with names like `mcp__servername__toolname`
- These are dynamically loaded based on connected MCP servers

## Tool Execution Architecture

### Tool Definition Structure

Each tool is defined with this structure. The actual minified code uses single-letter variable names (A, B, Q, I, G, Z, Y, J, etc.) and minified function names throughout.

**Tool Name Constants (Lines 79873-79977)**
```javascript
[source fragment removed]
```

**Example: Read Tool Description (Lines 79942-79961)**
```javascript
[source fragment removed]
```

### How Tools Are Sent to Claude

**Location**: cli.prettier.js:460173

Tools are sent as part of the Anthropic API request:

```javascript
[source fragment removed]
```

### Tool Approval System

**Location**: cli.prettier.js:458727 (Function `Db6`)

Tools can be categorized as:
- **No approval required** - Execute automatically
- **Requires permission** - User must approve each use
- **Wildcard rules** - Pattern-based approval (e.g., `Bash(git:*)`)

Example tools without approval requirement:
```
mcp__code-intel__*, Bash(cat:*), Bash(git restore:*), Read, Edit, Grep, Glob
```

## The Task Tool: Subagent Execution

### What is a Task/Subagent?

A "Task" is **not arbitrary** - it refers to launching a **separate Claude API session** with its own system prompt and context. This is a subagent.

### Valid Task Types (Agents)

**Location**: cli.prettier.js:449080

Tasks must specify a valid `subagent_type`. Available agents are discovered from:

1. **Built-in agents** (hardcoded in Claude Code):
   - `general-purpose` (Line 448620)
   - `statusline-setup` (Line 450136)
   - `Explore`, `Plan`, etc.

2. **User-defined agents** (from `.claude/agents/*.md` files)

### How Subagents Execute

**Key Functions**:
1. **CA1** (Line 448511) - Subagent executor
2. **GS** (Line 428807) - Main loop for API calls
3. **p4A** (Line 460088) - Anthropic API wrapper
4. **messages.create** (Line 460414) - Actual API call

**Execution Flow**:

```
Main Claude Session
    ↓ (Task tool called)
Task Tool (Gd.call)
    ↓
CA1 function (subagent executor)
    ↓ Builds subagent context:
    - Separate system prompt (from agent definition)
    - Filtered tool set
    - New message context
    ↓
GS function (main loop)
    ↓
p4A function (API wrapper)
    ↓
Anthropic API: messages.create()
    ↓
Subagent runs independently
    ↓
Returns results to main session
```

**Yes, a subagent is a completely separate API call** to `POST /v1/messages` with its own:
- System prompt (simpler than main session)
- Tool set (filtered based on agent definition)
- Message history (isolated unless `forkContext: true`)
- Model selection (can override per agent)

### Subagent Independence

From the code analysis:

**Line 448544-448578**: Subagents get their own `toolUseContext` with:
```javascript
[source fragment removed]
```

**Key Point**: Each subagent invocation creates a fresh API request to Anthropic, completely independent of the main session except for what's explicitly passed via:
1. The `prompt` parameter (user's request to the agent)
2. Optional `forkContext` (copies main session messages)

## Task Tool Parameters

**Location**: cli.prettier.js:449010-449030

```javascript
[source fragment removed]
```

**NOT arbitrary** - Must match an existing agent type defined in:
- Built-in agents (hardcoded)
- User agents (`.claude/agents/*/`)
- Project agents (`./.claude/agents/*/`)

## Tool Implementation Patterns

### Task Tool (Gd) - Complete Implementation

**Location**: cli.prettier.js:449062-449191

The Task tool launches a complete subagent session. Here is the actual minified code:

```javascript
[source fragment removed]
```

**Parameter Mapping**:
- `A` = prompt
- `B` = subagent_type
- `Q` = description
- `I` = model
- `G` = resume
- `Z` = toolUseContext (2nd parameter)
- `Y` = canUseTool (3rd parameter)
- `J` = (4th parameter)

**Key Line**: `for await (let P of CA1({ ...w, override: { agentId: N } }))` (line 449140) executes the subagent

### Subagent Executor (CA1) - Complete Implementation

**Location**: cli.prettier.js:448511-448585

```javascript
[source fragment removed]
```

**Key Lines**:
- **Line 448534**: `T = A.systemPrompt ? [A.systemPrompt] : [O_2]` - Uses agent's systemPrompt or default `O_2`
- **Line 448535**: `P = W?.systemPrompt ? W.systemPrompt : await R_2(T, C, O)` - Builds system prompt via `R_2` function
- **Line 448544**: `for await (let g of GS({...}))` - Calls main API loop (GS function)
- **Line 448576**: `isSubAgent: !0` - Marks this context as a subagent

## MCP Tool Integration

MCP (Model Context Protocol) servers can provide additional tools dynamically.

### MCP Tool Naming

MCP tools are prefixed with `mcp__servername__`:
- `mcp__code-intel__find_symbol_by_name`
- `mcp__code-intel__get_code_context`
- `mcp__toolbox__find`

### MCP Tool Loading

**Location**: cli.prettier.js:284678-284813

MCP tools are:
1. Discovered from connected MCP servers
2. Transformed to Claude Code's tool format
3. Added to the tools array sent to the API
4. Available in both main session and subagents (unless filtered)

## Tool Permission Context

**Location**: cli.prettier.js:460891

Every tool execution checks permissions:

```javascript
[source fragment removed]
```

Permission modes:
- `ask` - Ask user for each tool use
- `auto` - Execute approved tools automatically
- `plan` - Planning mode (different prompts)

## Bash Tool Execution

**Location**: Line 78616

The Bash tool is special:
- Can run in foreground or background (`run_in_background: true`)
- Background processes get an ID
- Use `BashOutput` to read output from background processes
- Use `KillShell` to terminate background processes

### Bash Tool Pattern Matching

**Location**: cli.prettier.js:466746

Bash commands can be approved with patterns:
- `Bash(git:*)` - All git commands
- `Bash(cat:*)` - All cat commands
- `Bash(npm --silent pack:*)` - Specific npm commands

## Summary: Tools vs Subagents

| Aspect | Regular Tool | Subagent (Task) |
|--------|-------------|-----------------|
| Execution | Synchronous function call | Separate API request to Anthropic |
| System Prompt | Uses main session prompt | Own simplified prompt |
| Context | Shares main session context | Isolated context |
| Tools | All available tools | Filtered tool set |
| Cost | No additional API calls | Full API call with tokens |
| Use Case | File ops, commands, search | Complex multi-step reasoning |

**Key Insight**: When the main Claude Code LLM invokes the Task tool, it's not just calling a local function - it's making a **brand new API request** to Anthropic's `/v1/messages` endpoint with a completely separate context. The subagent is essentially "another instance of Claude" running independently.
