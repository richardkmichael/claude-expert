# Claude Code API Reference

This document provides detailed API documentation extracted from the Claude Code application source
code with exact line numbers, function signatures, and implementation details.

## Configuration Management API

### Core Configuration Functions

#### `WQ()` - Get Configuration Directory (Line 339,622)
```javascript
[source fragment removed]
```
**Returns**: String - Configuration directory path
- Default: `~/.claude/`
- Override: `$CLAUDE_CONFIG_DIR` environment variable
- Cross-platform: Uses Node.js `path.join()` and `os.homedir()`

#### `bJ()` - Get Configuration File Path (Line 339,682)
```javascript
[source fragment removed]
```
**Returns**: String - Configuration file path
**File Priority**:
1. `~/.claude/.config.json` (preferred)
2. `~/.claude.json` (fallback)
3. `$CLAUDE_CONFIG_DIR/.config.json` (if env var set)

#### `dQ(A)` - Parse Boolean Configuration (Line 339,625)
```javascript
[source fragment removed]
```
**Parameters**:
- `A`: String - Input value to parse
**Returns**: Boolean
**Accepted Values**: `"1"`, `"true"`, `"yes"`, `"on"` (case-insensitive)

### Settings Processing Pipeline

#### `kU9()` - Load and Merge Settings (Line 357,018)
```javascript
[source fragment removed]
```
**Returns**: Object `{ settings: Object, errors: Array<ErrorObject> }`
**Settings Sources**: `"user"`, `"project"`, `"local"`
**Error Format**: `{ file: String, path: String, message: String }`

#### `yU9(A, B)` - Merge Arrays with Deduplication (Line 357,011)
```javascript
[source fragment removed]
```
**Parameters**:
- `A`, `B`: Array - Arrays to merge
**Returns**: Array - Deduplicated merged array

#### `x41()` - Invalidate Settings Cache (Line 357,015)
```javascript
[source fragment removed]
```
**Purpose**: Clears cached settings, forcing reload on next access

## Agent System API

### Agent Directory Structure (Line 422,528)
```javascript
[source fragment removed]
```
**Constants**:
- `FOLDER_NAME`: `".claude"` - Primary configuration folder
- `AGENTS_DIR`: `"agents"` - Agents subdirectory name

**Directory Paths**:
- User agents: `~/.claude/agents/`
- Project agents: `./.claude/agents/`

### Agent Configuration Functions

#### Agent Directory Resolution (Lines 422,557-422,560)
```javascript
[source fragment removed]
```
**Paths**:
- User settings: `~/.claude/agents/`
- Project settings: `./.claude/agents/`

### Agent Object Schema

#### Agent Type Object (Lines 433,681-433,687)
```javascript
[source fragment removed]
```

#### Complete Agent Configuration Object
```javascript
[source fragment removed]
```

## File System Operations

### Files Read by Application
1. **Configuration Files**:
   - `~/.claude/.config.json`
   - `~/.claude.json`
   - `$CLAUDE_CONFIG_DIR/.config.json`

2. **Agent Files**:
   - `~/.claude/agents/*` (user agents)
   - `./.claude/agents/*` (project agents)

3. **Settings Files**:
   - User-level settings
   - Project-level settings
   - Local override settings

### Files Written by Application
1. **Settings Cache**:
   - `localSettings` file (Line 357,004)

2. **Agent Configurations**:
   - Agent definition files in agents directories

3. **Telemetry and Logs**:
   - Various debug and usage tracking files

## Data Structures and Types

### Settings Object Structure
```typescript
[source fragment removed]
```

### Error Object Structure
```typescript
[source fragment removed]
```

### Agent Discovery Result
```typescript
[source fragment removed]
```

## Implementation Patterns

### Error Handling
- **Deduplication**: Uses `Set` to prevent duplicate errors
- **Comprehensive Collection**: Collects errors from all sources
- **Graceful Degradation**: Continues processing on individual failures

### Performance Optimizations
- **Caching**: Settings cached until explicitly invalidated
- **Deduplication**: File processing and error deduplication
- **Lazy Loading**: Settings loaded on demand

### Cross-Platform Support
- **Path Resolution**: Uses Node.js `path.join()` for cross-platform paths
- **Environment Variables**: Supports `$CLAUDE_CONFIG_DIR` override
- **Home Directory**: Uses `os.homedir()` for user directory resolution

## Security Considerations
- **Path Validation**: File existence checks before reading
- **Environment Isolation**: Settings hierarchy (user → project → local)
- **Error Sanitization**: Structured error reporting without exposing internals

## Anthropic API Integration

### API Endpoint
**Base URL**: `https://api.anthropic.com`
**Messages Endpoint**: `POST /v1/messages`

Location: cli.prettier.js:82977

### Message Creation Function
```javascript
[source fragment removed]
```

### System Prompt Construction and API Transmission

**Important Distinction**: Claude Code builds multiple text strings that are sent to the Anthropic API's `system` field as an **array of content blocks**, not as a single concatenated string.

#### System Prompt Assembly (Before API Call)

**Location**: cli.prettier.js:460100-460130 (function `lb2`)

The system prompt is constructed as an array of text strings:

```javascript
[source fragment removed]
```

Where:
- `B` is an array of system prompt text strings
- `YRA()` returns the base prompt (from CLAUDE_CODE_PROMPTS.md)
- `B` is spread with additional components
- `X = mb6(B, W)` converts the string array to content blocks

#### Content Block Transformation

**Location**: cli.prettier.js:460540-460546 (function `mb6`)

The array of system prompt strings is transformed into Anthropic API content blocks:

```javascript
[source fragment removed]
```

This creates:
```javascript
[source fragment removed]
```

#### API Request Construction

**Location**: cli.prettier.js:460158-460180

The content block array is sent to the Anthropic API:

```javascript
[source fragment removed]
```

**Key Points**:
- `system: X` is an **array of content blocks**, each with `type: "text"` and `text` field
- NOT a single concatenated string
- Prompt caching headers (`cache_control`) are added per content block if enabled
- This matches the public Anthropic API specification for the `system` parameter

### Dynamic Context Rebuild

**Key Finding**: The system prompt is rebuilt on **every API call** because:

1. **Pr() is called async** - Located at cli.prettier.js:458735, it's an async function
2. **MCP servers filtered by connection status** - The `Hb6()` function filters for `G.type === "connected"`
3. **Output style resolved per-request** - `Ob2()` function (line 463774) is called to get current output style
4. **Tools list is dynamic** - `Z.options.tools` reflects current available tools

**Evidence of Per-Request Rebuild**:
- Line 428825: Each iteration starts fresh with `await eu(V, void 0, Z)`
- Line 428835: Compaction info includes `systemMessage` check
- Line 428869: Fresh `Oq2(B, I)` call to rebuild system prompt with current context
- Line 428874: `getToolPermissionContext()` is called asynchronously per-request
- Line 428879: `agents: Z.options.agentDefinitions.activeAgents` uses current active agents

This means:
- **MCP server instructions** are added/removed dynamically as servers connect/disconnect
- **Tool availability** changes are reflected immediately
- **Agent definitions** are reloaded before each API call
- **Output style changes** take effect immediately on the next API request

### API Request Body Structure

**Complete request sent to Anthropic API** (per public API specification):

```typescript
[source fragment removed]
```

**What Comprises the `system` Array**:

The system content blocks array is built from the following components (in order):
1. Base prompt from `YRA()` function
2. All components returned by `Pr()` function:
   - Core introduction and requirements
   - Tone and style guidelines (if not using custom output style)
   - Task management section (if TodoWrite tool available)
   - Hooks notice
   - Doing tasks section (if applicable)
   - Tool usage policy
   - Code references format
   - Output style details (if custom style active)
   - MCP server instructions (if servers connected with instructions)
   - Model information

Each component text string becomes a separate content block in the array, with prompt caching headers added if caching is enabled.

### Timeout Calculation

**Location**: cli.prettier.js:82977-82983

- Non-streaming requests: Calculated based on model and max_tokens
- Streaming requests: Uses configured timeout option
- Default timeout: 600,000 ms (10 minutes)

### Model Deprecation Handling

**Location**: cli.prettier.js:82968-82971

Checks `Qj0` object for deprecated models and logs warnings before API call.
