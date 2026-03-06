# Claude Code Hook Enhancement Patch Methodology

## Overview

This methodology creates new patches for Claude Code versions by understanding the semantic intent of existing patches and recreating equivalent changes in the new version's code structure.

## Core Principle

**NEVER apply old patches to new code.** Always generate patches from scratch by:
1. Understanding the semantic changes from existing patches
2. Locating equivalent code structures in the new version
3. Recreating the same semantic changes using new identifiers

## Problem Statement

Between Claude Code versions, minified code changes completely:
- **Different function names** (e.g., `pNA` → `XMA`, `lNA` → `JMA`, `XZ5` → `VJ5`)
- **Different variable names** (e.g., `yA` → `fA`, `I1` → `Y1`)
- **Different line numbers** (shifts of hundreds to thousands of lines)
- **Same underlying structure** (control flow, string literals, patterns preserved)

Old patches cannot be applied - they must be recreated from scratch for each version.

## Requirements

If the MCP code-intel tools are unavailable, STOP IMMEDIATELY and inform the user the tools are missing.

## Complete Workflow

### Phase 1: Understand Existing Patches

#### Step 1: Read Existing Patches

Examine patches from the most recent previous version to understand the semantic changes made.

**Essential**: Read the comprehensive semantic documentation in `patches/README.md` which contains:
- Detailed purpose and intent of each patch
- Original code behavior vs. patched behavior
- Critical design decisions and trade-offs
- Validation context structure and execution flow
- Backward compatibility considerations

This documentation provides the semantic understanding needed to recreate equivalent functionality in new versions, beyond what the patches themselves show.

#### Step 2: Extract Key Context (Optional)

If existing patches lack sufficient context to understand the changes, examine them in their original context:

1. Download the previous version that the patches target
2. Apply the patches to that version to see the complete before/after changes
3. Use code-intel tools to examine the surrounding context

This provides the semantic understanding needed to recreate equivalent changes in the new version.

### Phase 2: Locate Equivalent Code in New Version

#### Step 1: Search for Persistent String Literals

Find equivalent functions in the new version using string literals that persist across versions:

**PreToolUse Function:**
```bash
grep -n "PreToolUse" {VERSION}/package/cli.prettier.js
```
Look for `hook_event_name: "PreToolUse"`

**PostToolUse Function:**
```bash
grep -n "PostToolUse" {VERSION}/package/cli.prettier.js
```
Look for `hook_event_name: "PostToolUse"`

**Tool Execution Function:**
```bash
grep -n "tengu_tool_use_success" {VERSION}/package/cli.prettier.js
```
This telemetry call identifies the tool execution function.

#### Step 2: Verify Function Structure Using Code Intelligence

Use code intelligence tools to extract complete function definitions and verify they match the expected patterns:

```bash
mcp__code-intel__get_code_context {VERSION}/package/cli.prettier.js line char context_level
```

#### Step 3: Confirm Semantic Equivalence

Verify the functions match expected patterns from the existing patches:

**PreToolUse Function Expected Patterns:**
- `hook_event_name: "PreToolUse"`
- `executePreToolHooks called for tool:` debug message
- Simple hook execution wrapper

**PostToolUse Function Expected Patterns:**
- `hook_event_name: "PostToolUse"`
- `tool_response: Z` or similar response handling
- Generator function with progress handling

**Tool Execution Function Expected Patterns:**
- Schema validation patterns
- Input validation calls
- Telemetry calls: `tengu_tool_use_success` and `tengu_tool_use_error`
- Error handling for shell commands

#### Step 4: Map Function Call Sites

Find where the target functions are called to understand where modifications need to be made.

### Phase 3: Recreate Semantic Changes

Using the understanding from Phase 1 and the function locations from Phase 2, recreate the same semantic changes in the new version using the new identifiers.

#### Git Staging Strategy for Standalone Patches

Create independent, non-cumulative patches using git's staging area:

```bash
# Step 1: Stage original file
git add --force {VERSION}/package/cli.prettier.js

# Step 2: Apply ONLY the first semantic change
# (Based on understanding from existing patches - e.g., PreToolUse modifications)
# - Modify function signatures as needed
# - Add new functionality
# - Update call sites

# Step 3: Create first standalone patch
git diff {VERSION}/package/cli.prettier.js > patches/{VERSION}/001-[same-name-as-existing-patch].patch

# Step 4: Stage the first changes (preparing for next incremental diff)
git add {VERSION}/package/cli.prettier.js

# Step 5: Apply ONLY the second semantic change
# (Based on understanding from existing patches - e.g., PostToolUse modifications)

# Step 6: Create second standalone patch
git diff {VERSION}/package/cli.prettier.js > patches/{VERSION}/002-[same-name-as-existing-patch].patch
```

#### Key Principles

- **Recreate semantic intent**, not literal text from old patches
- **Use new version's identifiers** (function names, variables) throughout
- **Maintain same functionality** as existing patches but adapted to new code structure
- **Create standalone patches** - each can be applied independently

### Phase 4: Verification

#### Patch Verification
Confirm each patch:
- Contains only the intended semantic changes
- Uses correct identifiers for the new version
- Is standalone and independently applicable
- Maintains functional equivalence to existing patches

#### Function Verification
Before finalizing, verify:
- [ ] Functions have expected structural patterns
- [ ] String literals match expected patterns
- [ ] Function call sites properly updated
- [ ] No syntax errors introduced
- [ ] Semantic changes match existing patch intent

#### Post-verification Cleanup

Remove the working file from git staging area:
```bash
git restore --staged {VERSION}/package/cli.prettier.js
```

## Fallback Detection Methods

If primary string literal search fails:

### Method 1: Error Handling Patterns
```bash
grep -n "Shell command failed" {VERSION}/package/cli.prettier.js
grep -n "instanceof.*cN" {VERSION}/package/cli.prettier.js
```

### Method 2: Telemetry Patterns
```bash
grep -n "tengu_tool_use_error" {VERSION}/package/cli.prettier.js
grep -n "tengu_pre_tool_hook" {VERSION}/package/cli.prettier.js
```

## Success Criteria

### Semantic Understanding Success
1. **Existing patches analyzed** and semantic intent understood
2. **Key patterns identified** for locating equivalent code
3. **Context extracted** when needed using previous version analysis
4. **Function equivalents located** in new version using persistent identifiers

### Patch Creation Success
1. **Standalone patches created** - each independently applicable
2. **Semantic equivalence maintained** - same functionality as existing patches
3. **New identifiers used** - no old function names or variables remain
4. **Git staging workflow completed** - incremental diffs generated correctly
5. **File naming consistent** - patches follow `{NUMBER}-{DESCRIPTION}.patch` format

## Common Pitfalls

### Understanding Pitfalls
- **Don't copy literal text** from existing patches - understand the semantic intent
- **Don't skip context analysis** when patches are unclear
- **Don't assume patterns match exactly** - verify each function individually

### Implementation Pitfalls
- **Don't use old identifiers** - always use new version's function/variable names
- **Don't rely on line numbers** - they shift significantly between versions
- **Don't skip verification** - ensure semantic equivalence is maintained

### Git Workflow Pitfalls
- **Never commit cli.prettier.js files** - use git staging area only for patch creation
- **Don't create cumulative patches** - use staging area between modifications
- **Don't skip cleanup** - remove staged files after patch creation
