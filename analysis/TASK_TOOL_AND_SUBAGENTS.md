# TODO

- Document the TeammateTool and SendMessageTool prompt text in full.
- Document the magic-docs trigger mechanism: what conversation events cause `fqz()` to fire?
- Trace `SV()` (agent deduplication/priority) to understand how conflicting agent names are resolved.

# The Agent Tool: Subagent Execution

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

See also: [Tools and Execution Architecture](TOOLS_AND_EXECUTION.md)

## The Agent Tool

The Agent tool (formerly "Task") is how the main-session Claude launches subagents.  When Claude
decides a task should be delegated, it generates a tool call like this:

```json
{
  "name": "Agent",
  "input": {
    "description": "Find error handling code",
    "prompt": "Do a very thorough search for all files that handle client errors...",
    "subagent_type": "Explore"
  }
}
```

The tool's primary name is `"Agent"` (line 69122: `pq = "Agent"`), with `"Task"` retained as an
alias (line 69123: `JJ6 = "Task"`).

The `prompt` string becomes the sole user message in the subagent's conversation.  The subagent
receives its own system prompt (from the agent definition) and runs as a completely separate
Claude API session.

### Agent Tool Input Schema

Location: cli.prettier.js:418790-418843

The input schema is built from two merged Zod schemas: `RrY` (base) and `SrY` (extended with
team/isolation fields).  `Jm8` produces the final schema, omitting `cwd` for non-teammate use
and `run_in_background` if disabled by environment variable.

```javascript
[source fragment removed]
```

Required: `description`, `prompt`, `subagent_type`.

Note: `run_in_background` can be disabled via the `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`
environment variable, in which case it is removed from the schema entirely.

### Subagent Context Isolation

Subagents do NOT inherit the main session's system prompt.  Each subagent runs with its own
isolated system prompt from its agent definition.

Location: cli.prettier.js:419070-419082

```javascript
[source fragment removed]
```

What a subagent receives:
1. Its own system prompt from `getSystemPrompt()` (defined in the agent definition)
2. The `prompt` parameter as its sole user message
3. Optionally, the main session's message history if `forksParentContext: true`

What a subagent does NOT receive:
- The main session's system prompt
- The user's `CLAUDE.md` instructions
- Main session tone/style guidance
- Tool approval rules from the main session

Implications:
- Subagents operate with minimal, focused system prompts
- If specific instructions must be followed, they must be included in the `prompt` parameter
- User customizations in `CLAUDE.md` do not propagate to subagents
- Each agent type has purpose-built instructions optimized for its task

## Built-in Agents (Agent Tool)

Location: `lW1()` at cli.prettier.js:284529

The built-in agents are returned by `lW1()`:

```javascript
[source fragment removed]
```

| # | agentType                                        | Model   | Tools                                         | Purpose                    |
| - | ------------------------------------------------ | ------- | --------------------------------------------- | -------------------------- |
| 1 | [`general-purpose`](#general-purpose-agent)      | default | All (`*`)                                     | Research, multi-step tasks |
| 2 | [`statusline-setup`](#statusline-setup-agent)    | sonnet  | Read, Edit                                    | Configure status line      |
| 3 | [`Explore`](#explore-agent)                      | haiku   | Read-only (disallows Agent, Edit, Write, etc.) | Fast codebase exploration  |
| 4 | [`Plan`](#plan-agent)                            | inherit | Same disallowed as Explore                    | Architecture/planning      |
| 5 | [`claude-code-guide`](#claude-code-guide-agent)  | haiku   | Glob, Grep, Read, WebFetch, WebSearch         | Documentation/help agent   |

Agent #5 (`claude-code-guide`) is excluded when running under Agent SDK entrypoints (`sdk-ts`,
`sdk-py`, `sdk-cli`).

### Agent Loading Pipeline

Location: cli.prettier.js:284882

```
activeAgents = [...lW1(), ...CU6(), ...userFileAgents]
```

Where:
- `lW1()` returns the 4-5 built-in agents above
- `CU6()` loads agents from plugin directories
- `userFileAgents` are parsed from `.claude/agents/*.md` files (YAML frontmatter; see MARKDOWN_FRONTMATTER.md)
- `SV()` deduplicates/prioritizes the combined list

### How `whenToUse` is Communicated to the Main Session

The `whenToUse` values are NOT injected into the main session's system prompt.  Instead, they are
included in the Agent tool's description, which is part of the tool schema sent to the Anthropic API.

Location: cli.prettier.js:284824 (function `pX4`)

The Agent tool's `prompt()` method (line 418892) calls `pX4()` to dynamically build the tool
description.  This function iterates over all active agents and includes each agent's `whenToUse`
text.

The agent list is first filtered by `_g8()` which applies permission rules — agents denied by
`Agent(agent-type)` permission rules are excluded.  The optional `allowedAgentTypes` restriction
(from agent YAML) further limits which agents appear.

This means:
1. The main session Claude sees all available agents and their `whenToUse` descriptions in the
   Agent tool's JSON schema (under the `description` field)
2. When deciding whether to use Agent and which `subagent_type` to select, Claude reads these
   descriptions directly from the tool definition
3. Adding a custom agent via `.claude/agents/<name>.md` automatically adds its `whenToUse` to
   the Agent tool description

Example of what Claude sees (formatted for readability):

```
Available agent types and the tools they have access to:
- general-purpose: General-purpose agent for researching complex questions, searching
  for code, and executing multi-step tasks. (Tools: *)
- Explore: Fast agent specialized for exploring codebases. Use this when you need to
  quickly find files by patterns... (Tools: All tools except Agent, ExitPlanMode, Edit,
  Write, NotebookEdit)
[...]
```

### Agent Definition Structure

Each agent is an object with these properties:

```javascript
[source fragment removed]
```

## Built-in Agent Details

### general-purpose Agent

Example invocation by the main session:

```json
{
  "name": "Agent",
  "input": {
    "description": "Research authentication flow",
    "prompt": "Investigate how user authentication works in this codebase. Find the login handlers, session management, and any middleware involved.",
    "subagent_type": "general-purpose"
  }
}
```

#### Execution

```
System prompt:  Y9Y() (dynamic function, see Prompt below)
User message:   "Investigate how user authentication works in this codebase..."
Model:          default (no model specified, uses system default)
Tools:          [*] (all tools)
```

#### Definition

Location: cli.prettier.js:284045-284053

```javascript
[source fragment removed]
```

#### Prompt

Location: cli.prettier.js:284020-284041 (function `Y9Y` and variables `q9Y`, `K9Y`)

The system prompt is now dynamically constructed by `Y9Y()` which conditionally shortens the
output instructions when the `tengu_tight_weave` feature flag is enabled:

```
You are an agent for Claude Code, Anthropic's official CLI for Claude. Given
the user's message, you should use the tools available to complete the task.
Do what has been asked; nothing more, nothing less.

[When tight_weave enabled:]
  When you complete the task, respond with a concise report covering what was
  done and any key findings — the caller will relay this to the user, so it
  only needs the essentials.
[Otherwise:]
  When you complete the task simply respond with a detailed writeup.

Your strengths:
- Searching for code, configurations, and patterns across large codebases
- Analyzing multiple files to understand system architecture
- Investigating complex questions that require exploring many files
- Performing multi-step research tasks

Guidelines:
- For file searches: Use Grep or Glob when you need to search broadly. Use
  Read when you know the specific file path.
- For analysis: Start broad and narrow down. Use multiple search strategies
  if the first doesn't yield results.
- Be thorough: Check multiple locations, consider different naming conventions,
  look for related files.
- NEVER create files unless they're absolutely necessary for achieving your
  goal. ALWAYS prefer editing an existing file to creating a new one.
- NEVER proactively create documentation files (*.md) or README files. Only
  create documentation files if explicitly requested.

[When tight_weave enabled:]
  - In your final response, share file paths (always absolute, never relative)
    that are relevant to the task. Include code snippets only when the exact
    text is load-bearing — do not recap code you merely read.
[Otherwise:]
  - In your final response always share relevant file names and code snippets.
    Any file paths you return in your response MUST be absolute. Do NOT use
    relative paths.

- For clear communication, avoid using emojis.
```

### statusline-setup Agent

Example invocation by the main session:

```json
{
  "name": "Agent",
  "input": {
    "description": "Configure status line",
    "prompt": "Convert my shell PS1 prompt to a Claude Code status line.",
    "subagent_type": "statusline-setup"
  }
}
```

#### Execution

```
System prompt:  getSystemPrompt() (inline function, see Prompt below)
User message:   "Convert my shell PS1 prompt to a Claude Code status line."
Model:          sonnet
Tools:          [Read, Edit]
```

#### Definition

Location: cli.prettier.js:284057-284181

```javascript
[source fragment removed]
```

#### Prompt

Location: cli.prettier.js:284067-284180

```
You are a status line setup agent for Claude Code. Your job is to create or
update the statusLine command in the user's Claude Code settings.

When asked to convert the user's shell PS1 configuration, follow these steps:
1. Read the user's shell configuration files in this order of preference:
   - ~/.zshrc
   - ~/.bashrc
   - ~/.bash_profile
   - ~/.profile

2. Extract the PS1 value using this regex pattern:
   /(?:^|\\n)\\s*(?:export\\s+)?PS1\\s*=\\s*["']([^"']+)["']/m

3. Convert PS1 escape sequences to shell commands:
   - \\u → $(whoami)
   - \\h → $(hostname -s)
   - \\H → $(hostname)
   - \\w → $(pwd)
   - \\W → $(basename "$(pwd)")
   - \\$ → $
   - \\n → \\n
   - \\t → $(date +%H:%M:%S)
   - \\d → $(date "+%a %b %d")
   - \\@ → $(date +%I:%M%p)
   - \\# → #
   - \\! → !

4. When using ANSI color codes, be sure to use `printf`. Do not remove colors.
   Note that the status line will be printed in a terminal using dimmed colors.

5. If the imported PS1 would have trailing "$" or ">" characters in the output,
   you MUST remove them.

6. If no PS1 is found and user did not provide other instructions, ask for
   further instructions.

How to use the statusLine command:
1. The statusLine command will receive the following JSON input via stdin:
   {
     "session_id": "string",
     "transcript_path": "string",
     "cwd": "string",
     "model": {
       "id": "string",
       "display_name": "string"
     },
     "workspace": {
       "current_dir": "string",
       "project_dir": "string"
     },
     "version": "string",
     "output_style": {
       "name": "string",
     },
     "context_window": {
       "total_input_tokens": number,
       "total_output_tokens": number,
       "context_window_size": number,
       "current_usage": {
         "input_tokens": number,
         "output_tokens": number,
         "cache_creation_input_tokens": number,
         "cache_read_input_tokens": number
       } | null,
       "used_percentage": number | null,
       "remaining_percentage": number | null
     },
     "vim": {
       "mode": "INSERT" | "NORMAL"
     },
     "agent": {
       "name": "string",
       "type": "string"
     }
   }

   You can use this JSON data in your command like:
   - $(cat | jq -r '.model.display_name')
   - $(cat | jq -r '.workspace.current_dir')

2. For longer commands, save a new file in ~/.claude directory, e.g.:
   ~/.claude/statusline-command.sh

3. Update the user's ~/.claude/settings.json with:
   {
     "statusLine": {
       "type": "command",
       "command": "your_command_here"
     }
   }

4. If ~/.claude/settings.json is a symlink, update the target file instead.

Guidelines:
- Preserve existing settings when updating
- Return a summary of what was configured
- If the script includes git commands, they should skip optional locks
- IMPORTANT: At the end of your response, inform the parent agent that this
  "statusline-setup" agent must be used for further status line changes.
```

### Explore Agent

Example invocation by the main session:

```json
{
  "name": "Agent",
  "input": {
    "description": "Find error handling code",
    "prompt": "Do a very thorough search for all files that handle client errors. Look for try/catch blocks, error callbacks, and .catch() handlers across the codebase.",
    "subagent_type": "Explore"
  }
}
```

The main session chooses `"Explore"` based on the `whenToUse` text (see Definition below).
It writes the thoroughness level ("very thorough") and search instructions into `prompt`,
which becomes the user message in the Explore agent's conversation.

#### Execution

The executor builds a separate API request for the subagent:

```
System prompt:  getSystemPrompt() → z9Y  (see Prompt section below)
User message:   "Do a very thorough search for all files that handle client errors..." (generated by Claude, see above)
Model:          haiku
Tools:          [Glob, Grep, Read, Bash, ...]  (excluding Agent, ExitPlanMode, Edit, Write, NotebookEdit)
```

The subagent runs as an independent Claude API session.  It does not see the main session's
system prompt or conversation history.

#### Definition

Location: cli.prettier.js:284227-284237

```javascript
[source fragment removed]
```

Note: `whenToUse` is included verbatim in the Agent tool description that the main-session Claude
sees.  It is how the main session decides which agent to use, and what to include in the `prompt`
parameter.

The "thoroughness level" concept exists purely in this natural language -- there is no parameter or
enum for it.  The main session writes something like "do a very thorough search" into the free-text
`prompt`, and the Explore agent's system prompt tells it to "adapt your search approach based on the
thoroughness level specified by the caller."

#### Prompt

Location: cli.prettier.js:284192-284226 (variable `z9Y`)

Verbatim system prompt.  The `${...}` template variables have been resolved to their runtime
tool name values in the annotation column.

```
You are a file search specialist for Claude Code,
Anthropic's official CLI for Claude. You excel at
thoroughly navigating and exploring codebases.

=== CRITICAL: READ-ONLY MODE - NO FILE MODIFICATIONS ===
This is a READ-ONLY exploration task. You are STRICTLY
PROHIBITED from:
- Creating new files (no Write, touch, or file creation
  of any kind)
- Modifying existing files (no Edit operations)
- Deleting files (no rm or deletion)
- Moving or copying files (no mv or cp)
- Creating temporary files anywhere, including /tmp
- Using redirect operators (>, >>, |) or heredocs to
  write to files
- Running ANY commands that change system state

Your role is EXCLUSIVELY to search and analyze existing
code. You do NOT have access to file editing tools -
attempting to edit files will fail.

Your strengths:
- Rapidly finding files using glob patterns
- Searching code and text with powerful regex patterns
- Reading and analyzing file contents

Guidelines:
- Use ${gz} for broad file pattern matching             ← Glob
- Use ${N5} for searching file contents with regex      ← Grep
- Use ${wq} when you know the specific file path you    ← Read
  need to read
- Use ${a4} ONLY for read-only operations (ls, git      ← Bash
  status, git log, git diff, find, cat, head, tail)
- NEVER use ${a4} for: mkdir, touch, rm, cp, mv, git   ← Bash
  add, git commit, npm install, pip install, or any
  file creation/modification
- Adapt your search approach based on the thoroughness
  level specified by the caller
- Return file paths as absolute paths in your final
  response
- For clear communication, avoid using emojis
- Communicate your final report directly as a regular
  message - do NOT attempt to create files

NOTE: You are meant to be a fast agent that returns
output as quickly as possible. In order to achieve this
you must:
- Make efficient use of the tools that you have at your
  disposal: be smart about how you search for files and
  implementations
- Wherever possible you should try to spawn multiple
  parallel tool calls for grepping and reading files

Complete the user's search request efficiently and
report your findings clearly.
```

Additionally, `criticalSystemReminder_EXPERIMENTAL` is injected as an ongoing system reminder
during the agent's execution:

```
CRITICAL: This is a READ-ONLY task. You CANNOT edit, write, or create files.
```

### Plan Agent

Example invocation by the main session:

```json
{
  "name": "Agent",
  "input": {
    "description": "Plan authentication refactor",
    "prompt": "Design an implementation plan for migrating from session-based auth to JWT tokens. Consider the existing user model and API routes.",
    "subagent_type": "Plan"
  }
}
```

#### Execution

```
System prompt:  getSystemPrompt() → _9Y  (see Prompt below)
User message:   "Design an implementation plan for migrating from session-based auth..."
Model:          inherit (uses parent session's model)
Tools:          [Glob, Grep, Read, Bash, ...]  (excluding Agent, ExitPlanMode, Edit, Write, NotebookEdit)
```

#### Definition

Location: cli.prettier.js:284295-284307

```javascript
[source fragment removed]
```

#### Prompt

Location: cli.prettier.js:284245-284294 (variable `_9Y`)

The `${...}` template variables resolve to tool names: gz=Glob, N5=Grep, wq=Read, a4=Bash.

```
You are a software architect and planning specialist for Claude Code. Your
role is to explore the codebase and design implementation plans.

=== CRITICAL: READ-ONLY MODE - NO FILE MODIFICATIONS ===
This is a READ-ONLY planning task. You are STRICTLY PROHIBITED from:
- Creating new files (no Write, touch, or file creation of any kind)
- Modifying existing files (no Edit operations)
- Deleting files (no rm or deletion)
- Moving or copying files (no mv or cp)
- Creating temporary files anywhere, including /tmp
- Using redirect operators (>, >>, |) or heredocs to write to files
- Running ANY commands that change system state

Your role is EXCLUSIVELY to explore the codebase and design implementation
plans. You do NOT have access to file editing tools - attempting to edit
files will fail.

You will be provided with a set of requirements and optionally a perspective
on how to approach the design process.

## Your Process

1. **Understand Requirements**: Focus on the requirements provided and apply
   your assigned perspective throughout the design process.

2. **Explore Thoroughly**:
   - Read any files provided to you in the initial prompt
   - Find existing patterns and conventions using ${gz}, ${N5}, and ${wq}
   - Understand the current architecture
   - Identify similar features as reference
   - Trace through relevant code paths
   - Use ${a4} ONLY for read-only operations (ls, git status, git log, git
     diff, find, cat, head, tail)
   - NEVER use ${a4} for: mkdir, touch, rm, cp, mv, git add, git commit,
     npm install, pip install, or any file creation/modification

3. **Design Solution**:
   - Create implementation approach based on your assigned perspective
   - Consider trade-offs and architectural decisions
   - Follow existing patterns where appropriate

4. **Detail the Plan**:
   - Provide step-by-step implementation strategy
   - Identify dependencies and sequencing
   - Anticipate potential challenges

## Required Output

End your response with:

### Critical Files for Implementation
List 3-5 files most critical for implementing this plan:
- path/to/file1.ts - [Brief reason: e.g., "Core logic to modify"]
- path/to/file2.ts - [Brief reason: e.g., "Interfaces to implement"]
- path/to/file3.ts - [Brief reason: e.g., "Pattern to follow"]

REMEMBER: You can ONLY explore and plan. You CANNOT and MUST NOT write,
edit, or modify any files. You do NOT have access to file editing tools.
```

### claude-code-guide Agent

Example invocation by the main session:

```json
{
  "name": "Agent",
  "input": {
    "description": "Explain MCP configuration",
    "prompt": "How do I configure MCP servers in Claude Code? What's the format for .mcp.json?",
    "subagent_type": "claude-code-guide"
  }
}
```

#### Execution

```
System prompt:  getSystemPrompt({ toolUseContext }) → O9Y + dynamic context
User message:   "How do I configure MCP servers in Claude Code?..."
Model:          haiku
Tools:          [Glob, Grep, Read, WebFetch, WebSearch]
```

#### Definition

Location: cli.prettier.js:284384-284453

```javascript
[source fragment removed]
```

Note: This agent is excluded when running under Agent SDK entrypoints (`sdk-ts`, `sdk-py`,
`sdk-cli`).

#### Prompt

Location: cli.prettier.js:284314-284383 (base prompt `O9Y`)

The `getSystemPrompt` function returns the base prompt plus dynamically appended sections
for the current project's custom skills, custom agents, MCP servers, and user settings.

The `${...}` template variables resolve to: $9Y=docs URL, ft7=API docs URL, kD=WebFetch,
Gk=WebSearch, wq=Read, gz=Glob, N5=Grep.

```
You are the Claude guide agent. Your primary responsibility is helping users
understand and use Claude Code, the Claude Agent SDK, and the Claude API
(formerly the Anthropic API) effectively.

**Your expertise spans three domains:**

1. **Claude Code** (the CLI tool): Installation, configuration, hooks, skills,
   MCP servers, keyboard shortcuts, IDE integrations, settings, and workflows.

2. **Claude Agent SDK**: A framework for building custom AI agents based on
   Claude Code technology. Available for Node.js/TypeScript and Python.

3. **Claude API**: The Claude API (formerly known as the Anthropic API) for
   direct model interaction, tool use, and integrations.

**Documentation sources:**

- **Claude Code docs** (${$9Y}): Fetch this for questions about the Claude
  Code CLI tool, including:
  - Installation, setup, and getting started
  - Hooks (pre/post command execution)
  - Custom skills
  - MCP server configuration
  - IDE integrations (VS Code, JetBrains)
  - Settings files and configuration
  - Keyboard shortcuts and hotkeys
  - Subagents and plugins
  - Sandboxing and security

- **Claude Agent SDK docs** (${ft7}): Fetch this for questions about building
  agents with the SDK, including:
  - SDK overview and getting started (Python and TypeScript)
  - Agent configuration + custom tools
  - Session management and permissions
  - MCP integration in agents
  - Hosting and deployment
  - Cost tracking and context management

- **Claude API docs** (${ft7}): Fetch this for questions about the Claude API,
  including:
  - Messages API and streaming
  - Tool use (function calling) and Anthropic-defined tools
  - Vision, PDF support, and citations
  - Extended thinking and structured outputs
  - MCP connector for remote MCP servers
  - Cloud provider integrations (Bedrock, Vertex AI, Foundry)

**Approach:**
1. Determine which domain the user's question falls into
2. Use ${kD} to fetch the appropriate docs map
3. Identify the most relevant documentation URLs from the map
4. Fetch the specific documentation pages
5. Provide clear, actionable guidance based on official documentation
6. Use ${Gk} if docs don't cover the topic
7. Reference local project files (CLAUDE.md, .claude/ directory) when relevant
   using ${wq}, ${gz}, and ${N5}

**Guidelines:**
- Always prioritize official documentation over assumptions
- Keep responses concise and actionable
- Include specific examples or code snippets when helpful
- Reference exact documentation URLs in your responses
- Avoid emojis in your responses
- Help users discover features by proactively suggesting related commands,
  shortcuts, or capabilities

Complete the user's request by providing accurate, documentation-based guidance.
```

When the project has custom configuration, additional sections are appended:
- `**Available custom skills in this project:**`
- `**Available custom agents configured:**`
- `**Configured MCP servers:**`
- `**Available plugin skills:**`
- `**User's settings.json:**`

## Non-Agent-Tool Agent Types

These use `agentType` internally but are not selectable via the Agent tool's `subagent_type`.

### main-session

Location: cli.prettier.js:411530

```javascript
[source fragment removed]
```

The user's primary Claude Code session.  Not a subagent.

### teammate

Location: cli.prettier.js:412793-412855 (function `eiY` / `inProcessRunner`)

Teammates are agents spawned through the team/swarm system.  They run via a separate
execution path (`inProcessRunner`) rather than the Agent tool's executor.

The teammate's agent definition is constructed dynamically at runtime:

```javascript
[source fragment removed]
```

Key differences from Agent-tool subagents:
- Has inter-agent messaging via a polling loop (checks for messages from team lead and task list)
- Has an identity with `agentName`, `teamName`, `color`, and `planModeRequired`
- Marked `isTeamLead: false` -- the main session is the team lead
- Long-running: polls for new work rather than returning a single result
- Can be shut down via a protocol request/response handshake
- Always includes mandatory tools: SendMessage, Team tools, TaskCreate, TaskGet, TaskList, TaskUpdate

### verification (Internal)

Location: cli.prettier.js:284455-284528 (prompt variable `VM_`)

An internal agent type used by the team system.  Not user-selectable.  When a teammate completes
3+ tasks without verification, the system prompts it to spawn a verification agent:

```
NOTE: You just closed out 3+ tasks and none of them was a verification step.
Before writing your final summary, spawn the verification agent
(subagent_type="verification").
```

The verification agent's prompt instructs it to actively try to break the implementation rather
than confirm it works.  It can write ephemeral test scripts to `/tmp` but is prohibited from
modifying project files.

### magic-docs

Location: cli.prettier.js:458426-458435

```javascript
[source fragment removed]
```

Internal agent that auto-updates "Magic Doc" files after conversation turns.  The prompt is
constructed dynamically and substitutes `{{docContents}}`, `{{docPath}}`, `{{docTitle}}`, and
`{{customInstructions}}`.

The prompt instructs the agent to:
- Update documentation in-place to reflect current codebase state (not a changelog)
- Be terse, high signal only
- Focus on architecture, entry points, patterns, and design decisions
- Not duplicate what's obvious from reading code
- Preserve the `# MAGIC DOC: <title>` header

### subagent (telemetry label)

Not a real agent type.  `agentType: "subagent"` is metadata passed to the telemetry/tracking
wrapper for every agent launched via the Agent tool, regardless of which `subagent_type`
was selected.

## Team/Swarm System

The team system coordinates multiple Claude sessions working together.  It layers on top of the
Task Management tools.

### Architecture

- The user's main session acts as "team-lead"
- Teammates are spawned via the Agent tool with `team_name` and `name` parameters
- Each teammate runs as a separate Claude session with its own message polling loop
- Teams have a 1:1 correspondence with task lists

### File System Layout

```
~/.claude/teams/{team-name}/config.json    # Team config (members, lead, etc.)
~/.claude/tasks/{team-name}/               # Shared task list (JSON files per task)
```

The `cleanup` operation removes both directories, which is why `~/.claude/teams/` may not exist
on disk.

### TeammateTool

Location: cli.prettier.js:256750

Operations: `spawnTeam`, `discoverTeams`, `requestJoin`, `approveJoin`, `rejectJoin`, `cleanup`

### SendMessageTool

Location: cli.prettier.js:449554-450234

Message types: `message` (direct), `broadcast` (team-wide, discouraged), `shutdown_request`/
`shutdown_response` (protocol for shutdown), `plan_approval_response` (approve/reject plans)

### Teammate System Prompt Addendum

Location: cli.prettier.js:412068

Appended to every teammate's system prompt:

```
# Agent Teammate Communication

IMPORTANT: You are running as a teammate in a swarm. Your plain text output
is NOT visible to the user or the team lead. To communicate with anyone on
your team:
- Use the SendMessage tool to send messages
- Use the SendMessage tool with the `broadcast` operation sparingly
- Just typing a response in text is not visible to others - you must use the tool

The user interacts only with the team lead. Your work is coordinated through
the task system and teammate messaging.
```

### Team Context Reminder

Location: cli.prettier.js:534246

Injected as a system-reminder into teammate conversations:

```
# Team Coordination

You are a teammate in team "{teamName}".

Your Identity:
- Name: {agentName}

Team Resources:
- Team config: {teamConfigPath}
- Task list: {taskListPath}

Team Leader: The team lead's name is "team-lead". [...]

IMPORTANT: Always refer to teammates by their NAME, never by UUID.
```

## Task Management Tools

The task management tools (TaskCreate, TaskUpdate, TaskGet, TaskList) serve dual purpose:

1. Solo mode: Track multi-step work within a single session.  Tasks are stored in
   `~/.claude/tasks/{session-id}/` as individual JSON files (e.g., `1.json`, `2.json`).

2. Team mode: Coordinate work across teammates.  Tasks are stored in
   `~/.claude/tasks/{team-name}/` and shared by all team members.

Task files are not cleaned up after solo sessions end.

### Task Properties

```javascript
[source fragment removed]
```

### Team-Aware Behavior

The task tool prompts are conditionally expanded when the is-teammate check is true:
- TaskCreate adds guidance about assigning tasks to teammates
- TaskList includes `assignTask` info
- TaskUpdate's completion message tells teammates to call TaskList for next work

## Agent Tool: How Claude Generates Parameters

### Agent Tool Description (Sent to Claude in API)

Location: cli.prettier.js:284824 (function `pX4`)

The Agent tool description is dynamically generated by `pX4()`.  See
[How `whenToUse` is Communicated to the Main Session](#how-whentouse-is-communicated-to-the-main-session)
for the code that builds this description.

The description includes:
1. An overview of what the Agent tool does
2. The list of available agents with their `whenToUse` text and tools (dynamically generated)
3. Guidance on when NOT to use the Agent tool (prefer simpler tools for simple tasks)
4. Usage notes (parallelism, statelessness, context forking, etc.)
5. Example invocations

Claude sees this description as part of the tool schema in the API request, under the
`tools[].description` field.  This is how Claude knows:
- What agents are available
- What each agent specializes in (`whenToUse`)
- What tools each agent has access to
- When to use the Agent tool vs simpler alternatives

### Agent Tool Input Schema (Parameter Constraints)

Location: cli.prettier.js:418790-418843

```javascript
[source fragment removed]
```

### Potential Conflicts Between Generated Prompts and Agent Instructions

There are two sets of instructions that can conflict:

1. Instructions Claude follows to generate the `prompt` parameter:
   - Agent tool description: "your prompt should contain a highly detailed task description"
   - Input schema: "The task for the agent to perform"
   - Claude's understanding of the user's request

2. Instructions the subagent follows when executing:
   - Agent YAML frontmatter from `.claude/agents/<name>.md` (see MARKDOWN_FRONTMATTER.md)
   - Agent's system prompt
   - The generated `prompt` parameter becomes the user message to the subagent

The subagent's own instructions (system prompt / YAML) take precedence.  The subagent will
follow its constraints and potentially ignore parts of the generated prompt that conflict.

## Agent Tool Implementation

### Agent Tool (Tf6)

Location: cli.prettier.js:418891-419545

```javascript
[source fragment removed]
```

Parameter Mapping:
- `A` = prompt
- `q` = subagent_type
- `K` = description
- `Y` = resume
- `z` = run_in_background
- `w` = name (teammate)
- `_` = team_name
- `$` = mode
- `O` = isolation
- `H` = cwd
- `j` = toolUseContext (2nd parameter)
- `J` = canUseTool (3rd parameter)

### Subagent Executor (gS)

Location: cli.prettier.js:405115-405324

In 2.1.69, the executor is a unified async generator function `gS` that handles the full
subagent lifecycle: system prompt setup, permission mode, tool filtering, skill preloading,
MCP client setup, and the main API loop.

```javascript
[source fragment removed]
```

Key behavioral changes from 2.1.63:
- Default permission mode is now explicitly `"acceptEdits"` (line 419106) rather than inheriting
  the parent's mode
- `gS` is called by the Agent tool's `call` method (line 419273+), not by a separate `CA1`
  function
- MCP clients can now be provided to subagents via `QcY()` (line 405228)
- Skills can be preloaded via the agent definition's `skills:` field (line 405195)
- Hooks from the agent definition are applied (line 405194)

### Execution Flow

```
Main Claude Session
    ↓ (Agent tool called)
Agent Tool (Tf6.call)
    ↓ Permission check, model resolution, worktree setup
    ↓ Teammate check → if name+team: spawn teammate via Z1q()
    ↓ Otherwise: build subagent context
    ↓
gS function (unified executor)
    ↓ Builds subagent context:
    - Permission mode (acceptEdits default)
    - Filtered tool set via Ki()
    - System prompt from agent definition via dcY()
    - Preloaded skills content
    - MCP client setup
    ↓
pS function (main API loop)
    ↓
Anthropic API: messages.create()
    ↓
Subagent runs independently
    ↓
Returns results to main session
```

### Worktree Isolation (New in 2.1.69)

Location: cli.prettier.js:419058-419114, 415642-415883

When `isolation: "worktree"` is specified (either in the Agent tool call or the agent definition):

1. A git worktree is created in `.claude/worktrees/` with name `agent-{agentId[0:8]}`
2. The subagent runs with its working directory set to the worktree via `WZA()` (AsyncLocalStorage)
3. On completion, if the worktree has changes beyond the original HEAD commit, the worktree path
   and branch are returned in the result
4. If no changes were made, the worktree is automatically cleaned up via `bw6()`

### Subagent Independence

Each subagent invocation creates a fresh API request to Anthropic, completely independent of the
main session except for what's explicitly passed via:

1. The `prompt` parameter (user's request to the agent)
2. Optional `forksParentContext` (copies main session messages)

## Subagent Output Visibility

When a subagent completes, its output passes through a pipeline that determines what the parent
model sees and what the human operator sees.

### Output Pipeline

```
Subagent's last assistant message
  → wg8() (line 418677): extract text content blocks + usage stats
    → mapToolResultToToolResultBlockParam() (line 419554): package as tool_result
      → E34() (line 249352): apply character truncation
        → Parent model receives tool_result
```

### What the Parent Model Receives

The `mapToolResultToToolResultBlockParam()` method (line 419554) constructs a `tool_result` block
containing:

- All text content blocks from the subagent's final assistant message
- Metadata: agentId, total tokens, tool use count, duration
- Worktree path and branch (if isolation was used)

This is then passed through `E34()` which applies a character-based truncation:

| Limit                      | Value      | Location    |
| -------------------------- | ---------- | ----------- |
| Agent `maxResultSizeChars` | 100K chars | Line 418912 |
| Global hard cap (`Iv8`)    | 50K chars  | Line 249271 |
| Effective limit            | 50K chars  | `Math.min(100K, 50K)` |

If the result exceeds 50K characters, `E34()` persists the full output to a file on disk and
includes a reference to that file in the truncated tool result.

### What the Human Sees

The terminal display uses an `isTranscriptMode` flag to gate content visibility:

Default view (collapsed):
- One-line summary: `Done (X tool uses · Y tokens · Z time)`
- A dimmed hint to press ctrl+o to expand

Expanded view (ctrl+o):
- The subagent's prompt
- Progress messages (tool uses during execution)
- The subagent's text content blocks (the actual output)

The subagent's actual text output is only visible to the human after pressing ctrl+o.

### Implications

The parent model's system prompt says: "The result returned by the agent is not visible to the
user.  To show the user the result, you should send a text message back to the user with a concise
summary of the result."

This is an instruction to the parent model telling it to relay/summarize the subagent result as
regular text output, since the raw tool_result content is hidden behind ctrl+o in the UI.

A subagent cannot influence this behavior.  The display logic is hardcoded -- content is
always gated behind `isTranscriptMode`.  Even if a subagent's output contained instructions like
"SHOW THIS TO THE USER", those words would only be read by the parent model, which is already
instructed to summarize rather than relay verbatim.

## Summary: Tools vs Agent-Tool Subagents vs Teammates

| Aspect        | Regular Tool              | Agent-Tool Subagent              | Teammate                          |
| ------------- | ------------------------- | -------------------------------- | --------------------------------- |
| Execution     | Synchronous function call | Separate API request             | Separate API session with polling |
| System Prompt | Uses main session prompt  | Own simplified prompt            | Base prompt + teammate addendum   |
| Context       | Shares main session       | Isolated (unless forksParent)    | Isolated with message passing     |
| Tools         | All available tools       | Filtered per agent definition    | All or filtered per definition    |
| Lifecycle     | Single call-return        | Single call-return               | Long-running, polls for work      |
| Communication | Direct return value       | Single final message             | SendMessage tool                  |
| Cost          | No additional API calls   | Full API call with tokens        | Multiple API calls over lifetime  |
| Use Case      | File ops, commands        | Complex multi-step reasoning     | Coordinated multi-agent work      |
