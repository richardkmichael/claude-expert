# Claude Code Analysis - Hook Functionality

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

## Hook Events

All registered hook event names (from settings schema, line 109032):

| Event               | Schema line | Executor           | Executor line |
| ------------------- | ----------- | ------------------ | ------------- |
| PreToolUse          | 242611      | `Ug8`              | 530008        |
| PostToolUse         | 242631      | `dg8`              | 530031        |
| PostToolUseFailure  | 242642      | `cg8`              | 530049        |
| PermissionRequest   | 242621      | `z_6`              | 530275        |
| Notification        | 242654      | `Iu`               | -             |
| UserPromptSubmit    | 242664      | -                  | -             |
| SessionStart        | 242672      | -                  | -             |
| SessionEnd          | 242837      | -                  | -             |
| Stop                | 242690      | -                  | -             |
| SubagentStart       | 242703      | -                  | -             |
| SubagentStop        | 242712      | -                  | -             |
| PreCompact          | 242728      | -                  | -             |
| Setup               | 242682      | -                  | -             |
| TeammateIdle        | 242737      | -                  | -             |
| TaskCompleted       | 242746      | -                  | -             |
| Elicitation         | 242758      | -                  | -             |
| ElicitationResult   | 242771      | -                  | -             |
| ConfigChange        | 242790      | -                  | -             |
| InstructionsLoaded  | 242801      | -                  | -             |
| WorktreeCreate      | 242814      | -                  | -             |
| WorktreeRemove      | 242822      | -                  | -             |

## Hook Configuration Schema (line 109062)

Four hook types are supported, each defined via `Bz5()`:

### Command Hook (BashCommandHookSchema, line 109063)

```
type:          "command" (required)
command:       string   (required) - Shell command to execute
timeout:       number   (optional) - Timeout in seconds
statusMessage: string   (optional) - Custom spinner message
once:          boolean  (optional) - If true, removed after first execution
async:         boolean  (optional) - If true, runs in background without blocking
asyncRewake:   boolean  (optional) - UNDOCUMENTED, see below
```

### Prompt Hook (PromptHookSchema, line 109087)

```
type:          "prompt" (required)
prompt:        string   (required) - LLM prompt ($ARGUMENTS for hook input JSON)
timeout:       number   (optional) - Timeout in seconds
model:         string   (optional) - Model to use (default: small fast model)
statusMessage: string   (optional) - Custom spinner message
once:          boolean  (optional) - If true, removed after first execution
```

### HTTP Hook (HttpHookSchema, line 109110)

```
type:           "http"   (required)
url:            string   (required) - URL to POST hook input JSON to
timeout:        number   (optional) - Timeout in seconds
headers:        object   (optional) - Additional headers (supports $VAR_NAME interpolation)
allowedEnvVars: string[] (optional) - Env vars allowed for header interpolation
statusMessage:  string   (optional) - Custom spinner message
once:           boolean  (optional) - If true, removed after first execution
```

### Agent Hook (AgentHookSchema, line 109136)

```
type:          "agent"  (required)
prompt:        string   (required) - What to verify ($ARGUMENTS for hook input JSON)
timeout:       number   (optional) - Timeout in seconds (default 60)
model:         string   (optional) - Model to use (default: Haiku)
statusMessage: string   (optional) - Custom spinner message
once:          boolean  (optional) - If true, removed after first execution
```

## Hook Input Schemas

### PreToolUse (line 242611)

```json
{ "hook_event_name": "PreToolUse", "tool_name": "...", "tool_input": {}, "tool_use_id": "..." }
```

Plus base fields: `session_id`, `transcript_path`, `cwd`.

Tool-lifecycle events (PreToolUse, PostToolUse, PostToolUseFailure) also include
`agent_id` and `agent_type` fields identifying which agent triggered the tool call.

### PostToolUse (line 242631)

```json
{ "hook_event_name": "PostToolUse", "tool_name": "...", "tool_input": {}, "tool_response": {} }
```

### PostToolUseFailure (line 242642)

```json
{ "hook_event_name": "PostToolUseFailure", "tool_name": "...", "tool_input": {},
  "tool_use_id": "...", "error": "...", "is_interrupt": false }
```

Fires when tool execution throws an exception. Called from `X4q` (line 439717) in the
catch path. Receives the error string and whether it was a user interrupt.

### PermissionRequest (line 242621)

```json
{ "hook_event_name": "PermissionRequest", "tool_name": "...", "tool_input": {},
  "permission_suggestions": [] }
```

### Notification (line 242654)

```json
{ "hook_event_name": "Notification", "message": "...", "title": "...", "notification_type": "..." }
```

## Hook Output Schema (PreToolUse)

PreToolUse hooks can return JSON on stdout to control permission decisions:

```javascript
[source fragment removed]
```

### PreToolUse Behavior by Exit Code

| Exit code | Behavior                                            |
| --------- | --------------------------------------------------- |
| 0         | stdout/stderr not shown, JSON output parsed         |
| 2         | stderr shown to model and tool call blocked         |
| other     | stderr shown to user only, tool call continues      |

### PostToolUse Behavior by Exit Code

| Exit code | Behavior                                            |
| --------- | --------------------------------------------------- |
| 0         | stdout shown in transcript mode (Ctrl-O)            |
| 2         | stderr shown to model immediately                   |
| other     | stderr shown to user only                           |


## Tool Execution Pipeline

### Overall Flow

```
  1. Schema validation (Zod)
  2. Input validation (tool.validateInput)
  3. PreToolUse hooks (Ug8)
  4. Permission check (v3z -> checkPermissions)
  5. PermissionRequest hooks (z_6) -- if behavior="ask"
  6. Permission UI prompt -- if behavior="ask"
  7. Tool execution (tool.call)
  8. PostToolUse hooks (dg8) -- on success only
  9. PostToolUseFailure hooks (cg8) -- on exception only
```

### Key Functions

| Function | Line   | Role                                              |
| -------- | ------ | ------------------------------------------------- |
| `Ug8`    | 530008 | executePreToolHooks - fires PreToolUse hooks       |
| `v3z`    | 521380 | Core permission check (rules + checkPermissions)   |
| `rJ`     | 521534 | Outer permission wrapper (adds auto-mode logic)    |
| `VfY`    | 379573 | Interactive canUseTool helper                      |
| `z_6`    | 530275 | executePermissionRequestHooks                      |
| `dg8`    | 530031 | executePostToolHooks                               |
| `cg8`    | 530049 | executePostToolUseFailureHooks                     |
| `X4q`    | 439717 | PostToolUseFailure hook executor wrapper            |

### Input Validation Blocks Hooks

PreToolUse hooks only fire if both schema and input validation pass. If `validateInput`
rejects the input (e.g., file doesn't exist for Read), hooks are never called.

```
Schema validation fails  ->  early return, no hooks
Input validation fails   ->  early return, no hooks
Both pass                ->  PreToolUse hooks fire
```


## PermissionRequest Hook Timing

When a tool's `checkPermissions` returns `{ behavior: "ask" }`, the system must decide
between showing the UI prompt and running PermissionRequest hooks.

### Normal (interactive) flow

In the interactive CLI flow (line 588396):

1. The permission prompt entry is pushed to `toolUseConfirmQueue`
   - The UI renders immediately
2. In parallel, an async IIFE starts `runHooks` (line 588526):
   ```javascript
   [source fragment removed]
   ```
3. It's a race: user interaction vs. PermissionRequest hook completion

### awaitAutomatedChecksBeforeDialog

When `toolPermissionContext.awaitAutomatedChecksBeforeDialog` is set (line 588600),
PermissionRequest hooks run before the UI prompt is shown. If hooks resolve it, the
UI never appears.

### requiresUserInteraction

Tools with `requiresUserInteraction() === true` (like ExitPlanMode) always produce
`behavior: "ask"`, bypassing auto-mode classifiers and rule checks (line 521415, 521564).


## Plan-Related Hook Points

### ExitPlanMode Permission Flow

When Claude calls `ExitPlanMode`:

1. PreToolUse hooks fire with `tool_name: "ExitPlanMode"` (via `Ug8`)
2. `checkPermissions` returns `{ behavior: "ask", message: "Exit plan mode?" }` (line 433076)
3. `requiresUserInteraction()` returns `true` (line 433070), so "ask" is preserved
4. The "Ready to code?" UI renders (line 572716) with:
   - Plan content in a dashed-border box
   - Option buttons (approve with various modes, reject with feedback)
   - ctrl-g to edit plan in external editor
5. PermissionRequest hooks run concurrently with the UI (or before, if `awaitAutomatedChecksBeforeDialog`)
6. PostToolUse/PostToolUseFailure hooks fire after user responds

### Plan File Detection in Tool Display Names

When Write, Edit, Bash, or Read target a file in the plans directory (`d2()`), the
tool's `userFacingName` changes:

| Tool  | Normal   | Plan file       | Line        |
| ----- | -------- | --------------- | ----------- |
| Write | "Write"  | "Updated plan"  | 413422      |
| Edit  | "Update" | "Updated plan"  | 514713      |
| Read  | "Read"   | "Reading Plan"  | 238868      |

Detection is a simple path prefix check: `file_path.startsWith(d2())`.

### Plan Directory Resolution (`d2`, line 238715)

1. If `plansDirectory` set in config: use that (relative to project root, must stay within root)
2. Default: `~/.claude/plans/`

### Plan Mode System Messages

The plan system injects attachment types into the conversation:

| Attachment type       | When                                          | Line   |
| --------------------- | --------------------------------------------- | ------ |
| `plan_mode`           | Periodic reminder while plan mode is active   | -      |
| `plan_mode_reentry`   | Re-entering plan mode after previous exit     | 244688 |
| `plan_mode_exit`      | Exiting plan mode                             | 244711 |
| `plan_file_reference` | Plan file exists when entering plan mode      | 278030 |


## Undocumented Hook Features

### `asyncRewake` (Command Hook Property)

Schema definition at line 109081:
```
asyncRewake: boolean (optional)
  "If true, hook runs in background and wakes the model on exit code 2
   (blocking error). Implies async."
```

Present in schema but not in official documentation. Behavior (line 528424):

- Like `async: true`, the hook runs in the background without blocking
- On completion, if exit code is 2, pushes a notification to the model:
  ```javascript
  [source fragment removed]
  ```
- Unlike regular `async` hooks, `asyncRewake` does NOT produce an async hook response
  attachment. Regular `async` hooks use a separate path that calls `background()` and
  registers the process for later polling.

In summary:
- `async: true` — background, result appears as attachment when done
- `asyncRewake: true` — background, only notifies model on exit code 2, no attachment

### `PostToolUseFailure` Hook Event

Not mentioned in official hook documentation. Fires when tool execution
throws an exception (line 439721 in `X4q`).

Input schema:
```json
{
  "hook_event_name": "PostToolUseFailure",
  "tool_name": "Bash",
  "tool_input": { "command": "..." },
  "tool_use_id": "...",
  "error": "Shell command failed",
  "is_interrupt": false
}
```

The tool lifecycle is:
- Tool succeeds: PostToolUse fires
- Tool throws: PostToolUseFailure fires
- Tool never attempted (validation failure): neither fires


## Legacy Notes

The sections below document earlier analysis findings. Line numbers may not be
current. Key architectural findings remain valid.

### Why PreToolUse Hooks Don't Fire for Invalid Inputs

Root Cause: PreToolUse hooks are bypassed entirely when tool input validation fails
before hook execution.

Tool validation pipeline (Read tool example):
```javascript
[source fragment removed]
```

Read tool's `validateInput` checks:
- File in ignored directory -> errorCode 1
- File does not exist -> errorCode 2
- Binary file -> errorCode 4
- File too large -> errorCode 6

### Custom Error Classes

ShellError:
```javascript
[source fragment removed]
```

AbortError:
```javascript
[source fragment removed]
```

### Error Message Formatting

Error messages are automatically size-limited to 10KB with intelligent truncation
(first 5KB + last 5KB with truncation notice).
