---
name: search-for-libraries
description: Locate library code and version markers in minified JavaScript bundles using text search and code-aware extraction tools.
---

# Search Minified Code

This skill locates library code within large minified bundles and extracts manageable sections for detailed analysis. It bridges the gap between identifying version markers and pattern matching.

## When to Use This Skill

- You have a large minified JavaScript file (100k+ lines)
- You've identified version-specific markers from comparing source versions
- You need to locate where a library appears in a minified bundle
- You want to extract code sections before running pattern matching

## Challenge: Minified Bundles

Minified code characteristics:
- Variable names are obfuscated (`Box` → `Z0`, `children` → `A`)
- Code structure is preserved but compacted
- String literals survive unchanged
- Comments and whitespace are removed
- Related code may be scattered throughout the file

**Solution**: Use distinctive patterns that survive minification (string literals) combined with code-aware tools.

## Step 1: Search for String Literal Markers

String literals are the most reliable anchors because they survive minification unchanged.

```bash
# Search for library-specific strings
grep -n "string-literal" minified-file.js

# Search for component/class names
grep -n '"component-name"' minified-file.js

# Search for error messages or constants
grep -n '"error-message"' minified-file.js
```

**Examples across library types**:

For **UI Components (Ink)**:
```bash
# Search for component markers
grep -n '"ink-box"' cli.prettier.js
grep -n '"displayName"' cli.prettier.js
grep -n 'forwardRef' cli.prettier.js

# Search for version-specific strings
grep -n '"internal_static"' cli.prettier.js
grep -n '"isStaticDirty"' cli.prettier.js
```

For **HTTP Clients (Axios)**:
```bash
# Search for method markers
grep -n '"get"' minified-file.js
grep -n '"post"' minified-file.js
grep -n '"axios"' minified-file.js

# Search for version-specific methods
grep -n '"getUri"' minified-file.js
```

For **CLI Frameworks (Commander)**:
```bash
# Search for command markers
grep -n '"command"' minified-file.js
grep -n '"option"' minified-file.js

# Search for version-specific features
grep -n '"allowUnknownOption"' minified-file.js
```

**Grep output format**:
```
LINE_NUMBER:surrounding_code_with_match
```

Note multiple matches if they exist - different parts of the library may use the same string.

## Step 2: Extract Code Context

Once you've found a string literal marker, extract the surrounding code for analysis.

### Using sed (line-based)
```bash
# Extract lines around a match (e.g., line 78115 found by grep)
# Extract 50 lines before and after the match
sed -n '78065,78165p' minified-file.js > extracted-section.js
```

### Using code-intel (structure-aware)
```bash
# Use get_code_context for meaningful context extraction
mcp__code-intel__get_code_context(
  file="/path/to/cli.prettier.js",
  line=78115,
  char=0
)
```

**Advantages of code-intel**:
- Returns the meaningful context (full function/component)
- Handles nested structures automatically
- Returns line numbers for easy reference
- More intelligent than fixed line ranges

**Advantages of sed**:
- Simple and predictable
- Good for initial reconnaissance
- Faster on very large files

## Step 3: Examine Extracted Code

Look for patterns that match your identified markers:

```javascript
// Expected pattern for v6.0.0 Box component
ZY1 = EPA.forwardRef(({ children: A, ...B }, Q) => {
  // No backgroundColor parameter
  // ...
})

// Expected pattern for v6.0.1 Box component
ZY1 = EPA.forwardRef(({ children: A, backgroundColor: C, ...B }, Q) => {
  // Has backgroundColor parameter
  // ...
})
```

**Compare against source to verify**:
- Do the parameter counts match?
- Are string literals present where expected?
- Does the code structure align with one version?

## Step 4: Establish Library Boundaries

While extracting, note the start and end lines to understand where the library code begins and ends.

```bash
# Search for distinctive library markers to establish boundaries
grep -n "library-start-marker" minified-file.js
grep -n "library-end-marker" minified-file.js

# Example for Ink: Look for init sequences
grep -n "var.*=.*T(function" minified-file.js | grep -E "61[0-9]{3}|79[0-9]{3}"
```

**Markers for identifying boundaries**:

*Start of library*:
- Module variable declarations: `var dW, WS0, FS0, ...`
- First initialization block for the library
- First string literal from the library

*End of library*:
- Module aggregator that initializes all components
- Final dependency setup
- Transition to next library's code

## Step 5: Extract Multiple Candidate Sections

If `grep` returns multiple matches, extract sections around each:

```bash
# If you get multiple matches:
# LINE1: ... "ink-box" ...
# LINE2: ... "ink-box" ...
# LINE3: ... "ink-box" ...

# Extract around the most promising match (usually the first or where structure looks right)
sed -n 'START1,END1p' minified-file.js > candidate1.js
sed -n 'START2,END2p' minified-file.js > candidate2.js
sed -n 'START3,END3p' minified-file.js > candidate3.js
```

Later, use **match-code-patterns** to test each candidate with ast-grep patterns.

## Step 6: Save Extracted Sections

Organize extracted sections for later pattern testing:

```bash
# Create a directory for extracted sections
mkdir -p extracted-sections

# Save extracted code with descriptive names
cp extracted.js extracted-sections/component-v6.0.0-candidate.js
cp extracted.js extracted-sections/reconciler-minified.js
cp extracted.js extracted-sections/library-init-sequence.js
```

## Tips for Efficient Searching

### Narrowing Down Matches
```bash
# If you get too many matches, add context
grep -n '"component".*"property"' minified-file.js

# If searching for method names, look for function calls
grep -n 'method($' minified-file.js

# Combine multiple grep patterns
grep -n '"ink-' minified-file.js | head -5
```

### Handling Large Files
```bash
# Test on small extracted sections first
grep '"ink-box"' extracted-sections/sample.js

# Don't process entire minified file with grep alone - it works fine actually
# But limit results to most useful lines
grep -n "version-marker" minified-file.js | head -20
```

### Finding Related Code
```bash
# Once you find one location, look for nearby related code
sed -n 'LINE_START,LINE_ENDp' minified-file.js | grep -n "related-marker"

# This helps identify where the library code is concentrated
```

## Common Pitfalls

- ❌ Searching for variable names instead of string literals - names are obfuscated
- ❌ Extracting too-small sections - miss important context
- ❌ Extracting too-large sections - makes pattern matching inefficient
- ❌ Not checking multiple matches - first match might not be the right component
- ❌ Assuming linear code organization - dependencies may reference code far away

## Examples: Finding Code in Real Minified Bundles

### Example 1: Ink Box Component (Claude Code 2.0.37)
```bash
# Search for component marker
grep -n '"ink-box"' /work/2.0.37/package/cli.prettier.js
# Output: 78113:"ink-box"

# Extract surrounding code
sed -n '78050,78200p' /work/2.0.37/package/cli.prettier.js > box-minified.js

# Verify with code-intel
mcp__code-intel__get_code_context(
  file="/work/2.0.37/package/cli.prettier.js",
  line=78115,
  char=20
)
```

### Example 2: Multiple Matches
```bash
# Search returns multiple results
grep -n '"get"' minified-file.js
# 12340: ...axios...get...
# 45000: ...other...get...
# 62100: ...library...get...

# Extract around each
sed -n '12290,12400p' minified-file.js > candidate1.js
sed -n '44950,45100p' minified-file.js > candidate2.js
sed -n '62050,62200p' minified-file.js > candidate3.js

# Later: use match-code-patterns to test each
```

## Next Steps

With extracted code sections:
1. **match-code-patterns** - create and test ast-grep patterns on extracted code
2. Use results to confirm library version definitively
