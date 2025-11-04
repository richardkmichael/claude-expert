# Claude Code Analysis - Hook Functionality

This document analyzes the PreToolUse and PostToolUse hook functionality in Claude Code's bundled
JavaScript file `package/cli.prettier.js`, focusing on areas relevant for modifying hook behavior.

## Objective
Understand and modify the behavior of:
- **PreToolUse hooks**: Control tool execution permission (allow/deny/ask)
- **PostToolUse hooks**: Execute actions after tool completion

## Analysis Focus
Based on LIBRARY_BOUNDARIES.md, the relevant code is in:
- **Lines 357,001-444,530**: Pure Claude Code application implementation
- **Lines 339,457-357,000**: Mixed Claude Code + libraries (may contain hook-related code)

## Initial Findings from cli_prettier_notes.md

The following locations were identified (need validation):

### 1. Hook Configuration (L354256)
- Location appears to be in mixed Claude Code section
- Shows PostToolUse hook configuration with matchers
- Demonstrates tool-specific hooks (e.g., BashTool targeting)

### 2. Hook Output Schema (L363013)
- Location in pure Claude Code section
- Defines PreToolUse hook response format
- Critical for understanding hook return values

### 3. PreToolUse Execution Control (L419756)
- Location in pure Claude Code section
- Shows how permission decisions are enforced
- Key mechanism for tool blocking

### 4. PostToolUse Cancellation (L419906)
- Location in pure Claude Code section
- Demonstrates hook abortion mechanism
- Important for cleanup/error handling

## Verified Hook Implementation Details

### 1. Hook Configuration Format (L354256) ✅ VERIFIED
```javascript
[source fragment removed]
```

### 2. Hook Output Schema (L363013) ✅ VERIFIED
**Schema for hook responses:**
```javascript
[source fragment removed]
```

### 3. Hook Metadata and Behavior (L418318) ✅ VERIFIED
**PreToolUse Hook Behavior:**
- **Input**: JSON of tool call arguments
- **Exit code 0**: stdout/stderr not shown
- **Exit code 2**: show stderr to model and **block tool call**
- **Other exit codes**: show stderr to user only but continue with tool call

**PostToolUse Hook Behavior:**
- **Input**: JSON with "inputs" (tool call arguments) and "response" (tool call response)
- **Exit code 0**: stdout shown in transcript mode (Ctrl-O)
- **Exit code 2**: show stderr to model immediately
- **Other exit codes**: show stderr to user only

### 4. Permission Decision Processing (L363047-L363096) ✅ VERIFIED
**PreToolUse permission decisions are processed as:**
```javascript
[source fragment removed]
```

### 5. Tool Execution Control (L419754-L419765) ✅ VERIFIED
**Tool blocking mechanism:**
```javascript
[source fragment removed]
```

### 6. PostToolUse Cancellation (L419902-L419911) ✅ VERIFIED
**Hook cancellation mechanism:**
```javascript
[source fragment removed]
```

## Key Modification Points Identified

1. **Permission Control**: Lines 363047-363096 - Where hook permission decisions are translated to behavior
2. **Tool Blocking**: Lines 419754-419765 - Where tool execution is actually stopped
3. **Hook Metadata**: Lines 418318+ - Where hook behavior descriptions are defined
4. **Output Schema**: Lines 363013+ - Where valid hook responses are defined
5. **Cancellation Logic**: Lines 419902+ - Where hook execution can be aborted

## Why PreToolUse Hooks Don't Fire for Invalid Inputs ⚠️

**Root Cause Identified**: PreToolUse hooks are bypassed entirely when tool input validation fails **before** hook execution.

### Tool Validation Pipeline (Read Tool Example)
**Location**: Lines 419660-419680 in the main execution flow
```javascript
[source fragment removed]
```

### Read Tool's validateInput Function (CLI.js lines ~1776+)
```javascript
[source fragment removed]
```

### Impact on Hook Behavior
- **File doesn't exist**: `errorCode:2` → Tool fails immediately, PreToolUse hook never fires
- **Binary file**: `errorCode:4` → Tool fails immediately, PreToolUse hook never fires
- **File too large**: `errorCode:6` → Tool fails immediately, PreToolUse hook never fires
- **Only valid inputs**: Proceed to PreToolUse hook execution

This explains why PreToolUse hooks don't fire for non-existent files - the tool's own validation rejects the input before hooks are even considered.

## Tool Execution Code Boundaries

**Core Tool Processing Section**: Lines **419556-419948** (~392 lines)

### Key Functions in Tool Execution Pipeline:
1. **`JZ5` (Line 419556)**: Main tool orchestrator - processes multiple tool uses in parallel
2. **`Rh1` (Line 419572)**: Cleanup function - removes tool from in-progress tracking
3. **`s$B` (Line 419575)**: Individual tool handler - validates tool exists and delegates to XZ5
4. **`XZ5` (Line 419635)**: **Core tool execution wrapper** - handles schema validation, input validation, and hook execution

### Code Context:
- **Before (Lines ~417000-419555)**: Settings/UI management, policies, configuration
- **Tool Section (Lines 419556-419948)**: Pure tool execution logic
- **After (Lines 419949+)**: Error handling utilities, thinking tokens, model processing

## Solution: Force Hooks to Always Fire

**Target Modification**: Line 419660 in `XZ5` function

### Current Code Structure (Lines 419660-419689)
```javascript
[source fragment removed]
```

### Crude Solution: Comment Out validateInput Call
To force hooks to always fire, simply comment out or remove the validation check:

**Option 1: Comment out the validation (recommended for testing)**
```javascript
[source fragment removed]
```

**Option 2: Force validation to always pass**
```javascript
[source fragment removed]
```

### Expected Behavior After Modification
- ✅ PreToolUse hooks will **always fire** regardless of input validity
- ✅ Hooks can implement their own validation logic in the hook scripts
- ⚠️ **Warning**: Tools will attempt to execute on invalid inputs (non-existent files, etc.)
- ⚠️ **Error handling**: Tool execution may fail later, but hooks will have had a chance to run

### Alternative: Move Validation After Hooks
For a more sophisticated solution, relocate the validation check to occur after hook execution, allowing hooks to run but still preventing tool execution on invalid inputs.

## Hook System Architecture Deep Dive

### Complete Hook Execution Pipeline
**Location**: Tool processing section (Lines 419556-419948)

```javascript
[source fragment removed]
```

### Hook System Components

#### 1. Tool Orchestrator: `JZ5` (Line 419556)
- **Purpose**: Main entry point for tool execution
- **Function**: Processes multiple tool uses in parallel using `I4B()`
- **Delegates to**: `s$B()` for individual tool handling

#### 2. Single Tool Handler: `s$B` (Line 419575)
- **Purpose**: Validates tool exists and manages tool lifecycle
- **Key responsibilities**:
  - Finds tool definition by name: `Z.options.tools.find()`
  - Sets tool as in-progress: `Z.setInProgressToolUseIDs()`
  - Error handling for missing tools
  - Delegates to `XZ5()` for actual execution
  - Cleanup via `Rh1()` when complete

#### 3. Core Tool Executor: `XZ5` (Line 419635)
- **Purpose**: Complete tool execution wrapper with validation and hooks
- **Critical validation points**:
  - **Schema validation** (Line 419636): `A.inputSchema.safeParse(Q)`
  - **Semantic validation** (Line 419660): `A.validateInput?.(I.data, Z)` ← **BLOCKS HOOKS**
  - **Hook execution** (Line 419689): `lNA(A.name, B, J, O, Z.abortController.signal)` ← **Only if validation passes**

#### 4. PreToolUse Hook Executor: `lNA` (Called at Line 419689)
- **Purpose**: Executes PreToolUse hook scripts and processes results
- **Current parameters**:
  ```javascript
  [source fragment removed]
  ```
- **Hook result processing** (Lines 419691-419713):
  - Processes `j.permissionBehavior` ("allow", "deny", "ask")
  - Creates permission decision objects
  - Handles hook cancellation and blocking errors

#### 5. Cleanup Function: `Rh1` (Line 419572)
- **Purpose**: Removes tool from in-progress tracking
- **Called**: After tool completion in `s$B`

### Hook Result Processing Flow (Lines 419691-419725)
```javascript
[source fragment removed]
```

### PostToolUse Hook Execution
- **Location**: End of `XZ5` function (after tool execution)
- **Function call**: `pNA()` (similar to PreToolUse `lNA()`)
- **Processing**: Similar result handling for PostToolUse hooks

## Proposed Solution: Enhanced Hook Context

### Modified Hook Execution Call
Instead of bypassing validation, enhance hook context:

```javascript
[source fragment removed]
```

### Enhanced PreToolUse Hook Schema
```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../session.jsonl",
  "cwd": "/Users/...",
  "hook_event_name": "PreToolUse",
  "tool_name": "Read",
  "tool_input": {
    "file_path": "/path/to/nonexistent.txt"
  },
  "tool_validation": {
    "schema_validation": {
      "passed": true,
      "error_message": null
    },
    "input_validation": {
      "passed": false,
      "error_message": "File does not exist.",
      "error_code": 2
    }
  }
}
```

### Implementation Impact
- **✅ Backward Compatible**: `tool_validation` is optional
- **✅ Always Fires Hooks**: Hooks execute regardless of validation failures
- **✅ Intelligent Hook Logic**: Hooks can make informed decisions based on validation context
- **✅ Maintains Safety**: Tool execution can still be blocked, but after hook consultation

This architecture allows hooks to handle validation failures intelligently while preserving the existing safety mechanisms.

## PostToolUse Hook Enhancement Implementation ✅ COMPLETED

### Problem Resolved
PostToolUse hooks previously only fired on tool success, missing all tool execution failures. This limited hooks from implementing error recovery, cleanup, audit logging, or failure-specific workflows.

### Solution: Enhanced PostToolUse with tool_execution Property

**Architecture Decision**: Add `tool_execution` property containing execution metadata while preserving `tool_response` semantics for clean API separation.

### Complete Tool Execution Flow (Updated)

```javascript
[source fragment removed]
```

#### Detailed Flow Stages:

1. **Schema Validation** (Zod structure validation)
   - ❌ **Fails** → Early return, no hooks fire
   - ✅ **Passes** → Continue to input validation

2. **Input Validation** (Tool-specific business logic)
   - ❌ **Fails** (e.g., "file doesn't exist") → Early return, no hooks fire
   - ✅ **Passes** → Continue to PreToolUse hooks

3. **PreToolUse Hooks** (Always fire when reached)
   - Receive `tool_validation` context with both schema and input validation results
   - Can make informed decisions about tool execution
   - Can block tool execution via `permissionDecision: "deny"`

4. **Permission Checks**
   - Process hook decisions and user permissions
   - ❌ **Denied** → Stop, no tool execution, no PostToolUse
   - ✅ **Allowed** → Continue to tool execution

5. **Tool Execution** (Actual tool.call())
   - ✅ **Succeeds** → PostToolUse fires with success context
   - ❌ **Fails** → PostToolUse fires with error context
   - 🚫 **Never attempted** → No PostToolUse

6. **PostToolUse Hooks** (Only fire if tool execution was attempted)
   - Receive both `tool_response` (output) and `tool_execution` (metadata)
   - Handle success and failure cases uniformly

### Enhanced Hook Schemas

#### PostToolUse Success Case
```json
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Read",
  "tool_input": {"file_path": "/existing.txt"},
  "tool_response": {
    "type": "text",
    "file": {"content": "file contents...", "filePath": "/existing.txt"}
  },
  "tool_execution": {
    "success": true,
    "duration_ms": 145
  }
}
```

#### PostToolUse Failure Case
```json
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Bash",
  "tool_input": {"command": "nonexistent_command"},
  "tool_response": null,
  "tool_execution": {
    "success": false,
    "duration_ms": 234,
    "error_message": "Shell command failed",
    "error_type": "ShellError",
    "details": {
      "stdout": "",
      "stderr": "bash: nonexistent_command: command not found",
      "exitCode": 127,
      "interrupted": false
    }
  }
}
```

### Test Cases and Expected Behavior

#### ✅ PostToolUse WILL Fire (Tool Execution Attempted)
- **`Bash "false"`** → Tool executes, exits with code 1 → PostToolUse with ShellError
- **`Bash "exit 1"`** → Tool executes, exits with code 1 → PostToolUse with ShellError
- **`Bash "nonexistent_command"`** → Tool executes, command not found → PostToolUse with ShellError
- **`Grep "[invalid_regex"`** → Tool executes, regex fails → PostToolUse with ripgrep error
- **`Read "/existing.txt"`** → Tool executes successfully → PostToolUse with success context

#### ❌ PostToolUse will NOT Fire (Tool Never Executed)
- **`Read "/nonexistent.txt"`** → Input validation failure → No tool execution → No PostToolUse
- **`Edit "/file.txt" "old" "new"`** (file not read first) → Validation failure → No PostToolUse
- **`Read {"bad": "schema"}`** → Schema validation failure → No tool execution → No PostToolUse
- **`UnknownTool`** → Tool doesn't exist → No tool execution → No PostToolUse

### Design Rationale

**Clean Semantic Separation**:
- **PreToolUse**: "I'm about to try running this tool" (with validation context)
- **PostToolUse**: "I tried running this tool" (with execution context)
- **No PostToolUse**: "Tool was never attempted" (validation blocked it)

**Benefits**:
- ✅ **Complete Lifecycle Coverage**: Handle both success and failure execution cases
- ✅ **Rich Error Context**: Full stdout/stderr/exit codes from process-based tools
- ✅ **Clean API**: `tool_response` for output, `tool_execution` for metadata
- ✅ **Backward Compatible**: Existing hooks continue working unchanged
- ✅ **Size Safe**: Leverages existing SM0() 10KB error limiting
- ✅ **Consistent Flow**: PreToolUse handles validation, PostToolUse handles execution

**Hook Development Patterns**:
```javascript
[source fragment removed]
```

This implementation provides comprehensive PostToolUse hook coverage for actual tool execution attempts while maintaining logical flow boundaries and clean API semantics.

## Legacy PostToolUse Hook Analysis (Pre-Enhancement)

### Original PostToolUse Hook Behavior

**Previous Limitation**: PostToolUse hooks were **only called when the tool call succeeded**.

### Evidence from Code Analysis

#### 1. PostToolUse Hook Location (Lines 419900-419902)
The `pNA` (PostToolUse) function call is **outside and after** the try-catch block that handles tool execution:

```javascript
[source fragment removed]
```

#### 2. Early Return on Tool Failure
When a tool fails (exception thrown), the catch block:
1. Logs the error telemetry
2. Yields an error message to the user
3. **Returns early** (preventing PostToolUse execution)
4. PostToolUse hook code is **never reached**

#### 3. PostToolUse Hook Parameters (Line 419902)
The PostToolUse hook receives the **successful tool result** (`C`) as the `tool_response` parameter:

```javascript
[source fragment removed]
```

### What `tool_response` Contains

**`tool_response` = Raw Tool Result Data** (not output schema)

#### For Read Tool:
```json
{
  "type": "text",
  "file": {
    "filePath": "/path/to/file.txt",
    "content": "file content here...",
    "numLines": 42,
    "startLine": 1,
    "totalLines": 42
  }
}
```

#### For Edit Tool:
```json
{
  "filePath": "/path/to/file.txt",
  "oldString": "original text",
  "newString": "replacement text",
  "originalFile": "entire original file content",
  "structuredPatch": [/* diff hunks */],
  "userModified": false,
  "replaceAll": false
}
```

### Problem: PostToolUse Hooks Don't Fire on Tool Failures

**Current Limitation**: PostToolUse hooks cannot:
- ❌ Handle tool failures or errors
- ❌ Perform cleanup after failed operations
- ❌ Log or audit failed tool attempts
- ❌ Implement error recovery workflows

### Proposed Solution: Universal PostToolUse Hook Execution

**Goal**: Modify PostToolUse hooks to fire **regardless** of tool success or failure.

#### Enhanced PostToolUse Hook Schema
```json
{
  "session_id": "abc123",
  "hook_event_name": "PostToolUse",
  "tool_name": "Read",
  "tool_input": {"file_path": "/nonexistent.txt"},
  "tool_execution": {
    "success": false,
    "error_message": "File does not exist.",
    "error_type": "InputValidationError",
    "duration_ms": 156
  },
  "tool_response": null  // null for failures, result data for success
}
```

#### Implementation Strategy

**Option 1: Move PostToolUse Outside Try-Catch**
```javascript
[source fragment removed]
```

**Option 2: Duplicate PostToolUse Calls**
```javascript
[source fragment removed]
```

### Implementation Impact

#### ✅ Benefits:
- **Complete Tool Lifecycle Coverage**: Hooks handle both success and failure
- **Error Recovery**: Hooks can implement cleanup and recovery logic
- **Audit Trail**: All tool attempts are logged regardless of outcome
- **Backward Compatible**: Existing hooks continue to work (success case unchanged)

#### ⚠️ Considerations:
- **Hook Script Changes**: Scripts must handle both success and failure cases
- **Performance**: Additional hook execution on failures
- **Error Context**: Need to provide meaningful error information to hooks

## Complete Tool Execution Mechanism Analysis

### Tool Execution Flow (Lines 419803-419897)

**Tool execution is a direct function call**, not a spawned process:

```javascript
[source fragment removed]
```

### Error Information Flow

#### Tool Failure Scenarios:

1. **Exception During Execution** (Lines 419864-419895):
   ```javascript
   [source fragment removed]
   ```

2. **Input Validation Failures** (Lines 419660-419780):
   ```javascript
   [source fragment removed]
   ```

### Error Information Availability

**On Tool Failure**, the following information is available:
- **Exception object**: `O` (Error instance or string)
- **Error message**: `O.message` or `String(O)`
- **Tool name**: `A.name`
- **Tool input**: `J` (validated input)
- **Duration**: `Date.now() - D`
- **Tool use ID**: `B`

**On Validation Failure**, the following information is available:
- **Validation result**: `W` object containing:
  - `W.message`: Human-readable error message
  - `W.errorCode`: Tool-specific error code (1-9)
  - `W.meta`: Additional error metadata
- **Tool name**: `A.name`
- **Raw input**: `Q` (unvalidated)
- **Tool use ID**: `B`

### PostToolUse Hook Enhancement Implementation Strategy

Based on the complete execution analysis, here's the optimal approach:

#### Implementation Plan

**Option A: Finally Block Approach (Recommended)**
```javascript
[source fragment removed]
```

**Enhanced pNA Function Signature**:
```javascript
[source fragment removed]
```

#### Enhanced PostToolUse Hook Schema
```json
{
  "session_id": "abc123",
  "hook_event_name": "PostToolUse",
  "tool_name": "Read",
  "tool_input": {"file_path": "/nonexistent.txt"},
  "tool_response": null,  // null for failures, result data for success
  "tool_execution": {
    "success": false,
    "error": "File does not exist.",
    "error_type": "InputValidationError",
    "duration_ms": 156
  }
}
```

### Next Steps for Implementation

1. **Modify XZ5 function** (Lines 419803-419948):
   - Add execution state tracking
   - Move PostToolUse to finally block
   - Capture error information in catch block

2. **Enhance pNA function** (Line 363574):
   - Accept additional execution context parameter
   - Include `tool_execution` in hook input schema

3. **Update hook input construction** (Lines 363576-363582):
   - Add conditional `tool_execution` object
   - Maintain backward compatibility

4. **Test comprehensive scenarios**:
   - Tool success (existing behavior)
   - Tool execution failures (new)
   - Input validation failures (new)
   - Hook cancellation scenarios

This implementation provides complete tool lifecycle coverage while maintaining backward compatibility and providing rich error context to PostToolUse hooks.

## Built-In Tool Error Handling Patterns

### Process-Based Tools (Bash, Grep/Search)

**Pattern**: These tools spawn external processes and use structured error capture via `cN` (ShellError) class.

#### Bash Tool Implementation (Lines 384953-384997)
```javascript
[source fragment removed]
```

**Error Information Captured:**
- `H.stdout`: Command output
- `H.stderr`: Error messages from external process
- `H.code`: Process exit code
- `H.interrupted`: Process termination status

#### Grep/Search Tool Implementation
**Configuration** (Lines 348249-348269): Uses ripgrep (`rg`) binary
```javascript
[source fragment removed]
```

**Process Execution** (Lines 40911, 40916): Uses same spawn infrastructure as Bash tool
```javascript
[source fragment removed]
```

**Error Handling**: Should follow same `cN` (ShellError) pattern as Bash tool.

### File-Based Tools (Read, Edit, Write)

**Pattern**: These tools perform direct file system operations and only have validation errors, no process execution.

**Key Difference**: These tools **do not throw errors** during execution - they only return validation failure objects during `validateInput()` phase.

From TOOLS_ANALYSIS.md documentation:
- **Read Tool**: File existence, permissions, binary detection (Lines 382353-382399)
- **Edit Tool**: File state tracking, string matching (Lines 393309-393416)
- **Write Tool**: File modification detection (Lines 393972-393998)

### MCP Tools

**Pattern**: Should follow the **process-based tool pattern** when spawning external commands.

**Recommendation for MCP jq tool:**
```javascript
[source fragment removed]
```

## Custom Error Classes in Claude Code

### ShellError (`cN` class) - Lines 341631-341644
```javascript
[source fragment removed]
```

**Purpose**: Captures complete process execution context that Node.js child_process doesn't provide in a single object.

### AbortError (`XV` class) - Lines 341615-341620
```javascript
[source fragment removed]
```

**Purpose**: User cancellation/abortion errors.

## Error Information Flow Analysis

### Current Error Processing (Lines 419864-419895)
```javascript
[source fragment removed]
```

**Problem**: Only captures `O.message`, **loses rich ShellError context** (stdout, stderr, exit codes).

### Error Message Formatting (`SM0` function) - Lines 419963-419983
```javascript
[source fragment removed]
```

**Safety**: Error messages are automatically size-limited to ≤10KB with intelligent truncation.

## Enhanced PostToolUse Implementation Strategy

### Proposed Implementation Enhancement

#### Error Capture with tool_execution Property
```javascript
[source fragment removed]
```

#### Enhanced pNA Function (Line 363574)
```javascript
[source fragment removed]
```

### Enhanced PostToolUse Hook Schema

**Success Case:**
```json
{
  "session_id": "abc123",
  "hook_event_name": "PostToolUse",
  "tool_name": "jq_tool",
  "tool_input": {"filter": ".name", "data": "{\"name\":\"John\"}"},
  "tool_response": {
    "type": "json",
    "result": "John"
  },
  "tool_execution": {
    "success": true,
    "duration_ms": 145
  }
}
```

**Failure Case:**
```json
{
  "session_id": "abc123",
  "hook_event_name": "PostToolUse",
  "tool_name": "jq_tool",
  "tool_input": {"filter": ".foo", "data": "invalid json"},
  "tool_response": null,
  "tool_execution": {
    "success": false,
    "duration_ms": 234,
    "error_message": "Shell command failed: jq parse error...",
    "error_type": "ShellError",
    "details": {
      "stdout": "",
      "stderr": "jq: parse error: Invalid JSON at line 1, column 5",
      "exitCode": 5,
      "interrupted": false
    }
  }
}
```

### Implementation Benefits

1. **✅ Process Error Context**: Captures stdout, stderr, exit codes from all process-based tools
2. **✅ Clean API Semantics**: `tool_response` always contains actual tool output (or null), `tool_execution` contains execution metadata
3. **✅ Consistent Schema**: Same hook structure for success and failure cases
4. **✅ Simple Hook Logic**: `tool_execution.success` boolean enables clean branching
5. **✅ Size Safety**: Leverages existing `SM0()` size limiting (10KB max)
6. **✅ Tool Agnostic**: Works for Bash, Grep, MCP tools, and any future process-based tools
7. **✅ Backward Compatible**: Existing hooks checking `tool_response` continue working unchanged
8. **✅ Type Safe**: Clean separation enables proper TypeScript/schema definitions
9. **✅ Future Extensible**: `tool_execution` can capture additional metadata (profiling, resource usage)
10. **✅ Minimal Changes**: Reuses existing error classes and formatting infrastructure

### Hook Development Patterns

**Simple Success/Failure Handling:**
```javascript
[source fragment removed]
```

**Process-Based Tool Error Handling:**
```javascript
[source fragment removed]
```

This enhancement enables rich error context for PostToolUse hooks while maintaining clean API semantics and full backward compatibility.
