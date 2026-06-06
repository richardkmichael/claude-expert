# Session Transcript Format

Behavioral model verified against 2.1.165. This document follows the landmark style in
`GUIDELINES.md`: it anchors on version-stable strings (record `type` discriminants, field names,
the JSONL path patterns, env vars, behavioral logic) with grep re-location recipes, not on minified
symbol names or line numbers, which churn every release. The field and record names are themselves
the durable contract. Per-release changes are in the appendix.

Claude Code persists conversation state as JSONL (newline-delimited JSON): one self-contained JSON
object per line, terminated by `\n`. There is no official schema. A companion JSON Schema
(Draft 2020-12) lives at [`schemas/transcript.schema.json`](schemas/transcript.schema.json); it is
cross-checked against a large corpus of real transcripts across many Claude Code versions
(`bin/generate-transcript-schema.py` regenerates that observed-coverage view), and is the
machine-readable counterpart to this prose model. For token-usage attribution from these records,
see `MONITORING_USAGE.md`.

## Re-location recipes

| Target                     | Grep anchor                                                          |
|----------------------------|---------------------------------------------------------------------|
| Envelope writer            | `logicalParentUuid` — the function spreading it onto each record     |
| Conversation type guard    | the predicate testing `=== "progress"` against the record `type`    |
| Read-path result shape     | `attributionSnapshots` (a distinctive Map key in the returned object)|
| JSONL parser               | `Bun.JSONL` (Bun path) / the split-on-newline skip-malformed loop    |
| Path builder               | `subagents` joined under the `projects` directory                   |
| Big-file partial load      | `CLAUDE_CODE_DISABLE_PRECOMPACT_SKIP`                                |

## File locations

| File                                                                            | Purpose                              |
|---------------------------------------------------------------------------------|--------------------------------------|
| `~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl`                            | Main session transcript              |
| `~/.claude/projects/<encoded-cwd>/<sessionId>/subagents/agent-<agentId>.jsonl`  | Subagent transcript                  |
| `~/.claude/history.jsonl`                                                       | Prompt input history (different format) |
| `~/.claude/dump-prompts/<sessionId>.jsonl`                                      | Debug API request dump (dead code)   |
| `<errorDir>/errors.jsonl`                                                       | Error log sink                       |
| `<mcpLogsDir>/<serverName>.jsonl`                                               | MCP server logs                      |
| `<debugDir>/bridge-transcript-<sessionId>.jsonl`                                | Bridge subprocess stdout             |

`<encoded-cwd>` is the project working directory with path separators replaced by dashes (e.g.
`-Users-you-src-claude-code-analysis`). The subagent transcript path is
what the SubagentStop hook reports as `agent_transcript_path` (see `HOOKS.md`).

## Conversation structure

Messages form a linked list via `parentUuid`, not a flat sequence. The chain is reconstructed by
following `parentUuid` backward from leaf messages. After compaction, `logicalParentUuid` bridges
across a `compact_boundary` record whose own `parentUuid` is null.

## Record categories

Records fall into two categories:

1. Conversation records — wrapped with envelope fields by the envelope writer.
2. Metadata-only records — written directly (append), no envelope.

A type guard recognizes the conversation record types: `user`, `assistant`, `attachment`,
`system`, `progress`.

## Envelope fields

Every conversation record is wrapped with these fields by the envelope writer (grep
`logicalParentUuid`). The envelope is merged with the message object via spread, so envelope fields
appear at the top level. The message's own `uuid` becomes the key in the session message Map on
read.

| Field               | Type                    | Description                                          |
|---------------------|-------------------------|------------------------------------------------------|
| `parentUuid`        | string or null          | UUID of previous message; null at `compact_boundary` |
| `logicalParentUuid` | string or undefined     | UUID bridging across compaction boundaries           |
| `isSidechain`       | boolean                 | Whether this is a subagent conversation              |
| `teamName`          | string or undefined     | Team name if in a team context                       |
| `agentName`         | string or undefined     | Agent name within a team                             |
| `userType`          | `"external"` or `"ant"` | User type                                            |
| `cwd`               | string                  | Working directory at time of write                   |
| `sessionId`         | string                  | Session UUID                                         |
| `version`           | string                  | Claude Code version (e.g. `"2.1.165"`)               |
| `gitBranch`         | string or undefined     | Current git branch                                   |
| `agentId`           | string or undefined     | Agent ID for subagent transcripts                    |
| `slug`              | string or undefined     | Human-readable session slug                          |
| `entrypoint`        | string or undefined     | Originating client (`cli`, `sdk-cli`, `sdk-py`, `claude-desktop`, `claude-vscode`) |
| `forkedFrom`        | object or undefined     | Source session/message this conversation was forked from |

## Conversation record types

### `user` — human turn or tool result

Re-locate by grepping the record carrying `isCompactSummary` and `toolUseResult`.

| Field                       | Type                 | Description                                                 |
|-----------------------------|----------------------|-------------------------------------------------------------|
| `type`                      | `"user"`             | Record type discriminator                                   |
| `uuid`                      | string               | UUIDv4                                                      |
| `timestamp`                 | string               | ISO 8601                                                    |
| `message.role`              | `"user"`             | Always "user"                                               |
| `message.content`           | string or array      | Plain string for human turns; or array of `tool_result`, `text`, `image`, `document` blocks |
| `isMeta`                    | boolean or undefined | True for injected meta-messages                             |
| `isVisibleInTranscriptOnly` | boolean or undefined | Display-only message                                        |
| `isCompactSummary`          | boolean or undefined | True when this is a compaction summary                      |
| `summarizeMetadata`         | object or undefined  | Present on compaction summaries                             |
| `toolUseResult`             | object or undefined  | Structured tool result data (see below)                     |
| `mcpMeta`                   | object or undefined  | MCP-related metadata                                        |
| `imagePasteIds`             | array or undefined   | IDs of pasted images                                        |
| `sourceToolAssistantUUID`   | string or undefined  | UUID of the assistant record that issued the tool call      |
| `sourceToolUseID`           | string or undefined  | Tool use ID that produced this result                       |
| `interruptedMessageId`      | string or undefined  | Message ID interrupted by this turn                         |
| `permissionMode`            | string or undefined  | Permission mode (`default`/`acceptEdits`/`bypassPermissions`/`plan`/`dontAsk`/`auto`) |
| `planContent`               | string or undefined  | Plan text when submitted from plan mode                     |
| `promptSource`              | string or undefined  | How the prompt was entered (`typed`, `queued`, `system`)    |
| `promptId`                  | string or undefined  | Identifier for the originating prompt                       |
| `origin`                    | object or undefined  | Prompt origin metadata                                      |
| `thinkingMetadata`          | object or undefined  | Contains `maxThinkingTokens` when thinking is active        |
| `todos`                     | array or undefined   | Todo list state snapshot                                    |

When `message.content` is an array, each block is one of: `tool_result`
(`{ type, tool_use_id, content, is_error? }`), `text`, `image` (base64 source), or `document`
(base64 source, e.g. a pasted PDF). The `toolUseResult` field is either an object with tool-specific
fields (commonly `stdout`, `stderr`, `interrupted`, `isImage`; Grep adds `mode`, `numFiles`,
`filenames`, `content`, `numLines`), a plain string (error output), or an array of content blocks.

### `assistant` — model response

Re-locate by grepping the record carrying `requestId` and `isApiErrorMessage`.

| Field                        | Type                | Description                                       |
|------------------------------|---------------------|---------------------------------------------------|
| `type`                       | `"assistant"`       | Record type discriminator                         |
| `uuid`                       | string              | UUIDv4                                            |
| `timestamp`                  | string              | ISO 8601                                          |
| `requestId`                  | string or undefined | Anthropic API request ID                          |
| `apiError`                   | object or undefined | API error details                                 |
| `apiErrorStatus`             | int or undefined    | HTTP status of an API error (e.g. 429, 529)       |
| `error`                      | object or undefined | General error                                     |
| `isApiErrorMessage`          | boolean             | Whether this record represents an API error       |
| `attributionSkill`           | string or undefined | Skill credited with this turn's work              |
| `attributionPlugin`          | string or undefined | Plugin credited with this turn's work             |
| `attributionMcpServer`       | string or undefined | MCP server credited with this turn's work         |
| `attributionMcpTool`         | string or undefined | MCP tool credited with this turn's work           |
| `message.id`                 | string              | Anthropic message ID (e.g. `msg_01…`)             |
| `message.model`              | string              | Model ID (e.g. `"claude-opus-4-8"`)               |
| `message.role`               | `"assistant"`       | Always "assistant"                                |
| `message.type`               | `"message"`         | Always "message"                                  |
| `message.stop_reason`        | string or null      | `end_turn`, `stop_sequence`, `tool_use`, `max_tokens`, `refusal`, or null (streaming) |
| `message.stop_sequence`      | string              | The stop sequence if applicable                   |
| `message.container`          | null                | Reserved                                          |
| `message.context_management` | null                | Reserved                                          |
| `message.content`            | array               | Content blocks (see below)                        |
| `message.usage`              | object              | Token usage (see below)                           |

Content block types in `message.content`:

| Block type   | Key fields                                                   |
|--------------|--------------------------------------------------------------|
| `"thinking"` | `thinking` (text), `signature` (string)                      |
| `"text"`     | `text` (string)                                              |
| `"tool_use"` | `id`, `name`, `input` (object), `caller: { type: "direct" }` |

Usage object (`message.usage`) — the canonical field reference; `MONITORING_USAGE.md` points here:

| Field                                        | Type                    |
|----------------------------------------------|-------------------------|
| `input_tokens`                               | int                     |
| `output_tokens`                              | int                     |
| `cache_creation_input_tokens`                | int                     |
| `cache_read_input_tokens`                    | int                     |
| `cache_creation.ephemeral_1h_input_tokens`   | int                     |
| `cache_creation.ephemeral_5m_input_tokens`   | int                     |
| `server_tool_use.web_search_requests`        | int                     |
| `server_tool_use.web_fetch_requests`         | int                     |
| `service_tier`                               | string or null          |
| `inference_geo`                              | string or null          |
| `iterations`                                 | int, array, or null     |
| `speed`                                      | number, string, or null |

The same `message.id` may appear on two consecutive assistant records — one with `stop_reason: null`
(streaming start, typically the thinking block) and one with the final `stop_reason`. This is a
streaming artifact.

### `progress` — tool/hook progress

Re-locate by grepping `toolUseID` alongside `parentToolUseID`.

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
`data.message`. Any `normalizedMessages` within `data` is cleared to `[]` before writing.

### `attachment` — structured event/notification

Re-locate by grepping the record whose payload is keyed by `attachment` and discriminated by
`attachment.type`.

| Field        | Type           | Description                                  |
|--------------|----------------|----------------------------------------------|
| `type`       | `"attachment"` | Record type discriminator                    |
| `uuid`       | string         | UUIDv4                                        |
| `timestamp`  | string         | ISO 8601                                      |
| `attachment` | object         | Payload, discriminated by `attachment.type`  |

`attachment.type` is an open set; the schema treats it as a string. Observed values (grep each
literal to confirm in a given version):

| Subtype                       | Category      |
|-------------------------------|---------------|
| `hook_blocking_error`         | Hooks         |
| `hook_cancelled`              | Hooks         |
| `hook_error_during_execution` | Hooks         |
| `hook_non_blocking_error`     | Hooks         |
| `hook_success`                | Hooks         |
| `hook_system_message`         | Hooks         |
| `hook_additional_context`     | Hooks         |
| `hook_stopped_continuation`   | Hooks         |
| `plan_mode`                   | Plan mode     |
| `plan_mode_reentry`           | Plan mode     |
| `plan_mode_exit`              | Plan mode     |
| `plan_file_reference`         | Plan mode     |
| `ultramemory`                 | Memory        |
| `todo_reminder`               | Tasks         |
| `task_reminder`               | Tasks         |
| `task_status`                 | Tasks         |
| `structured_output`           | Output        |
| `max_turns_reached`           | Control flow  |
| `queued_command`              | Command queue |
| `invoked_skills`              | Skills        |
| `teammate_shutdown_batch`     | Teams         |
| `new_file`                    | Files         |
| `new_directory`               | Files         |
| `file`                        | Files         |
| `directory`                   | Files         |
| `edited_text_file`            | Files         |
| `agent_mention`               | Teams         |

### `system` — system events

Common fields: `type` (`"system"`), `subtype`, `uuid`, `timestamp`, optional `level` (`"info"` /
`"error"` / `"suggestion"` / `"warning"`), `isMeta` (true), `content` (human-readable). Subtypes and
their extra fields:

`compact_boundary` — `compactMetadata.trigger`, `compactMetadata.preTokens`,
`compactMetadata.userContext?`, `compactMetadata.messagesSummarized?`, plus `logicalParentUuid?`.

`microcompact_boundary` — `microcompactMetadata.trigger`, `.preTokens`, `.tokensSaved`,
`.compactedToolIds` (string[]), `.clearedAttachmentUUIDs` (string[]).

`local_command` — `content` carries the command output text; `hasOutput`, `toolUseID`.

`api_error` — `cause?`, `error`, `retryInMs`, `retryAttempt`, `maxRetries`.

`stop_hook_summary` — `hookInfos`, `hookCount`, `hookErrors`, `stopReason`, `preventedContinuation`,
`pendingWorkflowCount`, `pendingBackgroundAgentCount`.

`turn_duration` — turn timing metrics: `durationMs`, `messageCount`; `level`/`content` may be
absent.

`away_summary` — summary written while the user is away.

`bridge_status` — bridge (remote-control) connection status.

`scheduled_task_fire` — a scheduled task / cron fired.

`informational` — informational notice (e.g. mode explainers, "Args from unknown skill"); carries
`content`, often `level`, and sometimes `url` / `upgradeNudge`.

## Metadata-only record types

Written directly (append), not wrapped with envelope fields; all carry `sessionId` (except
`summary`, keyed by `leafUuid`).

| Record type             | Shape                                                                          |
|-------------------------|--------------------------------------------------------------------------------|
| `custom-title`          | `{ type, customTitle, sessionId }` — user-set title                            |
| `ai-title`              | `{ type, aiTitle, sessionId }` — auto-generated title (distinct from `custom-title`) |
| `tag`                   | `{ type, tag, sessionId }`                                                     |
| `agent-name`            | `{ type, agentName, sessionId }`                                               |
| `agent-color`           | `{ type, agentColor, sessionId }`                                              |
| `agent-setting`         | `{ type, agentSetting, sessionId }`                                            |
| `mode`                  | `{ type, mode, sessionId }`                                                    |
| `permission-mode`       | `{ type, permissionMode, sessionId }` — active permission mode (distinct from `mode`) |
| `pr-link`               | `{ type, sessionId, prNumber, prUrl, prRepository, timestamp }`                |
| `summary`              | `{ type, summary, leafUuid }` — written at session end, keyed by `leafUuid`     |
| `last-prompt`           | `{ type, sessionId, lastPrompt?, leafUuid? }` — most recent prompt              |
| `file-history-snapshot` | `{ type, messageId, snapshot, isSnapshotUpdate }`                              |
| `attribution-snapshot`  | `{ type, messageId, …otherFields }`                                            |
| `queue-operation`       | `{ type, operation, timestamp, sessionId, content? }`                          |
| `speculation-accept`    | `{ type, timestamp, timeSavedMs }`                                             |
| `bridge-session`        | `{ type, sessionId, bridgeSessionId, lastSequenceNum }`                        |
| `worktree-state`        | `{ type, sessionId, worktreeSession }` — `worktreeSession` is an object or null |

The `file-history-snapshot` `snapshot` object contains `messageId`, `trackedFileBackups` (file path
→ backup data), and `timestamp`. `queue-operation` operations are `"enqueue"`, `"dequeue"`,
`"remove"`, `"popAll"`. The `worktree-state` `worktreeSession` object carries `originalCwd`,
`worktreePath`, `worktreeName`, `worktreeBranch`, `originalBranch`.

## JSONL parser

All JSONL files pass through one parser. On Bun it uses `Bun.JSONL` chunk parsing with error
recovery; on Node it splits on newline (string) or byte 10 (Buffer) and `JSON.parse`s each line.
Empty and malformed lines are silently discarded.

## Read path

A full read returns an object whose Map fields key the metadata-only records by `sessionId` (and
`messageId` / `leafUuid` where noted): `messages` (by `uuid`), `summaries` (by `leafUuid`),
`customTitles`, `tags`, `agentNames`, `agentColors`, `agentSettings`, `prNumbers`, `prUrls`,
`prRepositories`, `modes`, `fileHistorySnapshots` (by `messageId`), `attributionSnapshots` (by
`messageId`), and `leafUuids` (a Set). Grep `attributionSnapshots` to locate it.

For very large files (size-gated), the read path scans for the last `compact_boundary` and loads
only post-compaction content. Setting `CLAUDE_CODE_DISABLE_PRECOMPACT_SKIP` disables that and forces
a full load. (Earlier releases used a differently named, opposite-sense variable; see the appendix.)

Lite mode reads only filesystem metadata; hydration does fast string-scanning of head/tail bytes for
key fields without full JSON parsing.

## Write path

Conversation records: the envelope writer wraps each message with the envelope fields, then entries
are routed through an async write queue that batches and appends via `fs/promises` `appendFile`. The
drain interval is 100 ms (10 ms when remote ingress is active); batches cap around 100 MB. Files are
created mode `0o600` (owner read/write only). Metadata-only records take a synchronous append path.

## Compaction

When the conversation approaches context limits, a `compact_boundary` system record is written with
`compactMetadata` (trigger, pre-compaction token count, messages summarized); its `parentUuid` is
set to null, breaking the linked list, while `logicalParentUuid` preserves the logical chain. A user
record with `isCompactSummary: true` follows, carrying the summary. `microcompact_boundary` is a
lighter pass that trims specific tool results (`compactedToolIds`) and attachments
(`clearedAttachmentUUIDs`). Full behavioral model: `CLEAR_COMPACT_FORK_CONTEXT.md`.

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

## Per-release appendix

- 2.1.165: verified, and the companion schema refreshed to `x-schema-version` 1.2.0 (validated with
  zero failures against the local transcript corpus, observed range 2.0.27–2.1.167). Record types
  added since the earlier inventory: `ai-title`, `last-prompt`, `permission-mode`, `bridge-session`,
  `worktree-state`. System subtypes added: `away_summary`, `bridge_status`, `scheduled_task_fire`,
  `informational`. Envelope gained `entrypoint` and `forkedFrom`. `assistant` `stop_reason` gained
  `max_tokens` and `refusal`; `system` `level` gained `warning`; `user` content gained `document`
  blocks.
- The big-file partial-load env var is `CLAUDE_CODE_DISABLE_PRECOMPACT_SKIP` (default skips
  pre-compaction content; the var forces a full load) — renamed and inverted from the earlier
  `CLAUDE_CODE_SKIP_PRECOMPACT_LOAD`. The `hook_additional_context` attachment subtype persists, but
  the prior `CLAUDE_CODE_SAVE_HOOK_ADDITIONAL_CONTEXT` gate is no longer present under that name.
