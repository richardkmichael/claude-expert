# Hooks

Behavioral model verified against 2.1.165. This document follows the landmark style in
`GUIDELINES.md`: it anchors on version-stable strings (hook event names, config keys, the Zod
`.describe(...)` strings shipped in the schema, `tengu_*` names, env vars, behavioral logic) with
grep re-location recipes, not on minified symbol names or line numbers, which churn every release.
The `.describe(...)` strings are the durable anchors here: they are product-authored documentation
embedded in the bundle. Per-release changes are in the appendix.

## Re-location recipes

| Target                        | Grep anchor                                               |
|-------------------------------|-----------------------------------------------------------|
| All event input schemas       | `hook_event_name: v.literal(`                             |
| Base/common input fields      | `Subagent identifier. Present only when the hook fires`   |
| Hook type config schemas      | `MCP tool hook type`                                      |
| Output schema                 | `terminalSequence` and `hookSpecificOutput`               |
| Exit-code logic               | `Failed with non-blocking status code:`                   |
| Missing-script downgrade      | `Hook script appears to be missing`                       |
| Pipeline dispatch             | `[Stall] tool_dispatch_start`                             |
| Stop→SubagentStop conversion  | `Converting Stop hook to SubagentStop`                    |

## Event inventory

The current set is 30 events, up from 21 in earlier releases. Each is defined as a shared base
schema `.and(v.object({ hook_event_name: v.literal("X"), ... }))`, so every event extends the
base/common fields. Grouped by purpose:

| Group              | Events                                                                      |
|--------------------|-----------------------------------------------------------------------------|
| Tool lifecycle     | PreToolUse, PostToolUse, PostToolUseFailure, PostToolBatch, PermissionRequest, PermissionDenied |
| Prompt             | UserPromptSubmit, UserPromptExpansion                                        |
| Session lifecycle  | SessionStart, SessionEnd, Setup                                             |
| Stop / subagent    | Stop, StopFailure, SubagentStart, SubagentStop                             |
| Compaction         | PreCompact, PostCompact                                                     |
| Teams / tasks      | TeammateIdle, TaskCreated, TaskCompleted                                    |
| MCP elicitation    | Elicitation, ElicitationResult                                             |
| Config / memory    | ConfigChange, InstructionsLoaded                                           |
| Filesystem / cwd   | CwdChanged, FileChanged                                                     |
| Worktree           | WorktreeCreate, WorktreeRemove                                             |
| Display            | MessageDisplay                                                             |

Net new since the 21-event era: PostToolBatch, PermissionDenied, MessageDisplay,
UserPromptExpansion, StopFailure, PostCompact, TaskCreated, CwdChanged, FileChanged.

## Base / common input fields

Every event extends a shared schema. Re-locate by the `agent_id` describe string above. Fields:

| Field             | Type                       | Notes                                                |
|-------------------|----------------------------|------------------------------------------------------|
| `session_id`      | string                     | always present                                       |
| `transcript_path` | string                     | the main session transcript                          |
| `cwd`             | string                     | working directory                                    |
| `permission_mode` | string, optional           | `default`/`acceptEdits`/`bypassPermissions`/`plan`/`dontAsk`/`auto` |
| `agent_id`        | string, optional           | subagent identity (see below)                        |
| `agent_type`      | string, optional           | agent type name (see below)                          |
| `effort`          | `{ level: string }`, opt.  | reasoning effort for the turn (see below)            |

Subagent vs. main thread. The describe strings are explicit and authoritative: `agent_id` is
"Present only when the hook fires from within a subagent (e.g., a tool called by an AgentTool
worker). Absent for the main thread, even in --agent sessions. Use this field (not agent_type) to
distinguish subagent calls from main-thread calls." `agent_type` is "Present when the hook fires
from within a subagent (alongside agent_id), or on the main thread of a session started with
--agent (without agent_id)." So the test for "is this hook firing inside a subagent" is the
presence of `agent_id`, not `agent_type`.

Effort. `effort.level` is the "Active effort level for the current turn (e.g., low, medium, high,
xhigh, max), after any silent downgrade for the selected model. Also exposed to hook commands and
Bash as the CLAUDE_EFFORT env var." It is present only for hooks firing in a tool-use context
(PreToolUse, PostToolUse, Stop, SubagentStop, …) on a model that supports effort; absent for
session-lifecycle hooks. The same value is injected into the hook command environment as
`$CLAUDE_EFFORT`.

## Event input schemas

Fields below are in addition to the base/common fields. Quoted strings are verbatim `.describe(...)`
text from the schema.

### Tool lifecycle

PreToolUse — `tool_name`, `tool_input`, `tool_use_id`.

PostToolUse — `tool_name`, `tool_input`, `tool_response`, `tool_use_id`, optional `duration_ms`
("Tool execution time in milliseconds. Excludes permission-prompt and hook time.").

PostToolUseFailure — `tool_name`, `tool_input`, `tool_use_id`, `error`, optional `is_interrupt`,
optional `duration_ms`. Fires when tool execution throws (not when input validation rejects — see
"Validation gates hooks" below).

PostToolBatch — `tool_calls: array`, each `{ tool_name, tool_input, tool_use_id, tool_response? }`.
Schema describe: "Fired once after every tool call in a batch has resolved, before the next model
request. PostToolUse fires per-tool and may run concurrently for parallel tool calls; PostToolBatch
fires exactly once with the full batch."

PermissionRequest — `tool_name`, `tool_input`, optional `permission_suggestions` (a union of
permission-update suggestions: add/replace/remove rules, set mode, add/remove directories).

PermissionDenied — `tool_name`, `tool_input`, `tool_use_id`, `reason`. Fires when a call is denied
(notably by the auto-mode classifier); the output `retry` field can re-enable the call.

### Prompt

UserPromptSubmit — `prompt`, optional `session_title`.

UserPromptExpansion — `expansion_type` (`slash_command` | `mcp_prompt`), `command_name`,
`command_args`, optional `command_source`, `prompt`. Fires when a slash command or MCP prompt
expands, so a hook can inject context at expansion time.

### Session lifecycle

SessionStart — `source` (`startup` | `resume` | `clear` | `compact`), optional `agent_type`,
`model`, `session_title`.

SessionEnd — `reason` (`clear` | `resume` | `logout` | `prompt_input_exit` | `other` |
`bypass_permissions_disabled`).

Setup — `trigger` (`init` | `maintenance`).

### Stop / subagent

Stop — `stop_hook_active`, optional `last_assistant_message` ("Text content of the last assistant
message before stopping. Avoids the need to read and parse the transcript file."), optional
`background_tasks`, optional `session_crons`. The `background_tasks` describe distinguishes "session
is done" from "session is paused waiting for background work to wake it"; `session_crons` lists
session-scoped wakeups from `CronCreate`, `ScheduleWakeup`, `/loop`.

StopFailure — `error`, optional `error_details`, optional `last_assistant_message`.

SubagentStart — `agent_id`, `agent_type` (both required here).

SubagentStop — `stop_hook_active`, `agent_id`, `agent_transcript_path`, `agent_type`, optional
`last_assistant_message`, optional `background_tasks`, optional `session_crons`.
`agent_transcript_path` points at the subagent's own JSONL,
`<projectDir>/<sessionId>/subagents/[<key>/]agent-<agentId>.jsonl`, the basis for exact
per-subagent token accounting (see `MONITORING_USAGE.md`).

A `background_tasks` element carries `id`, `type` ("Friendly task-type label, e.g. 'shell',
'subagent', 'monitor', 'workflow'"), `status`, `description` (capped at 1000 chars), and
type-specific `command` / `agent_type` / `server` / `tool` / `name`. A `session_crons` element
carries `id`, `schedule` (cron expression), `recurring`, `prompt`.

### Compaction

PreCompact — `trigger` (`manual` | `auto`), `custom_instructions` (nullable).

PostCompact — `trigger`, `compact_summary` ("The conversation summary produced by compaction").

### Teams / tasks

TeammateIdle — `teammate_name`, `team_name`.

TaskCreated / TaskCompleted — `task_id`, `task_subject`, optional `task_description`,
`teammate_name`, `team_name`.

### MCP elicitation

Elicitation — `mcp_server_name`, `message`, optional `mode` (`form` | `url`), `url`,
`elicitation_id`, `requested_schema`. Describe: "Fired when an MCP server requests user input. Hooks
can auto-respond (accept/decline) instead of showing the dialog."

ElicitationResult — `mcp_server_name`, optional `elicitation_id`, `mode`, `action` (`accept` |
`decline` | `cancel`), optional `content`. Describe: hooks can observe or override the response
before it is sent to the server.

### Config / memory

ConfigChange — `source` (`user_settings` | `project_settings` | `local_settings` |
`policy_settings` | `skills`), optional `file_path`.

InstructionsLoaded — `file_path`, `memory_type` (`User` | `Project` | `Local` | `Managed`),
`load_reason` (`session_start` | `nested_traversal` | `path_glob_match` | `include` | `compact`),
optional `globs`, `trigger_file_path`, `parent_file_path`.

### Filesystem / cwd

CwdChanged — `old_cwd`, `new_cwd`. Output may set `watchPaths`.

FileChanged — `file_path`, `event` (`change` | `add` | `unlink`). Output may set `watchPaths`.

### Worktree

WorktreeCreate — `name`. WorktreeRemove — `worktree_path`.

### Display

MessageDisplay — `turn_id`, `message_id` ("UUID of the assistant message being displayed. Stable
across every flush of the same message. Not the API msg_… id."), `index` (zero-based delta index),
`final` (true on the last flush), `delta` ("The newly completed lines since the prior flush. Always
whole lines, except on the final flush which may end mid-line."). Display-only: it does not change
the stored message or what the model sees. Output `displayContent` replaces the on-screen delta.

## Hook types

Five types, discriminated on `type`. Re-locate by the `MCP tool hook type` describe string. All
types share: optional `if` ("Permission rule syntax to filter when this hook runs (e.g., Bash(git
*)). Only runs if the tool call matches the pattern."), optional `statusMessage`, optional `once`
("If true, hook runs once and is removed after execution"), optional positive `timeout`.

command — `command` (string). Optional `args` (exec form: when present, `command` is spawned
directly with these args and no shell, so quotes/`$`/backticks never reach a shell parser; absent →
runs through the shell). Optional `shell` (`bash` | `powershell`). Optional `async` ("runs in
background without blocking"). Optional `asyncRewake` ("runs in background and wakes the model on
exit code 2 (blocking error). Implies async."), with `rewakeMessage` / `rewakeSummary` to customize
the re-wake reminder.

prompt — `prompt` (use `$ARGUMENTS` for the hook input JSON), optional `model` (default: the small
fast model), optional `continueOnBlock` ("Sets the continue value for the decision:block produced
when ok is false. … On PostToolUse, the reason is fed back to Claude and the turn continues.").

mcp_tool (new) — `server` (an already-configured MCP server), `tool` (a tool on that server),
optional `input` ("Arguments passed to the MCP tool. String values support `${path}` interpolation
from the hook input JSON, e.g. `${tool_input.file_path}`").

http — `url`, optional `headers` (values may reference env vars via `$VAR` / `${VAR}`, but only
names listed in `allowedEnvVars` are interpolated), optional `allowedEnvVars`. A settings-level
`httpHookAllowedEnvVars` allowlist intersects with each hook's `allowedEnvVars`.

agent — `prompt` ("Prompt describing what to verify…", `$ARGUMENTS` for hook input), optional
`model` (default Haiku), default timeout 60s. An agentic verifier.

## Hook output schema

A hook controls behavior by writing JSON to stdout. Top-level fields: `continue`, `suppressOutput`,
`stopReason`, `decision` (`approve` | `block`), `systemMessage`, `reason`, `terminalSequence` ("A
terminal escape sequence (e.g. OSC 9 / OSC 777 desktop-notification) … Only notification/title OSCs
(0, 1, 2, 9, 99, 777) and BEL are permitted; anything else is dropped."), and a `hookSpecificOutput`
object discriminated by `hookEventName`. Alternatively a hook may return `{ async: true,
asyncTimeout? }` to detach.

`hookSpecificOutput` by event (most carry `additionalContext`):

| Event             | Fields beyond `additionalContext`                                          |
|-------------------|----------------------------------------------------------------------------|
| PreToolUse        | `permissionDecision` (`allow`/`deny`/`ask`/`defer`), `permissionDecisionReason`, `updatedInput` |
| UserPromptSubmit  | `sessionTitle`, `suppressOriginalPrompt`                                   |
| SessionStart      | `initialUserMessage`, `sessionTitle`, `watchPaths`, `reloadSkills`         |
| PostToolUse       | `updatedToolOutput` ("Replaces the tool output before it is sent to the model"), `updatedMCPToolOutput` |
| Stop              | `additionalContext` — "non-error feedback delivered to the model; the conversation continues" |
| SubagentStop      | `additionalContext` — "delivered to the subagent; the subagent continues so it can act on it" |
| PermissionRequest | `decision`: allow `{ behavior, updatedInput?, updatedPermissions? }` or deny `{ behavior, message?, interrupt? }` |
| PermissionDenied  | `retry`                                                                    |
| MessageDisplay    | `displayContent` (replaces the on-screen delta)                            |
| Elicitation / ElicitationResult | `action`, `content`                                          |
| CwdChanged / FileChanged | `watchPaths`                                                        |
| WorktreeCreate    | `worktreePath` (command hooks print the path on stdout instead)            |

The PreToolUse `permissionDecision` enum gained `defer`, which is print-mode-only and solo-only
(grep `defer is print-mode only` / `defer is solo-only`): it warns and is ignored in interactive
mode or inside a multi-tool batch.

## Exit-code behavior (command hooks)

If stdout parses as a JSON output object, that path wins. Otherwise exit code governs:

| Exit code | Behavior                                                                       |
|-----------|--------------------------------------------------------------------------------|
| 0         | success; trimmed stdout becomes additional context for the model               |
| 2         | blocking; stderr surfaced as a blocking error, format `[<command>]: <stderr>`   |
| other     | non-blocking error; `Failed with non-blocking status code: <stderr>`, continues |

Missing-script downgrade. For Stop, SubagentStop, TaskCompleted, TeammateIdle, and plugin
UserPromptSubmit hooks, an exit 2 with empty stdout and a stderr matching "no such file" / "can't
open" is downgraded to non-blocking with the message "Hook script appears to be missing …  Treating
as non-blocking." plus a reinstall hint. This keeps a missing plugin script from wedging the turn.

## Tool-execution pipeline

The order verified for 2.1.165 (re-locate via `[Stall] tool_dispatch_start`):

```
1. Input schema validation (Zod)        -> on fail: <tool_use_error>InputValidationError...
2. Tool input validation (validateInput) -> on fail: <tool_use_error>...
3. PreToolUse hooks                       -> may allow/ask/deny, rewrite input, add context, defer
4. Permission check                       -> tengu_tool_use_can_use_tool_allowed / _rejected
5. PermissionRequest hooks                -> when decision is "ask"; set the decision used in (4)
6. Permission UI prompt                   -> when "ask"
7. tool.call
8. PostToolUse hooks (success)            -> may rewrite output via updatedToolOutput
   PostToolUseFailure hooks (throw)       -> receives error + is_interrupt
9. PostToolBatch hooks                    -> once per batch, after all per-tool PostToolUse resolve
```

PostToolBatch is the structural addition versus earlier releases: per-tool PostToolUse may run
concurrently for parallel calls, then PostToolBatch fires exactly once with the whole batch before
the next model request (grep `Execution stopped by PostToolBatch hook`). PostToolUse output rewrites
are validated against the tool's output schema; a mismatch keeps the original output and records a
hook error. After a hook edits a file post-Edit, the read-file state is re-synced so the next Edit
does not fail with a stale-file error.

### Validation gates hooks

PreToolUse hooks fire only after both schema and input validation pass. If `validateInput` rejects
the input (e.g. a Read of a nonexistent file), the call short-circuits and no PreToolUse hook runs.
Tool succeeds → PostToolUse; tool throws → PostToolUseFailure; validation fails → neither. See
`TOOL_VALIDATION.md` for the per-tool `validateInput` reasons.

## Permission-request timing

When a tool's permission check returns "ask", the UI prompt and the PermissionRequest hooks race:
the prompt renders while the hooks run; whichever resolves first decides. When
`awaitAutomatedChecksBeforeDialog` is set on the permission context, the hooks run before the prompt
appears, and if they resolve the request the UI never shows. Tools whose `requiresUserInteraction()`
is true (e.g. ExitPlanMode) always produce "ask", bypassing auto-mode classifiers and rule checks,
so the "Ready to code?" plan prompt (grep `Ready to code?`) always renders, and its
PostToolUse/PostToolUseFailure hooks fire after the user responds.

## Stop becomes SubagentStop inside a subagent

Two mechanisms route stop events for subagents. At the engine level, a context that has an
`agent_id` (a subagent or sidechain) fires SubagentStop rather than Stop. At registration time, when
an agent's frontmatter hooks are registered with the subagent flag set, any `Stop` hook is rewritten
to `SubagentStop` — grep the log line "Converting Stop hook to SubagentStop for … (subagents trigger
SubagentStop)". So a `Stop` hook declared in subagent-applicable config silently becomes a
`SubagentStop` hook.

## Hooks and token usage

No hook input carries a token, usage, or cost field. The SubagentStop input does carry
`agent_transcript_path`, which enables exact per-subagent token accounting by reading and summing
that file. The full attribution story — trailers, OTEL, the SubagentStop recipe — is in
`MONITORING_USAGE.md`.

## Per-release appendix

- 2.1.165: verified. 30 event input schemas (was 21). New events: PostToolBatch, PermissionDenied,
  MessageDisplay, UserPromptExpansion, StopFailure, PostCompact, TaskCreated, CwdChanged,
  FileChanged. Five hook types (was four): `mcp_tool` added. New command-hook fields: `args` (exec
  form, no shell), `shell`, `asyncRewake` + `rewakeMessage` / `rewakeSummary`. New output field
  `terminalSequence` (restricted OSC escapes); async return form `{ async: true, asyncTimeout? }`.
  PreToolUse `permissionDecision` gained `defer` (print-mode, solo-only). Base input fields gained
  `permission_mode`, `agent_id`, `agent_type`, `effort` (with `$CLAUDE_EFFORT` env injection).
  SubagentStop gained `agent_transcript_path`. `prompt`-type hooks gained `continueOnBlock`;
  `SessionStart` output gained `reloadSkills`; `PostToolUse` output gained `updatedToolOutput` /
  `updatedMCPToolOutput`.
