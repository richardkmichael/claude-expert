# Claude Code Bash Tool Execution Analysis

## Executive Summary

The Claude Code Bash tool executes commands by:
1. Passing them to a shell (bash/zsh/sh) via `spawn()` with `-c` flag
2. Using environment variable inheritance from `process.env`
3. Special handling for piped commands to prevent stdin blocking issues

## Key Findings

### 1. Command Execution Method

**Location:** `/path/to/claude-code-analysis/2.0.29/package/cli.prettier.js`

**Main execution function:** `TgA()` (line 248885)

```javascript
[source fragment removed]
```

**Key points:**
- Uses `nv8()` which wraps `spawn()` from Node's `child_process` module
- Arguments passed: `["-c", ...(T ? [] : ["-l"]), L]`
  - `-c` flag tells the shell to execute the command string
  - `-l` flag for login shell (conditional)
  - `L` is the full command string to execute

### 2. Pipe Handling

**Location:** Lines 248895-248898

```javascript
[source fragment removed]
```

**Critical Issue - D9Q Function (line 248479-248488):**

```javascript
[source fragment removed]
```

**What this means:**
- For `cmd1 | cmd2 | cmd3`, it becomes: `cmd1 | < /dev/null cmd2 | cmd3`
- This redirects `/dev/null` AFTER the first pipe, breaking the pipeline
- The stdin redirection syntax is incorrect (should be inside the compound command)

### 3. Environment Variable Inheritance

**Location:** Line 248934-248941

```javascript
[source fragment removed]
```

**Critical Finding:**
- All environment variables from `process.env` are inherited
- **No filtering or cleaning of environment variables**
- Parent process environment is fully passed to child
- Piping does NOT affect environment inheritance (it's passed to the shell itself)

### 4. The Actual Shell Invocation

**Location:** Line 248933

```javascript
[source fragment removed]
```

Where:
- `X` = shell executable (bash/zsh/sh)
- `P` = arguments array `["-c", "-l", "COMMAND_STRING"]`
- Command string `L` (built on line 248913) contains ALL pipes and redirections

**Result:**
```bash
bash -c "source snapshot.sh && eval 'user_command_here | pipe2 | pipe3' && pwd -P > /tmp/claude-xxxx-cwd"
```

### 5. The Pipe Redirection Problem

**Lines 248898 and D9Q function show the issue:**

When a piped command is detected:
1. Original: `echo hello | wc -l`
2. Transformed to: `echo hello | < /dev/null wc -l`
3. When passed to bash: `bash -c "echo hello | < /dev/null wc -l"`

**This is syntactically incorrect!**

The correct syntax would be:
- `bash -c "echo hello | wc -l < /dev/null"` (redirect input to wc)
- Or not redirect at all if not needed

### 6. Spawn Implementation Details

**Location:** Lines 34434-34441 (child_process wrapper)

```javascript
[source fragment removed]
```

**Key points:**
- Uses Node.js built-in `child_process.spawn()`
- The `I.options` includes the `env` object with all inherited variables
- Spawning bash with arguments means: `spawn('bash', ['-c', 'COMMAND_STRING'], { env: {...} })`

## Environment Variable Handling Summary

| Aspect | Details |
|--------|---------|
| **Inheritance** | Complete - all `process.env` vars passed |
| **Filtering** | None - no env var cleaning or filtering |
| **Sandbox Impact** | Sandbox applies restrictions, but doesn't filter env vars |
| **Pipe Impact** | Pipes DO NOT affect env var inheritance |
| **Shell Specification** | Bash shell executable location passed explicitly |
| **CWD** | Set separately via `cwd` option, not in env |

## Pipe and Command Execution Flow

```
User command: "echo hello | wc -l"
                      ↓
Detected as piped (E = F9Q(A) returns true)
                      ↓
D9Q() applies transformation:
  "echo hello | wc -l" → "echo hello | < /dev/null wc -l"
                      ↓
Build full command string L:
  source snapshot && eval 'echo hello | < /dev/null wc -l' && pwd -P > /tmp/...
                      ↓
Pass to bash -c:
  bash -c "source snapshot && eval 'echo hello | < /dev/null wc -l' && pwd..."
                      ↓
spawn('bash', ['-c', '...'], { env: {...process.env...} })
                      ↓
Child process executes with INHERITED environment variables
```

## Code References

**File:** `/path/to/claude-code-analysis/2.0.29/package/cli.prettier.js`

| Function | Line | Purpose |
|----------|------|---------|
| `TgA()` | 248885 | Main command execution orchestrator |
| `Vb8()` | 249063 | Generator that yields progress updates |
| `p2.call()` | 249366 | Bash tool's main entry point |
| `C9Q()` | 248459 | Command quoting/escaping |
| `D9Q()` | 248479 | Pipe-specific command transformation |
| `nv8()` | (imported) | Wrapper around `child_process.spawn()` |

## Conclusion

1. **Pipes are handled with a problematic redirection syntax** that gets inserted before the first pipe
2. **Environment variables are NOT filtered** - all parent process env vars pass through to child bash process
3. **Pipe operations do NOT cause env var loss** - the environment is passed to the shell directly via the `env` option
4. **The issue with pipes is syntactic, not environmental** - it's about how `< /dev/null` is placed in the command string
