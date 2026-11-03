---
verified: 2.1.281
verified_on: 2026-09-23
section: Sessions, context, and history
style: landmark
scope: JSONL transcript format, record types, linkage model
landmarks:
  - parentUuid
  - logicalParentUuid
  - <sessionId>.jsonl
  - '"atis-latch": "last-wins"'
  - tengu_context_announcement
---
# Session Transcript Format

This document follows the landmark style in `GUIDELINES.md`: it anchors on version-stable strings
(record `type` discriminants, field names, the JSONL path patterns, env vars, `tengu_*` events,
behavioral logic) with grep re-location recipes, not on minified symbol names or line numbers, which
churn every release. The field and record names are themselves the durable contract.

Claude Code persists conversation state as JSONL (newline-delimited JSON): one self-contained JSON
object per line, terminated by `\n`. There is no official schema. A companion JSON Schema (Draft
2020-12, `x-schema-version` 1.3.0) lives at
[`schemas/transcript.schema.json`](schemas/transcript.schema.json); it is cross-checked against a
large corpus of real transcripts across many Claude Code versions
(`bin/generate-transcript-schema.py` regenerates that observed-coverage view), and is the
machine-readable counterpart to this prose model. The schema carries the per-field and
per-attachment-subtype detail; this doc gives the model. For token-usage attribution from these
records, see `MONITORING_USAGE.md`.

## Re-location recipes

| Target                      | Grep anchor                                                      |
|-----------------------------|------------------------------------------------------------------|
| Envelope writer             | `logicalParentUuid` / `tengu_chain_self_reference_write`         |
| Record policy tables        | `rg -n '"atis-latch": "(last-wins\|always)"'`                    |
| Write-routing switch        | `appendEntry invariant: dedup-transcript policy`                 |
| Metadata loader dispatch    | `rg -n 'type === "atis-latch" &&'` (an if/else chain)            |
| Read-path result shape      | `attributionSnapshots`, `artifactAutoReactLedgers`, `costStates` |
| JSONL parser                | `Bun.JSONL` / the split-on-newline skip-malformed loop           |
| Path builder                | `"subagents"` under `projects`; `"subagents", "workflows"`       |
| Big-file partial load       | `CLAUDE_CODE_DISABLE_PRECOMPACT_SKIP`                            |
| Write queue                 | `FLUSH_INTERVAL_MS`, `MAX_CHUNK_BYTES`                           |
| Session-metadata re-append  | `Metadata re-append failed`                                      |
| `session_id` stamping       | `[engine] sdkEventQueue push key`                                |
| Context announcements       | `tengu_context_announcement`, `carriesContext`, `refreshReason`  |
| Frozen attachment rendering | `renderedInHumanTurn`                                            |
| Attachment load guard       | `transcript load: dropped`                                       |

## File locations

| File                                                     | Purpose                            |
|----------------------------------------------------------|------------------------------------|
| `<proj>/<sessionId>.jsonl`                               | Main session transcript            |
| `<proj>/<sessionId>/subagents/agent-<agentId>.jsonl`     | Subagent transcript                |
| `<proj>/<sessionId>/subagents/agent-<agentId>.meta.json` | Subagent sidecar (not JSONL)       |
| `<proj>/<sessionId>/subagents/workflows/<runId>/`        | Workflow run directory             |
| `~/.claude/history.jsonl`                                | Prompt history (other format)      |
| `~/.claude/dump-prompts/<sessionId>.jsonl`               | Debug API request dump (dead code) |
| `<errorDir>/errors.jsonl`                                | Error log sink                     |
| `<mcpLogsDir>/<serverName>.jsonl`                        | MCP server logs                    |
| `<debugDir>/bridge-transcript-<sessionId>.jsonl`         | Bridge subprocess stdout           |

`<proj>` is `~/.claude/projects/<encoded-cwd>`, where `<encoded-cwd>` is the project working
directory with path separators replaced by dashes (e.g.
`-Users-you-src-claude-expert`). The subagent transcript path is what the
SubagentStop hook reports as `agent_transcript_path` (see `HOOKS.md`).

Subagent transcripts use the same record format as the main transcript and carry both categories of
record: conversation records with `isSidechain: true` and an `agentId` are routed to the subagent
file, and the `route-by-agent` metadata types (`fork-context-ref`, `content-replacement`,
`observer-ref`) land there when they carry an `agentId`. The `agent-<agentId>.meta.json` sidecar is
a single JSON object (`agentType`, `description`, `toolUseId`), not JSONL.

A Workflow run keeps its agents' transcripts (`agent-<agentId>.jsonl`, same record format) together
with a `journal.jsonl` under `subagents/workflows/<runId>/`. The journal is a different format and
does not validate against the transcript schema: one `{type: "started", key, agentId}` line when an
agent starts and one `{type: "result", key, agentId, result}` line per completed agent (the Workflow
prompt describes it as `one {"type":"result",...} line per completed agent`), bracketed by
`{type: "restoring"}` / `{type: "restored"}` markers when a resume rewrites it. `key` is the
content hash used to return cached results on `resumeFromRunId`. Transcript tooling that globs
`**/*.jsonl` must skip `journal.jsonl`.

## Conversation structure

Messages form a linked list via `parentUuid`, not a flat sequence. The chain is reconstructed by
following `parentUuid` backward from leaf messages. After compaction, `logicalParentUuid` bridges
across a `compact_boundary` record whose own `parentUuid` is null.

## Record categories

Records fall into two categories:

1. Conversation records: `user`, `assistant`, `attachment`, `system` (and the legacy `progress`).
   Wrapped with envelope fields by the envelope writer.
2. Metadata-only records: every other `type`. Written without the envelope.

The authoritative list of record types the writer can emit is the pair of per-type policy tables
next to the transcript writer (grep `"atis-latch": "last-wins"` and `"atis-latch": "always"`); both
are object literals keyed by record `type`.

Load-retention table (how the loader keeps a type):

| Value              | Meaning                                                                 |
|--------------------|-------------------------------------------------------------------------|
| `transcript`       | Conversation record; joins the `parentUuid` chain                       |
| `boundary-cleared` | Dropped with the pre-compaction history when a load skips to a boundary |
| `accumulate`       | Every record kept and merged; also the default for an unlisted type     |
| `last-wins`        | The latest record (per session, or per key) wins                        |

Write-routing table (where the append goes):

| Value              | Meaning                                                                |
|--------------------|------------------------------------------------------------------------|
| `dedup-transcript` | Conversation records; skipped when the `uuid` is already in the file   |
| `always`           | Appended unconditionally to the session file                           |
| `route-by-agent`   | Subagent file when the record carries `agentId`, else the session file |

Under `dedup-transcript`, a sidechain record with an `agentId` is routed to that agent's subagent
file instead of the session file.

`progress` is still listed as `dedup-transcript` and `boundary-cleared`, but the transcript
persistence filter drops every `progress` record before it reaches the writer (the same predicate
drops an empty `hook_success` attachment; `tengu_dead_probe_legacy_progress_bridge` sits beside the
routing table). It is read only from old transcripts.

## Envelope fields

Every conversation record is wrapped with these fields by the envelope writer (grep
`logicalParentUuid` or `tengu_chain_self_reference_write`). The envelope is merged with the message
object via spread, so envelope fields appear at the top level. The message's own `uuid` becomes the
key in the session message Map on read. The persisted shape is `{parentUuid, logicalParentUuid,
isSidechain, teamName, agentName, promptId, agentId, ...message, ...sessionFields, gitBranch,
slug}`, where a shared helper supplies `{sessionKind, userType, entrypoint, cwd, sessionId,
version}`.

| Field               | Type                    | Description                                      |
|---------------------|-------------------------|--------------------------------------------------|
| `parentUuid`        | string or null          | UUID of previous message; null at                |
|                     |                         | `compact_boundary`                               |
| `logicalParentUuid` | string or undefined     | UUID bridging across compaction boundaries       |
| `isSidechain`       | boolean                 | Whether this is a subagent conversation          |
| `teamName`          | string or undefined     | Team name if in a team context                   |
| `agentName`         | string or undefined     | Agent name within a team                         |
| `promptId`          | string or undefined     | Originating prompt; set by the envelope writer   |
|                     |                         | on `user` only                                   |
| `userType`          | `"external"` or `"ant"` | Build flavor; public builds hard-code `external` |
| `cwd`               | string                  | Working directory at time of write               |
| `sessionId`         | string                  | Session UUID (matches the file name)             |
| `version`           | string                  | Claude Code version (e.g. `"2.1.281"`)           |
| `gitBranch`         | string or undefined     | Current git branch                               |
| `agentId`           | string or undefined     | Agent ID for subagent transcripts                |
| `slug`              | string or undefined     | Human-readable session slug                      |
| `entrypoint`        | string or undefined     | Raw `CLAUDE_CODE_ENTRYPOINT` (see below)         |
| `forkedFrom`        | object or undefined     | Source session/message this conversation was     |
|                     |                         | forked from                                      |
| `sessionKind`       | string or undefined     | `CLAUDE_CODE_SESSION_KIND` when a known kind     |
|                     |                         | (see below)                                      |
| `session_id`        | string or undefined     | Session that first emitted the record (see       |
|                     |                         | below)                                           |

- `userType`: the helper hard-codes `"external"`; `"ant"` appears only in internal builds.
- `entrypoint`: the raw `CLAUDE_CODE_ENTRYPOINT` value, not validated on the transcript path (the
  telemetry copy validates it), so treat it as an open string. Startup defaults are `cli`,
  `sdk-cli` (non-interactive), `mcp` (`mcp serve`) and `claude-code-github-action`; the SDKs set
  `sdk-ts` / `sdk-py`. The known set (grep `"claude-coworker-terminal": !0`) also includes
  `claude-vscode`, `claude-desktop`, `claude-desktop-3p`, `local-agent`, `bench`, the `remote*`
  family, `claude_in_slack` / `claude-in-slack`, `claude-in-teams`, `claude-security`,
  `ssh-remote`, `claude-coworker`, `claude-coworker-terminal`.
- `sessionKind`: the helper keeps only `bg`, `daemon`, and `daemon-worker` and omits the field
  otherwise. It is written on every envelope record. /resume hides daemon kinds (grep `filtered
  from /resume: sessionKind=`). Only `bg` is observed locally.
- `session_id` (snake case) is not written by the envelope helper. The query engine wraps every
  message it yields in `{...msg, session_id, uuid}` (grep `[engine] sdkEventQueue push key`), and
  records persisted from that stream keep the key inside the message spread. It therefore appears on
  many, not all, `user` / `assistant` / `attachment` / `system` records. It usually equals
  `sessionId`. It differs when records were carried into another session file (a branch, a fork, or
  a relocation): `sessionId` is rewritten to the new file's id, while `session_id` keeps the session
  that first emitted the record.

## Conversation record types

### `user` — human turn or tool result

Re-locate by grepping the record carrying `isCompactSummary` and `toolUseResult`; the
user-message factory is the function that also sets `turnCompanion` and `toolDenialKind`.

| Field                       | Type                 | Description                                |
|-----------------------------|----------------------|--------------------------------------------|
| `type`                      | `"user"`             | Record type discriminator                  |
| `uuid`                      | string               | UUIDv4                                     |
| `timestamp`                 | string               | ISO 8601                                   |
| `message.role`              | `"user"`             | Always "user"                              |
| `message.content`           | string or array      | Plain string for human turns, or content   |
|                             |                      | blocks (see below)                         |
| `isMeta`                    | boolean or undefined | True for injected meta-messages            |
| `isVisibleInTranscriptOnly` | boolean or undefined | Display-only message                       |
| `isCompactSummary`          | boolean or undefined | True when this is a compaction summary     |
| `summarizeMetadata`         | object or undefined  | Present on compaction summaries            |
| `toolUseResult`             | object or undefined  | Structured tool result data (see below)    |
| `mcpMeta`                   | object or undefined  | MCP-related metadata                       |
| `imagePasteIds`             | array or undefined   | IDs of pasted images                       |
| `sourceToolAssistantUUID`   | string or undefined  | UUID of the assistant record that issued   |
|                             |                      | the tool call                              |
| `sourceToolUseID`           | string or undefined  | Tool use ID that produced this result      |
| `interruptedMessageId`      | string or undefined  | Message ID interrupted by this turn        |
| `permissionMode`            | string or undefined  | Permission mode in effect (domain below)   |
| `planContent`               | string or undefined  | Plan text when submitted from plan mode    |
| `promptSource`              | string or undefined  | `typed`, `queued`, `suggestion_accepted`,  |
|                             |                      | `sdk`, `system`                            |
| `promptId`                  | string or undefined  | Identifier for the originating prompt      |
| `origin`                    | object or undefined  | Prompt origin metadata                     |
| `thinkingMetadata`          | object or undefined  | Contains `maxThinkingTokens` when thinking |
|                             |                      | is active                                  |
| `todos`                     | array or undefined   | Todo list state snapshot                   |

`permissionMode` is one of `default`, `acceptEdits`, `bypassPermissions`, `plan`, `dontAsk`,
`auto`. When `message.content` is an array, each block is one of: `tool_result`
(`{ type, tool_use_id, content, is_error? }`), `text`, `image` (base64 source), or `document`
(base64 source, e.g. a pasted PDF). A `tool_result`'s own `content` array can hold `text`, `image`,
and `tool_reference` (`{type, tool_name}`) items. The `toolUseResult` field is either an object
with tool-specific fields (commonly `stdout`, `stderr`, `interrupted`, `isImage`; Grep adds `mode`,
`numFiles`, `filenames`, `content`, `numLines`; nearly 200 distinct keys across tools), a plain
string (error output), or an array of content blocks.

Further fields, by purpose (the schema carries the per-field detail and domains):

- Turn classification. `turnOrigin` is stamped on the turn's prompt record: `human`, `sdk`,
  `scheduled`, `task_notification`, `auto_continuation`, `peer`, `host_synthetic`, `system`,
  `unknown` (grep `"host_synthetic",`); values outside the list are deleted on load.
  `turnCompanion: true` marks side-product records of the current turn (meta notes, skill/hook
  injections, usage-limit wrap-up) rather than a new human turn.
- Tool denial and feedback. `toolDenialKind` says why the tool call did not run: `user-rejected`,
  `permission-rule`, `automode-blocked`, `automode-unavailable`, `automode-parsing-error`,
  `interrupted`, `cancelled` (grep `a denied tool call is persisted as a`). `userFeedback` is the
  text typed when rejecting a permission prompt. `toolEndsTurn` marks a result that ends the turn
  without another model call.
- Auto-mode classifier. `classifierMetaLines` (newline-terminated `{"meta":{...}}` JSON lines),
  `classifierBoundary` (only ever `true`), and `serverClassifierContext` (`{request, context}`;
  `request` matches the issuing assistant record's `serverClassifierRequest`).
- Queue resurrection. `queuePriority` (only ever `"later"`), `queueOrigin`, `queueSkipAttachments`,
  `queueTranscriptOnly`: stamped by the queued-command drain so a resumed session can re-enqueue
  the command the same way (grep `admissionExempt: "resurrected"`).

The user-message factory also knows fields not observed on disk (`promptShellHandOff`, `ephemeral`,
`usageLimitNote`, `replacesSpan`, `isVirtual`, `hostClassifierContext`, `toolDenialEndsTurn`,
`toolResultRemedy`, `interruptedByShutdown`); some are likely stripped before the write.

### `assistant` — model response

Re-locate by grepping the record carrying `requestId` and `isApiErrorMessage`.

| Field                           | Type                | Description                             |
|---------------------------------|---------------------|-----------------------------------------|
| `type`                          | `"assistant"`       | Record type discriminator               |
| `uuid`                          | string              | UUIDv4                                  |
| `timestamp`                     | string              | ISO 8601                                |
| `requestId`                     | string or undefined | Anthropic API request ID                |
| `apiError`                      | object or undefined | API error details                       |
| `apiErrorStatus`                | int or undefined    | HTTP status of an API error (e.g. 429,  |
|                                 |                     | 529)                                    |
| `error`                         | string or object    | Error code on an API-error record (see  |
|                                 |                     | below)                                  |
| `isApiErrorMessage`             | boolean             | Whether this record represents an API   |
|                                 |                     | error                                   |
| `attributionSkill`              | string or undefined | Skill credited with this turn's work    |
| `attributionPlugin`             | string or undefined | Plugin credited with this turn's work   |
| `attributionMcpServer`          | string or undefined | MCP server credited with this turn's    |
|                                 |                     | work                                    |
| `attributionMcpTool`            | string or undefined | MCP tool credited with this turn's work |
| `attributionAgent`              | string or undefined | Subagent type credited with this turn's |
|                                 |                     | work                                    |
| `message.id`                    | string              | Anthropic message ID (e.g. `msg_01…`)   |
| `message.model`                 | string              | Model ID (e.g. `"claude-opus-4-8"`)     |
| `message.role`                  | `"assistant"`       | Always "assistant"                      |
| `message.type`                  | `"message"`         | Always "message"                        |
| `message.stop_reason`           | string or null      | See below; null while streaming         |
| `message.stop_sequence`         | string or null      | The stop sequence if applicable         |
| `message.stop_details`          | object or null      | Refusal details (e.g.                   |
|                                 |                     | `category: "cyber"`)                    |
| `message.diagnostics`           | object or null      | e.g. `cache_miss_reason`                |
| `message.input_transformations` | array or undefined  | Server-side input edits, e.g.           |
|                                 |                     | `thinking_dropped`                      |
| `message.container`             | null                | Reserved                                |
| `message.context_management`    | object or null      | Context management data                 |
| `message.content`               | array               | Content blocks (see below)              |
| `message.usage`                 | object              | Token usage (see below)                 |

`message.stop_reason` is one of `end_turn`, `stop_sequence`, `tool_use`, `max_tokens`, `refusal`,
`pause_turn`, `compaction`, `model_context_window_exceeded` (grep
`"model_context_window_exceeded",`), or null. The string `error` codes come from the SDK
assistant-error list (grep `"cloud_credential_error",`): `authentication_failed`,
`oauth_org_not_allowed`, `account_on_hold`, `verification_required`, `billing_error`,
`rate_limit`, `overloaded`, `invalid_request`, `model_not_found`, `server_error`, `unknown`,
`max_output_tokens`, `cloud_credential_error`.

Further fields, by purpose:

- Effort. `effort` is the request's `output_config.effort` (`low`, `medium`, `high`, `xhigh`,
  `max`); `perTurnEffort` is a per-turn override or null, and resume prefers it over `effort`.
- Request context. `advisorModel` (advisor tool model, when one was active), `attributionAgent`
  (from a query source of `agent:builtin:<name>` / `agent:custom:<name>`).
- Streaming. `apiBlockIndex` is the API content-block index each streamed record carries;
  `isAbortedMidStream` keeps a partial text block after an abort.
- Wire fidelity. `wireToolInputs` (tool input as received, before normalization; telemetry lane
  `tether_wire_tool_input`) and `wireIngestContext` (e.g. `{cwd}` stripped from a Bash command),
  both keyed by `tool_use` id.
- Auto-mode classifier. `serverClassifierRequest` is the classifier request key that the resulting
  `tool_result` records echo in `serverClassifierContext.request`.
- Errors. `truncatedAfterOutput` ("The response above may be incomplete."), `errorDetails` (raw
  error text), `quotaLimits` (rate-limit state from the `anthropic-ratelimit-unified-*` headers).
- Refusal fallback. `supersedesUuids` lists earlier assistant records this one replaces
  (`tengu_refusal_fallback_supersedes`).

Content block types in `message.content`:

| Block type    | Key fields                                                                       |
|---------------|----------------------------------------------------------------------------------|
| `"thinking"`  | `thinking` (text), `signature` (string)                                          |
| `"text"`      | `text` (string)                                                                  |
| `"tool_use"`  | `id`, `name`, `input` (object), `caller: { type: "direct" }`                     |
| `"fallback"`  | `from: {model}`, `to: {model}` — a server-side model switch mid-response         |
| server blocks | `redacted_thinking`, `server_tool_use`, `*_tool_result`, `compaction`, … (below) |

The `fallback` block is normalized to `from` / `to` only (grep `type: "fallback", from: { model:`);
the raw API block may also carry a `trigger`. It is observed locally. The server-side block types
(`redacted_thinking`, `server_tool_use`, `web_search_tool_result`, `web_fetch_tool_result`,
`advisor_tool_result`, `code_execution_tool_result`, `bash_code_execution_tool_result`,
`text_editor_code_execution_tool_result`, `tool_search_tool_result`, `mcp_tool_use`,
`mcp_tool_result`, `container_upload`, `compaction`) come from the same list that includes
`"fallback"` (grep `"text_editor_code_execution_tool_result",`); the normalizer passes unknown types
through. None of them is observed locally.

Usage object (`message.usage`) — the canonical field reference; `MONITORING_USAGE.md` points here:

| Field                                      | Type                     |
|--------------------------------------------|--------------------------|
| `input_tokens`                             | int                      |
| `output_tokens`                            | int                      |
| `cache_creation_input_tokens`              | int                      |
| `cache_read_input_tokens`                  | int                      |
| `cache_creation.ephemeral_1h_input_tokens` | int                      |
| `cache_creation.ephemeral_5m_input_tokens` | int                      |
| `server_tool_use.web_search_requests`      | int                      |
| `server_tool_use.web_fetch_requests`       | int                      |
| `service_tier`                             | string or null           |
| `inference_geo`                            | string or null           |
| `iterations`                               | int, array, or null      |
| `speed`                                    | number, string, or null  |
| `output_tokens_details.thinking_tokens`    | int (object may be null) |

`iterations` array items are `{type: "message" | "fallback_message", model, token counts}`; a
server-side model fallback adds the `fallback_message` entry. `speed` is observed only as
`"standard"` or null, and `inference_geo` also as `""`.

The same `message.id` appears on several consecutive assistant records: each streamed content
block is persisted as its own record (`apiBlockIndex` says which), and the first ones carry
`stop_reason: null` while the last carries the final `stop_reason`. This is a streaming artifact.

### `progress` — tool/hook progress (legacy)

Not written: the transcript persistence filter drops every `progress` record (see Record
categories). Old transcripts carry it, and the loader keeps it as `boundary-cleared`. Re-locate by
grepping `toolUseID` alongside `parentToolUseID`.

| Field             | Type                | Description                  |
|-------------------|---------------------|------------------------------|
| `type`            | `"progress"`        | Record type discriminator    |
| `uuid`            | string              | UUIDv4                       |
| `timestamp`       | string              | ISO 8601                     |
| `toolUseID`       | string              | Tool use ID this relates to  |
| `parentToolUseID` | string or undefined | Parent tool use ID           |
| `data`            | object              | Progress payload (see below) |

The `data` object commonly contains `data.type` (e.g. `"hook_progress"`), `data.hookEvent` (e.g.
`"PreToolUse"` / `"PostToolUse"`), `data.hookName` (e.g. `"PreToolUse:Bash"`), `data.command`, and
`data.message`. Any `normalizedMessages` within `data` was cleared to `[]` before writing.

### `attachment` — structured event, notification, or model context

Re-locate by grepping the record whose payload is keyed by `attachment` and discriminated by
`attachment.type`.

| Field                 | Type               | Description                                         |
|-----------------------|--------------------|-----------------------------------------------------|
| `type`                | `"attachment"`     | Record type discriminator                           |
| `uuid`                | string             | UUIDv4                                              |
| `timestamp`           | string             | ISO 8601                                            |
| `attachment`          | object             | Payload, discriminated by `attachment.type`         |
| `rendered`            | array or undefined | Frozen model-facing text, `[{content}]` per message |
| `renderedInHumanTurn` | array or undefined | `queued_command` only: alternate same-turn framing  |

Every attachment record comes from one factory that wraps the payload as `{attachment, type:
"attachment", uuid, timestamp, ...rendered}` (`queued_command` and `poll_events` take the record
timestamp from `attachment.timestamp` when present). The model-facing text comes from a renderer
map keyed by subtype plus a trailing `switch`; a renderer that returns nothing means the record is
transcript/UI state only and never reaches the model.

What is persisted. The persistence filter drops only an empty `hook_success` (no content, stdout,
or stderr) and a `cowork_memory_context` with `leg: "laptop"`; every other attachment that reaches
the message list is written. Some subtypes never reach the transcript: `batching_reminder` and
`secondary_reminder` are spliced into the API request only (their persisted counterparts are the
`*_sent` subtypes), and `async_hook_response_batch` / `teammate_shutdown_batch` are display-only
collapses built by the message-grouping UI.

What is loaded. A payload-shape guard drops malformed records ("transcript load: dropped N
attachment entries with a missing or malformed payload"); it checks `invoked_skills`,
`hook_success`, `skill_listing`, `hook_additional_context`, `task_reminder` / `todo_reminder`, and
`file` / `already_read_file`. Retired subtypes are accepted silently and render nothing; any other
unknown subtype logs "Unknown attachment type".

#### Frozen rendering: `rendered` / `renderedInHumanTurn`

The factory renders the payload at write time and, when every resulting message is a string or
text-only, stores it as `rendered: [{content}]`, one entry per message. `queued_command` is rendered
a second time with the in-human-turn framing and stored as `renderedInHumanTurn` only when it
differs. Neither field is written when the payload renders to nothing, when any block is non-text
(images), for `poll_events`, or when rendering throws; replacing a payload recomputes both.

When the conversation is rebuilt for the API, a valid stored `rendered` overlays the fresh render
(metadata such as `isMeta`, `origin`, `uuid` still comes from current code); if the message count
differs, each stored entry becomes its own meta user message. The effect: a resumed session sends
the same reminder bytes the earlier CLI version sent, so wording changes in a newer release do not
rewrite old history, and the prompt-cache prefix survives. Exceptions: `deferred_tools_delta` when
the caller supplies a different surfaced-tool set, and `queued_command` records in a subagent
transcript loaded for resume, which have both fields deleted and render fresh (landmark
`subagent_resume_transcript_missing`).

#### Context announcements: system-prompt context as attachments

Session context (date, environment, CLAUDE.md, and the like) travels as attachment records instead
of being rebuilt in the system prompt on every request, so the system prompt bytes stay stable when
the date, environment, or CLAUDE.md change.

1. Session start drains the `userContext` / `systemContext` maps: `claudeMd` becomes per-file
   `instructions` entries (`files[]` of path, `type`, trimmed content; `type` is `User`, `Project`,
   `Local`, `Managed`, `AutoMem`, `AutoMemPinned`); `currentDate` becomes `date`; `userEmail`,
   `attachedProject`, `gitStatus`, `perforceMode` become `session_context`; `workerToolsContext`
   becomes `coordinator_context`; every other non-empty key becomes `context_sections`. Only
   `cacheBreaker` stays in `systemContext`.
2. Per-turn producers emit the rest: `environment` (the "# Environment" section, "You have been
   invoked in the following environment: ", as `snapshot`), `model` (`identity`, `text`: "You are
   powered by the model named …"), and `output_style_instructions` / `language` from session
   settings.
3. `prompt_snapshot` freezes whatever remains in the system prompt: the rendered prompt blocks, the
   tool definitions, and the identity prefix (`cliPrefix`). Later requests and resumes reuse the
   record until compaction. The SDK initialize option `systemPromptSnapshot` ("Record the
   conversation's system prompt once and reuse it verbatim") controls it; recording is on unless
   `CLAUDE_CODE_SIMPLE` is set, and forced on for `CLAUDE_CODE_SESSION_KIND=bg` and
   `CLAUDE_CODE_REMOTE`.
4. Each announcement renders as a `<system-reminder>` meta user message ("As you answer the user's
   questions, you can use the following context:", "Today's date is …", "# Environment", "# Output
   Style: <name>"), frozen into `rendered` at write time.

Each announcement is diffed against the last matching record in the transcript and re-emitted only
when something changed, with `changed: true` and, for `instructions` and `session_context`, a
`reason` from `session_start`, `compaction`, `policy_refresh`, `directory_added`, `settings_sync`,
`account_change`, `hooks_invalidate`, `policy_verdict` ("Instruction files were re-read", "The
session context was re-read"). `environment` is re-sent in full when there is no earlier full copy
or platform/shell/osVersion differ; otherwise it carries `changes` alongside the current `snapshot`,
rendered under "# Environment update". Every emission fires `tengu_context_announcement`
(`announcement_type`, `updates_copy`, `refresh_reason`). After compaction the announcer re-places
these records behind the summary (`compact_kept_tail_announcements`). The family is skipped on
resume, for bare forks, isolated contexts, most auxiliary query sources, and under
`CLAUDE_CODE_SIMPLE`. The persisted transcript is therefore the record of what the model was told. A
date change is announced by `date` with `changed`; `date_change` is legacy.

#### Subtypes by purpose

`attachment.type` is an open set. The schema has a `$def` per subtype with field-level notes; this
table only groups them. Relocate a constructor with `rg -n 'type: "<subtype>"'`. "Bookkeeping"
subtypes render to nothing and are filtered out of API history.

| Purpose                | Subtypes                                                                |
|------------------------|-------------------------------------------------------------------------|
| Context announcements  | `instructions`, `date`, `session_context`, `environment`, `model`,      |
|                        | `output_style_instructions`, `language`, `coordinator_context`,         |
|                        | `context_sections`, `prompt_snapshot`, `prompt_render_point`; legacy    |
|                        | `date_change`                                                           |
| Tool and agent surface | `deferred_tools_delta`, `deferred_tools_record`,                        |
|                        | `mcp_instructions_delta`, `mcp_dropped_tools_delta`,                    |
|                        | `agent_listing_delta`, `skill_listing`, `invoked_skills`,               |
|                        | `dynamic_skill`, `command_permissions`, `tool_search_usage_reminder`,   |
|                        | `tool_hosts_notice`, `tool_hosts_correction`, `tool_host_result_lines`, |
|                        | `advisor_tool`, `advisor_stripped`, `bash_output_audience_note`,        |
|                        | `sandbox_instructions`                                                  |
| Hooks                  | `hook_success`, `hook_additional_context`, `hook_blocking_error`,       |
|                        | `hook_non_blocking_error`, `hook_error_during_execution`,               |
|                        | `hook_cancelled`, `hook_system_message`, `hook_stopped_continuation`,   |
|                        | `hook_permission_decision`, `hook_deferred_tool`, `async_hook_response` |
| Files, IDE, mentions   | `file`, `already_read_file`, `compact_file_reference`, `directory`,     |
|                        | `edited_text_file`, `edited_image_file`, `nested_memory`,               |
|                        | `pdf_reference`, `read_truncation_notice`, `inlined_image_paths`,       |
|                        | `at_mention_reference`, `mcp_resource`, `opened_file_in_ide`,           |
|                        | `selected_lines_in_ide`, `selected_lines_in_diff`, `diagnostics`,       |
|                        | `dir_sync_notice`, `artifact_opening_prefetch`                          |
| Modes                  | `plan_mode`, `plan_mode_reentry`, `plan_mode_exit`,                     |
|                        | `plan_file_reference`, `auto_mode`, `auto_mode_exit`, `output_style`,   |
|                        | `ultra_effort_enter`, `ultra_effort_exit`, `ultrathink_effort`          |
| Turn flow and tasks    | `queued_command`, `poll_events`, `task_reminder`, `todo_reminder`,      |
|                        | `task_status`, `structured_output`, `max_turns_reached`, `goal_status`, |
|                        | `silent_turn_reminder`, `unknown_command_fallback`,                     |
|                        | `workflow_keyword_request`, `workflow_size_guideline_change`            |
| Budgets and reminders  | `total_tokens_reminder`, `token_usage`, `output_token_usage`,           |
|                        | `budget_usd`, `batching_reminder_sent`, `secondary_reminder_sent`,      |
|                        | `critical_system_reminder`                                              |
| Model and thinking     | `thinking_drop`, `thinking_stripped`, `credential_org`                  |
| Teams, peers, remote   | `agent_mention`, `peer_mention`, `team_context`, `teammate_mailbox`,    |
|                        | `remote_session_change`, `fork_briefing`, `thread_state`                |
| Memory                 | `relevant_memories`, `memory_update`, `cowork_memory_context`           |
| Retired (load-only)    | `ultramemory`, `new_file`, `new_directory`, `todo`, `task_progress`,    |
|                        | `autocheckpointing`, `background_task_status`, `compaction_reminder`,   |
|                        | `current_session_memory`, `thinking_reminder`, `companion_intro`,       |
|                        | `pen_mode_enter`, `pen_mode_exit`, `ultrawork_request`,                 |
|                        | `echo_activities`, `verify_plan_reminder`, `fold_nudge`, `context_tip`  |

Bookkeeping (render to nothing, filtered from API history): `prompt_snapshot`,
`prompt_render_point`, `deferred_tools_record`, `thinking_drop`, `credential_org`. Other subtypes
whose renderer returns nothing (transcript/UI state): `already_read_file`, `command_permissions`,
`edited_image_file`, `hook_cancelled`, `hook_error_during_execution`, `hook_non_blocking_error`,
`hook_system_message`, `hook_permission_decision`, `hook_deferred_tool`, `goal_status`,
`structured_output`, `max_turns_reached`, `batching_reminder_sent`, `secondary_reminder_sent`.

### `system` — system events

Common fields: `type` (`"system"`), `subtype`, `uuid`, `timestamp`, optional `level`, optional
`isMeta`, `content` (human-readable). Every internal system message that reaches the message list
is persisted (the transcript filter has no system-subtype exclusions), so the subtype domain is the
set of internal system-message builders. SDK stream frames (snake_case, carrying
`compact_metadata`, `original_model`, …) are a separate wire format and are not written to the
JSONL, though the SDK schemas (grep `From internal SystemMessage`) are the best source of field
semantics.

`level` is one of `info`, `notice`, `suggestion`, `warning`, `error`. `notice` renders in inactive
gray; informational banners (hook `says:` lines, "Claude auto-replied to … while you were away",
goal notices) and `cloud_session_status` use it.

`isMeta` is not always true. 2.1.281 writes `false` on nearly every subtype, `true` only on
`file_snapshot`, and omits it on `api_error`, `stop_hook_summary`, and `upgrade_relay_marker`.

| Subtype                     | `level`    | Extra fields / notes                                  |
|-----------------------------|------------|-------------------------------------------------------|
| `compact_boundary`          | info       | `compactMetadata`, `logicalParentUuid?` (see below)   |
| `local_command`             | info       | `content`, `hasOutput`, `toolUseID`, `commandRun`,    |
|                             |            | `commandOutcome`, `contextUsage`, `usageReport`       |
| `api_error`                 | error      | `error` (plain-data snapshot), `retryInMs`,           |
|                             |            | `retryAttempt`, `maxRetries`, `source`; `cause`       |
|                             |            | legacy                                                |
| `stop_hook_summary`         | suggestion | `hookInfos`, `hookCount`, `hookErrors`, `stopReason`, |
|                             |            | `preventedContinuation`, `pendingWorkflowCount`,      |
|                             |            | `pendingBackgroundAgentCount`,                        |
|                             |            | `hookAdditionalContext`                               |
| `turn_duration`             | omitted    | `durationMs`, `messageCount`; `budgetTokens` /        |
|                             |            | `budgetLimit` / `budgetNudges` under a token budget   |
| `away_summary`              | omitted    | Summary written while the user is away                |
| `bridge_status`             | omitted    | Remote-control status; `url`, `upgradeNudge`          |
| `scheduled_task_fire`       | omitted    | `taskId`, `cron`, `prompt`, `taskKind`, `cronKind`,   |
|                             |            | `noOpStreak`, `streakStartedAt`, `foldedUuids`        |
| `informational`             | varies     | Generic banner; `toolUseID`, `preventContinuation`    |
|                             |            | from the tool-scoped builder                          |
| `agents_killed`             | omitted    | Background agents terminated (e.g. on interrupt)      |
| `permission_retry`          | info       | `commands` (content "Allowed <commands>")             |
| `model_refusal_fallback`    | warning    | `trigger`, `direction`, `scope`, `originalModel`,     |
|                             |            | `fallbackModel`, `requestId`, `apiRefusalCategory`,   |
|                             |            | `apiRefusalExplanation`, `retractedMessageUuids`,     |
|                             |            | `refusedUserMessageUuid`, `sawCyberRefusal?`,         |
|                             |            | `provisional?`                                        |
| `model_refusal_no_fallback` | warning    | `originalModel`, `requestId`, `apiRefusalCategory`,   |
|                             |            | `apiRefusalExplanation`, `refusedUserMessageUuid`     |
| `model_consent_fallback`    | warning    | `choice`, `originalModel`, `originalModelName`,       |
|                             |            | `fallbackModel`, `persistedAsDefault`                 |
| `model_fallback`            | warning    | `trigger` (`model_not_found`, `permission_denied`,    |
|                             |            | `overloaded`, `server_error`, `last_resort`,          |
|                             |            | `model_blocked`), `originalModel`, `fallbackModel`    |
| `memory_saved`              | omitted    | `writtenPaths`, `teamCount`, `verb`                   |
| `cloud_session_status`      | notice     | `entry` (`create` / `attach`), `url`                  |
| `file_snapshot`             | info       | `snapshotFiles`                                       |
|                             |            | `[{key: plan \| workshop, path, content}]`;           |
|                             |            | `isMeta: true`                                        |
| `upgrade_relay_marker`      | info       | CCR worker handoff only; `content` is JSON naming     |
|                             |            | `anchor_line_uuid`                                    |
| `microcompact_boundary`     | —          | Legacy, read only (see Compaction)                    |

`model_fallback`, `memory_saved`, `cloud_session_status`, `file_snapshot`, and
`upgrade_relay_marker` are source-only (not observed locally). Landmarks for the less obvious
builders: `/remote-control is active` (`bridge_status`), `loop_noop_fold` (`scheduled_task_fire`),
`requires usage credits` (`model_consent_fallback`), `[extractMemories] writtenPaths=`
(`memory_saved`), `Attached to cloud session` (`cloud_session_status`), `Plan over snapshot cap`
(`file_snapshot`), `planRelayFromHandoff` (`upgrade_relay_marker`). `read_divider` and `thinking`
have renderers but no builder, and `task_notification`, `status`, `init`, `api_retry`,
`session_state_changed`, and similar are SDK-stream frames only; none of them is persisted.

`compact_boundary` — `compactMetadata.trigger` (`manual` / `auto`), `.preTokens`, `.postTokens`,
`.userContext?`, `.messagesSummarized?`, `.cumulativeDroppedTokens`, `.durationMs`,
`.precomputed`, `.preCompactDiscoveredTools`, `.preservedSegment` (`{headUuid, anchorUuid,
tailUuid}`), `.preservedMessages` (`{anchorUuid, uuids, allUuids?}`), plus `logicalParentUuid?`.

## Metadata-only record types

Written without envelope fields (no `uuid`, `parentUuid`, `cwd`, or `version`). Load and Write are
the policy-table values (see Record categories). Status: `observed` in real transcripts, `source`
(writer present in 2.1.281 but not observed locally), or `legacy` (no writer).

| Record type                 | Load             | Write          | Status   |
|-----------------------------|------------------|----------------|----------|
| `custom-title`              | last-wins        | always         | observed |
| `ai-title`                  | last-wins        | always         | observed |
| `tag`                       | last-wins        | always         | observed |
| `agent-name`                | last-wins        | always         | observed |
| `agent-color`               | last-wins        | always         | observed |
| `agent-setting`             | last-wins        | always         | observed |
| `mode`                      | last-wins        | always         | observed |
| `permission-mode`           | last-wins        | always         | observed |
| `pr-link`                   | last-wins        | always         | observed |
| `summary`                   | last-wins        | always         | observed |
| `last-prompt`               | boundary-cleared | always         | observed |
| `file-history-snapshot`     | boundary-cleared | always         | observed |
| `file-history-delta`        | boundary-cleared | always         | observed |
| `attribution-snapshot`      | last-wins        | always         | observed |
| `queue-operation`           | last-wins        | always         | observed |
| `bridge-session`            | last-wins        | always         | observed |
| `worktree-state`            | last-wins        | always         | observed |
| `atis-latch`                | last-wins        | always         | observed |
| `continued-in`              | boundary-cleared | always         | observed |
| `cost-state`                | last-wins        | always         | observed |
| `fork-context-ref`          | accumulate       | route-by-agent | observed |
| `frame-link`                | accumulate       | always         | observed |
| `history-suppression`       | last-wins        | always         | observed |
| `relocated`                 | last-wins        | always         | observed |
| `artifact-comment-monitor`  | accumulate       | always         | observed |
| `artifact-autoreact-ledger` | last-wins        | always         | observed |
| `content-replacement`       | accumulate       | route-by-agent | source   |
| `ended-by-model`            | last-wins        | always         | source   |
| `isolation-latch`           | last-wins        | always         | source   |
| `memory-mode`               | accumulate       | always         | source   |
| `observer-ref`              | last-wins        | route-by-agent | source   |
| `speculation-accept`        | —                | —              | legacy   |

Shapes (every record also carries `type`). Most carry `sessionId`; the exceptions say so.

- `custom-title` `{customTitle, sessionId}`: user-set title. `ai-title` `{aiTitle, sessionId}`:
  auto-generated title, distinct from `custom-title`.
- `tag` `{tag, sessionId}`, `agent-name` `{agentName, sessionId}`, `agent-color`
  `{agentColor, sessionId}`.
- `agent-setting` `{agentSetting, sessionId}`: `agentSetting` is a string, the `agentType` of the
  main-thread agent the session runs as (from `--agent` or the `agent` setting), e.g.
  `"general-purpose"`.
- `mode` `{mode, sessionId}`; `permission-mode` `{permissionMode, sessionId}`: the active
  permission mode, distinct from `mode`.
- `pr-link` `{sessionId, prNumber, prUrl, prRepository, timestamp}`.
- `summary` `{summary, leafUuid}`: keyed by `leafUuid`, no `sessionId`.
- `last-prompt` `{sessionId, lastPrompt?, leafUuid?, explicit?, rewound?}`: the most recent
  prompt. `explicit: true` / `rewound: true` come from the leaf checkpoint written by rewind and
  branch (`persistLeafCheckpoint`); there `leafUuid` may be null (rewind to before the first
  message). Backgrounding also writes `{sessionId, leafUuid, explicit: true}` with no
  `lastPrompt`.
- `file-history-snapshot` `{messageId, snapshot, isSnapshotUpdate}`, no `sessionId`: `snapshot`
  contains `messageId`, `trackedFileBackups` (file path → backup descriptor `{backupFileName |
  null, version, backupTime, realParentDir?}`), and `timestamp`.
- `attribution-snapshot` `{messageId, …otherFields}`.
- `queue-operation` `{operation, timestamp, sessionId, content?, reason?}`: operations are
  `"enqueue"`, `"dequeue"`, `"remove"`, `"popAll"`; `reason` is written only on `remove`
  (observed: `absorbed_mid_turn`).
- `bridge-session` `{sessionId, bridgeSessionId, lastSequenceNum, …}`: optional
  `declaredDialogKinds`, `sessionGroupingId`, `noHistoryBackfill` (only `true`),
  `ownerAccountUuid`, `ownerOrganizationUuid` (an invalid owner UUID voids both on load). Clearing
  the link (`clearBridgeSession: transcript append failed`) writes `bridgeSessionId: ""` and
  `lastSequenceNum: 0`.
- `worktree-state` `{sessionId, worktreeSession}`: `worktreeSession` is null or an object carrying
  `originalCwd`, `worktreePath`, `worktreeName`, `worktreeBranch`, `originalBranch`.
- `speculation-accept` `{timestamp, timeSavedMs}`, no `sessionId`: no writer and no string
  occurrence in 2.1.281; kept in the schema so older transcripts validate.
- `atis-latch` `{atis, sessionId}`: an opaque server pin from cached bootstrap client data, sent
  as request header `x-cc-atis` (a mismatch logs "Server ATIS pin differs from cached clientData;
  refetching"). It is latched per conversation on the first request when `tengu_kestrel_moor` is
  on, and stamped before a message chain whenever the latch differs from the file's last stamp.
  `atis` is `""` when there was no pin; the reader accepts only printable ASCII.
- `continued-in` `{timestamp, sessionId, continuedInSessionId}`: written into the parent's
  transcript when a session is backgrounded (`tengu_background`); /resume then hides the parent
  (`filtered from /resume: continued in`). Landmark: `[bg] continued-in record not written`.
- `cost-state` `{sessionId, totalCostUSD, totalAPIDuration, totalAPIDurationWithoutRetries,
  totalToolDuration, totalLinesAdded, totalLinesRemoved, totalDuration, startTime, modelUsage,
  hasUnknownModelCost}`: the cost ledger, `modelUsage` keyed by model name. Re-stamped at exit and
  on /clear; the loader validates it and drops invalid records.
- `file-history-delta` `{messageId, snapshotMessageId, trackingPath, backup, timestamp}`, no
  `sessionId`: written when an edit first touches a file in the turn, adding one backup to the
  turn's snapshot instead of rewriting it (`FileHistory: Failed to record delta`,
  `tengu_file_history_track_edit_success`). `backup` has the `trackedFileBackups` value shape.
- `fork-context-ref` `{agentId, parentSessionId, parentLastUuid, contextLength}`, no `sessionId`:
  written only into a subagent transcript when a forked subagent inherits the parent's messages;
  it points at the parent session and its last message instead of copying them.
- `frame-link`: an Artifact publish writes `{sessionId, path, frameUrl, title, artifactCount,
  timestamp}`; the metadata re-append writes `{artifactCount, sessionId, timestamp}`. The reader
  counts `max(artifactCount, distinct frameUrl)`.
- `history-suppression` `{sessionId, cause, vetoedAgainstAccountUuid?, ts}`: a sticky mark that
  the session's prior history is suppressed; forks inherit it. `cause` is one of `fork_inherit`,
  `meta_seed`, `chokepoint_veto`, `restored_owner_mismatch`, `env_owner_mismatch` (the last three
  from remote-control cross-account vetoes, `rc_cross_account_suppression`), or `migration`,
  which the metadata re-append always writes, so the original cause is lost after a resume. Uses
  `ts`, not `timestamp`. Landmark: `writeHistorySuppression: transcript append failed`.
- `relocated` `{sessionId, relocatedCwd}`: the transcript was moved to another project directory
  (`relocateSessionTranscript: relocated stamp failed`).
- `artifact-comment-monitor` `{v: 1, sessionId, artifacts}`: per artifact `{state: armed |
  stopped, writtenAtMs, title?, holder…?}`; holder fields appear only on monitors held by a
  background session (`holder: "bg"`).
- `artifact-autoreact-ledger` `{v: 1, sessionId, accountUuid, artifacts}`: which artifact
  comments were auto-reacted to, per account. The reader is strict at every level and has a
  byte-prefix fast path on `{"type":"artifact-autoreact-ledger","v":1,"sessionId":"`, so key
  order matters.
- Source only: `content-replacement` `{sessionId, agentId?, replacements: [{kind: "tool-result",
  toolUseId, replacement}]}` pairs with `tengu_tool_result_persisted_message_budget`;
  `ended-by-model` `{timestamp, sessionId}` with `tengu_end_conversation_tool_call`
  (`markSessionEndedByModel: transcript append failed`); `isolation-latch` `{side: web |
  connectors, sessionId}` is gated by `tengu_doorbell_agave` (`saveIsolationLatch: failed to
  append`); `memory-mode` `{mode: on | off, afterUuid, timestamp, reason?, account?, sessionId}`
  logs `saveMemoryMode: failed to append memory-mode entry`; `observer-ref` `{agentId?,
  observerTaskId, observerAgentType, timestamp}` pairs with `agent_observer_delivery`.

## JSONL parser

All JSONL files pass through one parser. On Bun it uses `Bun.JSONL` chunk parsing with error
recovery; on Node it splits on newline (string) or byte 10 (Buffer) and `JSON.parse`s each line.
Empty and malformed lines are silently discarded.

## Read path

A full read returns an object whose Map fields key the metadata-only records by `sessionId` (and
`messageId` / `leafUuid` / `agentId` where noted): `messages` (by `uuid`), `summaries` (by
`leafUuid`), `customTitles`, `endedSessions`, `aiTitles`, `tags`, `relocatedCwds`, `agentNames`,
`agentColors`, `agentSettings`, `prNumbers`, `prUrls`, `prRepositories`, the `bridge*` maps
(`bridgeSessionIds`, `bridgeLastSeqs`, `bridgeDialogKindsBySession`, `bridgeSessionGroupingIds`,
`bridgeNoBackfill`, `bridgeOwnerAccountUuids`, `bridgeOwnerOrganizationUuids`),
`historySuppressed`, `modes`, `permissionModes`, `isolationLatches`, `memoryModeStamps`,
`atisLatches`, `worktreeStates`, `artifactCommentMonitors`, `artifactAutoReactLedgers`,
`costStates`, `fileHistorySnapshots` and `fileHistoryDeltas` (by `messageId`),
`attributionSnapshots` (by `messageId`), `contentReplacements` / `agentContentReplacements`,
`forkContextRefs` (by `agentId`), and `leafUuids` (a Set). Grep `attributionSnapshots` to locate
it.

For very large files (size-gated), the read path scans for the last `compact_boundary` and loads
only post-compaction content; `boundary-cleared` types are dropped with the skipped history. Setting
`CLAUDE_CODE_DISABLE_PRECOMPACT_SKIP` disables that and forces a full load.

Lite mode reads only filesystem metadata; hydration does fast string-scanning of head/tail bytes for
key fields without full JSON parsing. That is why the session-metadata re-append (below) keeps
current copies of the last-wins metadata near the tail of the file.

## Write path

Every record, conversation or metadata, enters through one append entry point that looks up the
write-routing table (`dedup-transcript`, `always`, `route-by-agent`) to pick the target file, then
goes through an async write queue that batches and appends via `fs/promises` `appendFile`. The
drain interval (`FLUSH_INTERVAL_MS`) is 100 ms, dropped to 10 ms when remote ingress or the CCR v2
internal event writer is active; batches cap at 100 MB (`MAX_CHUNK_BYTES`). Files are created mode
`0o600` (owner read/write only).

The session-metadata re-append re-stamps the current last-wins metadata (titles, tag, mode,
`atis-latch`, `relocated`, `history-suppression`, `frame-link` count, and similar) at the tail of
the file, asynchronously once enough bytes have been written since the last re-append (failure logs
"Metadata re-append failed") and synchronously via `appendFileSync` at exit; `cost-state` is
registered as an exit re-stamp provider. Fork and branch copies carry these records into the new
file as well.

## Compaction

When the conversation approaches context limits, a `compact_boundary` system record is written with
`compactMetadata` (trigger, pre- and post-compaction token counts, messages summarized, preserved
segment); its `parentUuid` is set to null, breaking the linked list, while `logicalParentUuid`
preserves the logical chain. A user record with `isCompactSummary: true` follows, carrying the
summary. `microcompact_boundary` is a legacy record of a lighter pass that trimmed specific tool
results (`microcompactMetadata.compactedToolIds`) and attachments (`.clearedAttachmentUUIDs`);
nothing constructs it (`microcompactMetadata` does not occur in the bundle), but readers stop at it
and render it. Full behavioral model: `CLEAR_COMPACT_FORK_CONTEXT.md`.

## history.jsonl

Separate file at `~/.claude/history.jsonl`, distinct from session transcripts. Each line:

```
{
  display:        string               -- display text of the prompt
  pastedContents: {
    [id: number]: {
      id:           int
      type:         "text" | "image"
      content?:     string             -- inline if <= 1024 chars
      contentHash?: string             -- hash pointer if > 1024 chars
      mediaType:    string | undefined
      filename:     string | undefined
    }
  }
  timestamp:  number                   -- epoch ms
  project:    string                   -- cwd path
  sessionId:  string                   -- session UUID
}
```

## MCP and error log formats

MCP debug entry: `{ debug, timestamp, sessionId, cwd }`. MCP error entry:
`{ error, timestamp, sessionId, cwd }`. General error entry: `{ error }`.
