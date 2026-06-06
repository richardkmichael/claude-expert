# Tool Validation

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

This document analyzes the validation system used by Claude Code tools, focusing on whether validations are per-tool or generic across all tools, with source line references from `package/cli.prettier.js`.

## Summary

Validation is TOOL-SPECIFIC, not generic. Each tool implements its own `validateInput` function with custom validation logic and error codes. There is no shared validation system.

## Validation Architecture

### Two-Tier Validation System

1. Schema Validation (Generic)
   - Uses Zod schema to validate input structure
   - Handled by tool execution framework in `XZ5` function
   - Validates parameter types, required fields, etc.
   - Fails fast if schema doesn't match

2. Input Validation (Per-Tool)
   - Custom `async validateInput()` function per tool
   - Tool-specific business logic validation
   - Returns `{result: boolean, message?: string, errorCode?: number}`
   - THIS IS WHERE HOOKS GET BLOCKED in original implementation

## Detailed Tool Analysis

### Read Tool Validation

Location: Lines 382353-382399 in `package/cli.prettier.js`

Input Validation (Tool-Specific):
```javascript
[source fragment removed]
```

### Edit Tool Validation

Location: Lines 393309-393416 in `package/cli.prettier.js`

Input Validation (Tool-Specific):
```javascript
[source fragment removed]
```

### Write Tool Validation

Location: Lines 393972-393998 in `package/cli.prettier.js`

Input Validation (Tool-Specific):
```javascript
[source fragment removed]
```

## Error Code Patterns

### Read Tool Error Codes
- `1`: File in ignored directory (Line 382361)
- `2`: File does not exist -- PRIMARY TEST CASE (Line 382370)
- `4`: Binary file not supported (Line 382378)
- `5`: Empty image file (Line 382385)
- `6`: File too large without pagination (Line 382396)

### Edit Tool Error Codes
- `1`: No changes (old_string === new_string) (Line 393319)
- `2`: File in ignored directory (Line 393328)
- `3`: Cannot create - file already exists (Line 393346)
- `4`: File does not exist (when editing) (Line 393358)
- `5`: Jupyter notebook (use NotebookEdit instead) (Line 393365)
- `6`: File not read yet (Line 393375)
- `7`: File modified since read (Line 393384)
- `8`: String to replace not found (Line 393400)
- `9`: Multiple matches without replace_all (Line 393410)

### Write Tool Error Codes
- `1`: File in ignored directory (Line 393979)
- `2`: File not read yet (Line 393989)
- `3`: File modified since read (Line 393996)

## Key Findings

### 1. No Shared Validation Framework
- Each tool implements its own `validateInput` function
- Error codes are tool-specific, not standardized
- Validation logic is entirely custom per tool

### 2. Validation Complexity Varies by Tool
- Read Tool: File system focused (existence, permissions, file type)
- Edit Tool: Most complex (file state, string matching, conflict detection)
- Write Tool: Simplest (mainly file state tracking)

### 3. File State Management
- Edit and Write tools require files to be read first
- They track file modification times to detect external changes
- This creates a dependency chain: Read -> Edit/Write

### 4. Hook Blocking Points
- Validation failures cause immediate returns in `XZ5` function
- Original implementation: hooks never execute on validation failure
- Enhanced implementation: hooks receive validation context first

## Test Cases for Hook Enhancement

### Primary Test Case: Non-existent File (Read Tool)
```bash
Read /tmp/this_file_definitely_does_not_exist.txt
```
Expected Results:
- Before Enhancement: Hook never fires, tool fails with "File does not exist." (Line 382370)
- After Enhancement: Hook fires with validation context:
  ```json
  {
    "tool_validation": {
      "schema_validation": {"passed": true, "error_message": null},
      "input_validation": {
        "passed": false,
        "error_message": "File does not exist.",
        "error_code": 2
      }
    }
  }
  ```

### Secondary Test Cases

Binary File (Read Tool):
```bash
Read /usr/bin/ls
```
- Validation Failure: Error Code 4, binary file not supported (Line 382378)

File in Ignored Directory (Read Tool):
```bash
Read node_modules/some-package/package.json
```
- Validation Failure: Error Code 1, ignored directory (Line 382361)

Edit Tool - File Not Read:
```bash
Edit /some/file.txt old_text new_text
```
- Validation Failure: Error Code 6, file not read yet (Line 393375)

## Hook Enhancement Implementation

Our enhanced PreToolUse hook implementation provides hooks with validation context for all these tool-specific validations, enabling sophisticated hook logic that can handle validation failures intelligently.

Key Changes Made:
- lNA function (Line 363564): Added `validationContext` parameter
- XZ5 function (Line 419689): Create and pass validation context to hooks
- Validation flow: Hooks execute before validation blocking

This analysis confirms that our hook enhancement correctly addresses the core issue: validation failures were blocking hook execution entirely, preventing hooks from making informed decisions about tool usage based on the specific validation failures.

### PostToolUse Hook Enhancement with tool_execution Property

Our PostToolUse hook enhancement uses a separate `tool_execution` property to provide rich error context while maintaining clean API semantics. This approach preserves `tool_response` for actual tool output and adds execution metadata separately.

## Built-In Tool Error Handling Architecture

Based on comprehensive code analysis, Claude Code tools fall into two distinct categories with different error handling patterns:

### Process-Based Tools

These tools spawn external processes and use Claude Code's custom `cN` (ShellError) class for structured error capture.

#### 1. Bash Tool (Lines 384953-384997)
Process Execution Pattern:
```javascript
[source fragment removed]
```

Error Information Available:
- `H.stdout`: Complete command output
- `H.stderr`: Error messages from shell command
- `H.code`: Process exit code (0 = success, non-zero = failure)
- `H.interrupted`: Boolean indicating if process was killed/interrupted

#### 2. Grep/Search Tool (Ripgrep)

Ripgrep binary resolution is documented authoritatively in `FILE_INCLUSION.md`
("Ripgrep Binary Selection", verified against 2.1.165). The memoised resolver returns
`{ mode, command, args, argv0? }` with two modes: `embedded` (the packaged-native default —
re-execs the host process as ripgrep with `args: ["--no-config"]`, `argv0: "rg"`) and `system`
(a real `rg` on PATH, `args: []`, selected when `USE_BUILTIN_RIPGREP` is disabled
(`0`/`false`/`no`/`off`) or the build is not native). The older `--ripgrep` re-exec flag and the
vendored `vendor/ripgrep/{arch}-{platform}/rg` fallback shown in earlier builds are gone as of
2.1.165.

Process Spawning (Lines 40911, 40916):
```javascript
[source fragment removed]
```

Error Handling: Uses same infrastructure as Bash tool, should throw `cN` (ShellError) on ripgrep failures.

Tool Description (Lines 372740-372748):
```javascript
[source fragment removed]
```

#### 3. MCP Tools Pattern
Identification (Line 419871): MCP tools are flagged in telemetry
```javascript
[source fragment removed]
```

Recommended Pattern: MCP tools should follow the same ShellError pattern when spawning processes:
```javascript
[source fragment removed]
```

### File-Based Tools

These tools perform direct file system operations and do not throw errors during execution. They only have validation failures during `validateInput()` phase.

#### Error Pattern Differences:
- Process Tools: Throw `cN` (ShellError) with rich context -> PostToolUse hooks can receive error details
- File Tools: Return validation objects -> No execution errors -> PostToolUse hooks never fire on failures

Current Impact: Only process-based tools can benefit from enhanced PostToolUse error handling.

## ShellError (`cN`) Class Implementation

Location: Lines 341631-341644
```javascript
[source fragment removed]
```

Design Purpose:
- Custom Claude Code implementation (not Node.js built-in)
- Structured error capture - Node.js child_process only provides separate streams and events
- Single object containing complete process execution context
- Hook-friendly - all error information available in one place

## Error Size and Safety Controls

### Error Message Formatting (`SM0` function) - Lines 419963-419983
```javascript
[source fragment removed]
```

Safety Features:
- 10KB limit on error messages
- Intelligent truncation preserves beginning and end of large errors
- Automatic formatting handles different error types
- No memory issues even with massive stderr output

## PostToolUse Hook Enhancement Strategy

### Current Limitation (Lines 419864-419895)
```javascript
[source fragment removed]
```

### Enhanced Error Context Capture with tool_execution Property
```javascript
[source fragment removed]
```

### Enhanced Hook Schema Examples

Successful jq tool:
```json
{
  "tool_response": {
    "type": "json",
    "result": {"name": "John", "age": 30}
  },
  "tool_execution": {
    "success": true,
    "duration_ms": 142
  }
}
```

Failed jq tool:
```json
{
  "tool_response": null,
  "tool_execution": {
    "success": false,
    "duration_ms": 234,
    "error_message": "Shell command failed: parse error: Invalid JSON...",
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

Failed grep tool:
```json
{
  "tool_response": null,
  "tool_execution": {
    "success": false,
    "duration_ms": 89,
    "error_message": "Shell command failed: No such file or directory",
    "error_type": "ShellError",
    "details": {
      "stdout": "",
      "stderr": "rg: /nonexistent/path: No such file or directory",
      "exitCode": 2,
      "interrupted": false
    }
  }
}
```

Failed Read tool (validation error):
```json
{
  "tool_response": null,
  "tool_execution": {
    "success": false,
    "duration_ms": 0,
    "error_message": "File does not exist.",
    "error_type": "InputValidationError",
    "details": {
      "error_code": 2
    }
  }
}
```

Generic JavaScript error:
```json
{
  "tool_response": null,
  "tool_execution": {
    "success": false,
    "duration_ms": 156,
    "error_message": "TypeError: Cannot read property 'foo' of undefined",
    "error_type": "TypeError",
    "details": {
      "stack": "TypeError: Cannot read property 'foo' of undefined\n    at toolFunction..."
    }
  }
}
```

## Implementation Benefits

1. Complete Process Context: Captures all stdout, stderr, exit codes from external commands
2. Tool Agnostic: Works for any tool that uses ShellError pattern (Bash, Grep, MCP tools)
3. Size Safe: Leverages existing 10KB limiting with intelligent truncation
4. Backward Compatible: Existing PostToolUse hooks continue working unchanged
5. Structured Data: Clean separation of core error info and tool-specific details
6. Minimal Implementation: Reuses all existing error handling infrastructure

This enhancement enables PostToolUse hooks to receive rich error context from any process-based tool failure while maintaining all existing safety measures and compatibility.
