# Patch 1: PreToolUse Hook Validation Context

## Purpose
Enable PreToolUse hooks to receive validation context information, allowing hooks to react
intelligently to validation failures while preserving the original program's error handling and
control flow.

## Original Code Behavior
In unpatched Claude Code:
1. **Schema validation** → If failed: error reporting → early return (hook never runs)
2. **Input validation** → If failed: error reporting → early return (hook never runs)
3. **PreToolUse hooks** → Only run on valid input
4. **Tool execution** → Only happens after successful validation

This prevented hooks from:
- Measuring validation failure frequency
- Taking corrective actions on invalid input
- Implementing custom validation logic
- Providing user feedback on validation issues

## Patch Implementation

### Key Changes
1. **Remove early returns** from validation blocks (preserve error reporting)
2. **Add validation flags** (`schemaFailed`, `inputFailed`) for new logic only
3. **Create validation context** with detailed validation results
4. **Pass validation context to hooks** via new parameter to the PreToolUse hook execution function
5. **Add flagged return** immediately after hook execution to preserve original control flow

### Critical Design Decisions

**Error Reporting Timing**: Error reporting remains in original location (immediately after
validation) rather than after hooks to ensure reliability if hooks crash.

**Input Validation Safety**: Input validation only runs when schema validation passes, preserving
original safety guarantees and preventing the input validation function from receiving malformed data.

**Hook Message Processing**: If validation failed, hook messages are not processed - hooks run but
their output is ignored, ensuring users only see validation errors (original behavior).

**Minimal Code Changes**: Original validation logic uses original conditions (schema validation
success check, input validation result check) while new logic uses clean flags (`schemaFailed`,
`inputFailed`).

### Validation Context Structure
Hooks receive a `tool_validation` object with complete validation information:

**Schema failure:**
```javascript
{
  schema_validation: { passed: false, error_message: "..." },
  input_validation: { skipped: true, reason: "schema_validation_failed" }
}
```

**Schema passes, input fails:**
```javascript
{
  schema_validation: { passed: true },
  input_validation: { passed: false, error_message: "...", error_code: "..." }
}
```

**Both pass:**
```javascript
{
  schema_validation: { passed: true },
  input_validation: { passed: true }
}
```

### Backward Compatibility Impact
**Breaking Change**: Hooks now may receive invalid input data along with validation context
indicating the input is invalid. Hook authors must check validation status before processing input:

```javascript
if (hookData.tool_validation?.schema_validation?.passed === false) {
  // Handle schema failure - tool_input may be malformed
} else if (hookData.tool_validation?.input_validation?.passed === false) {
  // Handle input validation failure - tool_input is schema-valid but business-invalid
} else {
  // Normal processing - all validation passed
}
```

This breaking change is intentional and necessary for the feature to be useful.

### Function Signature Changes
- PreToolUse hook execution function gains `validationContext` parameter before optional timeout parameter
- Call site passes validation context when calling the PreToolUse hook execution function

## Execution Flow
```
1. Schema validation → Error reporting if failed → Set schemaFailed flag
2. Input validation (only if schema passed) → Error reporting if failed → Set inputFailed flag
3. Create complete validation context with all validation results
4. Run PreToolUse hooks (always, with validation context)
5. if (validation failed) return; ← Preserve original control flow
6. Process hook messages/results (only if validation passed)
7. Continue with permission logic and tool execution (original behavior)
```

This preserves original program behavior exactly while enabling hooks to access validation
information and react appropriately to validation failures.

# Patch 2: PostToolUse Hook Execution Context

## Purpose
Enable PostToolUse hooks to receive detailed execution context information and run even when tool
execution fails, allowing hooks to react intelligently to both successful and failed tool executions
for monitoring, cleanup, and error handling.

## Original Code Behavior
In unpatched Claude Code:
1. **Tool execution succeeds** → PostToolUse hooks run with valid tool response data
2. **Tool execution fails** → Early return → PostToolUse hooks never run

This prevented hooks from:
- Monitoring tool execution failures
- Performing cleanup after errors
- Logging failure metrics and patterns
- Taking corrective actions on tool failures
- Providing user feedback on execution issues

## Patch Implementation

### Key Changes
1. **Add execution context parameter** to PostToolUse hook execution function signature
2. **Create execution context object** tracking success/failure, timing, and error details
3. **Remove early return on tool failure** to allow hooks to run regardless of execution outcome
4. **Pass execution context to hooks** via new parameter to the PostToolUse hook execution function
5. **Set tool response to null on failure** while providing execution context

### Critical Design Decisions

**Hook Execution on Failure**: Unlike original behavior where hooks only ran on success, hooks now
always run and receive execution context indicating what happened. This is intentional to enable
failure monitoring and cleanup.

**Execution Context Structure**: Comprehensive context object provides all information hooks need to
understand execution outcome:
- Success/failure status
- Execution timing (duration_ms)
- Error details with type-specific information
- Start time for correlation

**Tool Response Safety**: When tool execution fails, `tool_response` is set to `null` but execution
context provides complete failure information. Hooks must check execution status before processing
tool response data.

**Early Return Removal**: The critical change is removing the early return after tool execution
failure, allowing PostToolUse hooks to run in all scenarios while providing context about what
occurred.

### Execution Context Structure
Hooks receive a `tool_execution` object with detailed execution information:

**Tool execution succeeds:**
```javascript
{
  success: true,
  duration_ms: 150
}
```

**Tool execution fails (generic error):**
```javascript
{
  success: false,
  duration_ms: 89,
  error_message: "Command failed",
  error_type: "Error",
  details: {
    stack: "Error: Command failed\n    at ..."
  }
}
```

**Tool execution fails (command error):**
```javascript
{
  success: false,
  duration_ms: 234,
  error_message: "Command exited with code 1",
  error_type: "CommandError",
  details: {
    stdout: "...",
    stderr: "Permission denied",
    exitCode: 1,
    interrupted: false
  }
}
```

**Tool execution aborted:**
```javascript
{
  success: false,
  duration_ms: 45,
  error_message: "Operation was aborted",
  error_type: "AbortError",
  details: {
    aborted: true
  }
}
```

### Backward Compatibility Impact
**Breaking Change**: Hooks now may receive `null` tool_response data when tool execution fails,
along with execution context indicating failure. Hook authors must check execution status before
processing tool response:

```javascript
if (hookData.tool_execution?.success === false) {
  // Tool failed - tool_response is null, use execution context for error details
  console.log(`Tool failed: ${hookData.tool_execution.error_message}`);
  // Perform cleanup or error handling
} else {
  // Tool succeeded - tool_response contains actual result
  // Normal processing of successful execution
}
```

This breaking change is intentional and necessary for hooks to be useful in failure scenarios.

### Function Signature Changes
- PostToolUse hook execution function gains `executionContext` parameter
- Call site passes execution context when calling the PostToolUse hook execution function

## Execution Flow
```
1. Tool execution begins (timing starts)
2. Tool execution completes or fails → Create execution context with results/errors
3. Set tool response (valid data on success, null on failure)
4. Run PostToolUse hooks (always, with execution context and tool response)
5. Process hook messages/results (normal hook processing)
6. Function completes
```

The key difference from original behavior is that PostToolUse hooks now run regardless of tool
execution outcome, receiving complete context about what happened. This enables comprehensive
monitoring, error handling, and cleanup capabilities while maintaining all original functionality
for successful executions.
