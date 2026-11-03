---
verified: 2.1.76
verified_on: 2026-06-06
section: API, networking, and MCP
style: landmark
scope: API call sites and request-construction pipeline
landmarks:
  - beta.messages.stream
  - CLAUDE_CODE_EXTRA_BODY
  - DISABLE_PROMPT_CACHING
---
# Anthropic API Call Sites Analysis

This document analyzes all locations where Claude Code makes API requests to Anthropic's API,
documenting the request construction pipeline and all control mechanisms that affect what context
gets included.

---

## Table of Contents

1. [Overview](#overview)
2. [API Call Sites Inventory](#api-call-sites-inventory)
3. [Request Construction Pipeline](#request-construction-pipeline)
4. [Context Control Mechanisms](#context-control-mechanisms)
5. [Parameter-Specific Assembly](#parameter-specific-assembly)
6. [Main Session vs Agent API Requests](#main-session-vs-agent-api-requests)
7. [Control Mechanism Mapping](#control-mechanism-mapping)
8. [Key Code Locations Reference](#key-code-locations-reference)
9. [Next Steps](#next-steps)

---

## Overview

Claude Code makes API requests to Anthropic's `/v1/messages` endpoint. Every request contains three
critical parameters:

- **`system`**: Array of content blocks containing the system prompt and instructions
- **`tools`**: Array of tool schemas (built-in + MCP tools)
- **`messages`**: Conversation history with user/system context wrappers

Understanding where API calls happen and how these parameters are constructed is essential for
tracing context sources.

---

## API Call Sites Inventory

### Primary API Call Site

The streaming function is the main API call for both interactive and non-interactive sessions.

**Actual API Call**:
The primary call is a streaming beta-messages request, made through the SDK client with an abort
signal attached so the session can cancel it.

A wrapper sits above it, adding a fixture-testing layer and delegating to the real implementation.
Relocate both by grepping `beta.messages.stream`.

### Secondary API Call Sites

| Function          | Purpose                    | API Method               |
| ----------------- | -------------------------- | ------------------------ |
| Batch processing  | Batch API requests         | `beta.messages.create()` |
| Token counting    | Count tokens for messages  | `beta.messages.create()` |
| Test validation   | Validate API responses     | `beta.messages.create()` |
| Print mode        | Non-streaming requests     | `beta.messages.create()` |
| Streaming wrapper | Alternative streaming path | `beta.messages.stream()` |

### Call Site Selection Logic

The primary entry point is the query entry point function, which:
1. Checks for "off-switch" (emergency disable)
2. Selects Bedrock inference profiles if applicable
3. Delegates to the streaming function for streaming
4. Returns async generator of API events

---

## Request Construction Pipeline

### High-Level Flow

```
CLI Arguments / Environment Variables / Config Files
                    ↓
        Parse & Validate Options
                    ↓
        Build Options Object
                    ↓
        Query entry point
                    ↓
        System Prompt Assembly
                    ↓
        Tool Schema Preparation
                    ↓
        Streaming function
                    ↓
        Request Body Construction
                    ↓
        Anthropic SDK API Call
```

### Values threaded through the streaming function

The streaming function holds, in order of construction: the raw system prompt array, the raw
messages array, the raw tool schemas, then the processed forms of each (system prompt as content
blocks with cache control, normalized messages, prepared tool schemas), then the assembled request
object, alongside the options object it was called with.

The distinction that matters is raw versus processed. Each of the three inputs exists in both
forms simultaneously, and only the processed form reaches the request.

### Request Object Construction

Constructed by a closure inside the streaming function:

| Field                | Built from                                             |
| -------------------- | ------------------------------------------------------ |
| `model`              | Resolved model identifier                              |
| `messages`           | Normalized conversation messages                       |
| `system`             | System prompt content blocks                           |
| `tools`              | Tool schemas plus `extraToolSchemas`                   |
| `tool_choice`        | The caller's tool-choice strategy                      |
| `betas`              | Conditional, only when beta features are active        |
| `metadata`           | User metadata                                          |
| `max_tokens`         | Resolved output cap                                    |
| `thinking`           | Extended-thinking config, or absent                    |
| `context_management` | Conditional, requires betas active and the beta listed |
| Extra fields         | Spread last, from `CLAUDE_CODE_EXTRA_BODY`             |

The extra-body spread comes last, so it can override any field above it.

### Key Processing Functions

| Function                        | Purpose                                     |
| ------------------------------- | ------------------------------------------- |
| Model resolver                  | Model identifier normalization              |
| the message normalizer          | Normalize messages with cache control       |
| the system-prompt block builder | Convert system prompt to content blocks     |
| the tool-schema preparer        | Process and filter tool schemas             |
| Metadata builder                | Generate metadata with user and session ids |

---

## Context Control Mechanisms

### 1. Command-Line Arguments

#### System Prompt Controls

| Argument                             | Effect                           | API Parameter   |
| ------------------------------------ | -------------------------------- | --------------- |
| `--system-prompt <prompt>`           | Replaces entire system prompt    | `system[0]`     |
| `--system-prompt-file <file>`        | Loads system prompt from file    | `system[0]`     |
| `--append-system-prompt <prompt>`    | Appends to default system prompt | `system[N]`     |
| `--append-system-prompt-file <file>` | Appends file contents to default | `system[N]`     |

**Processing**:
Each of the two system-prompt flags has a file-valued counterpart, and supplying both forms of the
same flag is an error printed in red to stderr. The file variant is read synchronously as UTF-8.

The pairs are `--system-prompt` with `--system-prompt-file`, and `--append-system-prompt` with
`--append-system-prompt-file`.

**Effect on Request**:
The presence of an append-system-prompt is carried through the options object as a boolean, not as
the text itself, because the base-prompt selector needs only to know whether one exists.

#### Tool Configuration

| Argument                        | Effect                             | API Parameter   | Restrictions        |
| ------------------------------- | ---------------------------------- | --------------- | ------------------- |
| `--tools <tools...>`            | Specifies available built-in tools | `tools[]`       | Only with `--print` |
| `--allowed-tools <tools...>`    | Whitelist tool patterns            | `tools[]`       | All modes           |
| `--disallowed-tools <tools...>` | Blacklist tool patterns            | `tools[]`       | All modes           |

**Example**:
```yaml
claude_args: '--allowed-tools "Bash(gh issue view:*),Bash(gh search:*),..."'
```

#### Model & Output Configuration

| Argument                    | Effect                        |
| --------------------------- | ----------------------------- |
| `--model <model>`           | Sets model for session        |
| `--fallback-model <model>`  | Auto-fallback when overloaded |
| `--print` / `-p`            | Non-interactive mode          |
| `--output-format <format>`  | text/json/stream-json         |
| `--max-turns <turns>`       | Limits agentic turns          |
| `--max-budget-usd <amount>` | Budget limit                  |

#### MCP & Plugin Configuration

| Argument                    | Effect                        |
| --------------------------- | ----------------------------- |
| `--mcp-config <configs...>` | Load MCP servers from JSON    |
| `--strict-mcp-config`       | Only use specified MCP config |
| `--plugin-dir <paths...>`   | Load plugins from directories |

#### Permission & Session Controls

| Argument                    | Effect                                      |
| --------------------------- | ------------------------------------------- |
| `--permission-mode <mode>`  | Sets permission mode (auto/manual/disabled) |
| `--session-id <uuid>`       | Use specific session ID                     |
| `--continue` / `-c`         | Continue most recent conversation           |
| `--resume [sessionId]`      | Resume a conversation                       |
| `--fork-session`            | Create new session ID when resuming         |
| `--settings <file-or-json>` | Load additional settings                    |

### 2. Environment Variables

#### Authentication & API Provider

| Variable                  | Effect                | Default   |
| ------------------------- | --------------------- | --------- |
| `ANTHROPIC_API_KEY`       | API key for Anthropic | Required  |
| `CLAUDE_CODE_OAUTH_TOKEN` | OAuth token           | Preferred |
| `CLAUDE_CODE_USE_BEDROCK` | Use AWS Bedrock       | False     |
| `CLAUDE_CODE_USE_VERTEX`  | Use Google Vertex     | False     |

**Provider Detection**:
Bedrock and Vertex are each selected by a truthy env var, and each has a companion var that skips
its authentication: `CLAUDE_CODE_USE_BEDROCK` with `CLAUDE_CODE_SKIP_BEDROCK_AUTH`, and
`CLAUDE_CODE_USE_VERTEX` with `CLAUDE_CODE_SKIP_VERTEX_AUTH`.

#### Context & Content Controls

| Variable                          | Effect                      | API Parameter   |
| --------------------------------- | --------------------------- | --------------- |
| `CLAUDE_CODE_DISABLE_CLAUDE_MDS`  | Disable CLAUDE.md loading   | `system[]`      |
| `CLAUDE_CODE_DISABLE_ATTACHMENTS` | Disable attachments         | `messages[]`    |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS`   | Override max output tokens  | `max_tokens`    |
| `CLAUDE_CODE_EXTRA_BODY`          | Extra JSON for request body | All params      |

**EXTRA_BODY Processing**:
`CLAUDE_CODE_EXTRA_BODY` is parsed as JSON. A value that parses to a non-array object is used; a
value that parses to anything else, or fails to parse, logs an error and is discarded rather than
throwing. The result is spread over the request body.

**Power User Note**: `CLAUDE_CODE_EXTRA_BODY` can inject ANY field into the request body!

#### Prompt Caching Controls

| Variable                        | Effect                     |
| ------------------------------- | -------------------------- |
| `DISABLE_PROMPT_CACHING`        | Disable all prompt caching |
| `DISABLE_PROMPT_CACHING_HAIKU`  | Disable for Haiku only     |
| `DISABLE_PROMPT_CACHING_SONNET` | Disable for Sonnet only    |
| `DISABLE_PROMPT_CACHING_OPUS`   | Disable for Opus only      |

**Cache Enable Function**:
Caching is enabled unless `DISABLE_PROMPT_CACHING` is truthy, which disables it outright. Three
per-model variants, `DISABLE_PROMPT_CACHING_HAIKU`, `_SONNET` and `_OPUS`, disable it only when the
resolved model matches that family.
The caching decision is passed into the system-prompt block builder as a parameter, so the same
builder produces cached or uncached blocks.

#### Tool & Bash Configuration

| Variable                                      | Effect                            | Code Location        |
| --------------------------------------------- | --------------------------------- | -------------------- |
| `CLAUDE_CODE_USE_NATIVE_FILE_SEARCH`          | Use native file search vs ripgrep |                      |
| `CLAUDE_CODE_GIT_BASH_PATH`                   | Git bash path (Windows)           |                      |
| `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`    | Maintain bash cwd                 |                      |
| `CLAUDE_CODE_SHELL_PREFIX`                    | Prefix for shell commands         |                      |
| `CLAUDE_CODE_DISABLE_COMMAND_INJECTION_CHECK` | Disable injection check           |                      |

#### Performance & Behavior

| Variable                                 | Effect                     | Code Location        |
| ---------------------------------------- | -------------------------- | -------------------- |
| `CLAUDE_CODE_SUBAGENT_MODEL`             | Override subagent model    |                      |
| `CLAUDE_CODE_MAX_RETRIES`                | Max API retries            |                      |
| `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY`   | Tool concurrency limit     |                      |
| `CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING` | Disable file checkpointing |                      |

### 3. Configuration Files

#### Settings Files (JSON)

**Locations checked in order**:
1. Managed settings: `~/.claude/managed-settings.json`
2. User settings: `~/.claude/settings.json`
3. Project settings: `.claude/settings.json`

**Schema**: `https://json.schemastore.org/claude-code-settings.json`

**CLI Override**: `--settings <file-or-json>`

**Source Control**: `--setting-sources <sources>` controls which are loaded

#### MCP Configuration

**Default Locations**: Checked at enterprise config level

**Overrides**:
- `--mcp-config <configs>`: Add additional configs
- `--strict-mcp-config`: ONLY use specified configs

### 4. Programmatic Controls

#### Options Object Structure

Passed to the query entry point function:

| Option                     | Meaning                              |
| -------------------------- | ------------------------------------ |
| `model`                    | Model id                             |
| `getToolPermissionContext` | Async permission context accessor    |
| `agents`                   | Custom agent definitions             |
| `isNonInteractiveSession`  | From `--print`                       |
| `hasAppendSystemPrompt`    | From `--append-system-prompt`        |
| `querySource`              | Source identifier                    |
| `mcpTools`                 | MCP tool schemas                     |
| `toolChoice`               | Tool-choice strategy                 |
| `enablePromptCaching`      | Prompt caching flag                  |
| `maxOutputTokensOverride`  | Output token override                |
| `temperatureOverride`      | Temperature override                 |
| `extraToolSchemas`         | Additional tool schemas              |
| `fallbackModel`            | Fallback model                       |
| `fetchOverride`            | Custom fetch implementation          |
| `queryTracking`            | Query tracking data                  |

#### Beta Features
The `betas` field is spread in conditionally, so it is absent rather than empty when no beta is
active.

Betas conditionally included based on:
- Model capabilities
- Environment settings
- Feature flags

#### Extended Thinking
Extended thinking is included only when the resolved budget is above zero, as
`{ budget_tokens, type: "enabled" }`, and omitted entirely otherwise.

Controlled by `maxThinkingTokens` parameter passed to the query entry point.

---

## Parameter-Specific Assembly

### System Prompt Assembly

#### Base Opening Statement

**Function**: the base-prompt selector

**Constants**:
Three base prompts exist as constants. Their opening lines are `You are Claude Code, Anthropic's
official CLI for Claude`, the same sentence extended with `running within the Claude Agent SDK`, and
`You are a Claude agent, built on Anthropic's Claude Agent SDK`. Verbatim text is in
`PROMPTS_RENDERED.md`.

**Selection Logic**:
Selection is by deployment and interactivity, not by model. Vertex always gets the plain CLI prompt.
A non-interactive session gets the Agent SDK prompt, in the `running within` form when an
append-system-prompt is present and the bare Claude-agent form when it is not. Everything else gets
the plain CLI prompt.

That an append-system-prompt changes which base prompt is selected, rather than only appending to
it, is the non-obvious part.

#### System Prompt Construction

The system prompt array is the selected base prompt, followed by any custom system prompts from the
CLI arguments, followed by the MCP tools documentation. Falsy entries are filtered out, so an absent
section leaves no gap.

Components assembled:
1. Base opening statement (the base-prompt selector)
2. Custom system prompt (from `--system-prompt` or `--append-system-prompt`)
3. MCP server instructions (the MCP tools documentation builder)

#### Agent System Prompt Assembly

**Function**: the agent prompt builder

The agent prompt builder appends two things to the base instructions it is given: a fixed `Notes:`
block, and the rendered environment information.

The notes cover three rules, which is worth knowing because they are agent-specific and appear
nowhere in the main-thread prompt: agent threads reset their working directory between bash calls so
paths must be absolute, the final response must share relevant file names and code snippets with
absolute paths, and emojis are to be avoided. Verbatim text is in `PROMPTS_RENDERED.md`.

#### Environment Information

**Function**: the environment-info renderer

Assembles environment block including:
- Working directory
- Git repository status
- Platform information
- OS version
- Today's date
- Model name and ID
- Knowledge cutoff date

#### MCP Server Instructions

**Function**: the MCP tools documentation builder

Adds comprehensive MCP CLI command documentation when MCP tools are available.

#### System Prompt to Content Blocks

**Function**: the system-prompt block builder

Each system prompt string becomes a `text` content block. When caching is enabled, every block also
carries a `cache_control` entry; when it is not, the blocks are otherwise identical.

Converts system prompt string array to content blocks with optional cache control.

### Tools Array Assembly

#### Built-in Tool Definitions

**Complete Built-in Tool Names (All 18 Tools)**:

Built-in tool names, as they appear in the `tools` array:

`Read`, `Write`, `Edit`, `NotebookEdit`, `Bash`, `BashOutput`, `KillShell`, `Glob`, `Grep`,
`WebFetch`, `WebSearch`, `Task`, `TodoWrite`, `AskUserQuestion`, `SlashCommand`, `Skill`,
`ListMcpResourcesTool`, `ReadMcpResourceTool`.

Most are held in module-level constants rather than written as literals at the registration site, so
grep a tool name and follow the constant to its uses. A few are named directly in their schema.

Tool descriptions are constants for the static ones and functions for those that vary at runtime.
The Bash description is a function because it assembles per-model and gated sections; see
`GIT_USAGE.md`. Verbatim text for every description is in `PROMPTS_RENDERED.md`.

#### Tool Processing Pipeline

Tools processed through the tool-schema preparer to prepare schemas

Final tools array assembly:
The tools array is the built-in and MCP schemas followed by `extraToolSchemas`, defaulting to empty.

Where:
- `J` = Processed built-in + MCP tools
- `Z.extraToolSchemas` = Additional runtime tools

### Messages Array Assembly

#### User Context Loading

**Function**: the claudeMd context entry

The `claudeMd` context entry is memoized and resolves to the assembled memory-file contents, or to
nothing at all when `CLAUDE_CODE_DISABLE_CLAUDE_MDS` is set. Note it is the key that disappears, not
a key with an empty value.

Loads CLAUDE.md memory files unless disabled.

#### System Context Loading

**Function**: the gitStatus context entry

The `gitStatus` entry is memoized the same way, and the key is present only when the git status
collector returns something.

Loads git status information.

#### Memory File Assembly

**Function**: the memory assembly

The memory assembly walks the memory file entries, skipping any without content, and renders each as
`Contents of <path><suffix>:` followed by a blank line and the file's content.

The suffix names the scope, and the three values are the useful landmark here:

| Entry type | Suffix                                                      |
| ---------- | ----------------------------------------------------------- |
| Project    | ` (project instructions, checked into the codebase)`        |
| Local      | ` (user's private project instructions, not checked in)`    |
| Other      | ` (user's private global instructions for all projects)`    |

With no entries carrying content the result is the empty string. Otherwise the rendered entries are
joined by blank lines under a fixed lead-in sentence.

**Preamble constant**:
The lead-in is a single constant sentence beginning `Codebase and user instructions are shown
below`, which asserts that these instructions override default behavior. Verbatim text is in
`PROMPTS_RENDERED.md`.

#### Memory File Discovery

**Function**: the memory-file collector

Searches for CLAUDE.md files in hierarchy:
1. Managed location (global `~/.claude/CLAUDE.md`)
2. User settings location
3. Project locations (walking up directory tree):
   - `CLAUDE.md`
   - `.claude/CLAUDE.md`
   - `CLAUDE.local.md`

#### Context Injection Wrapper

**Function**: the context injection function

Context entries are injected as a synthetic user message prepended to the conversation, and an empty
context object short-circuits to the original messages rather than producing an empty reminder.

The message is a `<system-reminder>` block whose body is the lead-in `As you answer the user's
questions, you can use the following context:`, then each entry rendered as a `#` heading naming the
key followed by its value, then a closing caution that the context may not be relevant. It is marked
`isMeta`. Verbatim text is in `PROMPTS_RENDERED.md`.

Wraps messages with user context (CLAUDE.md) and system context (git status).

#### Message Processing

**Function**: the message normalizer

Normalizes messages and adds cache control to message content blocks.

---

## Main Session vs Agent API Requests

### Comparison Table

| Aspect                      | Main Session                | Agent (Subagent)                       |
| --------------------------- | --------------------------- | -------------------------------------- |
| **API Call**                | Original request            | Separate, independent request          |
| **System Prompt**           | Full (~2.6k tokens)         | Simplified (~500 tokens)               |
| **Base Statement**          | "You are Claude Code..."    | "You are an agent for Claude Code..."  |
| **Tools**                   | All 18 + MCP tools          | Filtered subset (per agent definition) |
| **Conversation History**    | Full session history        | Isolated (or forked if configured)     |
| **MCP Server Instructions** | Included in system prompt   | Empty (no MCP clients)                 |
| **Memory Files**            | Included (CLAUDE.md)        | NOT included                           |
| **Environment Info**        | Included                    | Included                               |
| **Token Cost**              | Part of main session budget | Separate API call (additional cost)    |
| **Context Isolation**       | Shared with user            | Isolated task context                  |

### Main Session System Prompt Components

1. Base opening: "You are Claude Code, Anthropic's official CLI for Claude."
2. Core instructions (tone, style, professional objectivity)
3. Task Management section (if TodoWrite available)
4. Hooks notice
5. Tool usage policy
6. Environment information
7. Code references format
8. Output style details (if custom)
9. MCP server instructions (if MCP tools connected)
10. Memory files (CLAUDE.md)

### Agent System Prompt Components

1. Base opening: "You are an agent for Claude Code..."
2. Agent-specific instructions
3. Notes about absolute paths and emoji avoidance
4. Environment information

**Agent System Prompt Function**: the agent prompt builder

### Why This Matters

1. **Cost**: Each subagent invocation = separate API call with own token usage
2. **Context Isolation**: Subagents don't see memory files or full conversation
3. **Tool Filtering**: Subagents only get tools specified in their definition
4. **Simpler Instructions**: Subagents have focused, task-specific instructions

---

## Control Mechanism Mapping

### Master Control → API Parameter Table

| Control Type   | Control Name                      | API Parameter              | Code Location   |
| -------------- | --------------------------------- | -------------------------- | --------------- |
| CLI Arg        | `--system-prompt`                 | `system` array             | 468789-468796   |
| CLI Arg        | `--append-system-prompt`          | `system` array, flag       | 468792          |
| CLI Arg        | `--model`                         | `model`                    | 468837          |
| CLI Arg        | `--tools`                         | `tools` array              | 468840          |
| CLI Arg        | `--allowed-tools`                 | `tools` array (filtered)   | Tool filtering  |
| CLI Arg        | `--disallowed-tools`              | `tools` array (filtered)   | Tool filtering  |
| Env Var        | `CLAUDE_CODE_MAX_OUTPUT_TOKENS`   | `max_tokens`               | 468844          |
| Env Var        | `CLAUDE_CODE_EXTRA_BODY`          | Entire request body        | 468585-468609   |
| Env Var        | `DISABLE_PROMPT_CACHING`          | Cache control blocks       | 468797          |
| Env Var        | `CLAUDE_CODE_DISABLE_CLAUDE_MDS`  | `system` array content     | 321038          |
| Env Var        | `CLAUDE_CODE_DISABLE_ATTACHMENTS` | Message attachments        | 313062          |
| Env Var        | `CLAUDE_CODE_USE_BEDROCK`         | Provider, endpoint, model  | 206235          |
| Env Var        | `CLAUDE_CODE_USE_VERTEX`          | Provider, endpoint, system | 206261          |
| Programmatic   | `isNonInteractiveSession`         | Base system prompt variant | 468791          |
| Programmatic   | `maxThinkingTokens`               | `thinking` parameter       | 468828          |
| Programmatic   | `temperatureOverride`             | `temperature`              | 468813          |
| Programmatic   | `toolChoice`                      | `tool_choice`              | 468841          |
| Programmatic   | `extraToolSchemas`                | `tools` array              | 468840          |
| Programmatic   | `mcpTools`                        | `system` array (MCP docs)  | 468795          |
| Programmatic   | `enablePromptCaching`             | Cache control blocks       | 468797          |
| Programmatic   | `querySource`                     | Metadata/telemetry         | 468816          |
| Metadata       | Session/Account IDs               | `metadata.user_id`         | 468843          |
| Config         | Beta features                     | `betas` array              | 468842          |

### Controls by API Parameter

#### `system` Parameter

| Control                          | Effect                           |
| -------------------------------- | -------------------------------- |
| `--system-prompt`                | Replaces entire system prompt    |
| `--append-system-prompt`         | Appends to default system prompt |
| `CLAUDE_CODE_DISABLE_CLAUDE_MDS` | Removes CLAUDE.md content        |
| `isNonInteractiveSession`        | Changes base opening statement   |
| `mcpTools`                       | Adds MCP server instructions     |

#### `tools` Parameter

| Control              | Effect                    |
| -------------------- | ------------------------- |
| `--tools`            | Specifies available tools |
| `--allowed-tools`    | Whitelist filter          |
| `--disallowed-tools` | Blacklist filter          |
| `extraToolSchemas`   | Adds additional tools     |

#### `messages` Parameter

| Control                           | Effect                        |
| --------------------------------- | ----------------------------- |
| `CLAUDE_CODE_DISABLE_ATTACHMENTS` | Removes attachments           |
| User/system context wrappers      | Adds CLAUDE.md and git status |

#### Other Parameters

| Control                         | Parameter     | Effect                   |
| ------------------------------- | ------------- | ------------------------ |
| `--model`                       | `model`       | Sets model ID            |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | `max_tokens`  | Overrides token limit    |
| `maxThinkingTokens`             | `thinking`    | Extended thinking budget |
| `DISABLE_PROMPT_CACHING`        | Cache control | Disables caching         |
| `CLAUDE_CODE_EXTRA_BODY`        | ANY           | Injects arbitrary fields |

---

## Key Code Locations Reference

### Quick Lookup Table

| Function/Location                   | Purpose                      |
| ----------------------------------- | ---------------------------- |
| the query entry point               | Main API call entry point    |
| the streaming function              | Streaming API implementation |
| Request construction                | Builds final request object  |
| Actual API call                     | `c.beta.messages.stream()`   |
| System prompt assembly              | Builds system array          |
| the base-prompt selector            | Base system prompt selection |
| the agent prompt builder            | Agent system prompt assembly |
| the environment-info renderer       | Environment information      |
| the MCP tools documentation builder | MCP server instructions      |
| the system-prompt block builder     | System to content blocks     |
| the message normalizer              | Messages normalization       |
| Metadata builder                    | Metadata generation          |
| the memory assembly                 | CLAUDE.md assembly           |
| the memory-file collector           | CLAUDE.md discovery          |
| the context injection function      | Context wrapper injection    |
| the claudeMd context entry          | User context loader          |
| the gitStatus context entry         | System context loader        |
| the caching predicate               | Cache enable check           |
| EXTRA_BODY parsing                  | Extra request body fields    |
| CLI args parsing                    | System prompt args           |
| Tool constants                      | Built-in tool names          |

### Key Constants

| Constant            | Value                                                                  |
| ------------------- | ---------------------------------------------------------------------- |
| CLI base prompt     | `You are Claude Code, Anthropic's official CLI for Claude.`            |
| Agent SDK prompt    | The same sentence extended with `running within the Claude Agent SDK.` |
| Claude agent prompt | `You are a Claude agent, built on Anthropic's Claude Agent SDK.`       |
| Memory preamble     | `Codebase and user instructions are shown below...`                    |

Verbatim text is in `PROMPTS_RENDERED.md`.

---

## Next Steps

This document establishes the foundation for deeper context tracing. The following phases can now
proceed:

### Phase 2: System Prompt Text Sources

**Goal**: Trace every string literal and variable that contributes to the `system` parameter.

**Approach**:
1. Start from the system-prompt block builder function
2. Trace backward through `B` variable assembly
3. Follow each component:
   - the base-prompt selector → base statement constants
   - Custom system prompts → CLI args
   - the MCP tools documentation builder → MCP instructions
4. Use code-intel tools to find all references
5. Document every source location

### Phase 3: Tool Registration & Descriptions

**Goal**: Document all tool schemas and their text descriptions.

**Approach**:
1. Start from `tools` array in request
2. Trace `J` variable through the tool-schema preparer processing
3. Find all built-in tool definitions
4. Trace MCP tool integration
5. Document tool description sources

### Phase 4: Dynamic Context Assembly

**Goal**: Understand runtime context assembly (memory files, environment, etc.).

**Approach**:
1. Trace the memory assembly → the memory-file collector → file reads
2. Follow the environment-info renderer → environment variable collection
3. Map the context injection function → context wrapper injection
4. Document all file I/O and environment access

### Phase 5: Complete Context Map

**Goal**: Create comprehensive map of ALL context sources.

**Deliverable**: Master document showing:
- Every text literal contributing to context
- Every variable/function in the data flow
- Every file read operation
- Every environment variable
- Complete traceability from source to API request

---

---

## Additional Technical Details & Clarifications

### 1. Anthropic SDK Version

**SDK Type**: The code uses the beta Anthropic SDK via `client.beta.messages.stream()` and
`client.beta.messages.create()`.

**Version**: The SDK version is not explicitly declared in package.json (no `@anthropic-ai/sdk`
dependency listed). The code bundles the SDK or uses dynamic imports.

**Note**: The use of `client.beta.*` methods indicates the SDK uses the beta namespace, which is the
standard way to access beta API features (see Claude docs).

### 2. System-Reminder XML Element

**Purpose**: The `<system-reminder>` XML wrapper is **custom to Claude Code**, not part of the
official Anthropic API specification.

Generated by the context injection function.

**Function**: It wraps user context (CLAUDE.md files) and system context (git status) to inject them
into the conversation as specially-marked metadata messages that Claude treats as system-level
information.

**Example Content** (from):
```
<system-reminder>
As you answer the user's questions, you can use the following context:
# claudeMd
[CLAUDE.md contents here]

IMPORTANT: this context may or may not be relevant to your tasks. You should not respond to this context unless it is highly relevant to your task.
</system-reminder>
```

**Why XML**: The XML-style markup makes it visually distinct in the message stream and helps Claude
understand it's metadata rather than user content.

### 3. Beta Features Currently Active/Available

Based on code analysis, Claude Code includes these beta features:

| Beta Feature                      | Constant               | Code Line      | Enabled When                                                  |
| --------------------------------- | ---------------------- | -------------- | ------------------------------------------------------------- |
| `interleaved-thinking-2025-05-14` | `gAQ`                  | 206331, 206378 | Model supports thinking & not disabled                        |
| `context-management-2025-06-27`   | `luA`                  | 206334, 206386 | `preserve_thinking` enabled OR `USE_API_CONTEXT_MANAGEMENT=1` |
| Token-efficient tools             | `uAQ`                  | 206384         | First-party Anthropic & fine-grained streaming enabled        |
| `oauth-2025-04-20`                | `aAA`                  | 31679, 206373  | User authenticated via OAuth                                  |
| Fine-grained tool streaming       | `uAQ`                  | 206384         | First-party, fine-grained streaming not disabled              |
| Tool PEAR                         | `mAQ`                  | 206388         | Feature flag `tengu_tool_pear` enabled                        |
| Vertex AI features                | `dAQ`                  | 206389         | Running on Vertex AI                                          |
| Custom betas from env             | `ANTHROPIC_BETAS`      | 206390-206395  | `ANTHROPIC_BETAS` environment variable set                    |
| Skills                            | `skills-2025-10-02`    | 146283+        | Used throughout file operations                               |
| Files API                         | `files-api-2025-04-14` | 145705+        | Used for file upload operations                               |

**Key Functions**:
- **the beta-features builder function**: Builds the beta features array based on model and configuration
- **the model-specific beta filter function**: Applies model-specific filtering (Bedrock filters some betas)
- **the Bedrock beta list function**: Gets Bedrock-specific betas only

### 4. Context Management Beta Feature (`context_management` Parameter)

**Documentation Match**: YES - This relates directly to the Anthropic API's context editing feature.

**What It Is**: The `context_management` parameter enables automatic context editing strategies to
manage conversation context as it grows.

**How It Works**:
`context_management` is included only when all three hold: a config was built, betas are active, and
the context-management beta is in the active beta list.

Where:
- `y` = context management configuration from the context-management config builder function
- `C` = betas are enabled
- `X.includes(luA)` = context-management-2025-06-27 beta is included
- `luA` = "context-management-2025-06-27"

**Configuration Source** (the context-management config builder):
The context-management config is built only when the `preserve_thinking` feature returns enabled,
and is otherwise absent. Within it, two env vars select the strategies:
`USE_API_CLEAR_TOOL_RESULTS` and `USE_API_CLEAR_TOOL_USES`, feeding the dated
`clear_tool_uses_*` and `clear_thinking_*` edit types.

**Environment Variables That Control It**:
- `USE_API_CLEAR_TOOL_RESULTS`: Enable tool result clearing strategy
- `USE_API_CLEAR_TOOL_USES`: Enable tool use clearing strategy
- `API_MAX_INPUT_TOKENS`: Threshold for clearing
- `API_TARGET_INPUT_TOKENS`: Target tokens after clearing

**Relation to Thinking Blocks**: YES - When extended thinking is enabled, `context_management` can
automatically manage thinking block history to prevent context overflow, as documented in the
Anthropic API.

### 5. CLAUDE_CODE_EXTRA_BODY Purpose

**Function**: **Experimental feature for Anthropic to inject custom API request fields** without
requiring Claude Code code changes.

**How It Works**:
The extra-body builder parses `CLAUDE_CODE_EXTRA_BODY` as JSON, accepts only a non-array object,
logs and discards anything else, and spreads the result over the request body. It then merges
`anthropic_beta` separately rather than letting the spread overwrite the computed beta list.

**Use Cases**:
1. **Anthropic experiments**: Test new API fields without shipping code changes
2. **Feature flags**: Enable/disable fields per deployment
3. **Custom headers**: Add organization-specific metadata
4. **A/B testing**: Vary request structure across clients

**Example Usage**:
```bash
CLAUDE_CODE_EXTRA_BODY='{"custom_field":"value","experimental_mode":true}' claude
```

**Merged Into**: The final request body: `...AA`

### 6. `fetchOverride` and `queryTracking`

**`fetchOverride`**:
- Part of options object passed to the query entry point function
- Allows custom HTTP client implementation
- Used for network customization, proxying, or testing
- Not used in the visible request construction: the fetch call is built without consulting it.

**`queryTracking`**:
- Passed to telemetry/analytics: `queryTracking: Z.queryTracking`
- Consumed by the query-tracking reporter
- Includes information like:
  - `model`: Model used
  - `messagesLength`: Serialized request size
  - `temperature`: Temperature override
  - `betas`: Enabled beta features
  - `permissionMode`: Permission mode
  - `querySource`: Source identifier

**Purpose**: Provides fine-grained telemetry about API calls for monitoring and debugging.

### 7. Agent System Prompt (the agent prompt builder) Customization

**Can It Be Changed?**

No direct CLI customization for agent system prompts. The the agent prompt builder function builds a
fixed system prompt structure for agents:

The agent prompt builder returns the base instructions, then the fixed `Notes:` block, then the
rendered environment information. See "System Prompt Assembly" above.

**Arguments**:
- `A`: Base system prompt components (not user-customizable)
- `B`: Agent metadata (not user-customizable)
- `Q`: Query object (not user-customizable)

**Affected By**:
- `--append-system-prompt`: Does NOT affect agent prompts (agents get separate context)
- `--system-prompt`: Does NOT affect agent prompts
- Only main session prompts are customizable via CLI

**Agent-Specific Design**: Agents intentionally have simplified prompts to keep them focused and
reduce context overhead.

### 8. Token Count Claims (500 vs 2.6K)

These are **estimates, not exact**. Evidence:

**Main Session**: ~2.6k tokens based on:
- Base system prompt: ~500-600 tokens
- Tone and style section: ~200 tokens
- Task management section: ~300-400 tokens
- Tool usage policy: ~300-400 tokens
- Environment info: ~150 tokens
- MCP instructions (when present): ~200-500 tokens
- Memory files (when present): Variable

**Agent Session**: ~500 tokens based on:
- Base agent opening: ~50 tokens
- Notes section: ~100 tokens
- Environment info: ~150 tokens
- Simplifications: No tone/style, no task management, no tool policy sections

**How Known**: These are reasonable estimates based on:
1. Typical token counting (roughly 1 token per 4 characters for English text)
2. Code structure analysis
3. Actual tests with the token counting API (for how the categories fill a session, see
   [Explore the context window](https://code.claude.com/docs/en/context-window))

**Note**: Token counts are NOT coded as constants in the source - they're derived from analysis.

### 9. Core Instructions Text - Found!

The "Core instructions" category is generated dynamically from multiple sources rather than a single
text constant. However, key sections are:

**Base core instructions** are in the main system prompt assembly, and include:
- "You are Claude Code, Anthropic's official CLI for Claude."
- "You are an interactive CLI tool that helps users with software engineering tasks..."
- Security policy text about authorized usage
- Help and feedback instructions

**These sections are conditionally assembled** in the request construction from:
1. the base-prompt selector function result (base statement)
2. Custom system prompt (from CLI args)
3. the MCP tools documentation builder result (MCP instructions)

The full literal text isn't a single constant - it's built at runtime from multiple sources as
described in the report's "System Prompt Assembly" section.

---

## Summary

Claude Code provides extensive control over API request context through:

- **26 CLI arguments** affecting requests
- **60+ environment variables** controlling behavior
- **3-tier configuration system** (managed/user/project)
- **Programmatic API options** for advanced control
- **Special modes** (Agent SDK, Bedrock, Vertex)

The most powerful control mechanisms:
1. `CLAUDE_CODE_EXTRA_BODY` - Injects arbitrary fields
2. Programmatic options object - Fine-grained control
3. `--system-prompt` / `--append-system-prompt` - Direct system prompt control

All controls flow through: the query entry point → the streaming function → request body assembly →
Anthropic API

**Key Insight**: Starting from the API request construction we can trace backward to find ALL
context sources, because everything must flow through one of the three parameters: `system`,
`tools`, or `messages`.
