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

# Patch 3: Piped Command Environment Variable Expansion

## Purpose
Enable piped bash commands to correctly expand environment variables, allowing commands like `echo $CLAUDE_CODE_SESSION_ID | python -c ...` to receive the variable's value rather than empty stdin.

## Original Code Behavior
In unpatched Claude Code:
1. **Non-piped commands** → Environment variables expand correctly (e.g., `echo $VAR`)
2. **Piped commands** → Environment variables are stripped/empty (e.g., `echo $VAR | cat` receives nothing)
3. **Hook environment** → Variables exported in hook files but treated differently in piped vs non-piped

This prevented:
- Passing environment data through piped command chains
- Using hook-exported variables in piped workflows
- Implementing documented bash tool workflows with variables

## Patch Implementation

### Key Changes
1. **Modify F6Q() function signature** to accept `varEnv` parameter for variable preservation
2. **Update SY() call** to pass the varEnv parameter for variable-preserving tokenization
3. **Modify C6Q() token processing** to preserve tokens starting with `$` without escaping
4. **Update cuA() call site** to pass a variable preservation function `(varName) => \`${varName}\``

### Critical Design Decisions

**Function Environment vs. Object Environment**: The fix passes a function `(varName) => \`${varName}\`` to the tokenizer instead of an object mapping. This approach:
- Preserves all variable references universally (not just hook variables)
- Aligns with precedent in Claude Code (other parts use function envs)
- Maintains code readability with clear intent: "preserve variable syntax"
- Avoids dependency on knowing all valid variable names in advance

**Token Prefix Checking in C6Q()**: Individual tokens starting with `$` are preserved without escaping because the tokenizer has already preserved them in their variable reference form. The shell-quote library would normally escape `$` as a metacharacter, but since we're preserving the entire token intact, no escaping is needed.

**Redirection Placement**: The `< /dev/null` stdin redirection remains outside the eval's quoted argument to preserve pipe operator precedence and security properties.

### Code Changes

**F6Q() function (piped commands):**
```javascript
function F6Q(A, varEnv) {
  if (A.includes("`")) return u8([A, "<", "/dev/null"]);
  let B = SY(A, varEnv);  // Pass varEnv to preserve variables
  if (!B.success) return u8([A, "<", "/dev/null"]);
  let Q = B.tokens, I = mm8(Q);
  if (I <= 0) return u8([A, "<", "/dev/null"]);
  let G = [...C6Q(Q, 0, I, varEnv), "< /dev/null", ...C6Q(Q, I, Q.length, varEnv)];
  return u8([G.join(" ")]);
}
```

**C6Q() function (token processing):**
Modified to preserve variable references without escaping:
```javascript
} else {
  G = !0;
  if (Y.startsWith("$")) {
    I.push(Y);  // Preserve variable reference unescaped
  } else {
    I.push(u8([Y]));  // Normal escaping for other tokens
  }
}
```

**cuA() call site (bash command execution):**
```javascript
if (!Y && A.includes("|") && D) E = F6Q(A, (varName) => `${varName}`);
```

### Backward Compatibility Impact
**Fully Transparent**: This patch has no breaking changes to the Claude Code API or user-facing behavior. It fixes previously non-functional behavior:

- Piped commands that previously received empty stdin now receive correctly expanded variables
- Non-piped commands are unaffected
- Hook files continue to work as before
- All existing scripts that worked continue to work; scripts that didn't work (piped variables) now work

No user code needs modification to benefit from this fix.

### Function Signature Changes
- F6Q() function gains optional `varEnv` parameter for variable preservation function
- C6Q() function internal parameters may include varEnv for consistent token handling
- SY() tokenizer call site passes varEnv to enable variable-preserving tokenization
- cuA() call site provides variable preservation function when calling F6Q()

## Limitations and Known Constraints

**Escaped Variables**:

Shell-quote's parser normalizes escape sequences like `\$FOO` to `$FOO` (consistent with bash
behavior), making them indistinguishable from intentional variable references.  Commands like `echo
\$HOME | cat` will expand the variable when literal output was intended. This is a shell-quote
library limitation, not a flaw in this fix.

**Early Return Paths**:

Backtick detection and parse failure paths use simpler quoting (`u8([A, "<", "/dev/null"])`) rather
than tokenization. Combined scenarios (backticks + pipes + variables) may have untested behavior.
Validation against original test suite is recommended.

**Combined Scenarios**:

The following scenarios have **not** been extensively tested:
- Variable assignments with pipes: `FOO=$BAR | cat`
- File descriptor redirections with variables: `echo $VAR 2>&1 | cat`
- Multiple pipes with multiple variables: `echo $VAR1 | grep $VAR2 | cat`
- Backticks combined with pipes and variables

## Execution Flow
```
1. cuA() receives piped bash command with potential variables
2. Call F6Q(A, (varName) => `${varName}`) with variable preservation function
3. F6Q() passes varEnv to SY() tokenizer
4. SY() (shell-quote.parse) receives an env-context function
5. Tokenizer preserves $VARIABLE references as tokens (not interpolated)
6. C6Q() processes tokens, checking prefix:
   - Tokens starting with $: preserved as-is
   - Other tokens: normal shell-quote escaping
7. Tokens rejoined with spaces between command parts and redirection
8. Final command: eval "echo $VAR | python ..." < /dev/null
9. Bash expands $VAR at execution time, preserving pipe semantics
```

This approach enables piped commands to expand variables while maintaining all original security and
pipe handling properties.

# Patch 4: Agent and Skill File Content Interpolation

## Purpose
Allow external agent and skill `.md` files (under `.claude/agents/` and `.claude/skills/`) to
reference a set of named string constants using `${VARIABLE_NAME}` syntax, so that boilerplate
text and dynamic values (model name, attribution strings) can be injected at runtime rather than
hardcoded in every file.

## Original Code Behavior
In unpatched Claude Code, external agent and skill files are loaded verbatim:
1. File read from disk with `readFileSync` as a UTF-8 string
2. YAML frontmatter stripped by `mD()`
3. Body content stored as a plain string and returned from `getSystemPrompt()` unchanged

Any `${...}` tokens in the file reach Claude's context literally — there is no template
evaluation step. Internal (built-in) agents such as Explore and Plan do support `${...}`
interpolation because their system prompts are JavaScript template literals compiled into the
bundle, where module-level constants like `K4` ("Bash") are in scope at evaluation time. External
files have no such JS evaluation context.

## Patch Implementation

### Key Changes
1. Add `interpolateAgentContent(A)` function immediately before `YU7` (the agent directory
   scanner), after the `path` import at line 261136.
2. In `zU7` (plugin agent loader): wrap the returned content `V` with
   `interpolateAgentContent(V)` in both the plain-return and the memory-appended-return paths.
3. In `Lf9` (user/project agent loader): same change on `U`.

### The interpolation function
`interpolateAgentContent` builds a substitution map and applies it with a single
`String.prototype.replace` pass using the regex `/\$\{([A-Z_]+)\}/g`. Only tokens consisting
entirely of uppercase letters and underscores are matched; any other `${...}` patterns pass
through untouched.

The map contains:

| Token | Value source | Notes |
|---|---|---|
| `BASH_TOOL_NAME` | `K4` (module constant) | Always `"Bash"` |
| `GLOB_TOOL_NAME` | `ZY` (module constant) | Always `"Glob"` |
| `GREP_TOOL_NAME` | `z5` (module constant) | Always `"Grep"` |
| `READ_TOOL_NAME` | `Aq` (module constant) | Always `"Read"` |
| `WEBFETCH_TOOL_NAME` | `dH` (module constant) | Always `"WebFetch"` |
| `WRITE_TOOL_NAME` | `l3` (module constant) | Always `"Write"` |
| `EDIT_TOOL_NAME` | `xq` (module constant) | Always `"Edit"` |
| `TASK_TOOL_NAME` | `CK` (module constant) | Always `"Task"` |
| `WEBSEARCH_TOOL_NAME` | `xL` (module constant) | Always `"WebSearch"` |
| `GIT_COMMAND_PARALLEL_NOTE` | Inline template literal | See note below |
| `COMMIT_CO_AUTHORED_BY_CLAUDE_CODE` | `$T1().commit` | Dynamic — includes model name |
| `PR_GENERATED_WITH_CLAUDE_CODE` | `$T1().pr` | Dynamic — includes Claude Code URL |

### Critical Design Decisions

**`COMMIT_CO_AUTHORED_BY_CLAUDE_CODE` / `PR_GENERATED_WITH_CLAUDE_CODE` via `$T1()`**: These
values are not module-level variables — they are local variables inside `$T1()`. Calling `$T1()`
at `getSystemPrompt()` invocation time is the only way to obtain them, and it is the correct
approach: `$T1()` reads current user settings and resolves the active model name, so the
attribution string always reflects the live configuration rather than a value frozen at startup.

**`GIT_COMMAND_PARALLEL_NOTE` text duplication**: This text lives inline inside the `S_q()`
template literal and is never assigned to a module-level variable, so there is no reference to
grab. The patch duplicates the paragraph as a template literal inside `interpolateAgentContent`,
where `${K4}` evaluates to `"Bash"` identically to the original. If Anthropic changes this
paragraph in a future version the two copies will diverge; this is accepted because the text is
stable boilerplate. The alternative — extracting it into a module-level `var` and modifying
`S_q()` to reference it — would widen the patch footprint to a large and central function for
cosmetic benefit.

**Regex scope**: The pattern `[A-Z_]+` intentionally excludes lowercase and mixed-case names.
This means normal template-style usage such as `${someVariable}` or `${tool.name}` in agent file
content is never touched, reducing the risk of unintended substitution.

**Invocation timing**: `interpolateAgentContent` is called inside `getSystemPrompt()`, not at
file-load time. This ensures `$T1()` always has access to fully initialised user settings.

### Function Placement
The new function is inserted between the `import { join, basename } from "path"` statement and
`function YU7(...)` (the agent directory scanner). All three functions it references — `$T1`,
`K4`, `ZY`, etc. — are either hoisted function declarations or `var`-declared module-level
constants, so placement before their textual declaration is safe.

### Backward Compatibility Impact
Fully transparent for existing agent and skill files that contain no `${ALL_CAPS}` tokens — they
pass through the regex unchanged. Files that happen to contain `${ALL_CAPS_TOKEN}` patterns where
the token matches a name in the map will now have those tokens replaced; this is the intended
behaviour and not a concern for existing files in practice.

## Execution Flow
```
1. Agent .md file read from disk → frontmatter stripped → body stored as plain string (V or U)
2. getSystemPrompt() called
3. interpolateAgentContent(V/U) called
   a. $T1() called → commit and pr attribution strings obtained
   b. GIT_COMMAND_PARALLEL_NOTE template literal evaluated (K4 → "Bash")
   c. Substitution map built
   d. Regex pass replaces ${ALL_CAPS_TOKENS} with mapped values; unknowns left as-is
4. Interpolated string returned (optionally with memory content appended via A36())
5. Claude receives the resolved system prompt
```

## Version Notes
First introduced for version 2.1.47. The minified identifiers used in the substitution map
(`K4`, `ZY`, `z5`, `Aq`, `dH`, `l3`, `xq`, `CK`, `xL`, `$T1`) are version-specific and must be
re-identified when recreating this patch for a new version.

# Patch 5: Additional Workspace Directory File Indexing

## Purpose
Make files in additional workspace directories (configured via `additionalDirectories` in
settings) discoverable by the file index and `@`-file completion, so that multi-directory
projects can reference files across all configured directories.

## Original Code Behavior
In unpatched Claude Code:
1. The file index assembler only indexes files in the current working directory (via
   `git ls-files` or ripgrep) and the `.claude/` directory
2. `@`-file completion only searches the cwd file index
3. The `fileSuggestion` command hook receives no information about additional directories
4. Additional directories are used for CLAUDE.md loading but not for file discovery

This prevented:
- Finding files in additional workspace directories via `@`-completion
- Read/Edit tool suggestions from including files in additional directories
- Hook-based file suggestion commands from searching additional directories

## Patch Implementation

### Key Changes
1. Add `getAdditionalDirFiles(abortSignal, respectGitignore, dirPath)` helper function that
   indexes a single additional directory using git ls-files with ripgrep fallback — the same
   strategy used for the main cwd
2. Modify the file index assembler to fetch the additional directories list and include their
   files in the index via parallel `Promise.all` alongside existing cwd and `.claude/` fetches
3. Modify the `@`-completion entry point to pass `additional_dirs` in the hook payload when
   `fileSuggestion` is configured as a command hook
4. Simplify the Rust index error handler (remove verbose logging and telemetry for a
   non-actionable fallback path)

### Critical Design Decisions

Parallel Fetching: Additional directory file lists are fetched in parallel with the cwd and
`.claude/` fetches using `Promise.all` spread, so adding directories does not serialize the
index build.

Result Ordering: Additional directory files are inserted between the cwd files and `.claude/`
files in the merged list (`[...cwd, ...extraDirs.flat(), ...dotClaude]`), keeping `.claude/`
results at the end.

Relative Paths: Files from additional directories are converted to paths relative to the cwd
using `path.relative(cwd, path.join(dir, file))`, matching the format used by the main file
lister.

Git-first with Ripgrep Fallback: The helper mirrors the main file lister's strategy — try
`git ls-files` first (respects `.gitignore` and submodules), fall back to ripgrep if git fails
(non-git directories, git errors).

### Function Signatures

`getAdditionalDirFiles(abortSignal, respectGitignore, dirPath)`:
- `abortSignal` — shared 10s timeout from the file index assembler
- `respectGitignore` — from user/project config, controls ripgrep `--no-ignore-vcs`
- `dirPath` — absolute path to the additional directory

### Backward Compatibility Impact
Fully transparent. When no additional directories are configured, the `additionalDirectories`
list is empty and the spread produces zero extra promises — identical behavior to unpatched
code.

## Version History

| Version | File index assembler | cwd file lister | Helper symbols                   |
|---------|---------------------|-----------------|----------------------------------|
| 2.1.63  | `zeY()`             | `YeY()`         | `Z7`, `eA`, `Lu`, `WJ`, `y1`    |
| 2.1.69  | `Oqz()`             | `$qz()`         | `Y7`, `oA`, `Ky`, `xJ`, `h1`    |

# Patch 6: CLAUDE_SKILL_DIR in Hook Commands

## Purpose
Allow hook commands defined in skill YAML frontmatter to use `${CLAUDE_SKILL_DIR}` for
referencing files relative to the skill directory, matching the behavior already available in
skill prompt body content.

## Original Code Behavior
In unpatched Claude Code (2.1.69):
1. `${CLAUDE_SKILL_DIR}` is substituted in skill `.md` prompt body content (two code paths)
2. `${CLAUDE_PLUGIN_ROOT}` is substituted in hook commands and set as an environment variable
3. The hook execution function `dh1` receives the skill root path as parameter `O` but only
   uses it to set `CLAUDE_PLUGIN_ROOT` — it does not perform `CLAUDE_SKILL_DIR` substitution
   in the command string or set it as an environment variable

This prevented:
- Hook commands from referencing scripts relative to the skill directory
- Using `${CLAUDE_SKILL_DIR}` in hook `command` fields in YAML frontmatter
- Consistent variable naming between prompt content and hook commands

## Patch Implementation

### Key Changes
Two additions to the hook execution function `dh1` (line 538399):
1. Command string substitution: `if (O) X = X.replace(/\$\{CLAUDE_SKILL_DIR\}/g, M(O));`
   immediately after the existing `CLAUDE_PLUGIN_ROOT` substitution
2. Environment variable: `if (O) G.CLAUDE_SKILL_DIR = M(O);` alongside the existing
   `CLAUDE_PLUGIN_ROOT` environment variable assignment

### Critical Design Decisions

Both Mechanisms: The patch adds both command-string substitution and environment variable
export. Command substitution handles `${CLAUDE_SKILL_DIR}` in the YAML `command` field
directly. The environment variable allows child processes and shell expansion (`$CLAUDE_SKILL_DIR`)
to access the value.

Preserves CLAUDE_PLUGIN_ROOT: The existing `CLAUDE_PLUGIN_ROOT` behavior is untouched.
`CLAUDE_SKILL_DIR` is added alongside it, not as a replacement. Both variables point to the
same path (parameter `O`) but the naming is consistent with their respective contexts — plugin
root for backward compatibility, skill dir for the newer skill system.

### Backward Compatibility Impact
Fully transparent. Existing hook commands that do not use `${CLAUDE_SKILL_DIR}` are unaffected.
The new environment variable is additive.

## Version History
First introduced for version 2.1.69. The hook execution function is `dh1` at line 538399.

# Patch 7: Gate Git Tips with DISABLE_GIT_INSTRUCTIONS

## Purpose
Make the "For git commands:" tips section in the Bash tool description respect the
`CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` environment variable, so that disabling git instructions
removes all git-related content from the Bash tool — not just the commit/PR workflow sections.

## Original Code Behavior
In unpatched Claude Code (2.1.69), the `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` env var and
`includeGitInstructions` config setting gate the detailed git workflow sections (committing,
PRs, other operations) via the `vfz()` function. However, a separate set of git tips in the
Bash tool description builder `GNq()` is always included regardless of this setting:

```
"For git commands:",
K,   // Array of git tips: prefer new commits, avoid destructive ops, never skip hooks
```

This meant that even with git instructions disabled, the Bash tool still contained git-specific
behavioral guidance.

## Patch Implementation

### Key Changes
One change in `GNq()` (line 526658): replace the unconditional inclusion of the git tips
heading and array with a conditional spread gated by `vfz()`:

```javascript
// Before:
"For git commands:",
K,

// After:
...(vfz() ? ["For git commands:", K] : []),
```

### Critical Design Decisions

Reuse Existing Gate: The patch reuses the same `vfz()` function that gates the workflow
sections, ensuring a single control point for all git content. `vfz()` checks (in order):
truthy env var → return false (disabled), falsy env var → return true (enabled), fall back to
`config.includeGitInstructions` (default true).

Header and Content Together: The heading text "For git commands:" and the tips array `K` are
gated as a unit, preventing a dangling header when tips are disabled.

### The Gated Tips (variable K)
```javascript
[
  "Prefer to create a new commit rather than amending an existing commit.",
  "Before running destructive operations (e.g., git reset --hard, git push --force, ...)...",
  "Never skip hooks (--no-verify) or bypass signing (--no-gpg-sign, ...)...",
]
```

### Backward Compatibility Impact
Fully transparent. The default behavior of `vfz()` is `true` (git instructions enabled), so
the tips are included by default — identical to unpatched behavior. Only when the user
explicitly sets `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS=1` or `includeGitInstructions: false`
are the tips removed.

## Version History
First introduced for version 2.1.69. The Bash tool description builder is `GNq()`, the gate
function is `vfz()` (line 526454), and the tips variable is `K` (line 526638).

# Patch 4 (updated for 2.1.69): Agent and Skill File Content Interpolation

The original Patch 4 documentation above covers the full design. This section documents
changes specific to the 2.1.69 port.

## Changes from 2.1.47

### Three loader sites instead of two
In 2.1.47 there were two agent loader functions (plugin and user/project file-based). In
2.1.69 there are three:

1. Plugin agent loader (`sJ4`, line 283697) — content variable `f`
2. Settings-based agent loader (`JM4`, line 284639) — content variable `_`, from `Y.prompt`
3. File-based agent loader (`P9Y`, line 284777) — content variable `c`, from frontmatter-stripped `.md`

The settings-based loader is new in 2.1.69 — it handles agents defined in JSON config rather
than `.md` files. The patch wraps all three with `interpolateAgentContent()`.

### Updated GIT_COMMAND_PARALLEL_NOTE text
The parallel command note text changed slightly between versions. The 2.1.69 version matches
the current Bash tool description at line 526633, minus the chaining example which was
shortened.

### Symbol mapping

| Token                               | 2.1.47 | 2.1.69 |
|--------------------------------------|--------|--------|
| Attribution function                 | `$T1`  | `oV6`  |
| `BASH_TOOL_NAME`                     | `K4`   | `a4`   |
| `GLOB_TOOL_NAME`                     | `ZY`   | `gz`   |
| `GREP_TOOL_NAME`                     | `z5`   | `N5`   |
| `READ_TOOL_NAME`                     | `Aq`   | `wq`   |
| `WEBFETCH_TOOL_NAME`                 | `dH`   | `kD`   |
| `WRITE_TOOL_NAME`                    | `l3`   | `R3`   |
| `EDIT_TOOL_NAME`                     | `xq`   | `kq`   |
| `TASK_TOOL_NAME`                     | `CK`   | `JJ6`  |
| `WEBSEARCH_TOOL_NAME`                | `xL`   | `Gk`   |
| Memory append function               | `A36`  | `qY6`  |

# Patch 8: Allow Symlinked Local Settings Writes

## Purpose
Re-enable writes to a symlinked `.claude/settings.local.json`, restoring the pre-2.1.138 behavior for the
local scope only. Supports git-worktree workflows that share one `settings.local.json` across worktrees
via a symlink to a workspace-level file.

## Original Code Behavior
Since 2.1.138 the settings writer refuses to write through a symlinked project or local settings file,
throwing `SymlinkWriteRefusedError: Refusing to write through symlink: <path>`. The throw is swallowed to
an `error`-level log, so the write silently fails — MCP approvals, "always allow" grants, and the startup
migration write are all dropped. Only user settings (`~/.claude/settings.json`) are exempt. Full mechanism
in `analysis/SETTINGS.md` ("Settings writes refuse symlinks").

## Patch Implementation

### Key change
The writer sets `allowSymlink` per scope:

    allowSymlink: H === "userSettings" || T

The patch adds the local scope:

    allowSymlink: H === "userSettings" || H === "localSettings" || T

The writer only consults `checkParentDir` in the `allowSymlink === false` branch, so this also lets a
symlinked `.claude` directory through for local-settings writes.

### Scope: local only
`projectSettings` (`.claude/settings.json`) stays guarded. Project settings are committed/team-shared, so
a symlinked one is the more plausible attack vector; the local file is gitignored and not normally shipped
in a repo. The change is the minimum needed for the worktree workflow.

### Security note
This re-opens a link-following write (CWE-59) for the local settings file: a repo shipping a symlinked
`.claude/settings.local.json` could redirect a settings write outside the tree. Mitigate at the wrapper
level by warning/aborting when a `settings.local.json` already exists that the wrapper did not create.

## Relocation
Anchor on the `Refusing to write through symlink` / `SymlinkWriteRefusedError` string and read up to the
`allowSymlink:` / `checkParentDir:` option pair, or `rg -n 'allowSymlink: '`. The minified `H`/`T` names
churn; the stable anchors are the `allowSymlink:` key and the scope strings `"userSettings"` /
`"localSettings"`.

## Apply (bun-era, not yet worked out)
2.1.168 ships as a bun-compiled native binary (`// @bun @bytecode @bun-cjs`); `cli.prettier.js` is not
runnable standalone. Applying to the running binary means injecting the equivalent edit into the binary's
embedded cli.js (e.g. via `tweakcc`, the tool the prepare step uses to unpack it) and accounting for the
`@bytecode` pragma so the modified JS actually executes. The `.patch` here targets
`work/2.1.168/package/cli.prettier.js` for reference and the `verify/` flow.
