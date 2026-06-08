---
name: compare-library-signatures
description: Compare TypeScript definitions and source code across library versions to identify version-specific API changes and code markers.
---

# Compare Library Signatures

This skill identifies the key differences between library versions by analyzing API signatures (TypeScript definitions) and source code structure. These differences become the basis for locating specific versions in minified code.

## When to Use This Skill

- You have multiple library versions extracted in your work directory
- You need to identify what changed between versions
- You're looking for version-specific markers to search for in minified code
- You want to understand API signatures before pattern matching

## Step 1: Compare TypeScript Definitions

TypeScript definitions (`.d.ts` files) are the **canonical API specification** and show exactly what changed between versions.

```bash
# Compare the same component across versions
diff library-VERSION1-dts/package/build/COMPONENT.d.ts \
     library-VERSION2-dts/package/build/COMPONENT.d.ts

# Example: Compare Ink Box component
diff ink-6.0.0-dts/package/build/components/Box.d.ts \
     ink-6.0.1-dts/package/build/components/Box.d.ts
```

Look for:
- **New parameters** in function/component signatures
- **Removed parameters** or properties
- **New methods** or exported functions
- **Changed return types**
- **New exported types or interfaces**

## Step 2: Examine Source Code Differences

Once you've identified changes in `.d.ts` files, examine the actual implementation:

```bash
# Compare source implementations
diff library-VERSION1-src/package/build/COMPONENT.js \
     library-VERSION2-src/package/build/COMPONENT.js

# Example: Compare Ink Box source
diff ink-6.0.0-src/package/build/components/Box.js \
     ink-6.0.1-src/package/build/components/Box.js
```

**Diff output conventions**:
- Lines starting with `<` are in the first file (VERSION1)
- Lines starting with `>` are in the second file (VERSION2)
- Lines starting with `-` or `+` show specific changes within blocks
- Look for patterns between `---` and `===` boundaries

## Step 3: Identify Version-Specific Markers

After comparing files, classify the differences by category:

### Parameter Changes
```javascript
// v6.0.0
function Box({ children, ...style }) { ... }

// v6.0.1
function Box({ children, backgroundColor, ...style }) { ... }
//                      ^^^^^^^^^^^^^^^^ NEW PARAMETER
```

**Marker**: Look for `backgroundColor` parameter in minified code

### New Methods or Functions
```javascript
// v6.0.0
class Client { }

// v6.0.1
class Client {
  setAuthToken(token) { ... }  // NEW METHOD
}
```

**Marker**: String literal `"setAuthToken"` in minified code

### Code Structure Changes
```javascript
// v6.0.0
finalizeInitialChildren() {
  return false;
}

// v6.0.1
finalizeInitialChildren(A, B, Q, I) {
  if (A.internal_static) {
    I.isStaticDirty = true;  // NEW LOGIC BLOCK
  }
  return false;
}
```

**Marker**: Search for `"internal_static"` or `"isStaticDirty"` strings

### String Literals and Constants
```javascript
// v6.0.0
throw new Error("Invalid option");

// v6.0.1
throw new Error("Invalid option: must be a string");  // Changed message
```

**Marker**: Updated error message string in minified code

## Step 4: Categorize Changes by Type

Create a summary table for reference:

| Category | v6.0.0 | v6.0.1 | Search Marker |
|----------|--------|--------|---------------|
| Parameters | `({ children, ...style }, ref)` | `({ children, backgroundColor, ...style }, ref)` | `backgroundColor` |
| Methods | None | `setAuthToken()` | `"setAuthToken"` |
| Constants | None | `currentRootNode` | `"internal_static"` |
| Strings | Old message | New message | New message text |

## Examples Across Library Types

### UI Component Library (Ink)
```bash
# Compare Box component definitions
diff ink-6.0.0-dts/package/build/components/Box.d.ts \
     ink-6.0.1-dts/package/build/components/Box.d.ts

# Key finding: backgroundColor parameter added in v6.0.1
# Marker: Look for parameter in forwardRef call
```

### HTTP Client (Axios)
```bash
# Compare client API
diff axios-0.26.0-dts/package/index.d.ts \
     axios-0.27.0-dts/package/index.d.ts

# Key finding: getUri() method added
# Marker: String literal "getUri" in minified code
```

### CLI Framework (Commander)
```bash
# Compare command class
diff commander-7.0.0-dts/package/index.d.ts \
     commander-8.0.0-dts/package/index.d.ts

# Key finding: New allowUnknownOption() method
# Marker: String literal "allowUnknownOption" in minified code
```

## Step 5: Prioritize Markers

Not all differences are equally useful for finding code in minified bundles. Prioritize markers that:

### ✓ Good Markers (Easy to Find)
- **String literals** - survive minification unchanged
  - Error messages: `"Invalid option"`
  - Method names: `"setAuthToken"`
  - Component names: `"Box"`, `"Command"`
  - Configuration keys: `"timeout"`, `"retries"`

- **Parameter additions** - visible in function signatures
  - `({ children, backgroundColor, ...style }, ref)`
  - New parameters that are unlikely to be unused

- **Core functionality changes** - not optional features
  - Reconciliation logic changes
  - Core rendering changes
  - Main API modifications

### ✗ Poor Markers (Hard or Unreliable)
- **Internal variable names** - obfuscated in minified code
  - Local variables like `nodeState`, `reconciler`
  - These become `A`, `B`, `xyz` in minified code

- **Implementation refactoring** - same behavior, different code
  - Variable renaming without behavior change
  - Code reorganization without API change
  - Whitespace and comment changes

- **Optional/unused features** - may be tree-shaken away
  - Features not actively used by Claude Code
  - Conditional code paths that aren't executed
  - Example: v6.0.1 BackgroundContext provider (unused if no backgroundColor styling in Claude Code)

- **Comments and documentation** - removed in minification
  - JSDoc comments
  - Inline comments
  - Type comments

## Step 6: Create a Marker Reference Document

For future use, document your findings:

```markdown
## Library Version Markers

### v6.0.0
- Box component: `({ children, ...style }, ref)` - NO backgroundColor parameter
- Reconciler: No currentRootNode tracking
- String: No "internal_static" checks

### v6.0.1
- Box component: `({ children, backgroundColor, ...style }, ref)` - HAS backgroundColor
- Reconciler: currentRootNode variable tracking present
- String: "internal_static" checks in finalizeInitialChildren and prepareUpdate

### Detection Strategy
1. Search minified code for "internal_static" string
2. If found → v6.0.1
3. If not found, examine Box parameter signature
```

## Common Pitfalls

- ❌ Comparing random sections between versions - use the SAME file path
- ❌ Focusing on implementation details that change for refactoring - focus on API surfaces
- ❌ Assuming tree-shaken code is present - test on definitely-used components
- ❌ Not documenting findings - makes it hard to apply patterns later
- ❌ Choosing poor markers that are implementation-specific - stick to public API markers

## Next Steps

With identified markers, proceed to:
1. **search-minified-code** - locate where markers appear in the minified bundle
2. **match-code-patterns** - create ast-grep patterns based on these markers to confirm the version
