# Claude Code System Prompts Analysis

Version: 2.0.29

## Overview

Claude Code constructs its system prompt dynamically by combining multiple components at runtime. The system prompt is NOT static - it's assembled based on:

1. **Base prompt** - Simple opening statement
2. **Core instructions** - Main behavioral guidelines
3. **Conditional sections** - Based on available tools and configuration
4. **Model information** - Injected dynamically
5. **User-provided augmentation** - Via `--append-system-prompt` flag

## Base System Prompts

### Interactive Mode (Default)
```
lT0 = "You are Claude Code, Anthropic's official CLI for Claude."
```

### Non-Interactive Mode (Agent SDK)
```
Ly9 = "You are Claude Code, Anthropic's official CLI for Claude, running within the Claude Agent SDK."
```

### Claude Agent SDK Context
```
iT0 = "You are a Claude agent, built on Anthropic's Claude Agent SDK."
```

### Selection Logic (Function `YRA`)
Location: cli.prettier.js:80040

```javascript
[source fragment removed]
```

**Decision Tree:**
- If running in Vertex environment → Use `lT0`
- Else if non-interactive mode:
  - If has append system prompt:
    - If VSCode mode → Use `iT0`
    - Otherwise → Use `Ly9` (Agent SDK)
  - Otherwise → Use `iT0` (Claude Agent)
- Else interactive mode → Use `lT0`

## Full System Prompt Assembly

### Main Constructor Function
Location: cli.prettier.js:458735
Function name: `Pr(A, B, Q, I, G, Z)`

Parameters:
- `A` - Available tools
- `B` - Output style configuration
- `Q` - Tool permission context
- `I` - MCP servers
- `G` - Model information
- `Z` - Additional context

## Variable Resolution and Literal Text Injection

To understand exactly what text Claude Code injects into the LLM context, we must trace all variable dependencies. Below are all variables and constants used in system prompt construction, with their literal values.

### Constants and Variables

**Security Notice Constant - `Lb2`**
Location: cli.prettier.js:458966

```javascript
[source fragment removed]
```

**Claude Code Docs URL - `Eb6`**
Location: cli.prettier.js:458968

```javascript
[source fragment removed]
```

**Default Output Style Name - `AC`**
Location: cli.prettier.js:463779

```javascript
[source fragment removed]
```

**Output Styles Dictionary - `ma`**
Location: cli.prettier.js:463781-463850+ (object definition begins)

The output styles are defined as:

```javascript
[source fragment removed]
```

**Output Style Loading - `Ob2()` function**
Location: cli.prettier.js:463774-463777

```javascript
[source fragment removed]
```

Where `q0()` returns the current configuration object with an `outputStyle` property.

**Output Styles Loader - `da()` function**
Location: cli.prettier.js:463757-463773

```javascript
[source fragment removed]
```

The function merges:
1. Built-in styles from `ma` (Explanatory, Learning)
2. User-defined output styles (highest priority)
3. Project-defined output styles (medium priority)
4. Policy-defined output styles (lowest priority)

### Variable Dependencies in System Prompt

In the main `Pr()` function at line 458736, the variable `J` is assigned:

```javascript
[source fragment removed]
```

So `J` is the result of `Ob2()`, which is either:
- `null` if using the default "default" output style
- An output style object with properties: `{name, description, prompt, source, isCodingRelated}`

This variable `J` is then used throughout the Pr() function to conditionally include or exclude prompt sections:
- `J !== null` - custom output style is active
- `J === null` - default output style (include standard sections)
- `J.isCodingRelated === true` - coding-related style (include "Doing tasks" section)

### System Prompt Components (In Order)

The function returns an array of prompt components that are joined together. Here are the exact literal texts with line numbers for reference:

**Component 1: Core Introduction and Requirements**
Location: cli.prettier.js:458749-458768

```
You are an interactive CLI tool that helps users [OUTPUT_STYLE_DEPENDENT]. Use the instructions below and the tools available to you to assist the user.

[SECURITY_NOTICE]
IMPORTANT: You must NEVER generate or guess URLs for the user unless you are confident that the URLs are for helping the user with programming. You may use URLs provided by the user in their messages or local files.

If the user asks for help or wants to give feedback inform them of the following:
- /help: Get help with using Claude Code
- To give feedback, users should report the issue at https://github.com/anthropics/claude-code/issues

When the user directly asks about Claude Code (eg. "can Claude Code do...", "does Claude Code have...", "are you able...", "can you do..."), or asks how to use a specific Claude Code feature (eg. implement a hook, write a slash command, or install an MCP server), use the WebFetch tool to gather information to answer the question from Claude Code docs.
```

Where `[OUTPUT_STYLE_DEPENDENT]` is determined at line 458750:
- If custom output style configured: `according to your "Output Style" below, which describes how you should respond to user queries.`
- If no custom output style: `with software engineering tasks.`

**Component 2: Tone and Style (Conditional)**
Location: cli.prettier.js:458770-458790
Condition: Only included if NOT using custom output style (controlled by variable `J`)

```
# Tone and style
- Only use emojis if the user explicitly requests it. Avoid using emojis in all communication unless asked.
- Your output will be displayed on a command line interface. Your responses should be short and concise. You can use Github-flavored markdown for formatting, and will be rendered in a monospace font using the CommonMark specification.
- Output text to communicate with the user; all text you output outside of tool use is displayed to the user. Only use tools to complete tasks. Never use tools like Bash or code comments as means to communicate with the user during the session.
- NEVER create files unless they're absolutely necessary for achieving your goal. ALWAYS prefer editing an existing file to creating a new one. This includes markdown files.

# Professional objectivity
Prioritize technical accuracy and truthfulness over validating the user's beliefs. Focus on facts and problem-solving, providing direct, objective technical info without any unnecessary superlatives, praise, or emotional validation. It is best for the user if Claude honestly applies the same rigorous standards to all ideas and disagrees when necessary, even if it may not be what the user wants to hear. Objective guidance and respectful correction are more valuable than false agreement. Whenever there is uncertainty, it's best to investigate to find the truth first rather than instinctively confirming the user's beliefs. Avoid using over-the-top validation or excessive praise when responding to users such as "You're absolutely right" or similar phrases.
```

**Component 3: Task Management (Conditional)**
Location: cli.prettier.js:458791-458825
Condition: Only included if TodoWrite tool is available (checked via `X.has(kG.name)`)

```
# Task Management
You have access to the TodoWrite tools to help you manage and plan tasks. Use these tools VERY frequently to ensure that you are tracking your tasks and giving the user visibility into your progress.
These tools are also EXTREMELY helpful for planning tasks, and for breaking down larger complex tasks into smaller steps. If you do not use this tool when planning, you may forget to do important tasks - and that is unacceptable.

It is critical that you mark todos as completed as soon as you are done with a task. Do not batch up multiple tasks before marking them as completed.

[DETAILED EXAMPLES OF TASK USAGE...]
```

**Component 4: Hooks Notice**
Location: cli.prettier.js:458826-458828

```
Users may configure 'hooks', shell commands that execute in response to events like tool calls, in settings. Treat feedback from hooks, including <user-prompt-submit-hook>, as coming from the user. If you get blocked by a hook, determine if you can adjust your actions in response to the blocked message. If not, ask the user to check their hooks configuration.
```

**Component 5: Doing Tasks Section (Conditional)**
Location: cli.prettier.js:458829-458836
Condition: Only included if no custom output style OR output style is coding-related (checked via `J === null || J.isCodingRelated === !0`)

```
# Doing tasks
The user will primarily request you perform software engineering tasks. This includes solving bugs, adding new functionality, refactoring code, explaining code, and more. For these tasks the following steps are recommended:
- [Use the TodoWrite tool to plan the task if required]
- Tool results and user messages may include <system-reminder> tags. <system-reminder> tags contain useful information and reminders. They are automatically added by the system, and bear no direct relation to the specific tool results or user messages in which they appear.
```

**Component 6: Tool Usage Policy**
Location: cli.prettier.js:458838-458875
Conditional sections based on available tools

```
# Tool usage policy
- When doing file search, prefer to use the Task tool in order to reduce context usage.
- You should proactively use the Task tool with specialized agents when the task at hand matches the agent's description.
- [If WebFetch available at line 458849]: When WebFetch returns a message about a redirect to a different host, you should immediately make a new WebFetch request with the redirect URL provided in the response.
- [Slash command usage guidance if SlashCommand tool available at line 458745]
- You can call multiple tools in a single response. If you intend to call multiple tools and there are no dependencies between them, make all independent tool calls in parallel. Maximize use of parallel tool calls where possible to increase efficiency. However, if some tool calls depend on previous calls to inform dependent values, do NOT call these tools in parallel and instead call them sequentially. For instance, if one operation must complete before another starts, run these operations sequentially instead. Never use placeholders or guess missing parameters in tool calls.
- If the user specifies that they want you to run tools "in parallel", you MUST send a single message with multiple tool use content blocks. For example, if you need to launch multiple agents in parallel, send a single message with multiple Task tool calls.
- Use specialized tools instead of bash commands when possible, as this provides a better user experience. For file operations, use dedicated tools: Read for reading files instead of cat/head/tail, Edit for editing instead of sed/awk, and Write for creating files instead of cat with heredoc or echo redirection. Reserve bash tools exclusively for actual system commands and terminal operations that require shell execution. NEVER use bash echo or other command-line tools to communicate thoughts, explanations, or instructions to the user. Output all communication directly in your response text instead.
- VERY IMPORTANT: When exploring the codebase to gather context or to answer a question that is not a needle query for a specific file/class/function, it is CRITICAL that you use the Task tool with specialized agents instead of running search commands directly.

[FOLLOWED BY: List of tools without approval requirement from Db6() function at line 458732]
```

**Component 7: Environment and Model Information**
Location: cli.prettier.js:458877-458879 (injected via function `Mb2()`)

```
Here is useful information about the environment you are running in:
<env>
Working directory: [path]
Is directory a git repo: [Yes/No]
[Additional working directories if applicable]
Platform: [darwin/linux/win32]
OS Version: [system output]
Today's date: [YYYY-MM-DD]
</env>

[MODEL INFORMATION]:
You are powered by the model named [MODEL_NAME]. The exact model ID is [MODEL_ID].
```

**Component 8: Security Notice (Repeated)**
Location: cli.prettier.js:458878
```
[Same SECURITY_NOTICE from Component 1]
```

**Component 9: TodoWrite Emphasis (Conditional)**
Location: cli.prettier.js:458880-458882
Condition: Only included if TodoWrite tool is available

```
IMPORTANT: Always use the TodoWrite tool to plan and track tasks throughout the conversation.
```

**Component 10: Code References Format**
Location: cli.prettier.js:458884-458892

```
# Code References

When referencing specific functions or pieces of code include the pattern `file_path:line_number` to allow the user to easily navigate to the source code location.

<example>
user: Where are errors from the client handled?
assistant: Clients are marked as failed in the `connectToServer` function in src/services/process.ts:712.
</example>
```

**Component 11: Output Style Details (Conditional)**
Location: cli.prettier.js:458893-458895
Condition: Only included if custom output style is configured (checked via `J !== null`)

```
# Output Style: [STYLE_NAME]
[STYLE_PROMPT - provided by the output style configuration]
```

**Component 12: MCP Server Instructions (Conditional)**
Location: cli.prettier.js:458896-458911 (Function `Hb6`)
Condition: Only included if MCP servers with instructions are available (line 458897 filters)

```
# MCP Server Instructions

The following MCP servers have provided instructions for how to use their tools and resources:

## [SERVER_NAME]
[SERVER_PROVIDED_INSTRUCTIONS]

## [SERVER_NAME]
[SERVER_PROVIDED_INSTRUCTIONS]
...
```

## Key Variables and Configuration

### Tool Availability Detection
The code checks for these tools:
- `kG.name` - TodoWrite tool
- `pI` - Task/Agent tool
- `rC` - WebFetch tool
- `$N` - SlashCommand tool (custom commands)

### Dynamic Sections Based on Tools
1. **If TodoWrite available**: Includes task management section with examples
2. **If Task tool available**: Includes guidance on agent usage
3. **If WebFetch available**: Includes redirect handling instructions
4. **If SlashCommand available**: Includes custom command usage

### Conditional Content
The system prompt intelligently adjusts based on:
- **Output Style**: Different formatting if custom style configured
- **Tool Set**: Only mentions tools that are actually available
- **Environment**: Different base prompts for interactive vs non-interactive
- **Configuration**: Respects user's `--append-system-prompt` setting

## User-Provided System Prompt

### Command-Line Options
Location: cli.prettier.js:478558

Three ways to provide custom system prompt:

**Option 1: Direct prompt**
```bash
--system-prompt "Your custom prompt here"
```

**Option 2: From file**
```bash
--system-prompt-file /path/to/prompt.txt
```

**Option 3: Append to default**
```bash
--append-system-prompt "Additional instructions here"
```

### Mutual Exclusivity
- `--system-prompt` and `--system-prompt-file` are mutually exclusive
- If both provided, error is raised and program exits
- `--append-system-prompt` can be used with neither of the above

### Processing Logic
Location: cli.prettier.js:478720

```
if (J.systemPromptFile) {
  // Load from file
  if (J.systemPrompt) → ERROR (both specified)
  if (!fileExists) → ERROR
  MA = readFile(systemPromptFile)
} else if (J.systemPrompt) {
  // Use provided prompt directly
  MA = J.systemPrompt
} else {
  // Use default (from YRA function)
  MA = defaultPrompt
}

// If append is specified, it's added separately to this base
if (J.appendSystemPrompt) {
  // Appended after base prompt construction
}
```

## Prompt Assembly Flow

1. **Determine base prompt** (via `YRA` function)
   - Based on environment and configuration

2. **Build full system prompt** (via `Pr` function)
   - Includes all components based on available tools
   - Dynamically adjusts sections
   - Injects model information

3. **Check user override** (via command-line processing)
   - If `--system-prompt-file` or `--system-prompt` → Replace entirely
   - Otherwise → Use default from step 2

4. **Apply append** (if provided)
   - If `--append-system-prompt` → Add to end of base prompt
   - Adds user's additional instructions

## Summary

Claude Code's system prompt is **NOT a static string**. It's a dynamically constructed document that:

1. **Adapts to environment** - Different base prompts for different modes
2. **Reflects available tools** - Only documents tools that exist
3. **Respects user configuration** - Can be replaced or appended
4. **Includes model context** - Always specifies which model is running
5. **Provides conditional guidance** - Sections appear/disappear based on setup

This design allows the same Claude Code version to work in different contexts (interactive CLI, agent SDK, VSCode) while providing context-appropriate instructions to the AI assistant.

## Dynamic Context Additions at Runtime

Beyond the base system prompt, Claude Code adds dynamic context from four sources:

### 1. TOOLS - Tool Instructions and Policies

**Built-in Tools Available Without Permission:**
Location: cli.prettier.js:458727 (Function `Db6`)

Tools that don't require user approval are listed in the system prompt:

```javascript
[source fragment removed]
```

**Example Output:**
```
You can use the following tools without requiring user approval: mcp__code-intel__find_symbol_by_name, mcp__code-intel__get_code_context, Bash(cat:*), Bash(git restore:*), Edit, Read, Write
```

**Tool Usage Policy Section Covers:**
- Parallel execution guidelines
- Bash command restrictions
- Agent/Task tool usage
- File operation best practices (Read vs cat, Edit vs sed, Write vs echo)
- WebFetch redirect handling

### 2. AGENTS - Available Agent Types and Usage

**Agent Information Injection:**
Location: cli.prettier.js:415680 (Agent description formatter)

Each agent available in the session is documented with:

```javascript
[source fragment removed]
```

**Agent Properties Documented:**
- **agentType** - Name/identifier (e.g., "general-purpose", "Explore")
- **whenToUse** - Description of when to invoke this agent
- **isAsync** - Whether agent runs in background
- **forkContext** - Whether agent has access to current session context
- **tools** - Array of tools the agent has access to

**Example Section in Prompt:**
```
Available agent types and the tools they have access to:
- general-purpose: General-purpose agent for researching complex questions...
  (Properties: runs in background; access to current context; Tools: *)
- Explore: Fast agent specialized for exploring codebases
  (Tools: Glob, Grep, Read, Bash)
```

**Agent Usage Guidance Includes:**
- When NOT to use agents (recommends specialized tools for simpler tasks)
- How to launch agents (via Task tool with subagent_type parameter)
- Parallel agent execution
- Handling background agents with AgentOutputTool
- Agent statefulness and output handling

**"Use your judgement" Instruction:**
Location: cli.prettier.js:415711

The Task tool description includes this guidance:
```
- If the agent description mentions that it should be used proactively, then you should try your best to use it without the user having to ask for it first. Use your judgement.
```

This instructs the main Claude Code LLM to decide when to invoke subagents based on the task at hand.

## Subagent System Prompt Construction

When a subagent is launched via the Task tool, it receives its own separate system prompt that is distinct from the main Claude Code context.

### Subagent System Prompt Assembly

**Location**: cli.prettier.js:448511-448535 (Function `CA1`)

**Key Logic**:
```javascript
[source fragment removed]
```

Where:
- `A.systemPrompt` - Agent-specific system prompt from agent definition
- `O_2` - Default base agent prompt (line 458969)
- `R_2()` - Function that adds additional context (line 458952)

### Default Base Agent Prompt

**Constant O_2** - Location: cli.prettier.js:458969

```
"You are an agent for Claude Code, Anthropic's official CLI for Claude. Given the user's message, you should use the tools available to complete the task. Do what has been asked; nothing more, nothing less. When you complete the task simply respond with a detailed writeup."
```

### Agent-Specific System Prompts

Each agent type can define its own `systemPrompt` field. Example from "general-purpose" agent:

**Location**: cli.prettier.js:448620-448645

```javascript
[source fragment removed]
```

### Additional Context Added to Subagent Prompt

**Function R_2** - Location: cli.prettier.js:458952-458964

This function adds additional context to all subagent prompts:

```javascript
[source fragment removed]
```

### Complete Subagent System Prompt Structure

The full subagent system prompt is assembled as an array of strings:

1. **Agent-specific prompt** (from `agentDefinition.systemPrompt`) OR **default base prompt** (O_2)
2. **Additional notes**:
   - Agent threads have cwd reset between bash calls
   - Must use absolute file paths
   - Must avoid using emojis
3. **Model and environment information** (via `Mb2()` function):
   - Working directory
   - Git repo status
   - Platform/OS information
   - Today's date
   - Model name and ID
   - API endpoint (if not default)

### What Subagents DON'T Receive

Subagents have their own isolated context and do NOT receive:

1. **Main session's conversation history** (unless `forkContext: true` in agent definition)
2. **Main session's system prompt components**:
   - No "Tone and style" section
   - No "Task Management" section
   - No "Professional objectivity" guidance
   - No "Tool usage policy" section from main prompt
3. **Main session's MCP server instructions** (they get their own empty MCP clients array)
4. **Main session's output style configuration**
5. **User's custom system prompt** (from --append-system-prompt)

### What Subagents DO Receive

**Location**: cli.prettier.js:448544-448578

Subagents are initialized with:

1. **Their own toolUseContext** with:
   - Filtered tool set (via `i6A(A, Q.options.tools).resolvedTools`)
   - Empty commands array
   - Empty MCP clients array
   - `isSubAgent: true` flag
   - Their own abort controller
   - Model information (can be overridden per agent)

2. **Messages**:
   - If `forkContext: true`: Filtered main session messages + new user prompt
   - If `forkContext: false`: Only the new user prompt from Task tool

3. **User and System Context**:
   - Fresh user context (via `kF()`)
   - Fresh system context (via `yF()`)

### Example: statusline-setup Agent

**Location**: cli.prettier.js:450136+

Another built-in agent with custom systemPrompt:

```javascript
[source fragment removed]
```

### The Effect of `forkContext`

**Location**: cli.prettier.js:449101-449114

The `forkContext` property in agent definitions controls whether a subagent has access to the main session's conversation history.

**Who sets `forkContext`?** The user, when creating a custom agent definition.

**Where is it configured?** In the YAML frontmatter of agent `.md` files.

**IMPORTANT**: The official documentation (https://docs.claude.com/en/docs/claude-code/sub-agents.md) only documents these properties:
- `name` (required)
- `description` (required)
- `tools` (optional)
- `model` (optional)

**HOWEVER**, the actual code supports these **undocumented** properties:
- `color` (optional)
- `isAsync` (optional - "true", "false", or omitted)
- `forkContext` (optional - "true", "false", or omitted)

**Field Mapping** (lines 450337, 450369-450370):
- YAML `name` → internal property `agentType`
- YAML `description` → internal property `whenToUse`
- YAML `tools` → internal property `tools`
- YAML `model` → internal property `model`
- YAML `color` → internal property `color`
- YAML `isAsync` → internal property `isAsync`
- YAML `forkContext` → internal property `forkContext`

**Example agent definition using undocumented properties**:

```markdown
---
name: my-agent
description: Description of when to use this agent
forkContext: true  # UNDOCUMENTED - enables conversation history
tools: ["Read", "Grep"]
model: inherit  # Required when forkContext is true
color: blue  # UNDOCUMENTED - optional UI color
isAsync: false  # UNDOCUMENTED - whether agent runs in background
---

[Agent implementation details...]
```

**Documentation vs Reality**:
The Claude Code documentation does NOT mention `forkContext`, `isAsync`, or `color` properties, yet the code at lines 450347-450360 explicitly parses and validates them. These are hidden/undocumented features.

#### Code Implementation

```javascript
[source fragment removed]
```

Where:
- `C` = agent definition object
- `Z.messages` = main session's conversation history
- `A` = the prompt passed to the Task tool
- `D` = `forkContextMessages` (passed to subagent executor)
- `E` = `promptMessages` (initial messages for subagent)

**Line 448526** (in CA1 subagent executor):
```javascript
[source fragment removed]
```

Where:
- `Z` = `forkContextMessages` (the `D` from above)
- `B` = `promptMessages` (the `E` from above)
- `E` = final messages array sent to Anthropic API

#### Behavior

**If `forkContext: false` (default)**:
- `D = void 0` (undefined - no main session messages)
- `E = [_0({ content: A })]` (just a single user message with the prompt)
- Subagent receives only the task prompt
- **Token cost**: ~50 tokens for messages parameter

**If `forkContext: true`**:
- `D = Z.messages` (main session's full conversation history)
- `E = Pq2(A, J)` (prompt is processed/normalized)
- Subagent receives entire conversation history + new prompt
- **Token cost**: Can be 1,000s of tokens (entire conversation)

#### Example Comparison

**Main session conversation:**
```
User: What files are in the src directory?
Assistant: [lists files using Glob - shows api.ts, handlers.ts, utils.ts]

User: Now search for all error handling patterns
Assistant: [invokes Task tool with agent]
```

**With `forkContext: false`** (subagent receives):
```javascript
[source fragment removed]
```

**With `forkContext: true`** (subagent receives):
```javascript
[source fragment removed]
```

#### When to Use Each Mode

**Use `forkContext: false` (default) when:**
- Task is independent and self-contained
- Minimizing token cost is important
- All needed information is in the task prompt

**Use `forkContext: true` when:**
- Task builds on prior conversation (e.g., "analyze those files")
- Task references earlier findings or decisions
- Task requires understanding user's broader goals from conversation

**Token cost impact**: Enabling `forkContext` can 2-3x the subagent's API request size.

#### Validation and Requirements

**Location**: cli.prettier.js:450352-450360

When parsing agent definitions, Claude Code validates `forkContext`:

```javascript
[source fragment removed]
```

**Requirements**:
1. Value must be `"true"`, `"false"`, or omitted (defaults to false)
2. If `forkContext: true`, then `model` MUST be `"inherit"`
3. If you specify `forkContext: true` with a different model, Claude Code automatically overrides it to `"inherit"`

**Why the model requirement?** When forking context, the subagent needs to use the same model as the main session to avoid context length mismatches. The `"inherit"` value means "use whatever model the main session is using."

#### How It Appears in Task Tool Description

**Location**: cli.prettier.js:415686-415690

Agents with `forkContext: true` are documented in the Task tool's description shown to the main LLM:

```javascript
[source fragment removed]
```

**Example output**:
```
Available agent types:
- general-purpose: General-purpose agent for researching complex questions...
  (Tools: *)
- my-agent: Description of my custom agent
  (Properties: access to current context; Tools: Read, Grep, Glob)
```

The "access to current context" property tells the main Claude Code session that this agent will receive the conversation history.

#### Built-in Agents: Complete List

**Location**: cli.prettier.js:450267-450268 (function `Rr1()` returns array of built-in agents)

Claude Code 2.0.29 includes **5 built-in agents** defined directly in the JavaScript code (NOT in .md files):

1. **general-purpose** (`FA1`) - Line 448620
   - `agentType: "general-purpose"`
   - `tools: ["*"]` (all tools)
   - `model: "sonnet"`
   - `isAsync: !1` (false)
   - `source: "built-in"`
   - No `forkContext` or `color` properties

2. **statusline-setup** (`Vx2`) - Line 450131
   - `agentType: "statusline-setup"`
   - `tools: ["Read", "Edit"]`
   - `model: "sonnet"`
   - `color: "orange"` ← **Uses undocumented `color` property**
   - `source: "built-in"`
   - No `isAsync` or `forkContext` properties

3. **output-style-setup** (`Xx2`) - Line 450045
   - `agentType: "output-style-setup"`
   - `tools: [H5, PJ, B3, dK, aC]` (Read, Write, Edit, Glob, Grep)
   - `model: "sonnet"`
   - `color: "blue"` ← **Uses undocumented `color` property**
   - `callback: () => { Fx2(); }` ← **Additional undocumented property**
   - `source: "built-in"`
   - No `isAsync` or `forkContext` properties

4. **Explore** (`LN`) - Line 450225
   - `agentType: "Explore"`
   - `tools: [dK, aC, H5, T4]` (Glob, Grep, Read, Bash)
   - `model: "haiku"` ← **Uses faster/cheaper model**
   - `isAsync: !1` (false)
   - `source: "built-in"`
   - No `forkContext` or `color` properties

5. **Plan** (`U5A`) - Line 450257
   - `agentType: "Plan"`
   - `whenToUse: LN.whenToUse` ← **Reuses Explore's description**
   - `tools: LN.tools` ← **Reuses Explore's tools**
   - `systemPrompt: LN.systemPrompt` ← **Reuses Explore's system prompt**
   - `model: "sonnet"` ← **Different model than Explore (sonnet vs haiku)**
   - `source: "built-in"`
   - No `isAsync`, `forkContext`, or `color` properties

**Key Findings**:

1. **Built-in agents ARE using undocumented properties**:
   - `color` is used by `statusline-setup` and `output-style-setup`
   - `callback` is used by `output-style-setup`
   - `isAsync` is explicitly set to `!1` (false) on some agents

2. **None use `forkContext: true`**:
   - All built-in agents work independently with isolated context
   - This minimizes token costs for agent invocations

3. **Built-in agents are JavaScript objects**:
   - NOT defined in `.md` files
   - Hardcoded in the minified source
   - User agents (`.md` files) are parsed separately and merged with these

4. **Plan agent is a variant of Explore**:
   - Uses same system prompt and tools as Explore
   - Only difference is the model (sonnet instead of haiku)
   - Appears to be for plan mode vs execution mode

### Summary: Main Prompt vs Subagent Prompt

| Component | Main Claude Code Prompt | Subagent Prompt |
|-----------|------------------------|-----------------|
| Base opening | "You are Claude Code..." | "You are an agent for Claude Code..." |
| Tone and style | ✓ Included | ✗ Not included |
| Task management | ✓ Included (if TodoWrite available) | ✗ Not included |
| Professional objectivity | ✓ Included | ✗ Not included |
| Tool usage policy | ✓ Comprehensive section | ✗ Not included |
| Agent-specific guidelines | N/A | ✓ Included (per agent type) |
| Absolute paths requirement | Only in code references | ✓ Explicit notes section |
| Emoji guidance | In "Tone and style" | ✓ Explicit notes section |
| Model/environment info | ✓ Included | ✓ Included (via Mb2) |
| MCP server instructions | ✓ Included | ✗ Empty array |
| Conversation history | ✓ Full session | ✗ None (unless forkContext: true) |
| Custom user prompt | ✓ Can append | ✗ Not included |

### 3. MCP SERVERS - Server Instructions and Tools

**MCP Server Context Injection:**
Location: cli.prettier.js:458896 (Function `Hb6`)

```javascript
[source fragment removed]
```

**What Gets Included:**
- Only connected MCP servers (type === "connected")
- Only servers that have instructions defined
- Full instructions text from the server (included verbatim)
- Used as section titled "MCP Server Instructions" in the prompt

**Example:**
```
# MCP Server Instructions

## code-intel

Provides intelligent code analysis for JavaScript, TypeScript and Python projects.

This server helps you navigate and understand codebases through structure-aware analysis...

**Discovery Tools:**
- find_symbol_by_name: Find project-wide symbols (like a "Table of Contents")
```

### 4. SKILLS - User-Defined Task Instructions

**Skill Structure:**
```
.claude/skills/
├── skill-name-1/
│   └── SKILL.md       (literal filename)
├── skill-name-2/
│   └── SKILL.md
└── skill-name-3/
    └── SKILL.md
```

**Skill Tool Injection:**
Location: cli.prettier.js:433382 (Function that builds Skill tool description)

```javascript
[source fragment removed]
```

**What Gets Included:**
- All available skills (from `.claude/skills/*/SKILL.md`)
- All available commands (mode commands and regular commands)
- Skill names are listed with fully qualified names when applicable
- Formatted as `<available_skills>` section listing all executable skills

**How Skills Are Discovered:**
1. **Built-in skills** - Available from Claude Code's core installation
2. **User-defined skills** - Discovered from `.claude/skills/SKILL_NAME/SKILL.md` files
3. **Listed dynamically** - All available skills are listed in the Skill tool instructions

**Skill Invocation:**
- User calls Skill tool with skill name only (no arguments)
- Claude Code loads the SKILL.md file from the corresponding directory
- The SKILL.md file contains the skill's prompt and detailed instructions
- Skill executes with its context available to process the user's request

### Complete Context Addition Flow

When Claude Code initializes a session:

```
1. Load base system prompt (YRA function)
   ↓
2. Assemble full prompt (Pr function):
   - Core introduction
   - Tone and style guidance
   - Task management section (if TodoWrite available)
   - Tool usage policy (including Db6 output)
   - Code references format
   ↓
3. Add conditional sections:
   - Output style prompt (if configured)
   ↓
4. Add agent information (if Task tool available):
   - Available agent types
   - Agent properties and tool access
   - Usage examples and guidance
   ↓
5. Add MCP server instructions (Hb6 output):
   - For each connected server with instructions
   - Include server-provided instructions verbatim
   ↓
6. Inject model information:
   - Model name and exact ID
   ↓
7. Apply user overrides:
   - --system-prompt / --system-prompt-file
   - --append-system-prompt
   ↓
8. Final assembled prompt sent to Claude API
```

### Runtime Context Additions

**When Tool is Invoked:**
- Tool's instructions are available in the prompt
- Tool availability reflected in "no-approval" list
- Tool restrictions documented in tool usage policy

**When Skill is Invoked:**
- Skill's SKILL.md is loaded from `.claude/skills/SKILL_NAME/SKILL.md`
- Instructions passed to Skill tool
- Skill executes with provided context

**When Agent is Invoked:**
- Agent definition looked up from available agents
- Agent's tool set provided to the agent
- Agent runs with agent-specific instructions

### Key Integration Points

The main function `Pr(A, B, Q, I, G, Z)` (cli.prettier.js:458735) receives:
- `A` - Available tools array (for Db6 filtering)
- `B` - Output style configuration
- `Q` - Tool permission context
- `I` - MCP servers array (for Hb6 output)
- `G` - Model information
- `Z` - Additional context

All of this information is dynamically incorporated into the final system prompt before being sent to the Claude API.
