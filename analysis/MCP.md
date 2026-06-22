# Claude Code MCP Implementation Analysis

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

This document provides a comprehensive analysis of the Model Context Protocol (MCP) implementation in Claude Code, separating the TypeScript MCP SDK from Claude Code's application logic.

## Project (`.mcp.json`) server approval and enablement

Verified against `cli.prettier.js` 2.1.169 (2026-06-22). This section is newer than the rest of the
document (see the `Source:` line) and follows the landmark style.

Servers declared in a project's `.mcp.json` are not loaded until approved. Each carries a status —
`pending`, `approved`, or `rejected` — decided from three settings keys:

- name in `disabledMcpjsonServers` → `rejected`
- name in `enabledMcpjsonServers`, or `enableAllProjectMcpServers` is set → `approved`
- otherwise → `pending`: the server does not connect and does not appear in `/mcp`

Relocate with `rg -n 'enabledMcpjsonServers|disabledMcpjsonServers|enableAllProjectMcpServers'`. A raw
status function returns the literal `"pending"`/`"approved"`/`"rejected"` from those three keys, but it
is wrapped by an effective-status function that overrides `pending` → `approved` in two cases (find it
as the wrapper whose first call is the raw function, then two `return "approved"` guards):

- bypass-permissions session with `skipDangerousModePermissionPrompt` set, and `projectSettings` is an
  active settings source
- non-interactive run (`-p`/headless), and `projectSettings` is an active settings source

The effective function is what the connect path, the `/mcp` UI, and the pending-prompt list all call,
so a pending server in those two modes loads without ever prompting. Outside them, the three keys
decide. Relocate the override guards with `rg -n 'skipDangerousModePermissionPrompt'` and the
non-interactive flag check beside it.

Where the state lives. These three are settings-system keys (settings.json), not the legacy per-project
store. The `/mcp` UI and the approval prompt write the decision to local project settings
(`.claude/settings.local.json`): approving appends the name to `enabledMcpjsonServers`, "enable all"
sets `enableAllProjectMcpServers`, rejecting appends to `disabledMcpjsonServers`. Because these are
local-scope settings, the write goes through the guarded settings writer; a symlinked
`.claude/settings.local.json` silently refuses it, so an approval can appear to take in the UI yet
never persist (see `SETTINGS.md`, the symlink-refusal section). Older copies of these keys under
`~/.claude.json` `projects.<path>` are folded into local settings by a migration; the rejection UI
points there too — `Rejected (see disabledMcpjsonServers in settings)`. Local-scoped servers added
with `claude mcp add` instead live under `~/.claude.json` `projects.<path>.mcpServers` and load
directly with no approval — that asymmetry is why `claude mcp add` servers work immediately while
`.mcp.json` servers wait.

The approval prompt. The prompt to approve pending `.mcp.json` servers runs only at interactive
startup, and only when the config loaded without errors; it is not re-evaluated mid-session. Headless/
`-p` runs don't prompt because the effective-status override already approves pending servers there (see
above), not because the servers stay pending. A server added to `.mcp.json` during a running session
won't prompt until the next interactive start in that project. If it still doesn't prompt, `claude mcp
reset-project-choices` resets the project's approved/rejected decisions back to `pending` so the prompt
re-fires — but reset only re-arms; it never approves. The reliable fix is to set `enabledMcpjsonServers`
in `.claude/settings.local.json` directly (and confirm that file is a real file, not a symlink, or the
write silently no-ops — see `SETTINGS.md`). Explicit enablement loads the server regardless of the
prompt gates below — they only control whether the interactive prompt fires.

Two gates suppress the prompt before it ever renders, distinct from approval state:

- `IS_DEMO` set, or a background session (`CLAUDE_CODE_SESSION_KIND` of `bg`/`daemon`/`daemon-worker`),
  short-circuits the startup routine that drives onboarding, the trust dialog, and the approval prompt —
  none of the three appear. Relocate via `rg -n 'IS_DEMO|CLAUDE_CODE_SESSION_KIND'`; the startup
  function early-returns on `process.env.IS_DEMO` unless the session kind is the background fast-path.
- A settings-load error (severity not `warning`) in any source other than the local settings file leaves
  the prompt skipped with a startup notice: `skipping .mcp.json server approval (settings errors in
  <files>) · run /doctor and fix them, then restart`. A failed MCP server connection is explicitly NOT
  such an error — the suppressor filters on `!mcpErrorMetadata`, so a server stuck "failed" never blocks
  the prompt. Relocate via the notice string and `rg -n 'mcpErrorMetadata'`.

Project trust is a separate gate and is inherited up the directory tree: a project with no
`hasTrustDialogAccepted` entry of its own counts as trusted if any ancestor directory has it set, so a
nested worktree under a trusted source root needs no trust prompt.

Tripwire for a new version: □ the three keys present □ status literals `pending`/`approved`/`rejected`
□ effective-status wrapper still overrides to `approved` for bypass-permissions and non-interactive runs
□ approvals written to local settings, not `~/.claude.json` □ prompt gated on interactive startup with
no config errors □ `IS_DEMO` / background `CLAUDE_CODE_SESSION_KIND` still skip the prompt entirely
□ MCP server errors excluded from the suppressor (`!mcpErrorMetadata`) □ `claude mcp
reset-project-choices` subcommand present.

## Executive Summary

Claude Code uses the **TypeScript MCP SDK** (minified to JavaScript) for protocol implementation, while building application-specific configuration management, tool integration, and user interface components on top of it. The MCP implementation is production-grade with full protocol compliance and multiple transport options.

## File Structure Overview

**File**: `package/cli.prettier.js`
- **MCP SDK Implementation**: ~7,000 lines
- **Claude Code MCP Application Logic**: configuration management, tool integration, and connection management

---

## TypeScript MCP SDK Boundaries (IGNORE in future analysis)

### **Lines: 388,640 - 395,600 (~7,000 lines)**

This section contains the complete **minified TypeScript MCP SDK** that provides core protocol implementation. This is essentially a black box that Claude Code uses.

#### **Core MCP SDK Components:**

**Error Classes:**
- `Line 388645`: `class aV extends Error` - McpError class for MCP-specific errors
- Constructor: `super(\`MCP error ${A}: ${B}\`)`

**Protocol Handler:**
- `Line 388650+`: `class RY1` - JSON-RPC protocol implementation
- Handles request/response/notification routing
- Manages timeouts, progress handlers, and message validation

**Transport Classes:**
- `s$0` (Line 389366+) - **StdioClientTransport** - Handles stdio communication with MCP servers
- `Uw0` (Line 390994+) - **SSEClientTransport** - Server-Sent Events transport for HTTP connections
- `yw0` (Referenced) - **WebSocketClientTransport** - WebSocket transport
- `mw0` (Line 394390+) - **HTTP transport wrapper**

**Core MCP Client:**
- `ex1` (Line 394407+) - **Main MCP Client class** from TypeScript MCP SDK with methods:
  - `connect()` - Connect to MCP server
  - `getServerCapabilities()` - Get server capabilities
  - `request()` - Send JSON-RPC requests
  - `close()` - Cleanup connection

**Protocol Implementation:**
- **Protocol version**: Uses `MCP-Protocol-Version` header
- **Session management**: `mcp-session-id` header handling
- **Authentication**: OAuth 2.0 flow implementation
- **Message validation**: Zod schemas for protocol messages

**JSON-RPC Methods:**
- `resources/list` - List available resources
- `resources/read` - Read specific resource content
- `tools/call` - Execute MCP tools
- `notifications/roots/list_changed` - Notify of root changes

**Transport Protocols:**
- **STDIO**: Command-line spawning with stdin/stdout
- **SSE**: HTTP streaming with Server-Sent Events
- **WebSocket**: Real-time bidirectional communication
- **HTTP**: Request/response over HTTP

---

## Claude Code Application-Level MCP Integration (ANALYZE)

### **1. MCP Configuration Management**
**Lines: 353,077 - 353,500**

Claude Code's application logic for managing MCP server configurations.

#### **Key Configuration Functions:**

**Schema Definition:**
```javascript
[source fragment removed]
```

**Server Management:**
- `Line 353152`: Server conflict checking and validation
- `Line 353180`: `.mcp.json` file writing: `let W = { mcpServers: I }`
- `Line 353434`: Server name prefixing: `mcp__${vH(B)}__`

**Configuration Loading:**
- `Line 353081`: `.mcp.json` file reading
- `Line 353156-353162`: Conflict detection across user/local/project scopes
- `Line 353252`: Server enumeration: `FU1(Z?.mcpServers, A)`

#### **Configuration Scopes:**
- **Project**: `.mcp.json` in project root (shared via git)
- **User**: Global user configuration
- **Local**: Project-local configuration (not shared)
- **Dynamic**: Runtime-created servers (e.g., SDK servers)

### **2. Application Tools Using MCP**
**Lines: 392,580 - 393,000**

Claude Code's tool implementations that wrap MCP SDK calls.

#### **ListMcpResourcesTool (Line 392760):**
```javascript
[source fragment removed]
```

#### **ReadMcpResourceTool (Line 392881):**
```javascript
[source fragment removed]
```

#### **Tool Integration Pattern:**
1. **Input Validation**: Claude Code validates parameters
2. **Client Selection**: Find appropriate MCP client
3. **Capability Check**: Verify server supports the operation
4. **SDK Call**: Use MCP SDK to make protocol request
5. **Response Processing**: Format response for Claude Code UI
6. **Error Handling**: Convert MCP errors to user-friendly messages

### **3. MCP Connection Management**
**Lines: 410,914 - 411,023**

Claude Code's React component state management for MCP connections.

#### **React State Structure:**
```javascript
[source fragment removed]
```

#### **Connection State Management:**
```javascript
[source fragment removed]
```

#### **Connection Types:**
- `"pending"` - Connection attempt in progress
- `"connected"` - Successfully connected with capabilities
- `"failed"` - Connection failed
- `"needs-auth"` - Requires authentication

#### **Reconnection Logic (Lines 411019+):**
- Automatic reconnection for HTTP/SSE transports
- Manual reconnection for failed connections
- State transitions during reconnection attempts
- Error handling and user feedback

### **4. Tool Execution Entry Point**
**Line 394334**

Where Claude Code calls MCP tools through the SDK:

```javascript
[source fragment removed]
```

### **5. Transport Selection Logic**
**Line 393643**

Claude Code's logic for choosing MCP transport types:

```javascript
[source fragment removed]
```

---

## Key Debugging Entry Points

### **MCP Client Creation & Connection:**
- `Line 394407`: SDK client instantiation: `new ex1({ name: "claude-code", version: "1.0.120" })`
- `Line 394411`: Connection: `await W.connect(I)`
- `Line 393643`: Transport selection logic

### **Tool Execution:**
- `Line 394334`: Main tool call entry: `VA(B, \`Calling MCP tool: ${Q}\`)`
- `Line 394335`: Tool execution: `await A.callTool({ name: Q, arguments: Z })`

### **Protocol Communication:**
- `Line 389317`: JSON-RPC notification sending
- `Line 392760`: Resource listing: `client.request({ method: "resources/list" })`
- `Line 392881`: Resource reading: `client.request({ method: "resources/read", params: { uri: Z } })`

### **Configuration Loading:**
- `Line 353081`: `.mcp.json` file reading
- `Line 353152`: Server validation and conflict checking

---

## Analysis Guidelines

### **IGNORE (SDK Implementation - Lines 388,640-395,600):**
- Transport protocol details
- JSON-RPC message handling internal implementation
- Authentication flows (OAuth 2.0 internals)
- Protocol error handling internals
- Message validation schemas
- SDK connection management internals

### **ANALYZE (Claude Code Application Logic):**

#### **Configuration Management:**
- How `.mcp.json` is loaded, validated, and merged across scopes
- Server conflict detection and resolution
- Environment variable expansion in configurations
- Configuration file watching and updates

#### **Client Management:**
- How MCP connections are established and maintained
- Transport type selection logic
- Connection state transitions and error handling
- Automatic reconnection strategies

#### **Tool Integration:**
- How MCP tools are exposed to Claude Code users
- Tool parameter validation and transformation
- Response processing and formatting
- Integration with Claude Code's permission system

#### **State Management:**
- React component state for MCP connections
- Real-time updates when servers connect/disconnect
- Tool and resource availability updates
- Error propagation to UI components

#### **User Experience:**
- How MCP functionality is presented in the terminal interface
- Progress indication for long-running MCP operations
- Error messages and user feedback
- Command completion and help text

#### **Performance & Reliability:**
- Connection pooling and resource management
- Timeout handling and cancellation
- Error recovery and fallback strategies
- Resource cleanup and memory management

---

## Architecture Summary

The MCP implementation follows a clear separation of concerns:

1. **TypeScript MCP SDK** (Lines 388,640-395,600) - Protocol implementation black box
2. **Claude Code Configuration Layer** (Lines 353,000+) - Server management and configuration
3. **Claude Code Tool Layer** (Lines 392,580+) - Application tools that use MCP
4. **Claude Code UI Layer** (Lines 410,914+) - React components and state management

This architecture allows Claude Code to provide a rich MCP integration experience while leveraging the standard TypeScript MCP SDK for protocol compliance and reliability.

The boundary is clear: **SDK handles protocol, Claude Code handles integration, configuration, and user experience**.

---

## Current MCP Notification Status & Implementation Findings

### **Standard MCP Notifications: NOT IMPLEMENTED**

Claude Code does **NOT** implement any of the standard MCP notification handlers:

- ❌ `notifications/tools/list_changed` - No application usage found
- ❌ `notifications/resources/list_changed` - No application usage found
- ❌ `resources/subscribe` - No subscription mechanism implemented
- ❌ `notifications/resources/updated` - No application usage found

**Current Architecture**: Claude Code uses a **static discovery model** where it queries MCP servers once during connection establishment and caches the results. Dynamic notifications are not needed because:

1. **Tool discovery**: Uses `tools/list` during initial connection only
2. **Resource discovery**: Uses `resources/list` during initial connection only
3. **No dynamic updates**: Assumes tool/resource lists are stable during session

### **Custom MCP Notifications: IMPLEMENTED**

Claude Code implements 3 **custom** (non-standard) MCP notification handlers for IDE integration:

#### **1. `log_event` (Line 423438)**
**Purpose**: Forwards IDE telemetry events to Claude Code
```javascript
[source fragment removed]
```

#### **2. `at_mentioned` (Line 430353)**
**Purpose**: Notifies when files/code are referenced in conversation
```javascript
[source fragment removed]
```

#### **3. `selection_changed` (Line 432535)**
**Purpose**: Real-time IDE selection tracking
```javascript
[source fragment removed]
```

---

## Initial Tool and Resource Discovery Architecture

### **Connection Flow** (`lw0` function, line 394178)
```javascript
[source fragment removed]
```

### **Tool Discovery Function** (`dw0`, line 393995)
```javascript
[source fragment removed]
```

### **Resource Discovery Function** (`MGB`, line 394059)
```javascript
[source fragment removed]
```

### **State Management Integration** (line 410933)
```javascript
[source fragment removed]
```

---

## Proposed Implementation Strategy for `list_changed` Notifications

### **1. Add Notification Handlers in Application Code**

Add handlers alongside existing custom ones (after line 432535):

```javascript
[source fragment removed]
```

### **2. State Update Strategy**

Extend existing state management pattern from line 410933:

```javascript
[source fragment removed]
```

### **3. UI and LLM Context Implications**

#### **Text UI (User Interface) Considerations:**
1. **Tool Availability Changes:**
   - When `tools/list_changed` arrives, existing tool commands become invalid/valid
   - Need graceful handling if user tries to call a tool that was just removed
   - Consider brief notification: "Tools updated for server X"

2. **Resource Availability Changes:**
   - When `resources/list_changed` arrives, existing `ListMcpResourcesTool` results become stale
   - May need to invalidate cached resource lists
   - Resources in progress (being read) should complete, but list should refresh

#### **LLM Context (Assistant Interface) Considerations:**
1. **Tool Schema Updates:**
   - Assistant's tool schema knowledge becomes stale when tools change
   - Assistant might reference tools that no longer exist or miss newly available ones
   - **Mitigation**: Continue attempting to use tools - MCP will return appropriate errors

2. **Resource Discovery:**
   - Assistant's knowledge of available resources becomes outdated
   - **Mitigation**: Assistant can re-run `ListMcpResourcesTool` to get current state

### **4. Implementation Priorities**

1. **Essential**: Handle the notifications to keep internal state consistent
2. **Important**: Graceful error handling for stale tool/resource references
3. **Nice-to-have**: User feedback about capability changes

### **5. Key Implementation Insight**

The existing discovery functions (`dw0`, `MGB`) and state management patterns can be reused - we just need to trigger them when notifications arrive instead of only on initial connection. The MCP SDK already handles the protocol layer; Claude Code only needs to respond to the notifications in its application layer.

---

## Tools vs Resources: Architectural Analysis & Context Management

### **Fundamental Architectural Difference**

Claude Code implements **fundamentally different architectures** for tools vs resources, reflecting their different usage patterns in LLM interactions:

#### **Tools: API-Level Integration (Always Available)**
- **Definition**: Tool schemas are included in every Anthropic API call
- **Availability**: All tools are always visible to the LLM
- **Context**: Tool descriptions/schemas sent as part of API payload structure
- **State Management**: Must be kept current for API construction
- **Usage Pattern**: LLM can call any tool at any time during conversation

#### **Resources: Content-Level Integration (On-Demand)**
- **Definition**: Resource content is fetched and embedded when referenced
- **Availability**: Only loaded when mentioned via `@` notation
- **Context**: Resource content becomes part of message content, not API metadata
- **State Management**: Cached for `@` completion, but fetched fresh when used
- **Usage Pattern**: User mentions `@resource-name` → content fetched and embedded

---

## Tool Context Management Deep Dive

### **Tool Processing Flow to Anthropic API**

#### **1. Tool State Management (React State)**
```javascript
[source fragment removed]
```

#### **2. Tool Discovery and Wrapping (MCP → Claude Code)**
```javascript
[source fragment removed]
```

#### **3. Tool Aggregation for API Calls**
```javascript
[source fragment removed]
```

#### **4. Tool Context Generation Pattern**
Based on the architecture discovered:

1. **State-Driven**: Tool objects stored in React state with async methods
2. **Dynamic Descriptions**: `description()` methods called to build LLM context
3. **Fresh Generation**: Tool information regenerated for each API call from current state
4. **Anthropic API Format**: Tools transformed to API format with name/description/schema

**Likely Anthropic API Payload Structure**:
```json
{
  "model": "claude-3-5-sonnet-20241022",
  "messages": [...],
  "tools": [
    {
      "name": "mcp__server-name__tool-name",
      "description": "Tool description from MCP server",
      "input_schema": { "type": "object", "properties": {...} }
    }
  ]
}
```

### **Why Tool Dynamic Updates Work Seamlessly**

#### **Dynamic Method Pattern**
```javascript
[source fragment removed]
```

#### **State Replacement Pattern**
```javascript
[source fragment removed]
```

---

## Resource Context Management Deep Dive

### **Resource State vs Usage Pattern**

#### **1. Resource State Structure (Different from Tools)**
```javascript
[source fragment removed]
```

#### **2. Resource Discovery Function (State Caching)**
```javascript
[source fragment removed]
```

#### **3. Critical Discovery: ListMcpResourcesTool Bypasses State**
```javascript
[source fragment removed]
```

### **Resource Content Processing (@ Mention System)**

#### **Resource Content Integration (RGB Function - Line 394270)**
```javascript
[source fragment removed]
```

#### **@ Mention Resolution Flow**
Based on the resource processing architecture:

1. **User Input**: Types `@resource-name` in message
2. **Resource Discovery**: System calls `resources/list` to find available resources
3. **Resource Resolution**: Matches `@resource-name` to resource URI
4. **Content Fetch**: Calls `resources/read` with URI to get content
5. **Content Embedding**: Uses `RGB()` to embed resource content in message
6. **API Call**: Message sent to Anthropic with embedded resource content

**Example Message Transformation**:
```
User Input: "Analyze @my-document"

Becomes:
"Analyze [Resource from my-server at file://my-document.md]
<entire document content here>"
```

### **Why Resources Don't Need API-Level State Management**

#### **Content vs Metadata Distinction**
```javascript
[source fragment removed]
```

#### **On-Demand vs Always-Available**
- **Tools**: Must be current in API payload for LLM to call them
- **Resources**: Fetched fresh when `@` mentioned, embedded in content

---

## Implementation Strategy for `list_changed` Notifications

### **Tool List Changed Handler**
```javascript
[source fragment removed]
```

**Rationale**: Tools are in API payload, so state must be current for API construction.

### **Resource List Changed Handler**
```javascript
[source fragment removed]
```

**Rationale**: Resources are not in API payload, only need state consistency for @ completion.

### **Critical Architectural Insight**

The **different notification handling complexity** reflects the **different integration patterns**:

- **Tools**: Complex state management needed because they're **API-level** (part of every call)
- **Resources**: Simple state management sufficient because they're **content-level** (on-demand)

This architectural difference ensures that:
1. **Tool changes** immediately affect LLM capabilities in next conversation turn
2. **Resource changes** immediately affect `@` completion and resolution
3. **Both systems** remain performant and current without unnecessary complexity

### **Testing Strategy**

#### **Tool Updates**:
1. MCP server adds/removes/changes tools
2. Send `notifications/tools/list_changed`
3. Verify LLM can call new tools and no longer sees removed tools in next conversation

#### **Resource Updates**:
1. MCP server adds/removes/changes resources
2. Send `notifications/resources/list_changed`
3. Verify `@` completion shows updated resources and `@mentions` resolve correctly

Both should work seamlessly with the existing architecture once notification handlers are added.