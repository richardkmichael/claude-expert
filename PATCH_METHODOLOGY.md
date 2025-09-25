# Claude Code Hook Enhancement Patch Methodology

## Overview

This document describes the complete process for porting Claude Code hook enhancements to new
versions, despite function name changes from re-minification. The process involves detecting
equivalent functions across versions and creating standalone patches using git staging.

## Problem Statement

When Claude Code releases new versions, the minified code gets re-generated with:
- **Different function names** (e.g., `pNA` → `XMA`, `lNA` → `JMA`, `XZ5` → `VJ5`)
- **Different variable names** (e.g., `yA` → `fA`, `I1` → `Y1`)
- **Different line numbers** (shifts of hundreds to thousands of lines)
- **Same underlying structure** (control flow, string literals, patterns preserved)

## Complete Workflow

### Phase 1: Function Detection and Mapping

#### Step 1: Identify Target Functions by String Literals

Minified code preserves string literals, making them reliable anchors for function identification.

**PreToolUse Function Detection:**
```bash
grep -n "PreToolUse" package.{VERSION}/cli.prettier.js
```
Look for `hook_event_name: "PreToolUse"` - this identifies the PreToolUse hook function.

**PostToolUse Function Detection:**
```bash
grep -n "PostToolUse" package.{VERSION}/cli.prettier.js
```
Look for `hook_event_name: "PostToolUse"` - this identifies the PostToolUse hook function.

**Tool Execution Function Detection:**
```bash
grep -n "tengu_tool_use_success" package.{VERSION}/cli.prettier.js
```
This telemetry call is unique to the tool execution function's success path.

#### Step 2: Verify Function Structure

Use code intelligence tools to extract complete function definitions and verify structural equivalence:

```bash
# Using code-intel tools (if available)
mcp__code-intel__get_code_context file.js line char context_level
```

#### Step 3: Confirm Function Signatures and Patterns

Verify the functions have expected parameter counts and internal patterns:

**PreToolUse Function:**
- **Parameters**: 6 parameters `(A, B, Q, Z, G, Y)`
- **Key patterns**:
  - `hook_event_name: "PreToolUse"`
  - `executePreToolHooks called for tool:` debug message
  - Simple hook execution wrapper

**PostToolUse Function:**
- **Parameters**: 7 parameters `(A, B, Q, Z, G, Y, I)`
- **Key patterns**:
  - `hook_event_name: "PostToolUse"`
  - `tool_response: Z`
  - Generator function with progress handling

**Tool Execution Function:**
- **Parameters**: 6 parameters `(A, B, Q, Z, G, Y)`
- **Key patterns**:
  - Schema validation: `A.inputSchema.safeParse(Q)`
  - Input validation: `A.validateInput?.(I.data, Z)`
  - Telemetry: `tengu_tool_use_success` and `tengu_tool_use_error`
  - Error handling: `instanceof cN` (ShellError checks)

#### Step 4: Map Function Call Sites

Find where the target functions are called:

```bash
# Find PreToolUse function calls
grep -n "{PRETOOLUSE_FUNC}(" package.{VERSION}/cli.prettier.js

# Find PostToolUse function calls
grep -n "{POSTTOOLUSE_FUNC}(" package.{VERSION}/cli.prettier.js
```

#### Step 5: Document Function Mappings

Create a mapping table for reference:

| Enhancement | v113 Function | v120 Function | v113 Line | v120 Line | Line Drift |
|-------------|---------------|---------------|-----------|-----------|------------|
| PreToolUse  | `lNA` | `JMA` | 363570 | 364094 | +524 |
| PostToolUse | `pNA` | `XMA` | 363575 | 364104 | +529 |
| Tool Execution | `XZ5` | `VJ5` | 419638 | 422123 | +2,485 |

### Phase 2: Incremental Patch Creation

**CRITICAL**: Use git's staging area to create standalone, non-cumulative patches.

#### The Problem
Traditional patch creation results in cumulative patches where the second patch includes all changes
from the first patch, making patches interdependent.

#### The Solution: Git Staging Strategy

Use git's three-tree architecture (working tree, staging area, HEAD) to create truly incremental patches:

```bash
# Step 1: Stage original file
git add package.{VERSION}/cli.prettier.js

# Step 2: Apply ONLY PreToolUse changes
# - Modify PreToolUse function signature to accept validationContext
# - Move validation logic after PreToolUse hook in tool execution function
# - Create and pass validationContext to PreToolUse hook calls

# Step 3: Create first standalone patch
git diff package.{VERSION}/cli.prettier.js > patches/001-hook_pretooluse_tool_validation.{VERSION}.patch

# Step 4: Stage PreToolUse changes (preparing for next incremental diff)
git add package.{VERSION}/cli.prettier.js

# Step 5: Apply ONLY PostToolUse changes
# - Modify PostToolUse function signature to accept executionContext
# - Initialize and update executionContext during tool execution
# - Remove early returns from error handling
# - Pass executionContext to PostToolUse hook calls
# - Add success check at function end

# Step 6: Create second standalone patch
git diff package.{VERSION}/cli.prettier.js > patches/002-hook_posttooluse_tool_execution.{VERSION}.patch
```

#### Why This Works
- **git diff** compares working tree against staging area
- After staging PreToolUse changes, the second diff only shows PostToolUse changes
- Each patch is standalone and can be applied independently
- No dependency between patches

### Phase 3: Verification

#### Patch Verification
Confirm patches are standalone by checking:
- First patch contains only PreToolUse modifications
- Second patch contains only PostToolUse modifications
- Neither patch includes changes from the other

#### Function Verification
Before applying patches, verify:
- [ ] Functions have correct parameter counts
- [ ] String literals match expected patterns
- [ ] Function call sites identified
- [ ] No syntax errors in target functions
- [ ] Functions contain expected internal logic patterns

## Alternative Detection Methods

If string literal search fails, try these approaches:

### Method 1: Error Handling Pattern Search
```bash
grep -n "Shell command failed" package.{VERSION}/cli.prettier.js
grep -n "instanceof.*cN" package.{VERSION}/cli.prettier.js
```

### Method 2: Telemetry Pattern Search
```bash
grep -n "tengu_tool_use_error" package.{VERSION}/cli.prettier.js
grep -n "tengu_pre_tool_hook" package.{VERSION}/cli.prettier.js
```

## Success Criteria

### Function Detection Success
1. **String literals found** in expected locations
2. **Function signatures match** parameter patterns
3. **Internal structure verified** with key patterns present
4. **Call sites located** for modification planning
5. **Line number drift calculated** for patch coordinate adjustment

### Patch Creation Success
1. **Two standalone patches created** - each patch is independently applicable
2. **Git staging workflow completed** - incremental diffs generated correctly
3. **Functional equivalence verified** - changes match v113 functionality
4. **No cumulative dependencies** - second patch doesn't include first patch changes
5. **File naming consistent** - patches follow `{NUMBER}-{DESCRIPTION}.{VERSION}.patch` format

## Common Pitfalls

### Code Detection Pitfalls
- **Don't rely on line numbers alone** - they shift significantly between versions
- **Don't search for function names** - minification changes them unpredictably
- **Don't assume same structure** - verify each function individually
- **Don't skip verification** - similar patterns can exist in different functions

### Git Workflow Pitfalls
- **Never commit large cli.prettier.js files** - use git staging area only for patch creation
- **Don't create patches directly from modified files** - results in cumulative patches
- **Don't skip the staging step between patches** - breaks incremental diff creation
- **Don't work on multiple versions simultaneously** - can lead to patch cross-contamination

## Automation Potential

This process can be automated with a script that:
1. Searches for string literal anchors
2. Extracts function boundaries
3. Verifies structural patterns
4. Generates function mapping tables
5. Validates compatibility before patch application

The manual process documented here provides the foundation for such automation while remaining
reliable for occasional manual application.
