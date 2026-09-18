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
store. Read and write use different scopes. The status gate reads the effective merged settings (the
writer is hardcoded, the reader is not), so a name you hand-add to `enabledMcpjsonServers` in any
scope — including the shared, checked-in `.claude/settings.json` — is honored. But the `/mcp` UI and
the approval prompt always write the decision to local project settings (`.claude/settings.local.json`,
the `localSettings` scope is passed literally): approving appends the name to `enabledMcpjsonServers`,
"enable all" sets `enableAllProjectMcpServers`, rejecting (or cancelling/Esc, which the dialog treats as
"no") appends to `disabledMcpjsonServers`. Writing to local rather than the shared file is deliberate:
approval is a personal, untracked security decision, so it is not committed onto teammates, and a cloned
repo cannot pre-approve its own servers by shipping a `settings.json` with `enabledMcpjsonServers` —
approval has to come from your local file or the prompt. Because these are local-scope settings, the
write goes through the guarded settings writer; a symlinked `.claude/settings.local.json` silently
refuses it, so an approval can appear to take in the UI yet never persist (see `SETTINGS.md`, the
symlink-refusal section). Older copies of these keys under
`~/.claude.json` `projects.<path>` are folded into local settings by a migration; the rejection UI
points there too — `Rejected (see disabledMcpjsonServers in settings)`. Local-scoped servers added
with `claude mcp add` instead live under `~/.claude.json` `projects.<path>.mcpServers` and load
directly with no approval — that asymmetry is why `claude mcp add` servers work immediately while
`.mcp.json` servers wait.

Command-line `--mcp-config <path>` servers are a third scope, connected through a separate direct path
(the connect factory categorizes them `regular`/`alwaysLoad` and connects them) that never consults the
project approval gate or project-file discovery. So a server loaded with `--mcp-config` connects
regardless of approval state or any project-`.mcp.json` discovery problem — which is why
`claude --mcp-config ./.mcp.json` is a reliable workaround when interactive auto-discovery of the same
file fails. `--strict-mcp-config` restricts the session to only the `--mcp-config` servers, ignoring all
other MCP configuration. Relocate with `rg -n '"--mcp-config"|--strict-mcp-config'`.

The approval prompt. The prompt to approve pending `.mcp.json` servers runs only at interactive
startup, and only when the config loaded without errors; it is not re-evaluated mid-session. Headless/
`-p` runs don't prompt because the effective-status override already approves pending servers there (see
above), not because the servers stay pending. A server added to `.mcp.json` during a running session
won't prompt until the next interactive start in that project. If it still doesn't prompt, `claude mcp
reset-project-choices` resets the project's approved/rejected decisions back to `pending` so the prompt
re-fires — but reset only re-arms; it never approves. It deletes all three keys for the project from
both the `localSettings` file (`settings.local.json`) and the legacy `~/.claude.json`
`projects.<path>` store, so it is project-wide, not per-server. It clears the legacy store first; if
that fails it changes nothing, and if `settings.local.json` carries validation warnings it refuses to
rewrite the local file (clearing only the legacy store) and points at `/doctor`. It resets only MCP
choices — not the workspace trust dialog (`hasTrustDialogAccepted`) and not the external CLAUDE.md
includes decision (see `CLAUDE_MD_EXTERNAL_INCLUDES.md`), which have no reset subcommand. The reliable
fix is to set `enabledMcpjsonServers` in `.claude/settings.local.json` directly (and confirm that file
is a real file, not a symlink, or the write silently no-ops — see `SETTINGS.md`). Explicit enablement
loads the server regardless of the prompt gates below — they only control whether the interactive
prompt fires.

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

## `claude mcp add` scope targets

Verified against `cli.prettier.js` 2.1.186 (2026-07-02). `claude mcp add <name> <commandOrUrl>` takes
`-s`/`--scope <local|user|project>`, defaulting to `local` when omitted. Relocate the command
definition with `rg -n '"-s, --scope <scope>"'` (three `mcp` subcommands share the flag text; `add` is
the one whose description starts "Add an MCP server to Claude Code") and the per-scope write switch
with `rg -n 'Cannot add MCP server to scope: dynamic'` (a `switch (n)` a few lines above writes the
server; the cases below it validate for a pre-existing name of the same key).

Each scope writes a different file, and only one of the three lands inside the project directory:

- `project` — the shared, git-committable file. Reads/writes `.mcp.json` in the current working
  directory (not `.claude/.mcp.json` — there is no `.claude/` prefix) via a temp-file-then-rename
  write, under the top-level `mcpServers` key. This is what a teammate cloning the repo also sees;
  new entries here are `pending` until each clone's user approves them (see the approval section
  above).
- `user` — available in every project. Reads/writes the *top-level* `mcpServers` key of the global
  config file (`~/.claude.json`, or `$CLAUDE_CONFIG_DIR/.claude<oauth-suffix>.json` if set; see
  `SETTINGS.md`). Loads with no per-project approval prompt.
- `local` (the default when `-s` is omitted) — private to you, scoped to one project, and not stored
  in the project directory at all. Reads/writes `projects."<absolute-project-path>".mcpServers` inside
  that same `~/.claude.json`, keyed by the project's absolute path. Also loads with no approval
  prompt — this is the asymmetry the approval section above notes: `claude mcp add` servers (any
  scope) skip the `.mcp.json` pending/approved/rejected gate entirely; only servers hand-written into
  a project's `.mcp.json` file go through it.

So to add a server that lands in a specific project's own `.mcp.json` (e.g. so it's committed and
shared from that project), run `claude mcp add <name> ... -s project` with that project as the cwd —
`-s user`/`-s local` never touch a project-local file.

## Tool-call timeouts and the idle watchdog

Verified against `cli.prettier.js` 2.1.277 (2026-09-18). This section is newer than the rest of the
document (see the `Source:` line) and follows the landmark style.

Four timeouts exist, and only the last two apply to a tool call already in flight:

| Timeout               | Default                        | Set by                                        |
| --------------------- | ------------------------------ | --------------------------------------------- |
| Server startup        | 30000 ms                       | `MCP_TIMEOUT`                                 |
| Transport connect     | 5000 ms                        | `MCP_CONNECT_TIMEOUT_MS`                      |
| Tool call, wall clock | 1e8 ms (~27.8 h)               | per-server `timeout`, else `MCP_TOOL_TIMEOUT` |
| Tool call, idle       | 1800000 ms stdio, 300000 other | per-server `timeout`, else the idle env var   |

The two startup values come from a pair of one-line getters returning `30000` and `5000` when their
env var is unset or non-positive, each capped at `2147483647`; relocate with
`rg -n 'MCP_CONNECT_TIMEOUT_MS'` and take the module that exports both.

Relocate the tool-call path with `rg -n 'MCP tool idle timeout'`. The enclosing function takes a
destructured object (`client`, `tool`, `args`, `signal`, `onProgress`, `idleTimeoutMs`) and races
`callTool` against two rejection promises: a `setTimeout` holding the wall-clock limit and a
30-second `setInterval` holding the idle watchdog and the transport-drop check.

Wall clock. Resolved as per-server `timeout` (ignored below 1000 ms, so it falls through) ??
`MCP_TOOL_TIMEOUT` ?? `1e8`, clamped to `[1000, 2147483647]`; relocate the resolver with
`rg -n 'MCP_TOOL_TIMEOUT'` and take the function whose fallback constant is `1e8`. With neither set
the limit is about 27.8 hours, so a default-configured server has no practical wall-clock limit.
Expiry rejects with `MCP server "<name>" tool "<tool>" timed out after <n>s`, titled `MCP tool
timeout`, and carries `mcpErrorSource: "downstream_unreachable"`.

Progress notifications do not extend the wall clock. The `.mcp.json` `timeout` field states this in
its own schema description; relocate with `rg -n 'progress notifications do not extend it'`.

Idle watchdog. Resolved as `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` ?? 1800000 for stdio and 300000 for
every other transport, then floored by the per-server `timeout` and capped by the wall clock, so it
can never fire after the wall clock does. Setting the env var to 0 disables it, and it is disabled
outright for the `sse-ide`, `ws-ide` and `sdk` client types. The 30-second poll also writes
`Tool '<tool>' still running (<n>s elapsed)` to the MCP debug log. An `onprogress` notification
resets the idle clock, as does a pending elicitation: while one is open the clock is held at the
current time, and closing one restarts it from the moment it closed. The abort message names both
remedies, a per-server `timeout` for one server or `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` globally.

Transport drop. The same 30-second interval watches a per-call flag armed when the transport records
an error mid-call, and rejects 90 seconds after arming with `MCP transport lost mid-call`, on the
grounds that the response is presumed lost. Relocate with `rg -n 'response presumed lost'`.

Two consequences worth stating plainly. A stdio server that sends no progress notifications gets 30
minutes of silence before it is aborted; an HTTP or SSE server gets 5. And the SDK's own 60-second
default request timeout never governs a tool call, because the application always passes an explicit
`timeout` to `callTool`.

An internal per-server `request_timeout_ms` also exists, set by the host on the `mcp_set_servers`
control event rather than written into `.mcp.json` by hand. It raises the per-request fetch
first-byte budget and the tool-call watchdog for that one server, is capped at 5 minutes, and is
ignored when `timeout` is also set. Relocate with `rg -n 'request_timeout_ms'`.

Re-verify: □ startup getters still default to `30000` and `5000` □ wall-clock fallback constant
still `1e8` □ per-server `timeout` still ignored below 1000 ms □ idle defaults still 1800000 stdio /
300000 other □ idle watchdog still capped by the wall clock and disabled for `sse-ide` / `ws-ide` /
`sdk` □ poll interval still 30 s and transport-drop grace still 90 s □ both abort messages still
carry `mcpErrorSource: "downstream_unreachable"` □ `request_timeout_ms` still capped at 5 minutes
and still ignored when `timeout` is set.

## MCP tool auto-backgrounding

Verified against `cli.prettier.js` 2.1.277 (2026-09-18). This section is newer than the rest of the
document (see the `Source:` line) and follows the landmark style.

A foreground MCP tool call that has not returned within a threshold is moved to the background on
its own. The turn continues, the call is registered in the task registry with a description naming
the server and tool, and a notification arrives when it settles. This is unrelated to the gated-off
task machinery documented above: it is Claude Code's own mechanism, needing nothing from the server.

Relocate with `rg -n 'tengu_mcp_tool_auto_backgrounded'`. That telemetry call sits inside the
backgrounding helper, whose parameter list includes `autoBackgroundMs` and `onBackgrounded`; the
threshold resolver is the small function above it, ending in a gate call whose fallback is the
default constant.

Nothing changes on the wire. The call is issued once, and the helper races that single in-flight
promise against a timer; when the timer wins, the promise is not cancelled and no second request is
sent. The `tools/call` request stays open on the transport, so the wall-clock limit and the idle
watchdog above keep counting against a backgrounded call — backgrounding buys a responsive turn, not
a larger budget. It buys no durability either: the work lives on an open connection, so ending the
session ends it, with no handle to resume from. This is the difference from a real task, which
answers the request immediately with a handle the client can poll after a reconnect. A server is
neither told that its call was backgrounded nor able to detect it.

The threshold resolves in this order, and any zero means the call is never backgrounded:

- client type `sse-ide` or `ws-ide` → 0
- background tasks disabled for the session, either by the session's own `backgroundTasksDisabled`
  or by `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` → 0; relocate with
  `rg -n 'Background tasks are disabled in this session'`
- non-interactive session without `CLAUDE_AUTO_BACKGROUND_TASKS` set → 0
- `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS` set → that value, clamped to [0, 2147483647]
- otherwise the `tengu_mcp_auto_background` gate, whose default is on → 120000 ms

The recorded trigger is `timeout` for the threshold firing, or `deliver_message` when the call is
backgrounded to let a queued message through. On settling, the registry entry takes `completed`,
`tool_error`, `aborted` or `call_failed`, along with the server's own bounded status message.

The practical consequence is that the tool-call timeouts documented above are not what anyone waits
for. An interactive caller waits two minutes and gets the turn back while the call keeps running to
its wall-clock limit; only a headless caller without `CLAUDE_AUTO_BACKGROUND_TASKS`, or a session
with background tasks disabled, blocks for the whole call. A slow MCP server therefore does not need
to implement tasks to avoid blocking an interactive session, and wrapping the call in a subagent
buys nothing an interactive session does not already do.

Re-verify: □ default threshold still 120000 ms □ `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS` still
overrides and still clamps at [0, 2147483647] □ `sse-ide` / `ws-ide` still exempt □ non-interactive
still requires `CLAUDE_AUTO_BACKGROUND_TASKS` □ `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` still
disables □ gate `tengu_mcp_auto_background` still defaults on □ triggers still `timeout` and
`deliver_message` □ the in-flight call still raced against the timer rather than re-issued.

## Task-augmented tool calls: implemented, gated off

Verified against `cli.prettier.js` 2.1.277 (2026-09-18). This section is newer than the rest of the
document (see the `Source:` line) and follows the landmark style.

Claude Code carries a complete client-side implementation of MCP tasks — async tool calls — and a
feature gate keeps all of it unreachable. An MCP server therefore cannot make Claude Code run its
tool asynchronously, whatever it advertises.

Which tasks. The source names its own helpers `Sep2663`, but the wire methods it drives are the set
that spec revision 2025-11-25 defined under SEP-1686: `tasks/get`, `tasks/result`, `tasks/list`,
`tasks/cancel` and `notifications/tasks/status`, with per-tool opt-in through
`execution.taskSupport`. That design shipped as an explicitly experimental core feature and revision
2026-07-28 removed it from the core protocol, moving tasks to the official extension
`io.modelcontextprotocol/tasks` (SEP-2663). The extension is not wire-compatible with what Claude
Code implements: `tasks/get` carries the result inline for terminal states so `tasks/result` is
gone, `tasks/list` is removed, mid-flight input is fulfilled through a new `tasks/update`, a task
handle is identified by `resultType: "task"`, and task creation is server-directed, which retires
the per-tool `taskSupport` warmup. The dormant code is built on the superseded shape.

The gate. Relocate with `rg -n 'tasks: \{ requests: \{ elicitation'`. The client capability object
spreads its `tasks` entry only when a zero-argument gate function returns true, and that function's
entire body is `return !1`; it is defined in the same bun module as the capability builder. The same
gate guards the outbound call path: relocate with `rg -n 'getProtocolEra\(\) === "modern"'`, where
the gate result is computed into a variable that nothing reads and the request options object
built beside it is empty, so `tools/call` params never carry a `task` field. Task augmentation is
client-initiated, so a server that declares task support is simply never asked for a task.

The gate returns `!1` in 2.1.231, 2.1.263 and 2.1.277. The app-level machinery below is absent in
2.1.231 and present from 2.1.263, so the client work landed between those two and has stayed dark.

What sits behind the gate:

- Client plumbing for `tasks/get`, `tasks/result`, `tasks/list`, `tasks/cancel` and
  `notifications/tasks/status`, gated on the server advertising capability
  `tasks.requests.tools.call` and on the individual tool declaring `execution.taskSupport` of
  `"required"` or `"optional"` in `tools/list`. A plain call against a `"required"` tool throws
  rather than running; relocate with `rg -n 'requires task-based execution'`.
- Two drive modes for a tool result that carries a task, both reachable only through the gate.
  Inline polling reports the server's own `statusMessage` as tool progress; relocate with
  `rg -n 'polling inline'`. Backgrounding hands the task to Claude Code's task registry as task type
  `mcp_task`, returns a placeholder tool result, and writes sidecar metadata so the task survives a
  session restart; relocate with `rg -n 'backgrounded as'` and `rg -n 'Sep2663'` (three helpers:
  register-or-adopt, background-drive, placeholder-result).
- Poll cadence taken from the task's own `pollInterval`, defaulting to 2000 ms and clamped to
  [100, 60000]; the poller abandons a task after 10 consecutive failed polls. Relocate the poll loop
  with `rg -n 'poll failed'`, and the clamp constants as the `var` group above it.
- `input_required` handling that fetches the task result to surface the server's prompt, then
  resolves it through a user dialog.
- Telemetry `mcp_task_background`, `mcp_task_complete` and `mcp_task_restore`; relocate with
  `rg -n 'mcp_task_background'`.

The task object the client expects, from the bundled SDK schema: `taskId`, `status` (one of
`working`, `input_required`, `completed`, `failed`, `cancelled`), `ttl`, `createdAt`,
`lastUpdatedAt`, optional `pollInterval` and optional `statusMessage`. The client-side augmentation
it would send is `{ ttl?, pollInterval? }`. Relocate with `rg -n '"notifications/tasks/status"'`.

Re-verify: □ gate function still returns `!1` □ capability spread still guarded by it □ call-path
options object still built without a `task` field □ `taskSupport` still gates on `"required"` /
`"optional"` □ poll default still 2000 ms, clamp still [100, 60000], failure limit still 10 □ both
drive modes still present □ the three `mcp_task_*` telemetry names still present.

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