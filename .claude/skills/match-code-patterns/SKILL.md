---
name: match-code-patterns
description: Create and validate ast-grep patterns with metavariables to match version-specific code structures in minified bundles.
---

# Match Code Patterns

This skill uses ast-grep to find code structures by semantic meaning rather than text matching. It's essential for matching minified code where variable names are obfuscated but structure is preserved.

## When to Use This Skill

- You have extracted code sections from minified bundles
- You've identified version-specific markers from source comparison
- You need to confirm which version a minified library is based on code structure
- You want structure-aware pattern matching instead of text search

## Foundational Concepts

### Why ast-grep Instead of Text Search?

Minified code has obfuscated variable names, making text search unreliable:
```javascript
// Source code (readable)
const Box = forwardRef(({ children, ...style }, ref) => { ... })

// Minified code (obfuscated)
ZY1 = EPA.forwardRef(({ children: A, ...B }, Q) => { ... })
//^                          ^       ^  ^  ^
//All these names are obfuscated, but STRUCTURE is preserved
```

ast-grep matches **structure** (Abstract Syntax Tree), not text:
- Ignores variable names: `Box`, `ZY1`, etc. don't matter
- Ignores obfuscation: parameter names `children`, `A`, etc. don't matter
- Matches the meaningful structure: "forwardRef call with destructured object parameter"

### Tree-Sitter and AST Basics

ast-grep uses **Tree-sitter** to convert code into an Abstract Syntax Tree (AST):
- **Concrete Syntax Tree (CST)**: All nodes including keywords, operators, punctuation
- **Abstract Syntax Tree (AST)**: Only semantic nodes (functions, variables, expressions)

Example:
```javascript
function foo() { return 42; }

// CST has nodes for: function, foo, (, ), {, return, 42, ;
// AST has nodes for: function_declaration, identifier, block_statement, return_statement, number
```

ast-grep matches **structure** using **metavariables** - wildcards that capture nodes:
- `$VAR` - matches any single node
- `$$$` - matches zero or more nodes (non-greedy)
- `$$VAR` - matches unnamed nodes (keywords, operators)
- `$_` - matches any node but doesn't capture

**Key principle**: Patterns must be valid, parseable code. They're converted to AST themselves.

## Step 1: Understand Your Target Code

Before writing patterns, examine the extracted minified code:

```javascript
// What does the code structure look like?
ZY1 = EPA.forwardRef(({ children: A, ...B }, Q) => {
  return (
    bY(B.margin, "margin"),
    EPA.default.createElement("ink-box", {...})
  );
});
```

Ask:
- What's the main function/class structure?
- What parameters does it take?
- What string literals appear?
- How does it differ from other versions?

## Step 2: Extract Source Code to Test Against

Use the source versions you prepared earlier:

```bash
# Keep source files handy for testing
ls ink-6.0.0-src/package/build/components/Box.js
ls ink-6.0.1-src/package/build/components/Box.js

# This is where you test patterns BEFORE applying to minified code
```

## Step 3: Create Patterns with Metavariables

Patterns use metavariables instead of literal names to match obfuscated code.

### Bad Pattern (Won't Work on Minified Code)
```javascript
const Box = forwardRef(({ children, ...style }, ref) => {
  // Problem: "Box", "children", "style" are all obfuscated in minified code
  // Pattern would never match because variable names changed
})
```

### Good Pattern (Works on Minified Code)
```javascript
const $BOXNAME = forwardRef(({ children, ...$REST }, ref) => {
  // $BOXNAME matches any variable name (could be "Box" or "ZY1")
  // children matches the literal identifier "children" (survives minification)
  // ...$REST matches any spread operator with any parameter
  // ref matches the reference parameter
})
```

**Pattern Syntax Rules**:

1. **Patterns must be valid code**
   ```javascript
   // Valid: looks like real JavaScript
   $_ = forwardRef(({ children, ...$_ }, $_) => { $$$ })

   // Invalid: incomplete or syntactically wrong
   function $NAME {  // ERROR: no body
   ```

2. **Metavariables are placeholders**
   - `$UPPERCASE` - matches a single node
   - Use same name for "must match identical" constraints
   - Different names for "can be different" positions

3. **Multiple uses of same variable enforce identity**
   ```javascript
   // This pattern: $A + $A
   // Matches: x + x  ✓
   // Doesn't match: x + y  ✗
   // (Both $A must match the same identifier)
   ```

## Step 4: Test Patterns on Source Code First

Always test on unminified source before searching minified code.

```bash
# Test pattern on source code
ast-grep run --pattern 'const $_ = forwardRef(({ children, ...$REST }, $_) => { $$$ })' \
  --lang javascript ink-6.0.0-src/package/build/components/Box.js

# Expected output: Match found at line X
```

### Using --debug-query to Understand Patterns

```bash
# See how ast-grep parses your pattern
ast-grep run --pattern 'const $BOXNAME = forwardRef(({ children, ...$REST }, $REF) => { $$$ })' \
  --lang javascript --debug-query box.js

# Output shows:
# - Pattern AST structure
# - Metavariable locations
# - Any ERROR nodes (invalid syntax)
```

If you see ERROR nodes, fix the pattern syntax before proceeding.

## Step 5: Create Version-Specific Patterns

Once you have a basic pattern working, refine it to distinguish versions.

### Example: UI Component (Ink)

**v6.0.0 Pattern** (no backgroundColor parameter):
```javascript
$_ = forwardRef(({ children, ...$REST }, $_) => {
  return $_.default.createElement("ink-box", $$$)
})
```

**v6.0.1 Pattern** (has backgroundColor parameter):
```javascript
$_ = forwardRef(({ children, $BGCOLOR, ...$REST }, $_) => {
  // Includes backgroundColor parameter
  $$$
})
```

### Example: HTTP Client (Axios)

**v0.26 Pattern** (no getUri method):
```javascript
class $ClientName {
  get($$$) { $$$ }
  post($$$) { $$$ }
  // No getUri
}
```

**v0.27 Pattern** (has getUri method):
```javascript
class $ClientName {
  get($$$) { $$$ }
  post($$$) { $$$ }
  getUri($$$) { $$$ }  // NEW in v0.27
}
```

### Example: CLI Framework (Commander)

**v7 Pattern** (no allowUnknownOption):
```javascript
class $CommandClass {
  option($NAME, $DESC, $$$) { $$$ }
  action($$$) { $$$ }
}
```

**v8 Pattern** (has allowUnknownOption):
```javascript
class $CommandClass {
  option($NAME, $DESC, $$$) { $$$ }
  action($$$) { $$$ }
  allowUnknownOption($$$) { $$$ }  // NEW in v8
}
```

## Step 6: Test Patterns on Extracted Minified Code

Once patterns work on source, test on the extracted minified section:

```bash
# Test on minified extracted code
ast-grep run --pattern '$_ = forwardRef(({ children, ...$REST }, $_) => { $$$ })' \
  --lang javascript extracted-box-minified.js

# Expected output: Match found (if version is correct)
```

### If Pattern Doesn't Match

**Debug steps**:

1. **Check pattern syntax**
   ```bash
   ast-grep run --pattern 'YOUR_PATTERN' --lang javascript --debug-query minified.js
   ```
   Look for ERROR nodes.

2. **Simplify the pattern**
   - Start with just the outer structure
   - Add constraints gradually

   ```javascript
   // Too specific (might not match)
   $_ = forwardRef(({ children, backgroundColor, ...$REST }, $REF) => {
     const boxElement = $_.createElement("ink-box", { ref: $REF, style: {...} });
     if (backgroundColor) { return $_.createElement(...); }
     return boxElement;
   })

   // Simpler version
   $_ = forwardRef(({ children, $_, ...$REST }, $_) => { $$$ })
   ```

3. **Verify the minified code matches the pattern structure**
   - Compare extracted minified code to source
   - Is the structure similar or very different?
   - Did minification change function expression style?

4. **Use signature matching mode**
   ```bash
   ast-grep run --pattern 'PATTERN' --lang javascript \
     --strictness signature extracted-minified.js
   ```
   This ignores text content and matches only structure.

## Step 7: Use Strictness Modes Appropriately

Different strictness levels control how strictly ast-grep matches:

| Mode | Behavior | Use Case |
|------|----------|----------|
| `cst` | Match all nodes exactly | Need exact syntax |
| `smart` (default) | Require pattern nodes, skip unnamed in target | Most flexible |
| `ast` | Skip unnamed nodes in both | Pure structure |
| `signature` | Compare only node types | Best for minified code |

For minified code, try:
```bash
# First try default (smart)
ast-grep run --pattern 'PATTERN' --lang javascript minified.js

# If no matches, try signature mode
ast-grep run --pattern 'PATTERN' --lang javascript \
  --strictness signature minified.js
```

## Workflow Summary

1. **Extract code** from minified bundle
2. **Create basic pattern** with metavariables
3. **Test on source** - verify it matches unminified code
4. **Refine to version-specific** - add distinguishing constraints
5. **Test on minified extracted** - confirm it finds the obfuscated code
6. **Validate finding** - compare against expected structure from source

## Common Patterns Across Libraries

### Function Declaration with Parameters
```javascript
// General form
const $VAR = ($PARAMS) => { $$$ }
const $VAR = function($PARAMS) { $$$ }

// Specific form (React component)
const $VAR = forwardRef(({ $P1, $P2, ...$REST }, $REF) => { $$$ })
```

### Method on Class
```javascript
// Find specific method
class $CLASS {
  $METHOD($$$ARGS) { $$$ }
}

// Find method with specific name literal
class $CLASS {
  $METHOD($$$) { $$$ }
  get($$$) { $$$ }  // Specific method by name
}
```

### Function Calls with String Literals
```javascript
// Match createElement with specific component name
$_.createElement("component-name", $$$)

// Match initialization with specific string
var $_ = require("library-name")

// Match method call
$OBJ.method($STR, $$$)
```

### Conditional Blocks (Version Markers)
```javascript
// Match version-specific logic
if ($VAR.internal_static) {
  $VAR.isStaticDirty = true;
}
```

## Common Pitfalls

- ❌ Writing patterns without testing syntax - leads to ERROR nodes
- ❌ Using literal variable names - they're obfuscated in minified code
- ❌ Testing on entire minified file - extract sections first
- ❌ Forgetting patterns must be valid code - `function $NAME` without body is invalid
- ❌ Assuming exact source-to-minified mapping - code structure may differ
- ❌ Not using string literals in patterns - they're the most reliable anchors
- ❌ Generic patterns matching too much - add distinctive elements to narrow down

## Tips for Success

1. **Always test patterns on source code first**
   - Use `--debug-query` to verify parsing
   - Confirm matches before searching minified code

2. **Include string literals in patterns**
   - They survive minification and narrow down matches
   - Example: `$_.createElement("ink-box", $$$)` is better than `$_.createElement($$$)`

3. **Use metavariables thoughtfully**
   - `$_` for flexibility without capturing
   - `$VAR` for positions that need constraints
   - Same name = must match identical nodes

4. **Start simple, then refine**
   - Begin with broad pattern matching structure
   - Add version-specific distinguishing constraints
   - Test at each step

5. **Extract and test on small sections**
   - Don't run ast-grep on entire 444k line files
   - Extract target section first
   - Test on extracted code

## References

- **ast-grep CLI Reference**: https://ast-grep.github.io/reference/cli.md
- **Pattern Syntax Guide**: https://ast-grep.github.io/guide/pattern-syntax.md
- **Core Concepts**: https://ast-grep.github.io/advanced/core-concepts.md
- **How ast-grep Works**: https://ast-grep.github.io/advanced/how-ast-grep-works.md
- **Pattern Parsing**: https://ast-grep.github.io/advanced/pattern-parse.md
- **Match Algorithm**: https://ast-grep.github.io/advanced/match-algorithm.md

## Next Steps

After confirming patterns match:
- Use the results to definitively identify library version
- Document findings with line numbers and pattern evidence
- Proceed to other top-level libraries in the bundle
