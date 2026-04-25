# Anthropic API Call Sites Analysis

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

This document analyzes all locations where Claude Code makes API requests to Anthropic's API, documenting the request construction pipeline and all control mechanisms that affect what context gets included.

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

Claude Code makes API requests to Anthropic's `/v1/messages` endpoint. Every request contains three critical parameters:

- **`system`**: Array of content blocks containing the system prompt and instructions
- **`tools`**: Array of tool schemas (built-in + MCP tools)
- **`messages`**: Conversation history with user/system context wrappers

Understanding where API calls happen and how these parameters are constructed is essential for tracing context sources.

---

## API Call Sites Inventory

### Primary API Call Site

**Function**: `Js2()` (Streaming API implementation)
**Location**: Line 468762-469090
**Purpose**: Main streaming API call for interactive and non-interactive sessions

**Actual API Call** (Line 468871):
```javascript
[source fragment removed]
```

Where:
- `c` = Anthropic SDK client
- `EA` = Request object (constructed in closure)
- `G` = Abort signal for cancellation

**Wrapper Function**: `H6A()` (Line 468750-468761)
**Purpose**: Wraps `Js2()` with fixture testing layer, delegates to actual implementation

### Secondary API Call Sites

| Function | Line | Purpose | API Method |
|----------|------|---------|------------|
| Batch processing | 146096 | Batch API requests | `beta.messages.create()` |
| Token counting | 270240 | Count tokens for messages | `beta.messages.create()` |
| Test validation | 467051 | Validate API responses | `beta.messages.create()` |
| Print mode | 468649 | Non-streaming requests | `beta.messages.create()` |
| Streaming wrapper | 469090 | Alternative streaming path | `beta.messages.stream()` |

### Call Site Selection Logic

The primary entry point is `ES()` function (line 468734), which:
1. Checks for "off-switch" (emergency disable)
2. Selects Bedrock inference profiles if applicable
3. Delegates to `Js2()` for streaming
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
        ES() Entry Point (line 468734)
                    ↓
        System Prompt Assembly (lines 468788-468796)
                    ↓
        Tool Schema Preparation (line 468775)
                    ↓
        Js2() Streaming Function (line 468762)
                    ↓
        Request Body Construction (line 468836)
                    ↓
        Anthropic SDK API Call (line 468871)
```

### Variable Name Mapping (Obfuscated)

In `Js2()` function context:

| Variable | Purpose | Type |
|----------|---------|------|
| `B` | System prompt array (before processing) | `string[]` |
| `A` | Messages array | `Message[]` |
| `I` | Tools array (schemas) | `Tool[]` |
| `F` | Final system prompt blocks (with cache control) | `ContentBlock[]` |
| `V` | Normalized messages | `Message[]` |
| `J` | Processed tool schemas | `Tool[]` |
| `EA` | Final request object | `object` |
| `Z` | Options object passed to ES() | `object` |

### Request Object Construction

**Location**: Line 468836-468848
**Constructed in**: Closure function `U()` within `Js2()`

```javascript
[source fragment removed]
```

### Key Processing Functions

| Function | Line | Purpose |
|----------|------|---------|
| `kg()` | Unknown | Model identifier normalization |
| `sAI()` | 469227 | Normalize messages with cache control |
| `rAI()` | 469227 | Convert system prompt to content blocks |
| `f01()` | Unknown | Process and filter tool schemas |
| `Pu()` | 468632 | Generate metadata with user/session IDs |

---

## Context Control Mechanisms

### 1. Command-Line Arguments

#### System Prompt Controls

| Argument | Effect | API Parameter | Code Location |
|----------|--------|---------------|---------------|
| `--system-prompt <prompt>` | Replaces entire system prompt | `system[0]` | Line 491764 |
| `--system-prompt-file <file>` | Loads system prompt from file | `system[0]` | Line 491769 |
| `--append-system-prompt <prompt>` | Appends to default system prompt | `system[N]` | Line 491775 |
| `--append-system-prompt-file <file>` | Appends file contents to default | `system[N]` | Line 491781 |

**Processing** (Lines 491938-491987):
```javascript
[source fragment removed]
```

**Effect on Request** (Line 468792):
```javascript
[source fragment removed]
```

#### Tool Configuration

| Argument | Effect | API Parameter | Restrictions |
|----------|--------|---------------|--------------|
| `--tools <tools...>` | Specifies available built-in tools | `tools[]` | Only with `--print` |
| `--allowed-tools <tools...>` | Whitelist tool patterns | `tools[]` | All modes |
| `--disallowed-tools <tools...>` | Blacklist tool patterns | `tools[]` | All modes |

**Example** (Line 452365):
```yaml
claude_args: '--allowed-tools "Bash(gh issue view:*),Bash(gh search:*),..."'
```

#### Model & Output Configuration

| Argument | Effect | Code Location |
|----------|--------|---------------|
| `--model <model>` | Sets model for session | Line 491819 |
| `--fallback-model <model>` | Auto-fallback when overloaded | Line 491823 |
| `--print` / `-p` | Non-interactive mode | Line 491658 |
| `--output-format <format>` | text/json/stream-json | Line 491665 |
| `--max-turns <turns>` | Limits agentic turns | Line 491704 |
| `--max-budget-usd <amount>` | Budget limit | Line 491712 |

#### MCP & Plugin Configuration

| Argument | Effect | Code Location |
|----------|--------|---------------|
| `--mcp-config <configs...>` | Load MCP servers from JSON | Line 491751 |
| `--strict-mcp-config` | Only use specified MCP config | Line 491840 |
| `--plugin-dir <paths...>` | Load plugins from directories | Line 491857 |

#### Permission & Session Controls

| Argument | Effect | Code Location |
|----------|--------|---------------|
| `--permission-mode <mode>` | Sets permission mode (auto/manual/disabled) | Line 491789 |
| `--session-id <uuid>` | Use specific session ID | Line 491845 |
| `--continue` / `-c` | Continue most recent conversation | Line 491796 |
| `--resume [sessionId]` | Resume a conversation | Line 491801 |
| `--fork-session` | Create new session ID when resuming | Line 491806 |
| `--settings <file-or-json>` | Load additional settings | Line 491827 |

### 2. Environment Variables

#### Authentication & API Provider

| Variable | Effect | Code Location | Default |
|----------|--------|---------------|---------|
| `ANTHROPIC_API_KEY` | API key for Anthropic | Line 476435 | Required |
| `CLAUDE_CODE_OAUTH_TOKEN` | OAuth token | Line 476409 | Preferred |
| `CLAUDE_CODE_USE_BEDROCK` | Use AWS Bedrock | Line 206235 | False |
| `CLAUDE_CODE_USE_VERTEX` | Use Google Vertex | Line 206261 | False |

**Provider Detection** (Lines 206235-206261):
```javascript
[source fragment removed]
```

#### Context & Content Controls

| Variable | Effect | API Parameter | Code Location |
|----------|--------|---------------|---------------|
| `CLAUDE_CODE_DISABLE_CLAUDE_MDS` | Disable CLAUDE.md loading | `system[]` | Line 321038 |
| `CLAUDE_CODE_DISABLE_ATTACHMENTS` | Disable attachments | `messages[]` | Line 313062 |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | Override max output tokens | `max_tokens` | Line 469287 |
| `CLAUDE_CODE_EXTRA_BODY` | Extra JSON for request body | All params | Lines 468585-468609 |

**EXTRA_BODY Processing** (Lines 468585-468609):
```javascript
[source fragment removed]
```

**Power User Note**: `CLAUDE_CODE_EXTRA_BODY` can inject ANY field into the request body!

#### Prompt Caching Controls

| Variable | Effect | Code Location |
|----------|--------|---------------|
| `DISABLE_PROMPT_CACHING` | Disable all prompt caching | Line 468612 |
| `DISABLE_PROMPT_CACHING_HAIKU` | Disable for Haiku only | Line 468613 |
| `DISABLE_PROMPT_CACHING_SONNET` | Disable for Sonnet only | Line 468617 |
| `DISABLE_PROMPT_CACHING_OPUS` | Disable for Opus only | Line 468621 |

**Cache Enable Function** (Lines 468611-468626):
```javascript
[source fragment removed]
```

**Applied at Line 468797**:
```javascript
[source fragment removed]
```

#### Tool & Bash Configuration

| Variable | Effect | Code Location |
|----------|--------|---------------|
| `CLAUDE_CODE_USE_NATIVE_FILE_SEARCH` | Use native file search vs ripgrep | Line 472352 |
| `CLAUDE_CODE_GIT_BASH_PATH` | Git bash path (Windows) | Lines 38274-38278 |
| `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` | Maintain bash cwd | Line 3370 |
| `CLAUDE_CODE_SHELL_PREFIX` | Prefix for shell commands | Lines 269799, 310179 |
| `CLAUDE_CODE_DISABLE_COMMAND_INJECTION_CHECK` | Disable injection check | Lines 212358, 212466 |

#### Performance & Behavior

| Variable | Effect | Code Location |
|----------|--------|---------------|
| `CLAUDE_CODE_SUBAGENT_MODEL` | Override subagent model | Line 140963 |
| `CLAUDE_CODE_MAX_RETRIES` | Max API retries | Line 345668 |
| `CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY` | Tool concurrency limit | Line 348178 |
| `CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING` | Disable file checkpointing | Lines 208276, 325004 |

### 3. Configuration Files

#### Settings Files (JSON)

**Locations checked in order**:
1. Managed settings: `~/.claude/managed-settings.json` (line 476094)
2. User settings: `~/.claude/settings.json` (line 476135)
3. Project settings: `.claude/settings.json` (line 476148)

**Schema**: `https://json.schemastore.org/claude-code-settings.json` (line 34589)

**CLI Override**: `--settings <file-or-json>` (line 491827)

**Source Control**: `--setting-sources <sources>` controls which are loaded (line 491853)

#### MCP Configuration

**Default Locations**: Checked at enterprise config level (line 491891)

**Overrides**:
- `--mcp-config <configs>`: Add additional configs (line 491751)
- `--strict-mcp-config`: ONLY use specified configs (line 491840)

### 4. Programmatic Controls

#### Options Object Structure

Passed to `ES()` function at line 468734:

```javascript
[source fragment removed]
```

#### Beta Features

**Applied at Line 468842**:
```javascript
[source fragment removed]
```

Betas conditionally included based on:
- Model capabilities
- Environment settings
- Feature flags

#### Extended Thinking

**Applied at Lines 468828-468829**:
```javascript
[source fragment removed]
```

Controlled by `maxThinkingTokens` parameter passed to `ES()`.

---

## Parameter-Specific Assembly

### System Prompt Assembly

#### Base Opening Statement

**Function**: `zvA()` (Line 144616-144623)

**Constants** (Lines 144624-144627):
```javascript
[source fragment removed]
```

**Selection Logic**:
```javascript
[source fragment removed]
```

#### System Prompt Construction

**Location**: Lines 468788-468796

```javascript
[source fragment removed]
```

Components assembled:
1. Base opening statement (`zvA()`)
2. Custom system prompt (from `--system-prompt` or `--append-system-prompt`)
3. MCP server instructions (`la2()`)

#### Agent System Prompt Assembly

**Function**: `Th2()` (Lines 468074-468086)

```javascript
[source fragment removed]
```

#### Environment Information

**Function**: `ia2()` (Lines 468029-468062)

Assembles environment block including:
- Working directory
- Git repository status
- Platform information
- OS version
- Today's date
- Model name and ID
- Knowledge cutoff date

#### MCP Server Instructions

**Function**: `la2()` (Lines 467909-468027)

Adds comprehensive MCP CLI command documentation when MCP tools are available.

#### System Prompt to Content Blocks

**Function**: `rAI()` (Lines 469227-469233)

```javascript
[source fragment removed]
```

Converts system prompt string array to content blocks with optional cache control.

### Tools Array Assembly

#### Built-in Tool Definitions

**Complete Built-in Tool Names (All 18 Tools)**:

| Tool Name | Code Variable | Line |
|-----------|---------------|------|
| `Read` | `G7` | 144470 |
| `Write` | `oW` | 144499 |
| `Edit` | `f5` | 144498 |
| `NotebookEdit` | `fg` | 144512 |
| `Bash` | `x4` | 144420 |
| `Glob` | `Cq` | 144421 |
| `Grep` | `wH` | 144442 |
| `WebFetch` | `NC` | 144529 |
| `WebSearch` | `Un` | 144548 |
| `Task` | `i8` | 144428 |
| `BashOutput` | (named in schema) | 444641 |
| `KillShell` | (named in schema) | 444440 |
| `TodoWrite` | `UvA` | 144966 |
| `AskUserQuestion` | `ww` | 376517 |
| `SlashCommand` | `OS` | 377632 |
| `Skill` | `lN` | 377323 |
| `ListMcpResourcesTool` | (named in schema) | 307647 |
| `ReadMcpResourceTool` | (named in schema) | 307782 |

**Tool Description Constants**:
- `CHB` (Line 144477): Read tool description
- `LHB` (Lines 144752-144799): TodoWrite tool description
- `sEQ()` (Lines 268500-268548): Bash tool description (function)
- `KHB` (Line 144530): WebFetch tool description
- `EHB` (Lines 144549-144560): WebSearch tool description

#### Tool Processing Pipeline

**Line 468775-468787**: Tools processed through `f01()` to prepare schemas

**Line 468840**: Final tools array assembly:
```javascript
[source fragment removed]
```

Where:
- `J` = Processed built-in + MCP tools
- `Z.extraToolSchemas` = Additional runtime tools

### Messages Array Assembly

#### User Context Loading

**Function**: `rC()` (Lines 321037-321040)

```javascript
[source fragment removed]
```

Loads CLAUDE.md memory files unless disabled.

#### System Context Loading

**Function**: `sC()` (Lines 321033-321036)

```javascript
[source fragment removed]
```

Loads git status information.

#### Memory File Assembly

**Function**: `hjQ()` (Lines 311969-311990)

```javascript
[source fragment removed]
```

**Preamble constant** (Lines 311963-311964):
```javascript
[source fragment removed]
```

#### Memory File Discovery

**Function**: `HF()` (Lines 312004-312030)

Searches for CLAUDE.md files in hierarchy:
1. Managed location (global `~/.claude/CLAUDE.md`)
2. User settings location
3. Project locations (walking up directory tree):
   - `CLAUDE.md`
   - `.claude/CLAUDE.md`
   - `CLAUDE.local.md`

#### Context Injection Wrapper

**Function**: `Lr()` (Lines 445797-445816)

```javascript
[source fragment removed]
```

Wraps messages with user context (CLAUDE.md) and system context (git status).

#### Message Processing

**Function**: `sAI()` (Line 469227)

Normalizes messages and adds cache control to message content blocks.

---

## Main Session vs Agent API Requests

### Comparison Table

| Aspect | Main Session | Agent (Subagent) |
|--------|-------------|------------------|
| **API Call** | Original request | Separate, independent request |
| **System Prompt** | Full (~2.6k tokens) | Simplified (~500 tokens) |
| **Base Statement** | "You are Claude Code..." | "You are an agent for Claude Code..." |
| **Tools** | All 18 + MCP tools | Filtered subset (per agent definition) |
| **Conversation History** | Full session history | Isolated (or forked if configured) |
| **MCP Server Instructions** | Included in system prompt | Empty (no MCP clients) |
| **Memory Files** | Included (CLAUDE.md) | NOT included |
| **Environment Info** | Included | Included |
| **Token Cost** | Part of main session budget | Separate API call (additional cost) |
| **Context Isolation** | Shared with user | Isolated task context |

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

**Agent System Prompt Function**: `Th2()` at line 468074

### Why This Matters

1. **Cost**: Each subagent invocation = separate API call with own token usage
2. **Context Isolation**: Subagents don't see memory files or full conversation
3. **Tool Filtering**: Subagents only get tools specified in their definition
4. **Simpler Instructions**: Subagents have focused, task-specific instructions

---

## Control Mechanism Mapping

### Master Control → API Parameter Table

| Control Type | Control Name | API Parameter | Code Location |
|--------------|--------------|---------------|---------------|
| CLI Arg | `--system-prompt` | `system` array | 468789-468796 |
| CLI Arg | `--append-system-prompt` | `system` array, flag | 468792 |
| CLI Arg | `--model` | `model` | 468837 |
| CLI Arg | `--tools` | `tools` array | 468840 |
| CLI Arg | `--allowed-tools` | `tools` array (filtered) | Tool filtering |
| CLI Arg | `--disallowed-tools` | `tools` array (filtered) | Tool filtering |
| Env Var | `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | `max_tokens` | 468844 |
| Env Var | `CLAUDE_CODE_EXTRA_BODY` | Entire request body | 468585-468609 |
| Env Var | `DISABLE_PROMPT_CACHING` | Cache control blocks | 468797 |
| Env Var | `CLAUDE_CODE_DISABLE_CLAUDE_MDS` | `system` array content | 321038 |
| Env Var | `CLAUDE_CODE_DISABLE_ATTACHMENTS` | Message attachments | 313062 |
| Env Var | `CLAUDE_CODE_USE_BEDROCK` | Provider, endpoint, model | 206235 |
| Env Var | `CLAUDE_CODE_USE_VERTEX` | Provider, endpoint, system | 206261 |
| Programmatic | `isNonInteractiveSession` | Base system prompt variant | 468791 |
| Programmatic | `maxThinkingTokens` | `thinking` parameter | 468828 |
| Programmatic | `temperatureOverride` | `temperature` | 468813 |
| Programmatic | `toolChoice` | `tool_choice` | 468841 |
| Programmatic | `extraToolSchemas` | `tools` array | 468840 |
| Programmatic | `mcpTools` | `system` array (MCP docs) | 468795 |
| Programmatic | `enablePromptCaching` | Cache control blocks | 468797 |
| Programmatic | `querySource` | Metadata/telemetry | 468816 |
| Metadata | Session/Account IDs | `metadata.user_id` | 468843 |
| Config | Beta features | `betas` array | 468842 |

### Controls by API Parameter

#### `system` Parameter

| Control | Effect |
|---------|--------|
| `--system-prompt` | Replaces entire system prompt |
| `--append-system-prompt` | Appends to default system prompt |
| `CLAUDE_CODE_DISABLE_CLAUDE_MDS` | Removes CLAUDE.md content |
| `isNonInteractiveSession` | Changes base opening statement |
| `mcpTools` | Adds MCP server instructions |

#### `tools` Parameter

| Control | Effect |
|---------|--------|
| `--tools` | Specifies available tools |
| `--allowed-tools` | Whitelist filter |
| `--disallowed-tools` | Blacklist filter |
| `extraToolSchemas` | Adds additional tools |

#### `messages` Parameter

| Control | Effect |
|---------|--------|
| `CLAUDE_CODE_DISABLE_ATTACHMENTS` | Removes attachments |
| User/system context wrappers | Adds CLAUDE.md and git status |

#### Other Parameters

| Control | Parameter | Effect |
|---------|-----------|--------|
| `--model` | `model` | Sets model ID |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | `max_tokens` | Overrides token limit |
| `maxThinkingTokens` | `thinking` | Extended thinking budget |
| `DISABLE_PROMPT_CACHING` | Cache control | Disables caching |
| `CLAUDE_CODE_EXTRA_BODY` | ANY | Injects arbitrary fields |

---

## Key Code Locations Reference

### Quick Lookup Table

| Function/Location | Line | Purpose |
|-------------------|------|---------|
| `ES()` | 468734 | Main API call entry point |
| `Js2()` | 468762 | Streaming API implementation |
| Request construction | 468836-468848 | Builds final request object |
| Actual API call | 468871 | `c.beta.messages.stream()` |
| System prompt assembly | 468788-468796 | Builds system array |
| `zvA()` | 144616 | Base system prompt selection |
| `Th2()` | 468074 | Agent system prompt assembly |
| `ia2()` | 468029 | Environment information |
| `la2()` | 467909 | MCP server instructions |
| `rAI()` | 469227 | System to content blocks |
| `sAI()` | 469227 | Messages normalization |
| `Pu()` | 468632 | Metadata generation |
| `hjQ()` | 311969 | CLAUDE.md assembly |
| `HF()` | 312004 | CLAUDE.md discovery |
| `Lr()` | 445797 | Context wrapper injection |
| `rC()` | 321037 | User context loader |
| `sC()` | 321033 | System context loader |
| `Ys2()` | 468611 | Cache enable check |
| EXTRA_BODY parsing | 468585-468609 | Extra request body fields |
| CLI args parsing | 491764-491987 | System prompt args |
| Tool constants | 144470-144548 | Built-in tool names |

### Key Constants

| Constant | Line | Value |
|----------|------|-------|
| `$HB` | 144624 | "You are Claude Code, Anthropic's official CLI for Claude." |
| `$r4` | 144625 | "...running within the Claude Agent SDK." |
| `qr4` | 144626 | "You are a Claude agent, built on Anthropic's Claude Agent SDK." |
| `Xu6` | 311963 | CLAUDE.md preamble text |
| `G7` | 144470 | "Read" |
| `f5` | 144498 | "Edit" |
| `oW` | 144499 | "Write" |

---

## Next Steps

This document establishes the foundation for deeper context tracing. The following phases can now proceed:

### Phase 2: System Prompt Text Sources

**Goal**: Trace every string literal and variable that contributes to the `system` parameter.

**Approach**:
1. Start from `rAI()` function (line 469227)
2. Trace backward through `B` variable assembly (line 468788)
3. Follow each component:
   - `zvA()` → base statement constants
   - Custom system prompts → CLI args
   - `la2()` → MCP instructions
4. Use code-intel tools to find all references
5. Document every source location

### Phase 3: Tool Registration & Descriptions

**Goal**: Document all tool schemas and their text descriptions.

**Approach**:
1. Start from `tools` array in request (line 468840)
2. Trace `J` variable through `f01()` processing
3. Find all built-in tool definitions
4. Trace MCP tool integration
5. Document tool description sources

### Phase 4: Dynamic Context Assembly

**Goal**: Understand runtime context assembly (memory files, environment, etc.).

**Approach**:
1. Trace `hjQ()` → `HF()` → file reads
2. Follow `ia2()` → environment variable collection
3. Map `Lr()` → context wrapper injection
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

**Note**: The use of `client.beta.*` methods indicates the SDK uses the beta namespace, which is the standard way to access beta API features (see Claude docs).

### 2. System-Reminder XML Element

**Purpose**: The `<system-reminder>` XML wrapper is **custom to Claude Code**, not part of the official Anthropic API specification.

**Generation**: Generated in the `Lr()` function at line 445797-445816

**Function**: It wraps user context (CLAUDE.md files) and system context (git status) to inject them into the conversation as specially-marked metadata messages that Claude treats as system-level information.

**Example Content** (from line 445797):
```
<system-reminder>
As you answer the user's questions, you can use the following context:
# claudeMd
[CLAUDE.md contents here]

IMPORTANT: this context may or may not be relevant to your tasks. You should not respond to this context unless it is highly relevant to your task.
</system-reminder>
```

**Why XML**: The XML-style markup makes it visually distinct in the message stream and helps Claude understand it's metadata rather than user content.

### 3. Beta Features Currently Active/Available

Based on code analysis (lines 206360-206406), Claude Code includes these beta features:

| Beta Feature | Constant | Code Line | Enabled When |
|--------------|----------|-----------|--------------|
| `interleaved-thinking-2025-05-14` | `gAQ` | 206331, 206378 | Model supports thinking & not disabled |
| `context-management-2025-06-27` | `luA` | 206334, 206386 | `preserve_thinking` enabled OR `USE_API_CONTEXT_MANAGEMENT=1` |
| Token-efficient tools | `uAQ` | 206384 | First-party Anthropic & fine-grained streaming enabled |
| `oauth-2025-04-20` | `aAA` | 31679, 206373 | User authenticated via OAuth |
| Fine-grained tool streaming | `uAQ` | 206384 | First-party, fine-grained streaming not disabled |
| Tool PEAR | `mAQ` | 206388 | Feature flag `tengu_tool_pear` enabled |
| Vertex AI features | `dAQ` | 206389 | Running on Vertex AI |
| Custom betas from env | `ANTHROPIC_BETAS` | 206390-206395 | `ANTHROPIC_BETAS` environment variable set |
| Skills | `skills-2025-10-02` | 146283+ | Used throughout file operations |
| Files API | `files-api-2025-04-14` | 145705+ | Used for file upload operations |

**Key Functions**:
- **`pR1()` function** (lines 206369-206396): Builds the beta features array based on model and configuration
- **`hU()` function** (lines 206398-206402): Applies model-specific filtering (Bedrock filters some betas)
- **`lR1()` function** (lines 206403-206404): Gets Bedrock-specific betas only

### 4. Context Management Beta Feature (`context_management` Parameter)

**Documentation Match**: YES - This relates directly to the Anthropic API's context editing feature.

**What It Is**: The `context_management` parameter (line 468846) enables automatic context editing strategies to manage conversation context as it grows.

**How It Works**:
```javascript
[source fragment removed]
```

Where:
- `y` = context management configuration from `UHB()` function
- `C` = betas are enabled
- `X.includes(luA)` = context-management-2025-06-27 beta is included
- `luA` = "context-management-2025-06-27"

**Configuration Source** (`UHB()` at line 144561-144600):
```javascript
[source fragment removed]
```

**Environment Variables That Control It**:
- `USE_API_CLEAR_TOOL_RESULTS`: Enable tool result clearing strategy
- `USE_API_CLEAR_TOOL_USES`: Enable tool use clearing strategy
- `API_MAX_INPUT_TOKENS`: Threshold for clearing
- `API_TARGET_INPUT_TOKENS`: Target tokens after clearing

**Relation to Thinking Blocks**: YES - When extended thinking is enabled, `context_management` can automatically manage thinking block history to prevent context overflow, as documented in the Anthropic API.

### 5. CLAUDE_CODE_EXTRA_BODY Purpose

**Function**: **Experimental feature for Anthropic to inject custom API request fields** without requiring Claude Code code changes.

**How It Works** (lines 468583-468609):
```javascript
[source fragment removed]
```

**Use Cases**:
1. **Anthropic experiments**: Test new API fields without shipping code changes
2. **Feature flags**: Enable/disable fields per deployment
3. **Custom headers**: Add organization-specific metadata
4. **A/B testing**: Vary request structure across clients

**Example Usage**:
```bash
CLAUDE_CODE_EXTRA_BODY='{"custom_field":"value","experimental_mode":true}' claude
```

**Merged Into**: The final request body at line 468847: `...AA`

### 6. `fetchOverride` and `queryTracking`

**`fetchOverride`**:
- Part of options object passed to `ES()` function
- Allows custom HTTP client implementation
- Used for network customization, proxying, or testing
- **NOT currently actively used** in the request construction (line 468862 constructs fetch call but doesn't show override usage in visible code)

**`queryTracking`**:
- Passed to telemetry/analytics at line 468817: `queryTracking: Z.queryTracking`
- Used in `Qs2()` function for tracking query metadata
- Includes information like:
  - `model`: Model used
  - `messagesLength`: Serialized request size
  - `temperature`: Temperature override
  - `betas`: Enabled beta features
  - `permissionMode`: Permission mode
  - `querySource`: Source identifier

**Purpose**: Provides fine-grained telemetry about API calls for monitoring and debugging.

### 7. Agent System Prompt (`Th2()`) Customization

**Can It Be Changed?**

No direct CLI customization for agent system prompts. The `Th2()` function (line 468074) builds a fixed system prompt structure for agents:

```javascript
[source fragment removed]
```

**Arguments**:
- `A`: Base system prompt components (not user-customizable)
- `B`: Agent metadata (not user-customizable)
- `Q`: Query object (not user-customizable)

**Affected By**:
- `--append-system-prompt`: Does NOT affect agent prompts (agents get separate context)
- `--system-prompt`: Does NOT affect agent prompts
- Only main session prompts are customizable via CLI

**Agent-Specific Design**: Agents intentionally have simplified prompts to keep them focused and reduce context overhead.

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
3. Actual tests with token counting API (as shown in BLOG_CONTEXT.md)

**Note**: Token counts are NOT coded as constants in the source - they're derived from analysis.

### 9. Core Instructions Text - Found!

The "Core instructions" mentioned in BLOG_CONTEXT.md line 73 are **generated dynamically** from multiple sources rather than a single text constant. However, key sections are:

**Base core instructions** are in the main system prompt assembly, and include:
- "You are Claude Code, Anthropic's official CLI for Claude."
- "You are an interactive CLI tool that helps users with software engineering tasks..."
- Security policy text about authorized usage
- Help and feedback instructions

**These sections are conditionally assembled** in the request construction (lines 468789-468796) from:
1. `zvA()` function result (base statement)
2. Custom system prompt (from CLI args)
3. `la2()` result (MCP instructions)

The full literal text isn't a single constant - it's built at runtime from multiple sources as described in the report's "System Prompt Assembly" section.

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

All controls flow through: `ES()` → `Js2()` → request body assembly → Anthropic API

**Key Insight**: Starting from the API request construction at line 468836, we can trace backward to find ALL context sources, because everything must flow through one of the three parameters: `system`, `tools`, or `messages`.
