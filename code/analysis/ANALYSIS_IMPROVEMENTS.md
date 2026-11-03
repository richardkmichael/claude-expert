---
verified: 2.1.76
section: Methodology (not findings)
style: methodology
scope: ast-grep structural search techniques
---
# Claude Code Analysis Improvements with ast-grep

## Overview

`ast-grep` is a structural code search tool that works on Abstract Syntax Trees (ASTs) rather than text patterns. This makes it ideal for analyzing minified JavaScript code like Claude Code's `cli.prettier.js`.

Key advantages for minified code:
- Works on syntax structure, not formatting or whitespace
- Finds patterns regardless of variable names
- Can match nested structures precisely
- Much faster than manual grepping for complex patterns
- Resilient to code reorganization and minification

## Installation

```bash
# Via npm
npm install -g @ast-grep/cli

# Via homebrew (macOS)
brew install ast-grep

# Via cargo (Rust)
cargo install ast-grep
```

## Basic Usage

```bash
# Search with pattern
ast-grep --pattern 'PATTERN' file.js

# Interactive mode
ast-grep --pattern 'PATTERN' --interactive file.js

# JSON output for programmatic use
ast-grep --pattern 'PATTERN' --json file.js
```

## Pattern Syntax Quick Reference

### Meta Variables

- `$VAR` - Matches a single AST node (variable, expression, etc.)
- `$$$` - Matches zero or more AST nodes
- `$$VAR` - Matches a statement or multiple statements

Meta variable naming:
- Must start with `$`
- Followed by uppercase letters (A-Z), underscore (_), or digits (1-9)
- Examples: `$META`, `$META_VAR`, `$_123`

### Wildcards

- `$$$` captures any number of arguments, parameters, statements, etc.
- Works in function calls, object properties, array elements

## Patterns for Claude Code Analysis

### 1. Find All Tool Objects

Goal: Discover all tool definitions regardless of minified names

```bash
ast-grep --pattern '{
  name: $NAME,
  $$$,
  inputSchema: $SCHEMA,
  $$$,
  async *call($$$) { $$$ }
}' cli.prettier.js
```

What this finds:
- Objects with `name:` property
- Has `inputSchema:` property
- Has `async *call()` method
- Captures tool name in `$NAME`
- Captures schema in `$SCHEMA`

Why it works on minified code:
- AST-based matching ignores formatting
- Finds structure regardless of property order ($$$ allows any properties between)
- Works with minified variable names

### 2. Find All Async Generator Functions

Goal: Locate subagent executors, API wrappers, main loops

```bash
ast-grep --pattern 'async function* $FUNC($$$) { $$$ }' cli.prettier.js
```

What this finds:
- All async generator function declarations
- Captures function name in `$FUNC`

Enhanced pattern to find function expressions:

```bash
# Find async generator assigned to variables
ast-grep --pattern '$VAR = async function*($$$) { $$$ }' cli.prettier.js
```

### 3. Find Tool Name String Constants

Goal: Discover all tool name assignments

```bash
ast-grep --pattern 'var $VAR = "$NAME"' cli.prettier.js
```

What this finds:
- Variable declarations with string values

Filter for TitleCase names (post-processing):

```bash
ast-grep --pattern 'var $VAR = "$NAME"' cli.prettier.js | grep -E '"[A-Z][a-z]+'
```

### 4. Find API Call Sites

Goal: Locate where Anthropic API is called with tools parameter

```bash
ast-grep --pattern '$$.messages.create({
  $$$,
  tools: $TOOLS,
  $$$
})' cli.prettier.js
```

What this finds:
- All `messages.create()` calls
- That include a `tools:` parameter
- Captures the tools value in `$TOOLS`

More specific pattern for system and tools:

```bash
ast-grep --pattern '{
  model: $MODEL,
  messages: $MESSAGES,
  system: $SYSTEM,
  tools: $TOOLS,
  $$$
}' cli.prettier.js
```

### 5. Find Subagent Context Creation

Goal: Locate where subagent tool use context is created

```bash
ast-grep --pattern '{
  $$$,
  isSubAgent: $VALUE,
  $$$
}' cli.prettier.js
```

What this finds:
- Objects with `isSubAgent` property

Find complete toolUseContext objects:

```bash
ast-grep --pattern '{
  $$$,
  toolUseContext: {
    $$$,
    isSubAgent: $VALUE,
    $$$
  },
  $$$
}' cli.prettier.js
```

### 6. Find System Prompt Construction

Goal: Locate where system prompts are built for API calls

```bash
ast-grep --pattern 'systemPrompt: $PROMPT' cli.prettier.js
```

More specific - find prompt array construction:

```bash
ast-grep --pattern '$VAR = [$PROMPT1, ...$REST]' cli.prettier.js
```

### 7. Find Tool Arrays

Goal: Discover where tool arrays are constructed

```bash
ast-grep --pattern 'tools: [$$$]' cli.prettier.js
```

Find specific tool references:

```bash
# Find arrays containing a specific tool variable
ast-grep --pattern '[$$$, $TOOL, $$$]' cli.prettier.js
```

## Version Comparison Workflows

### Compare Tool Definitions Across Versions

```bash
# Extract all tool objects from version 1
ast-grep --pattern '{
  name: $NAME,
  $$$,
  async *call($$$) { $$$ }
}' v1/cli.prettier.js > v1_tools.txt

# Extract all tool objects from version 2
ast-grep --pattern '{
  name: $NAME,
  $$$,
  async *call($$$) { $$$ }
}' v2/cli.prettier.js > v2_tools.txt

# Compare
diff v1_tools.txt v2_tools.txt
```

### Find New Async Functions Between Versions

```bash
# Get function names from v1
ast-grep --pattern 'async function* $FUNC($$$) { $$$ }' v1/cli.prettier.js \
  | grep -oE 'function\* [A-Za-z0-9_]+' | sort > v1_funcs.txt

# Get function names from v2
ast-grep --pattern 'async function* $FUNC($$$) { $$$ }' v2/cli.prettier.js \
  | grep -oE 'function\* [A-Za-z0-9_]+' | sort > v2_funcs.txt

# Find new functions
comm -13 v1_funcs.txt v2_funcs.txt
```

### Find Changed Tool Schemas

```bash
# Extract tool input schemas
ast-grep --pattern '{
  name: $NAME,
  $$$,
  inputSchema: $SCHEMA,
  $$$
}' cli.prettier.js --json | jq '.[] | {name: .name, schema: .inputSchema}'
```

## Advanced Patterns

### Find Tool Objects with Specific Properties

```bash
# Find tools with checkPermissions method
ast-grep --pattern '{
  name: $NAME,
  $$$,
  async checkPermissions($PARAM) { $$$ },
  $$$
}' cli.prettier.js
```

### Find Nested Function Calls

```bash
# Find subagent executor function calls
ast-grep --pattern 'for await (let $VAR of $FUNC({ $$$ }))' cli.prettier.js
```

### Find Object Property Assignments

```bash
# Find where options.tools is assigned
ast-grep --pattern '$VAR.options.tools = $VALUE' cli.prettier.js
```

## Integration with Analysis Workflow

### Step 1: Discover All Tools

```bash
# Find all tool name constants
ast-grep --pattern 'var $VAR = "$NAME"' cli.prettier.js | \
  grep -E '"[A-Z][a-z]+' > tool_names.txt

# Find all tool objects
ast-grep --pattern '{
  name: $NAME,
  $$$,
  inputSchema: $SCHEMA,
  $$$,
  async *call($$$) { $$$ }
}' cli.prettier.js --json > tool_objects.json
```

### Step 2: Map Tool Names to Objects

```bash
# For each tool name found, find its object definition
for tool in $(cat tool_names.txt | grep -oE '"[A-Z][a-z]+"' | tr -d '"'); do
  echo "Tool: $tool"
  ast-grep --pattern "{
    name: $VAR,
    $$$
  }" cli.prettier.js | grep -A 5 "$tool"
done
```

### Step 3: Extract Function Call Chains

```bash
# Find what a subagent executor calls
ast-grep --pattern 'async function* $FUNC($$$) {
  $$$
  yield* $CALLEE($$$)
  $$$
}' cli.prettier.js
```

## JSON Output for Programmatic Analysis

```bash
# Get structured data for all tools
ast-grep --pattern '{
  name: $NAME,
  inputSchema: $SCHEMA,
  async *call($$$) { $$$ }
}' cli.prettier.js --json | jq
```

Process with jq:

```bash
# Extract just tool names
ast-grep --pattern '{ name: $NAME, $$$ }' cli.prettier.js --json | \
  jq -r '.[].name'

# Count tools
ast-grep --pattern '{
  name: $NAME,
  $$$,
  async *call($$$) { $$$ }
}' cli.prettier.js --json | jq 'length'
```

## YAML Rules for Complex Searches

For reusable, complex patterns, create a rule file:

tool-finder.yml:
```yaml
id: find-tools
language: javascript
rule:
  pattern:
    context: '{name: $NAME, $$$, inputSchema: $SCHEMA, $$$, async *call($$$) {$$$}}'
  constraints:
    NAME:
      regex: '^[A-Z]'
```

Usage:
```bash
ast-grep --config tool-finder.yml cli.prettier.js
```

## Troubleshooting

### Pattern Not Matching

1. Use interactive mode to test patterns:
   ```bash
   ast-grep --pattern 'YOUR_PATTERN' --interactive cli.prettier.js
   ```

2. Simplify the pattern - start broad, then narrow:
   ```bash
   # Start with
   ast-grep --pattern '{ name: $NAME }' cli.prettier.js

   # Then add constraints
   ast-grep --pattern '{ name: $NAME, inputSchema: $$$ }' cli.prettier.js
   ```

3. Check AST structure with `--debug-query`:
   ```bash
   ast-grep --pattern 'YOUR_PATTERN' --debug-query cli.prettier.js
   ```

### Performance with Large Files

1. Use specific patterns instead of wildcards when possible
2. Limit search scope with `--heading` or pipe to `head`
3. Use JSON output and process with jq for complex filtering

## Recommended Workflow for Claude Code Analysis

1. Install ast-grep: `brew install ast-grep` or `npm install -g @ast-grep/cli`

2. Find all tool names:
   ```bash
   ast-grep --pattern 'var $VAR = "$NAME"' cli.prettier.js | \
     grep -E '"[A-Z][a-z]+' | \
     sort -u > tool_names.txt
   ```

3. Find all tool objects:
   ```bash
   ast-grep --pattern '{
     name: $NAME,
     $$$,
     async *call($$$) { $$$ }
   }' cli.prettier.js --json > tool_objects.json
   ```

4. Find Task tool and subagent functions:
   ```bash
   # Find Task tool
   ast-grep --pattern '{ name: pI, $$$ }' cli.prettier.js

   # Find all async generator functions
   ast-grep --pattern 'async function* $FUNC($$$) { $$$ }' cli.prettier.js
   ```

5. Find API call sites:
   ```bash
   ast-grep --pattern '$$.messages.create({ $$$, tools: $TOOLS, $$$ })' cli.prettier.js
   ```

6. Compare versions:
   ```bash
   # Run steps 2-5 on both versions, then diff the results
   diff <(ast-grep --pattern '{ name: $NAME, $$$ }' v1/cli.prettier.js) \
        <(ast-grep --pattern '{ name: $NAME, $$$ }' v2/cli.prettier.js)
   ```

## Resources

- Official Documentation: https://ast-grep.github.io/
- Pattern Syntax: https://ast-grep.github.io/guide/pattern-syntax.html
- Rule Configuration: https://ast-grep.github.io/guide/rule-config.html
- Playground (test patterns): https://ast-grep.github.io/playground.html

## Benefits for Claude Code Analysis

1. Faster tool discovery - Single command finds all tools
2. Reliable version comparison - Structural diff, not text diff
3. Find renamed functions - Search by structure, not name
4. Discover new patterns - Identify new tool types automatically
5. Reduce manual grepping - Complex patterns in single command
6. JSON output - Easy integration with analysis scripts
7. Works on minified code - AST-based, not text-based
