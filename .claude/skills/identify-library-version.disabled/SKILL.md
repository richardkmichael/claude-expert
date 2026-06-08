---
name: identify-library-version
description: Systematically determine which version of a bundled library is used in minified code by comparing distinctive patterns from multiple source versions.
---

# Identify Library Version

This skill helps determine the exact version of a library that's bundled in minified JavaScript code. It's essential for analyzing tools like Claude Code that bundle multiple dependencies.

## When to Use This Skill

- You have minified code containing a bundled library
- You need to identify which version of a library is used
- Multiple versions of the library exist and have distinguishable code differences
- You want to establish library boundaries within a minified bundle

## General Process

### 1. Gather Multiple Versions

```bash
# List all available versions
npm show LIBRARY_NAME versions --json

# Download specific versions to a working directory
npm pack --pack-destination work/VERSION/ LIBRARY@VERSION
```

**Key Practice**: Always work in a version-specific directory (e.g., `work/2.0.37/`) to keep investigations organized.

### 2. Compare Source Versions

Extract the same files from multiple versions and compare them:

```bash
# Extract specific files from each version
for version in VERSION1 VERSION2 VERSION3; do
  mkdir -p library-${version}-src
  tar xf library-${version}.tgz -C library-${version}-src package/build/FILENAME
done

# Compare versions
diff library-VERSION1-src/package/build/FILENAME \
     library-VERSION2-src/package/build/FILENAME
```

**Strategy for Choosing Files to Compare**:
1. **Start with TypeScript definitions** (`.d.ts` files if available) - canonical API signatures with clear version differences
2. **Look at entry points** - main export files that typically change between versions
3. **Examine core modules** - the primary implementation file(s) for the library's main functionality
4. **Check for exported APIs** - public functions, classes, or types that would show parameter/signature changes

**Example - Ink (React-based UI library)**:
```bash
# Extract TypeScript definitions (most reliable)
tar xf ink-6.0.0.tgz -C extract ink-6.0.0-dts package/build/components/Box.d.ts
tar xf ink-6.0.1.tgz -C extract ink-6.0.1-dts package/build/components/Box.d.ts

# Compare to see API differences
diff extract/ink-6.0.0-dts/package/build/components/Box.d.ts \
     extract/ink-6.0.1-dts/package/build/components/Box.d.ts
```

**Example - HTTP Client (like Axios)**:
```bash
# Look at main export or configuration
tar xf library-VERSION1.tgz -C extract package/index.d.ts
tar xf library-VERSION2.tgz -C extract package/index.d.ts
diff extract/library-VERSION1/package/index.d.ts \
     extract/library-VERSION2/package/index.d.ts
```

### 3. Identify Version-Specific Markers

After comparing source files, identify patterns that distinguish versions:

**General Categories of Differences**:
- **Function/method signatures**: New parameters, removed parameters, changed parameter names
- **API additions/deletions**: New exported functions, classes, or properties
- **Code structure changes**: New conditionals, state management, optimization patterns
- **Dependency additions**: New imports or module dependencies
- **Configuration changes**: New or modified configuration options
- **String literals**: Changed error messages, new enum values, renamed constants

**How to Identify Markers from Diffs**:
1. Look for lines prefixed with `+` (additions) and `-` (deletions) in diff output
2. Prioritize changes that are:
   - Easy to spot in minified code (string literals, distinctive patterns)
   - Unlikely to be tree-shaken away (core functionality, not optional features)
   - Unambiguous (clearly present in one version, absent in another)
3. Avoid markers that are implementation details (local variable names, internal refactoring)

**Examples of Good Markers**:
- Ink: New parameter `backgroundColor` in Box component signature
- HTTP client: New method `setAuthToken()` on main client class
- CLI framework: New option type or validation rule
- SDK: New configuration property in initialization

**Examples of Poor Markers**:
- Internal variable names (obfuscated anyway in minified code)
- Implementation details (refactored between versions but same external behavior)
- Comments or documentation (removed in minification)
- Unused code paths (tree-shaken in bundling)

### 4. Extract from Minified Code

Locate the library code in the minified bundle using distinctive patterns that survive minification:

**Locate using string literals** (most reliable for minified code):
```bash
# Search for library-specific string literals
grep -n '"library-specific-string"' minified-file.js
grep -n '"displayName".*"ComponentName"' minified-file.js
```

**Locate using code-intel** (for known exported symbols):
```bash
mcp__code-intel__get_code_context(file, line, char)
mcp__code-intel__find_symbol_by_name("symbol_name")
```

Once located, extract a manageable section (200-500 lines around the target):
```bash
sed -n 'START_LINE,END_LINEp' minified-file.js > extracted-section.js
```

**Examples**:
- **Ink (React UI library)**: Search for `"ink-box"` or `"displayName"` assignments to locate Box component
- **HTTP client (Axios)**: Search for `"axios"` or known method names like `"get"`, `"post"`
- **CLI framework (Commander)**: Search for option parsing strings like `"option"`, `"command"`

### 5. Compare with Source Patterns

Use ast-grep to create structural patterns that work with obfuscated minified code:

**Workflow**:
1. Use `--debug-query` to understand the AST structure of source code
2. Create patterns with metavariables that capture structure, not literal variable names
3. Test patterns on source code first to verify they work
4. Only then apply to extracted minified sections

**Pattern Examples by Library Type**:

*UI Component Library (Ink)*:
```bash
# Test pattern on source first
ast-grep run --pattern '$_ = forwardRef(({ $PARAM1, ...$REST }, $REF) => { $$$ })' \
  --lang javascript ink-6.0.0-src/Box.js

# Then search extracted minified section
ast-grep run --pattern '$_ = forwardRef(({ $PARAM1, ...$REST }, $REF) => { $$$ })' \
  --lang javascript extracted-box-minified.js
```

*HTTP Client Library (Axios)*:
```bash
# Look for configuration object handling
ast-grep run --pattern 'const $_ = ($CONFIG) => { $$$ }' \
  --lang javascript axios-src/client.js
```

*CLI Framework (Commander)*:
```bash
# Look for option parsing
ast-grep run --pattern '$_.option($STR1, $STR2, $$$)' \
  --lang javascript commander-src/command.js
```

**Key Pattern Principles**:
- Use `$VAR` for single identifiable nodes that should match the same thing
- Use `$$$` for flexible multi-node matching
- Use `$_` when you need flexibility without capturing constraints
- Include string literals (`$STR1`, `$STR2`) to narrow down matches
- Test with `--debug-query` to verify pattern parses correctly before searching minified code

### 6. Verify with TypeScript Definitions

Always validate findings using `.d.ts` files, which are the canonical API specification:

```bash
# Extract TypeScript definitions from versions
tar xf library-VERSION.tgz -C extract-dir package/build/COMPONENT_PATH.d.ts

# Compare signatures - they show exact API differences
diff extract-dir-VERSION1/package/build/COMPONENT_PATH.d.ts \
     extract-dir-VERSION2/package/build/COMPONENT_PATH.d.ts
```

**Finding the right `.d.ts` file to compare**:
- Start with the main entry point or most commonly used component
- Look for files in `package/build/`, `package/types/`, or at the package root
- Compare the same file across versions to identify signature changes

**Examples**:
- **Ink**: Compare `package/build/components/Box.d.ts` to see parameter additions
- **Axios**: Compare `package/index.d.ts` to see new method signatures
- **Commander**: Compare `package/index.d.ts` to see new command/option properties

## Key Tools and Techniques

### String Literals (Survive Minification)
String literals in code are preserved during minification and serve as reliable markers:
- Component/class names: `"ink-box"`, `"display-name"`, `"component-type"`
- Error messages: `"Invalid option"`, `"Connection refused"`, `"Auth failed"`
- API method names: `"GET"`, `"POST"`, `"addEventListener"`, `"create"`
- Configuration keys: `"timeout"`, `"retries"`, `"apiVersion"`
- Enum values: `"success"`, `"pending"`, `"error"`

### Code-Intel for Extraction
- `find_symbol_by_name`: Find functions/classes
- `get_code_context`: Extract surrounding code context
- `find_references_to_symbol_at`: Find all usages

### AST-Grep for Structural Matching
- Use metavariables (`$VAR`, `$$VAR`) instead of literal names
- Test patterns on source code first with `--debug-query`
- Remember patterns must be valid JavaScript/code
- Use `--strictness signature` for minified code matching

### Common Version Markers

Patterns that reliably distinguish library versions across different library types:

- **Parameter additions/removals**: New function parameters or component props
  - *Example (Ink)*: Box component gains `backgroundColor` parameter in v6.0.1
  - *Example (Axios)*: Request interceptor gains `runWhen` parameter in newer versions

- **New conditional branches** or state management patterns
  - *Example (Ink)*: v6.0.1 adds static optimization checks with `currentRootNode` tracking
  - *Example (Commander)*: Option validation logic added between versions

- **Method additions/removals** to classes or exported objects
  - *Example (Axios)*: New `getUri()` method added in v0.27.0+
  - *Example (CLI frameworks)*: New `action()` or `option()` method overloads

- **Error messages and string constants**
  - *Example*: Changed error message for validation failures
  - *Example*: New enum values or configuration option names

- **Module dependencies** (presence of new imports or initialization code)
  - *Example (Ink)*: v6.0.1 requires additional yoga-layout features
  - *Example (Axios)*: Version adds support for new HTTP methods

## Example: Identifying Ink Version

**Difference found**: v6.0.0 vs v6.0.1

Version signatures:
```javascript
// v6.0.0
const Box = forwardRef(({ children, ...style }, ref) => { ... })

// v6.0.1
const Box = forwardRef(({ children, backgroundColor, ...style }, ref) => { ... })
```

In minified code, look for the parameter pattern:
- `({ children: A, ...B }, Q)` → v6.0.0 (no backgroundColor)
- `({ children: A, backgroundColor: C, ...B }, Q)` → v6.0.1 (has backgroundColor)

Additional confirmation: v6.0.1 adds `currentRootNode` variable tracking in reconciler, v6.0.0 does not.

## What Didn't Work (Lessons Learned)

❌ **Generic patterns without distinctive elements**
- Using `function $NAME { $$$ }` matches thousands of functions
- **Solution**: Include specific constants, string literals, or structure

❌ **Literal variable names in minified code**
- Names like `Box`, `reconciler` are obfuscated
- **Solution**: Use metavariables and focus on structure

❌ **Assuming all library code is contiguous**
- Minification can scatter related code throughout the bundle
- **Solution**: Use dependency analysis or restrict focus to known locations

❌ **Writing patterns without testing syntax**
- Invalid pattern syntax causes ERROR nodes
- **Solution**: Use `--debug-query` to verify pattern parses correctly

❌ **Testing on entire minified files**
- ast-grep on 444k+ line files is inefficient
- **Solution**: Extract target section first, test on extracted code

❌ **Assuming tree-shaken code is present**
- Unused code is removed by bundlers
- **Solution**: Focus on definitely-used code like core components

## Workflow for Identifying Library Versions

1. **Establish baseline**: Find one known component/function location in minified code using distinctive string literals or code-intel
2. **Download versions**: Get 2-3 consecutive versions of the library
3. **Extract source**: Pull relevant files (TypeScript definitions, main entry points, core modules) from each version
4. **Compare APIs**: Use TypeScript definitions first for unambiguous signatures
5. **Identify markers**: Find 1-2 key differences between versions (parameter changes, new methods, structural changes)
6. **Extract minified section**: Use grep or code-intel to locate the code in the minified bundle
7. **Create patterns**: Develop ast-grep patterns with metavariables that test on source first
8. **Verify match**: Apply patterns to minified code to confirm version-specific code matches one version exactly
9. **Document findings**: Record the version, evidence (line numbers, pattern matches), and tool references

## Tools Used

| Tool | Purpose | When to Use |
|------|---------|------------|
| `npm show` | List library versions | Initial discovery |
| `npm pack` | Download library packages | Getting source versions |
| `tar` | Extract from packages | Access source files |
| `diff` | Compare source versions | Finding version differences |
| `grep` | Find string literals | Locating code in minified file |
| `code-intel` | Extract code context | Getting surrounding code |
| `ast-grep` | Structural code matching | Confirming patterns in minified code |

## References

- **Ink Library**: https://github.com/vadimdemedes/ink
- **ast-grep Guide**: https://ast-grep.github.io/guide/pattern-syntax.md
- **Tree-sitter Parsing**: https://tree-sitter.github.io/

## Common Pitfalls to Avoid

- ❌ Assuming minified code has same structure as source
- ❌ Using generic patterns without context
- ❌ Searching entire minified files with ast-grep
- ❌ Writing patterns without testing on source first
- ❌ Using literal variable names in patterns
- ❌ Forgetting that patterns must be valid code
- ❌ Assuming all library code is in one contiguous block
- ❌ Not verifying with canonical sources (TypeScript definitions)

## Tips for Success

1. **Always compare TypeScript definitions first** - they show API changes clearly
2. **Extract target code before pattern matching** - makes analysis fast
3. **Test patterns on source first** - verify syntax and matching before minified code
4. **Use string literals in patterns** - they survive minification
5. **Start simple, then refine** - begin with broad patterns, add constraints
6. **Trust TypeScript definitions** - they're the authoritative API specification
7. **Document your findings** - record version, evidence, and line numbers for future reference
