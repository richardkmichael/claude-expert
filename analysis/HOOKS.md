# Hooks

Verified against: cli.prettier.js 2.1.280 (2026-09-22)

This document follows the landmark style in `GUIDELINES.md`: it anchors on version-stable strings
(hook event names, config keys, the Zod `.describe(...)` strings shipped in the schema, `tengu_*`
names, env vars, behavioral logic) with grep re-location recipes, not on minified symbol names or
line numbers, which churn every release. The `.describe(...)` strings are the durable anchors here:
they are product-authored documentation embedded in the bundle. Per-release changes are in the
appendix.

Since 2.1.242 the bundle is split into a thousand-odd `chunk-<hash>.js` modules; the hook schema,
the hook runner, the `/hooks` UI metadata and the query loop live in different chunks, so follow a
landmark rather than expecting neighbors to sit in the same module.

## Re-location recipes

| Target                       | Grep anchor                                                        |
|------------------------------|--------------------------------------------------------------------|
| All event input schemas      | `hook_event_name: ` (Zod alias before `(` is minified and churns)  |
| Runtime input builders       | `hook_event_name: "` (object literals, one per event)              |
| Base/common input fields     | `Subagent identifier. Present only when the hook fires`            |
| Hook type config schemas     | `MCP tool hook type`                                               |
| Output schema                | `terminalSequence` and `hookSpecificOutput`                        |
| `/hooks` UI event metadata   | `fieldToMatch` (per-event summary, exit-code text, matcher field)  |
| Matcher field per event      | `case "PreModelSwitch": {` inside the switch returning `tool_name` |
| Exit-code logic              | `Failed with non-blocking status code:`                            |
| Missing-script downgrade     | `Hook script appears to be missing`                                |
| Hook process env             | `CLAUDE_CODE_CHILD_SESSION` (env builder) and `CLAUDE_ENV_FILE`    |
| Pipeline dispatch            | `[Stall] tool_dispatch_start`                                      |
| Stop→SubagentStop conversion | `Converting Stop hook to SubagentStop`                             |
| Stop block cap               | `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`                                  |
| Non-blockable Stop firings   | `Stop hook block discarded`                                        |
| additionalContext delivery   | `hook_additional_context` (the message type Pre and Post build)    |
| Model-switch hooks           | `Model switch blocked by a PreModelSwitch hook`                    |
| background_tasks type labels | `auto-mode scan` (the task-type → label map)                       |

## Event inventory

33 events. The canonical list is an array literal that starts `"PreToolUse", "PostToolUse",
"PostToolUseFailure", "PostToolBatch", "Notification"` and appears twice (hook config and SDK
schema); `rg -o 'hook_event_name: "[A-Za-z]+"'` over the bundle yields the same 33 names from the
runtime input builders (UserPromptSubmit has two builders). Each input schema is a shared base
schema `.and(...object({ hook_event_name: ...literal("X"), ... }))`. Grouped by purpose:

| Group             | Events                                                                                          |
|-------------------|-------------------------------------------------------------------------------------------------|
| Tool lifecycle    | PreToolUse, PostToolUse, PostToolUseFailure, PostToolBatch, PermissionRequest, PermissionDenied |
| Prompt            | UserPromptSubmit, UserPromptExpansion                                                           |
| Session lifecycle | SessionStart, SessionEnd, Setup                                                                 |
| Stop / subagent   | Stop, StopFailure, SubagentStart, SubagentStop                                                  |
| Compaction        | PreCompact, PostCompact                                                                         |
| Model             | PreModelSwitch, PostModelSwitch                                                                 |
| Teams / tasks     | TeammateIdle, TaskCreated, TaskCompleted                                                        |
| MCP elicitation   | Elicitation, ElicitationResult                                                                  |
| Config / memory   | ConfigChange, InstructionsLoaded                                                                |
| Filesystem / cwd  | CwdChanged, FileChanged, DirectoryAdded                                                         |
| Worktree          | WorktreeCreate, WorktreeRemove                                                                  |
| Display           | MessageDisplay                                                                                  |
| Notification      | Notification                                                                                    |

Net new since the 21-event era: PostToolBatch, PermissionDenied, MessageDisplay,
UserPromptExpansion, StopFailure, PostCompact, TaskCreated, CwdChanged, FileChanged,
DirectoryAdded, PreModelSwitch, PostModelSwitch.

There is no event for a background task (a `run_in_background` Bash shell, a Monitor, a background
subagent, a workflow) starting or finishing. None of the 33 names covers it; the only hook-visible
trace of background work is the `background_tasks` array on Stop / SubagentStop (see "Background
work and hooks" below).

The `/hooks` UI carries a per-event summary, exit-code description and matcher field; grep
`fieldToMatch` to find the object. Its text is a second, product-authored description of each event
and is quoted below where it adds information.

## Base / common input fields

Every event extends a shared schema. Re-locate by the `agent_id` describe string above. Fields:

| Field             | Type                      | Notes                                                               |
|-------------------|---------------------------|---------------------------------------------------------------------|
| `session_id`      | string                    | always present                                                      |
| `transcript_path` | string                    | the main session transcript                                         |
| `cwd`             | string                    | working directory                                                   |
| `prompt_id`       | string, optional          | UUID of the current user prompt (see below)                         |
| `scratchpad_dir`  | string, optional          | session scratchpad path; runtime only, not in SDK schema            |
| `permission_mode` | string, optional          | `default`/`acceptEdits`/`bypassPermissions`/`plan`/`dontAsk`/`auto` |
| `agent_id`        | string, optional          | subagent identity (see below)                                       |
| `agent_type`      | string, optional          | agent type name (see below)                                         |
| `effort`          | `{ level: string }`, opt. | reasoning effort for the turn (see below)                           |

`prompt_id`: "UUID correlating a user prompt with all subsequent events until the next prompt. Same
value emitted on OpenTelemetry events as the `prompt.id` attribute, so hook output can be joined to
OTel events at prompt grain. Absent until the first user input of the process lifetime."

`scratchpad_dir` is set by the runtime input builder only when the scratchpad feature is on; it is
not declared in the SDK Zod schema.

Served calls. When a hook fires for a tool call served to a cloud session from this machine, the
base object is different: `session_id` is `served:<callerSessionId>` (or `served:unknown`),
`transcript_path` is the empty string, and `agent_type` / `prompt_id` / `scratchpad_dir` are
omitted.

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
session-lifecycle hooks.

## Event input schemas

Fields below are in addition to the base/common fields. Quoted strings are verbatim `.describe(...)`
text from the schema.

### Tool lifecycle

PreToolUse — `tool_name`, `tool_input`, `tool_use_id`, optional `mcp_server`.

PostToolUse — `tool_name`, `tool_input`, `tool_response`, `tool_use_id`, optional `duration_ms`
("Tool execution time in milliseconds. Excludes permission-prompt and hook time."), optional
`mcp_server`.

PostToolUseFailure — `tool_name`, `tool_input`, `tool_use_id`, `error`, optional `is_interrupt`,
optional `duration_ms`, optional `mcp_server`. Fires when tool execution throws (not when input
validation rejects — see "Validation gates hooks" below). The `/hooks` UI text also promises
`error_type` and `is_timeout`; neither the schema nor the runtime builder sets them.

PostToolBatch — `tool_calls: array`, each `{ tool_name, tool_input, tool_use_id, tool_response? }`.
Schema describe: "Fired once after every tool call in a batch has resolved, before the next model
request. PostToolUse fires per-tool and may run concurrently for parallel tool calls; PostToolBatch
fires exactly once with the full batch."

PermissionRequest — `tool_name`, `tool_input`, optional `permission_suggestions` (a union of
permission-update suggestions: add/replace/remove rules, set mode, add/remove directories),
optional `mcp_server`. No `tool_use_id`.

PermissionDenied — `tool_name`, `tool_input`, `tool_use_id`, `reason`, optional `mcp_server`. Fires
when a call is denied (notably by the auto-mode classifier); the output `retry` field can re-enable
the call.

`mcp_server` (on the five tool events above, MCP tools only) is `{ name, source }`. The describe
says to key trust on `source` ("sdk | plugin | user | project | local | dynamic | managed |
enterprise | claudeai | agent — an open set"), not on the name or the `mcp__*` prefix.

### Prompt

UserPromptSubmit — `prompt`, optional `session_title`. The SDK schema also declares an optional
`source` enum (`user` | `sdk` | `system` | `loop_wakeup` | `schedule_wakeup` | `poll_event`, "Who
authored/injected the prompt … `system` = other machine-injected turns (peer/channel messages, task
notifications, auto-continuation) … Payloads may omit it while the field rolls out"). In 2.1.280
both runtime builders spread a constant-false in the slot where `source` would go, so the CLI never
sends it.

UserPromptExpansion — `expansion_type` (`slash_command` | `mcp_prompt`), `command_name`,
`command_args`, optional `command_source`, `prompt`. Fires when a user-typed slash command or MCP
prompt expands, so a hook can inject context at expansion time.

### Session lifecycle

SessionStart — `source` (`startup` | `resume` | `clear` | `compact` | `fork`), optional
`agent_type`, `model`, `session_title`, and four resume/fork-only cache fields:
`seconds_since_last_response`, `context_tokens`, `prompt_cache_likely_expired`,
`estimated_cache_write_usd` (describes all start "resume/fork:").

SessionEnd — `reason` (`clear` | `resume` | `logout` | `prompt_input_exit` | `other`).
`bypass_permissions_disabled` is gone from the enum.

Setup — `trigger` (`init` | `maintenance`).

### Stop / subagent

Stop — `stop_hook_active`, optional `last_assistant_message` ("Text content of the last assistant
message before stopping. Avoids the need to read and parse the transcript file."), optional
`background_tasks`, optional `session_crons`. `background_tasks`: "In-flight background work
(running/pending + backgrounded) registered in this session. Lets hooks distinguish "session is
done" from "session is paused waiting for background work to wake it". Empty array when nothing is
in flight." `session_crons` lists session-scoped wakeups from `CronCreate`, `ScheduleWakeup`,
`/loop`.

StopFailure — `error` (matcher values: `rate_limit`, `overloaded`, `authentication_failed`,
`oauth_org_not_allowed`, `account_on_hold` (gated), `verification_required`, `billing_error`,
`invalid_request`, `model_not_found`, `server_error`, `max_output_tokens`, `cloud_credential_error`,
`unknown`), optional `error_details`, optional `last_assistant_message`. `/hooks` text: "Fires
instead of Stop when an API error … ended the turn. Fire-and-forget — hook output and exit codes are
ignored."

SubagentStart — `agent_id`, `agent_type` (both required here).

SubagentStop — `stop_hook_active`, `agent_id`, `agent_transcript_path`, `agent_type`, optional
`last_assistant_message`, optional `background_tasks`, optional `session_crons`.
`agent_transcript_path` points at the subagent's own JSONL,
`<projectDir>/<sessionId>/subagents/[<key>/]agent-<agentId>.jsonl`, the basis for exact
per-subagent token accounting (see `MONITORING_USAGE.md`). Both arrays are built from the session
task registry, so a subagent's Stop sees the whole session's background work, not only its own.

`background_tasks` and `session_crons` element shapes are under "Background work and hooks".

### Compaction

PreCompact — `trigger` (`manual` | `auto`), `custom_instructions` (nullable). Exit 0 stdout is
appended as custom compact instructions; exit 2 blocks compaction.

PostCompact — `trigger`, `compact_summary` ("The conversation summary produced by compaction").

### Model

PreModelSwitch / PostModelSwitch — `from_model`, `to_model` (resolved model ids),
`requested_model` (nullable: "alias such as "opus", a full id, or null for "default""), `source`,
`context_tokens`, `prompt_cache_warm`, `cache_ttl` (`5m` | `1h`), `estimated_cache_write_usd`,
`pricing` (`configured` | `catalog` | `default`). `source` is `command` | `picker` | `sdk` on
PreModelSwitch and additionally `auto` | `resume` on PostModelSwitch. Behavior is under "Model
switch hooks".

### Teams / tasks

TeammateIdle — `teammate_name`, `team_name`.

TaskCreated / TaskCompleted — `task_id`, `task_subject`, optional `task_description`,
`teammate_name`, `team_name`. On all three events `team_name` is now described "@deprecated
Sessions have a single implicit team; this carries the session-derived team name and will be
removed in a future release." What "task" means here is under "Background work and hooks".

### Notification

Notification — `message`, optional `title`, `notification_type`. Matcher values:
`permission_prompt`, `idle_prompt`, `auth_success`, `elicitation_dialog`, `agent_needs_input`,
`agent_completed`, `elicitation_url_dialog`, `worker_permission_prompt`, `push_notification`,
`computer_use_enter`, `computer_use_exit`, `quota_auto_resume_fired`, `quota_auto_resume_stale`,
`quota_auto_resume_disabled`, `model_refusal_fallback`, plus `elicitation_complete` and
`elicitation_response`. `agent_completed` / `agent_needs_input` come from the agent-view session
list (entries keyed by a session id), not from in-session background tasks.

### MCP elicitation

Elicitation — `mcp_server_name`, `message`, optional `mode` (`form` | `url`), `url`,
`elicitation_id`, `requested_schema`. Describe: "Fired when an MCP server requests user input. Hooks
can auto-respond (accept/decline) instead of showing the dialog."

ElicitationResult — `mcp_server_name`, optional `elicitation_id`, `mode`, `action` (`accept` |
`decline` | `cancel`), optional `content`. Describe: hooks can observe or override the response
before it is sent to the server.

### Config / memory

ConfigChange — `source` (`user_settings` | `project_settings` | `local_settings` |
`policy_settings` | `skills`), optional `file_path`. A block is ignored for `policy_settings`.

InstructionsLoaded — `file_path`, `memory_type` (`User` | `Project` | `Local` | `Managed`),
`load_reason` (`session_start` | `nested_traversal` | `path_glob_match` | `include` | `compact`),
optional `globs`, `trigger_file_path`, `parent_file_path`. Observability-only.

### Filesystem / cwd

CwdChanged — `old_cwd`, `new_cwd`. Output may set `watchPaths`.

FileChanged — `file_path`, `event` (`change` | `add` | `unlink`). Output may set `watchPaths`. The
matcher lists filenames to watch in the current directory (e.g. `.envrc|.env`).

DirectoryAdded — `directory` ("Absolute path of the directory that was added.") and `source`, an
enum of `slash_command` / `register_repo_root` — 'How the directory was added: "slash_command" for
/add-dir, "register_repo_root" for the SDK control_request.' It fires after the sandbox config is
refreshed. A directory already registered (including a duplicate request) is denied, and the
DirectoryAdded hooks do not re-run.

### Worktree

WorktreeCreate — `name`. WorktreeRemove — `worktree_path`.

### Display

MessageDisplay — `turn_id`, `message_id` ("UUID of the assistant message being displayed. Stable
across every flush of the same message. Not the API msg_… id."), `index` (zero-based delta index),
`final` (true on the last flush), `delta` ("The newly completed lines since the prior flush. Always
whole lines, except on the final flush which may end mid-line."). Display-only: it does not change
the stored message or what the model sees. Output `displayContent` replaces the on-screen delta.

## Matchers

A matcher is tested against one input field per event (grep the switch that returns `tool_name`
for the tool events). `*` or empty matches everything. A matcher made only of name characters and
`|` (plus `,`, space and `-` on the events that have a matcher field) is an exact-name list, with
no regex fallback; anything else is compiled as a regex. Events with no matcher field run every
configured hook.

| Matcher field              | Events                                                                                                                                      |
|----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| `tool_name`                | PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest, PermissionDenied                                                            |
| `command_name`             | UserPromptExpansion                                                                                                                         |
| `source`                   | SessionStart, ConfigChange, DirectoryAdded                                                                                                  |
| `trigger`                  | Setup, PreCompact, PostCompact                                                                                                              |
| canonical id of `to_model` | PreModelSwitch, PostModelSwitch                                                                                                             |
| `notification_type`        | Notification                                                                                                                                |
| `reason`                   | SessionEnd                                                                                                                                  |
| `error`                    | StopFailure                                                                                                                                 |
| `agent_type`               | SubagentStart, SubagentStop                                                                                                                 |
| `mcp_server_name`          | Elicitation, ElicitationResult                                                                                                              |
| `load_reason`              | InstructionsLoaded                                                                                                                          |
| basename of `file_path`    | FileChanged                                                                                                                                 |
| none                       | UserPromptSubmit, Stop, PostToolBatch, TeammateIdle, TaskCreated, TaskCompleted, CwdChanged, WorktreeCreate, WorktreeRemove, MessageDisplay |

For the model events the matcher is compared to the canonical model id derived from `to_model`
(through the model-overrides map), and a `[1m]` / `[2m]` suffix in the matcher is stripped before
comparison. When no canonical id can be derived, every hook runs regardless of matcher.

## Model switch hooks

PreModelSwitch (`/hooks`: "Before a requested model switch (/model, model picker, set_model)") runs
only for requested switches: `/model <name>`, the `/model` and Alt/Option+P pickers, the `/config`
Model row, turning on fast mode when that changes the model, and SDK / Remote Control / IDE
`set_model`. It never runs for automatic fallback or resume.

- Decision. `hookSpecificOutput.permissionDecision` is `allow` | `deny` | `ask` (no `defer`, no
  `updatedInput`, no `additionalContext`), described "Same contract as PreToolUse: allow proceeds
  (skipping the interactive cache-miss confirm), deny cancels the switch, ask asks the user to
  confirm (a headless session refuses instead)". Exit 2 or top-level `decision: "block"` also
  cancels. Across hooks the most restrictive wins: `deny` > `ask` > `allow`.
- Fail-closed. A hook that times out ("did not respond before its timeout"), throws, or is
  cancelled by a control-stream close blocks the switch. If plugin hook registration failed, the
  switch is refused with "…so organization-managed PreModelSwitch hooks could not be checked". An
  SDK host that re-initialized mid-hook gets a synthesized deny.
- Evaluated per mode. The switch is checked for the current permission mode and for its plan /
  default counterpart; each pair whose resolved from/to model differs runs the hooks once, so an
  `opusplan`-style setting can fire PreModelSwitch twice for one `/model`.
- Race guard. If the session model changes while hooks run, they re-run once; a second change
  refuses with "the session model changed while a PreModelSwitch hook was running; pick again".
- Refusal text: `Model switch blocked by a PreModelSwitch hook[: <reason>]`.
- Default timeout 30 s.

PostModelSwitch (`/hooks`: "After the session model changes (any cause)") fires whenever the
resolved main-loop model changes, including plan-mode entry/exit under a plan-mode model setting
(`source: "auto"` when nothing recorded a request) and resume. It cannot block. It runs
asynchronously; exit-0 stdout and `additionalContext` are queued per session and delivered as a
`hook_additional_context` message (hookName `PostModelSwitch`) on the next main-thread request that
the new model serves, never into a subagent. Exit-2 stderr becomes a notice, not a block. Default
timeout 30 s.

## Hook types

Five settings-configurable types, discriminated on `type`. Re-locate by the `MCP tool hook type`
describe string. All share: optional `if` ("Permission rule syntax to filter when this hook runs
(e.g., "Bash(git *)"). Only runs if the tool call matches the pattern. Avoids spawning hooks for
non-matching commands."), optional `statusMessage`, optional `once` ("If true, hook runs once and
is removed after execution"), optional positive `timeout` (seconds).

command — `command` (string). Optional `args` (exec form: when present, `command` is spawned
directly with these args and no shell, so quotes/`$`/backticks never reach a shell parser; absent →
runs through the shell). Optional `shell` (`bash` | `powershell`). Optional `async` ("runs in
background without blocking"). Optional `asyncRewake` ("runs in background and wakes the model on
exit code 2 (blocking error). Implies async."), with `@internal` `rewakeMessage` / `rewakeSummary`.
`@internal` `cloud` (`device` | `skip`) controls whether the hook is offered to a cloud session
driven from this machine.

prompt — `prompt` (use `$ARGUMENTS` for the hook input JSON), optional `model` (default: the small
fast model), optional `continueOnBlock` ("Sets the continue value for the decision:"block" produced
when ok is false. … On PostToolUse, the reason is fed back to Claude and the turn continues.").

mcp_tool — `server` (an already-configured MCP server), `tool` (a tool on that server), optional
`input` ("Arguments passed to the MCP tool. String values support ${path} interpolation from the
hook input JSON").

http — `url`, optional `headers` (values may reference env vars via `$VAR` / `${VAR}`, but only
names listed in `allowedEnvVars` are interpolated), optional `allowedEnvVars`, `@internal` `cloud`.

agent — `prompt` ("Prompt describing what to verify…", `$ARGUMENTS` for hook input), optional
`model` (default Haiku), default timeout 60 s. An agentic verifier.

The executor also knows non-settings types: `callback` / `function` (in-process SDK and
session-registered hooks) and an internal `script` type from the hook-modules system (gated by
`tengu_plugin_hooks_modules` / `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS`).

Default timeouts: 600 s for command / http / mcp_tool; 30 s for UserPromptSubmit, PreModelSwitch
and PostModelSwitch; SessionEnd hooks share a 1.5 s budget raised to the largest configured
per-hook `timeout` (capped), or set by `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS`.

## Hook configuration keys

| Key                      | Effect (settings `.describe(...)` paraphrase)                                   |
|--------------------------|---------------------------------------------------------------------------------|
| `hooks`                  | event → `[{ matcher?, hooks: [...] }]`                                          |
| `disableAllHooks`        | disables settings and plugin hooks and statusLine; built-in features keep going |
| `allowManagedHooksOnly`  | managed-settings only: run only managed hooks and managed-enabled plugins'      |
| `allowedHttpHookUrls`    | URL allowlist (`*` wildcard) for http hooks; `[]` allows none                   |
| `httpHookAllowedEnvVars` | intersected with each http hook's `allowedEnvVars`                              |

A PreToolUse / PermissionRequest entry that fails to parse is not silently dropped: it holds back
the permissions declared beside it (grep `a PreToolUse/PermissionRequest hook that cannot be
loaded`).

Hook-related env vars read by Claude Code: `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` (default 8
consecutive Stop/SubagentStop blocks before the turn is force-ended; `0` disables the cap),
`CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS`, `CLAUDE_CODE_DISABLE_HOOK_FORWARDING`,
`CLAUDE_CODE_DISABLE_PERMISSION_PROMPT_NOTIFY_HOOKS`, `CLAUDE_CODE_HOOKS_SAME_THREAD`,
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS`.

## Hook process environment

Command hooks inherit Claude Code's own environment (with a scrub list applied, e.g.
`CLAUDE_CODE_SUBSCRIPTION_TYPE`, `CLAUDE_CODE_RATE_LIMIT_TIER`) plus, set per spawn:

| Variable                       | Value / condition                                                  |
|--------------------------------|--------------------------------------------------------------------|
| `CLAUDE_PROJECT_DIR`           | project root (always)                                              |
| `CLAUDECODE`                   | `1`                                                                |
| `CLAUDE_CODE_SESSION_ID`       | the hook input's `session_id`                                      |
| `CLAUDE_CODE_CHILD_SESSION`    | `1`                                                                |
| `CLAUDE_CODE_SESSION_ATTENDED` | `1` for interactive / attended sessions, `0` for bg / daemon       |
| `CLAUDE_PID`                   | the Claude Code process's own pid                                  |
| `CLAUDE_EFFORT`                | the input's `effort.level`, when present                           |
| `TRACEPARENT`                  | when OTel trace propagation is active                              |
| `COLUMNS` / `LINES`            | from Claude Code's stdout dimensions, when it is a TTY             |
| `CLAUDE_PLUGIN_ROOT`           | plugin hooks, and skill hooks (skill dir)                          |
| `CLAUDE_PLUGIN_DATA`           | plugin hooks only                                                  |
| `CLAUDE_PLUGIN_OPTION_<KEY>`   | each plugin `user_config` value, key upper-cased, non-alnum → `_`  |
| `CLAUDE_ENV_FILE`              | SessionStart, Setup, CwdChanged, FileChanged; not for `powershell` |

So a hook process can identify the session and the Claude Code process from env alone
(`CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`), not only from stdin JSON. Anchor: grep
`CLAUDE_CODE_CHILD_SESSION: "1"` for the builder; the hook path passes it the hook input
(session id, effort) with a "harness" source, so `AI_AGENT` is not set for hooks. `${CLAUDE_*}`
placeholders in `command` / `args` are substituted too; referencing `${CLAUDE_PLUGIN_ROOT}` /
`${CLAUDE_PLUGIN_DATA}` from a non-plugin hook throws. A small allowlist of plugins (flag
`tengu_amber_lattice`) additionally receives `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY`.
Observability-only events (Notification, SessionStart/End, Setup, StopFailure, SubagentStart,
PostToolUseFailure, PostCompact, PostModelSwitch, PermissionDenied, Worktree*, InstructionsLoaded,
CwdChanged, FileChanged, DirectoryAdded, MessageDisplay) spawn in a `hooks` cgroup class where
cgroups are available.

## Hook output schema

A hook controls behavior by writing JSON to stdout. Top-level fields: `continue`, `suppressOutput`,
`stopReason`, `decision` (`approve` | `block`), `systemMessage`, `reason`, `terminalSequence` ("A
terminal escape sequence (e.g. OSC 9 / OSC 777 desktop-notification) … Only notification/title OSCs
(0, 1, 2, 9, 99, 777) and BEL are permitted; anything else is dropped."), and a `hookSpecificOutput`
object discriminated by `hookEventName` (a mismatch throws "Hook returned incorrect event name").
Alternatively a hook may return `{ async: true, asyncTimeout? }` to detach.

`hookSpecificOutput` by event:

| Event                                           | Fields                                                                                                               |
|-------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| PreToolUse                                      | `permissionDecision` (`allow`/`deny`/`ask`/`defer`), `permissionDecisionReason`, `updatedInput`, `additionalContext` |
| UserPromptSubmit                                | `additionalContext`, `sessionTitle`, `suppressOriginalPrompt`                                                        |
| UserPromptExpansion                             | `additionalContext`, `suppressOriginalPrompt`                                                                        |
| SessionStart                                    | `additionalContext`, `initialUserMessage`, `sessionTitle`, `watchPaths`, `reloadSkills`                              |
| Setup, SubagentStart                            | `additionalContext`                                                                                                  |
| PreModelSwitch                                  | `permissionDecision` (`allow`/`deny`/`ask`), `permissionDecisionReason`                                              |
| PostModelSwitch                                 | `additionalContext` ("Reaches the model with the next request the new model serves")                                 |
| PostToolUse                                     | `additionalContext`, `classifierContext`, `updatedToolOutput`, `updatedMCPToolOutput`                                |
| PostToolUseFailure, PostToolBatch, Notification | `additionalContext`                                                                                                  |
| Stop                                            | `additionalContext` — "non-error feedback delivered to the model; the conversation continues"                        |
| SubagentStop                                    | `additionalContext` — "delivered to the subagent; the subagent continues so it can act on it"                        |
| PermissionRequest                               | `decision`: allow `{ behavior, updatedInput?, updatedPermissions? }` or deny `{ behavior, message?, interrupt? }`    |
| PermissionDenied                                | `retry`                                                                                                              |
| MessageDisplay                                  | `displayContent` (replaces the on-screen delta)                                                                      |
| Elicitation / ElicitationResult                 | `action`, `content`                                                                                                  |
| CwdChanged / FileChanged                        | `watchPaths`                                                                                                         |
| WorktreeCreate                                  | `worktreePath` (command hooks print the path on stdout instead)                                                      |

`classifierContext` (PostToolUse) is "Host-asserted context shown to the auto-mode permission
classifier alongside this tool call's result", capped at 2000 UTF-16 code units shared across all
hooks for one call, honored on synchronous responses only, and dropped if the same hook's rewrite
is rejected or superseded.

The PreToolUse `permissionDecision` enum includes `defer`, which is print-mode-only and solo-only
(grep `defer is print-mode only` / `defer is solo-only`): it warns and is ignored in interactive
mode or inside a multi-tool batch.

### additionalContext cannot steer the call that triggered it

A PreToolUse `additionalContext` string does not reach the model before the tool runs. PreToolUse
fires after the model has already emitted the `tool_use` block, and no inference turn happens
between the hook and tool execution — the model's next read of the conversation is the turn that
processes the tool result. So Pre and Post `additionalContext` are consumed at the same inference
turn. Both handlers build the same `hook_additional_context` message (grep that string) and push it
onto the same per-tool-call message array, differing only in `hookName` / `hookEvent`.

The two are not fully interchangeable, on three axes:

| Axis                             | PreToolUse                                                       | PostToolUse                                                      |
|----------------------------------|------------------------------------------------------------------|------------------------------------------------------------------|
| Position in the message array    | Before the tool result                                           | After the tool result                                            |
| Emitted when the call is blocked | Yes                                                              | No — the event never fires                                       |
| Rest of the payload              | `permissionDecision`, `permissionDecisionReason`, `updatedInput` | `updatedToolOutput`, `updatedMCPToolOutput`, `classifierContext` |

The blocked-call row is the load-bearing one. In the PreToolUse handler the `additionalContext`
emission is not guarded by the permission decision — it is emitted on allow, ask, and deny alike,
so PreToolUse is the only hook that can attach context to a tool call that never executed.

Consequence for hook authors: to influence *how* a tool gets called, the information has to exist
before the model's turn (tool description, CLAUDE.md, skill body, or `additionalContext` from
`SessionStart` / `UserPromptSubmit`), or the hook has to force another turn by denying with
`permissionDecisionReason`, or skip the model entirely and rewrite the call with `updatedInput`.

## Exit-code behavior (command hooks)

If stdout parses as a JSON output object, that path wins. Otherwise exit code governs:

| Exit code | Behavior                                                                        |
|-----------|---------------------------------------------------------------------------------|
| 0         | success; stdout becomes context only for events that take it (see below)        |
| 2         | blocking; stderr surfaced as a blocking error, format `[<command>]: <stderr>`   |
| other     | non-blocking error; `Failed with non-blocking status code: <stderr>`, continues |

What exit 2 does per event, from the `/hooks` metadata text:

| Event(s)                                                    | Exit 2                                             |
|-------------------------------------------------------------|----------------------------------------------------|
| PreToolUse                                                  | stderr to model, tool call blocked                 |
| PostToolUse, PostToolUseFailure                             | stderr to model immediately                        |
| PostToolBatch                                               | stops the agentic loop (stderr to user)            |
| UserPromptSubmit                                            | blocks and erases the prompt (stderr to user)      |
| UserPromptExpansion                                         | blocks the expansion (stderr to user)              |
| Stop                                                        | stderr to model, conversation continues            |
| SubagentStop                                                | stderr to subagent, it keeps running               |
| TeammateIdle                                                | stderr to teammate, it keeps working               |
| TaskCreated / TaskCompleted                                 | stderr to model, creation / completion prevented   |
| PreCompact                                                  | blocks compaction                                  |
| PreModelSwitch                                              | blocks the switch                                  |
| ConfigChange                                                | change not applied (ignored for `policy_settings`) |
| Elicitation / ElicitationResult                             | deny / action becomes `decline`                    |
| SessionStart, Setup, SubagentStart, PostModelSwitch, others | stderr to user only; nothing blocks                |

Exit 0 stdout is added as model context on UserPromptSubmit, UserPromptExpansion, SessionStart and
PostModelSwitch; elsewhere it goes to the transcript view or debug log.

Missing-script downgrade. For Stop, SubagentStop, TaskCompleted, TeammateIdle, and plugin
UserPromptSubmit hooks, an exit 2 with empty stdout and a stderr matching "no such file" / "can't
open" is downgraded to non-blocking with the message "Hook script appears to be missing …  Treating
as non-blocking." plus a reinstall hint. This keeps a missing plugin script from wedging the turn.

## Background work and hooks

`background_tasks` (Stop, SubagentStop). Built from the session task registry: an entry is included
only when its status is `running` or `pending` and it is not explicitly un-backgrounded (a task
carrying `isBackgrounded: false`, i.e. still in the foreground, is skipped). Fields: `id`, `type`,
`status`, `description` (capped at 1000 chars with an in-string "… [+N chars]" marker), plus
`command` (shell), `agent_type` (subagent), `server` / `tool` (MCP monitor, MCP task), `name`
(workflow). The `type` label map (grep `auto-mode scan`), falling back to the raw discriminant:

| Registry type         | Label            |
|-----------------------|------------------|
| `local_bash`          | `shell`          |
| `local_agent`         | `subagent`       |
| `local_workflow`      | `workflow`       |
| `monitor_mcp`         | `monitor`        |
| `monitor_ws`          | `monitor`        |
| `mcp_task`            | `MCP task`       |
| `in_process_teammate` | `teammate`       |
| `dream`               | `dream`          |
| `auto_mode_scan`      | `auto-mode scan` |
| `remote_agent`        | `cloud session`  |

A monitor started by the Monitor tool is a `local_bash` task with `kind: "monitor"`, so it reports
as `shell` (with `command`), not `monitor`; only MCP and websocket monitors report `monitor`.
`session_crons` elements carry `id`, `schedule` (cron expression), `recurring`, `prompt` (capped
at 1000 chars).

No start/finish events. No hook event fires when a background shell, monitor, subagent or workflow
starts or completes (see the inventory). Completion reaches the model as a queued
`task-notification`; hooks see it only indirectly, via the turn it may start (below) or the
`background_tasks` array shrinking at the next Stop.

TaskCreated / TaskCompleted are about the TaskCreate / TaskUpdate task list, not the background
task registry. TaskCreated fires from the TaskCreate tool (exit 2 deletes the new task and fails the
call); TaskCompleted fires when TaskUpdate moves a task to `completed`, and at a teammate's turn end
for each `in_progress` task it owns. The list id is `CLAUDE_CODE_TASK_LIST_ID`, else the team name,
else the session-derived name, stored under `~/.claude/tasks/<id>`; so they fire in solo sessions
too, with `team_name` carrying the derived name.

Turns started by a task-notification. When a queued `task-notification` starts a new turn (the
agent was idle), both hooks run:

- UserPromptSubmit fires. The queue drain classifies the command's origin as non-human, so the
  prompt source resolves to `system` (grep the helper that returns `"system"` when `isMeta` or
  caller source is `system`); hooks are skipped only when that source is undefined, for `bash`
  mode, a fork dispatch, `skipSubmissionHooks` (set for `poll-event` mode), or a non-querying
  input. `prompt` is the notification text. The `source` field that would say `system` is not
  sent in 2.1.280 (see UserPromptSubmit above), so a hook must recognize the notification by its
  `<task-notification>` content.
- Stop fires. The turn-end path that runs Stop hooks has no gate on what started the turn.

A notification that arrives while a turn is running is attached to that turn as a
`queued_command` attachment instead and starts nothing. This is from reading the code paths, not a
live run.

Stop also fires, but cannot block, when a turn ends without a model re-invoke: a tool result that
ends the turn, an MCP end-turn meta, or a `/loop` dynamic wakeup tick. A block there is logged as
"Stop hook block discarded (turn ended by …, no model re-invoke)".

## Tool-execution pipeline

The order verified for 2.1.220 and unchanged in 2.1.280 (re-locate via `[Stall]
tool_dispatch_start`):

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

Per-tool PostToolUse may run concurrently for parallel calls, then PostToolBatch fires exactly once
with the whole batch before the next model request (grep `Execution stopped by PostToolBatch
hook`). PostToolUse output rewrites are validated against the tool's output schema; a mismatch
keeps the original output and records a hook error. After a hook edits a file post-Edit, the
read-file state is re-synced so the next Edit does not fail with a stale-file error.

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

After `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` (default 8) consecutive blocks the turn is ended anyway with
"A hook blocked the turn from ending N consecutive times — overriding and ending turn."

## Hooks and token usage

No hook input carries a token, usage, or cost field, except the model-switch events'
`context_tokens` / `estimated_cache_write_usd` and SessionStart's resume/fork cache estimates. The
SubagentStop input carries `agent_transcript_path`, which enables exact per-subagent token
accounting by reading and summing that file. The full attribution story — trailers, OTEL, the
SubagentStop recipe — is in `MONITORING_USAGE.md`.

## Published docs vs. source (2.1.280)

Checked against `/en/hooks` via the `claude-code-docs` MCP. The reference is current on the model
events, `prompt_id`, `scratchpad_dir`, `mcp_server`, timeouts and `CLAUDE_ENV_FILE`. Drift:

- The hook process env (`CLAUDE_CODE_SESSION_ID`, `CLAUDE_PID`, `CLAUDECODE`,
  `CLAUDE_CODE_CHILD_SESSION`, `CLAUDE_CODE_SESSION_ATTENDED`, `COLUMNS` / `LINES`) is not listed
  on the hooks page; only the changelog mentions `CLAUDE_CODE_SESSION_ID`.
- The `background_tasks` `type` list omits `dream` and `auto-mode scan`, and implies Monitor-tool
  monitors report `monitor`; they report `shell`.
- The docs do not say whether UserPromptSubmit / Stop fire for task-notification turns.
- PreModelSwitch's double evaluation for the plan/default counterpart is undocumented.
- In-product `/hooks` text for PostToolUseFailure lists `error_type` and `is_timeout`, which the
  CLI does not send.

## Per-release appendix

- 2.1.280: verified. 33 events (was 31): PreModelSwitch and PostModelSwitch (docs: since 2.1.251).
- 2.1.280: model events carry from/to/requested model, source, cache-cost fields; matcher on the
  canonical `to_model` id; PreModelSwitch allow/deny/ask, fail-closed on timeout.
- 2.1.280: base input gained `scratchpad_dir` (runtime only; docs: 2.1.257); `prompt_id` was
  already present by 2.1.220 but undocumented here.
- 2.1.280: `mcp_server { name, source }` on the five tool events (docs: 2.1.274).
- 2.1.280: SessionStart `source` gained `fork` plus four resume/fork cache fields.
- 2.1.280: SessionEnd `reason` lost `bypass_permissions_disabled` (docs: removed 2.1.234).
- 2.1.280: UserPromptSubmit `source` declared in the SDK schema but not sent by the CLI.
- 2.1.280: `team_name` marked @deprecated on TeammateIdle / TaskCreated / TaskCompleted.
- 2.1.280: hookSpecificOutput gained `additionalContext` on UserPromptExpansion, Setup,
  SubagentStart, PostToolUseFailure, PostToolBatch, Notification; PostToolUse `classifierContext`.
- 2.1.280: command / http hooks gained `@internal` `cloud`; executor knows an internal `script`
  type.
- 2.1.280: documented matcher table, exit-2 table, hook process env (incl. `CLAUDE_PID`,
  `CLAUDE_CODE_SESSION_ID`), config keys, and background-task / task-notification interplay.
- 2.1.220: verified. 31 event input schemas (was 30): `DirectoryAdded` added, carrying `directory`
  and a `source` enum (`slash_command` / `register_repo_root`). The event inventory table also
  gained `Notification`, which the 2.1.165 pass listed in the output-schema table but omitted from
  the inventory. All relocation anchors still resolve, except that the event-schema anchor was
  alias-specific (`v.literal`) and has been neutralized to `hook_event_name: `. Recorded the
  PreToolUse-vs-PostToolUse `additionalContext` delivery semantics: same consuming inference turn,
  differing only in message-array position, blocked-call emission, and sibling payload fields.
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
