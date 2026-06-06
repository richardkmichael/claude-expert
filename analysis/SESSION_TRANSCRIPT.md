# JSONL Session Transcript Format

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

Claude Code persists conversation state as JSONL (newline-delimited JSON) files.
Each line is a self-contained JSON object terminated by `\n`.
There is no official schema; this document is derived from source code analysis.

A JSON Schema (draft 2020-12) is provided at
[transcript.schema.json](schemas/transcript.schema.json),
validated against 248,000+ lines across 493 sessions spanning 61 Claude Code versions
(2.0.24 through 2.1.68).


## File Locations

| File                                                             | Purpose                              |
| ---------------------------------------------------------------- | ------------------------------------ |
| `~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl`             | Main session transcript              |
| `~/.claude/projects/<encoded-cwd>/<sessionId>/subagents/agent-<agentId>.jsonl` | Subagent transcript   |
| `~/.claude/history.jsonl`                                        | Prompt input history (different format) |
| `~/.claude/dump-prompts/<sessionId>.jsonl`                       | Debug API request dump (dead code)   |
| `<errorDir>/errors.jsonl`                                        | Error log sink                       |
| `<mcpLogsDir>/<serverName>.jsonl`                                | MCP server logs                      |
| `<debugDir>/bridge-transcript-<sessionId>.jsonl`                 | Bridge subprocess stdout             |

Path-building functions at lines 516219-516231 (`g$()`, `px()`).

The `<encoded-cwd>` is a URL-encoded representation of the project's working directory
(e.g. `-Users-you-src-claude-code-analysis`).


## Conversation Structure

Messages form a linked list via `parentUuid` fields, not a flat sequence.
The chain is reconstructed by following `parentUuid` links backward from leaf messages
using `Mn6()`. After compaction, `logicalParentUuid` bridges across `compact_boundary`
records.


## Record Categories

Records fall into two categories:

1. Conversation records — wrapped with envelope fields by `insertMessageChain()` (line 516449)
2. Metadata-only records — written directly with `Gb()` (line 516916), no envelope

The type guard `Oi()` (line 516207) recognizes conversation record types:

    type === "user" || type === "assistant" || type === "attachment" ||
    type === "system" || type === "progress"


## Envelope Fields

Every conversation record is wrapped with these fields by `insertMessageChain()`
(lines 516449-516463). The envelope is merged with the message object via spread,
so envelope fields appear at the top level:

| Field              | Type               | Description                                      |
| ------------------ | ------------------ | ------------------------------------------------ |
| `parentUuid`       | string or null     | UUID of previous message; null at compact_boundary |
| `logicalParentUuid`| string or undefined| UUID bridging across compaction boundaries        |
| `isSidechain`      | boolean            | Whether this is a subagent conversation           |
| `teamName`         | string or undefined| Team name if in a team context                    |
| `agentName`        | string or undefined| Agent name within a team                          |
| `userType`         | `"external"` or `"ant"` | User type                                   |
| `cwd`              | string             | Working directory at time of write                |
| `sessionId`        | string             | Session UUID                                      |
| `version`          | string             | Claude Code version (e.g. `"2.1.76"`)            |
| `gitBranch`        | string or undefined| Current git branch                                |
| `agentId`          | string or undefined| Agent ID for subagent transcripts                 |
| `slug`             | string or undefined| Human-readable session slug                       |

The message's own `uuid` becomes the key in the session message Map on read.


---


## Conversation Record Types


### `user` — Human Turn or Tool Result

Factory: `K8()` (line 518734)

| Field                        | Type                 | Description                                          |
| ---------------------------- | -------------------- | ---------------------------------------------------- |
| `type`                       | `"user"`             | Record type discriminator                            |
| `uuid`                       | string               | UUIDv4                                               |
| `timestamp`                  | string               | ISO 8601                                             |
| `message.role`               | `"user"`             | Always "user"                                        |
| `message.content`            | string or array      | Plain string for human turns; array of tool_result and/or text content blocks |
| `isMeta`                     | boolean or undefined | True for injected meta-messages                      |
| `isVisibleInTranscriptOnly`  | boolean or undefined | Display-only message                                 |
| `isCompactSummary`           | boolean or undefined | True when this is a compaction summary               |
| `summarizeMetadata`          | object or undefined  | Present on compaction summaries                      |
| `toolUseResult`              | object or undefined  | Structured tool result data (see below)              |
| `mcpMeta`                    | object or undefined  | MCP-related metadata                                 |
| `imagePasteIds`              | array or undefined   | IDs of pasted images                                 |
| `sourceToolAssistantUUID`    | string or undefined  | UUID of the assistant record that issued the tool call |
| `permissionMode`             | string or undefined  | e.g. `"plan"`, `"default"`                           |
| `thinkingMetadata`           | object or undefined  | Contains `maxThinkingTokens` when thinking is active |
| `todos`                      | array or undefined   | Todo list state snapshot                             |

When `message.content` is an array (tool results), each block has:

```
{ type: "tool_result", tool_use_id: string, content: string, is_error?: boolean }
```

The `toolUseResult` field can be:
- An object with tool-specific fields (common: `stdout`, `stderr`, `interrupted`,
  `isImage`; Grep adds: `mode`, `numFiles`, `filenames`, `content`, `numLines`)
- A plain string (e.g. error output)
- An array of content blocks (e.g. text blocks from web search results)


### `assistant` — Model Response

Factory: `iPq()` (line 518676)

| Field                    | Type                 | Description                                      |
| ------------------------ | -------------------- | ------------------------------------------------ |
| `type`                   | `"assistant"`        | Record type discriminator                        |
| `uuid`                   | string               | UUIDv4                                           |
| `timestamp`              | string               | ISO 8601                                         |
| `requestId`              | string or undefined  | Anthropic API request ID                         |
| `apiError`               | object or undefined  | API error details                                |
| `error`                  | object or undefined  | General error                                    |
| `isApiErrorMessage`      | boolean              | Whether this record represents an API error      |
| `message.id`             | string               | Anthropic message ID (e.g. `msg_01...`)          |
| `message.model`          | string               | Model ID (e.g. `"claude-opus-4-6"`)              |
| `message.role`           | `"assistant"`        | Always "assistant"                               |
| `message.type`           | `"message"`          | Always "message"                                 |
| `message.stop_reason`    | string or null       | `"end_turn"`, `"stop_sequence"`, `"tool_use"`, or null (streaming) |
| `message.stop_sequence`  | string               | The stop sequence if applicable                  |
| `message.container`      | null                 | Reserved                                         |
| `message.context_management` | null              | Reserved                                         |
| `message.content`        | array                | Content blocks (see below)                       |
| `message.usage`          | object               | Token usage (see below)                          |

Content block types in `message.content`:

| Block type    | Key fields                                                  |
| ------------- | ----------------------------------------------------------- |
| `"thinking"`  | `thinking` (text), `signature` (string)                     |
| `"text"`      | `text` (string)                                             |
| `"tool_use"`  | `id`, `name`, `input` (object), `caller: { type: "direct" }` |

Usage object (`message.usage`):

| Field                              | Type            |
| ---------------------------------- | --------------- |
| `input_tokens`                     | int             |
| `output_tokens`                    | int             |
| `cache_creation_input_tokens`      | int             |
| `cache_read_input_tokens`          | int             |
| `cache_creation.ephemeral_1h_input_tokens`  | int    |
| `cache_creation.ephemeral_5m_input_tokens`  | int    |
| `server_tool_use.web_search_requests`       | int    |
| `server_tool_use.web_fetch_requests`        | int    |
| `service_tier`                     | string or null  |
| `inference_geo`                    | string or null  |
| `iterations`                       | int, array, or null |
| `speed`                            | number, string, or null | (string for tier names, e.g. `"standard"`)

Note: The same `message.id` may appear on two consecutive assistant records — one with
`stop_reason: null` (streaming start, typically the thinking block) and one with the
final `stop_reason`. This is a streaming artifact.


### `progress` — Tool/Hook Progress

Factory: `lKq()` (line 518777)

| Field              | Type               | Description                                      |
| ------------------ | ------------------ | ------------------------------------------------ |
| `type`             | `"progress"`       | Record type discriminator                        |
| `uuid`             | string             | UUIDv4                                           |
| `timestamp`        | string             | ISO 8601                                         |
| `toolUseID`        | string             | Tool use ID this relates to                      |
| `parentToolUseID`  | string or undefined| Parent tool use ID                               |
| `data`             | object             | Progress payload (see below)                     |

The `data` object commonly contains:

| Field            | Type               | Description                            |
| ---------------- | ------------------ | -------------------------------------- |
| `data.type`      | `"hook_progress"`  | Progress type                          |
| `data.hookEvent` | string             | `"PreToolUse"` or `"PostToolUse"`      |
| `data.hookName`  | string             | e.g. `"PreToolUse:Bash"`              |
| `data.command`   | string             | Hook script/command                    |
| `data.message`   | object or undefined| Serialized user message                |

Note: `normalizedMessages` within `data` is always cleared to `[]` before writing
(lines 517451-517454 in `kPq()`).


### `attachment` — Structured Event/Notification

Factory: `wq()` (line 290751)

| Field              | Type               | Description                           |
| ------------------ | ------------------ | ------------------------------------- |
| `type`             | `"attachment"`     | Record type discriminator             |
| `uuid`             | string             | UUIDv4                                |
| `timestamp`        | string             | ISO 8601                              |
| `attachment`       | object             | Payload, discriminated by `attachment.type` |

Known `attachment.type` values:

| Subtype                      | Category      |
| ---------------------------- | ------------- |
| `hook_blocking_error`        | Hooks         |
| `hook_cancelled`             | Hooks         |
| `hook_error_during_execution`| Hooks         |
| `hook_non_blocking_error`    | Hooks         |
| `hook_success`               | Hooks         |
| `hook_system_message`        | Hooks         |
| `hook_additional_context`    | Hooks (filtered for non-Anthropic users unless `CLAUDE_CODE_SAVE_HOOK_ADDITIONAL_CONTEXT=1`) |
| `hook_stopped_continuation`  | Hooks         |
| `plan_mode`                  | Plan mode     |
| `plan_mode_reentry`          | Plan mode     |
| `plan_mode_exit`             | Plan mode     |
| `plan_file_reference`        | Plan mode     |
| `ultramemory`                | Memory        |
| `todo_reminder`              | Tasks         |
| `task_reminder`              | Tasks         |
| `task_status`                | Tasks         |
| `structured_output`          | Output        |
| `max_turns_reached`          | Control flow  |
| `queued_command`             | Command queue |
| `invoked_skills`             | Skills        |
| `teammate_shutdown_batch`    | Teams         |
| `new_file`                   | Files         |
| `new_directory`              | Files         |
| `file`                       | Files         |
| `directory`                  | Files         |
| `edited_text_file`           | Files         |
| `agent_mention`              | Teams         |


### `system` — System Events

Various factories (lines 520382-520437). Common fields:

| Field     | Type                   | Description                       |
| --------- | ---------------------- | --------------------------------- |
| `type`    | `"system"`             | Record type discriminator         |
| `subtype` | string                 | System event subtype              |
| `uuid`    | string                 | UUIDv4                            |
| `timestamp`| string                | ISO 8601                          |
| `level`   | `"info"`, `"error"`, or `"suggestion"` | Severity (optional on some subtypes) |
| `isMeta`  | boolean                | Always true                       |
| `content` | string                 | Human-readable description        |

System subtypes and their additional fields:

`compact_boundary` (line 520393):

| Field                                   | Type               |
| --------------------------------------- | ------------------ |
| `compactMetadata.trigger`               | string             |
| `compactMetadata.preTokens`             | int                |
| `compactMetadata.userContext`            | string or undefined|
| `compactMetadata.messagesSummarized`    | int (optional)     |
| `logicalParentUuid`                     | string or undefined|

`microcompact_boundary` (line 520411):

| Field                                        | Type     |
| -------------------------------------------- | -------- |
| `microcompactMetadata.trigger`               | string   |
| `microcompactMetadata.preTokens`             | int      |
| `microcompactMetadata.tokensSaved`           | int      |
| `microcompactMetadata.compactedToolIds`      | string[] |
| `microcompactMetadata.clearedAttachmentUUIDs`| string[] |

`local_command` (line 520382):

Content field contains the command output text.

`api_error` (line 520437):

| Field          | Type               |
| -------------- | ------------------ |
| `cause`        | Error or undefined |
| `error`        | Error              |
| `retryInMs`    | number             |
| `retryAttempt`  | int                |
| `maxRetries`   | int                |

`stop_hook_summary`:

Summary of stop-hook execution.

`turn_duration`:

Turn timing metrics. Fields vary; `level` and `content` may be absent.


---


## Metadata-Only Record Types

These are written directly with `appendFileSync` via `Gb()` (line 516916) or the async
queue. They are not wrapped with envelope fields. All have a `sessionId` field.


### `custom-title`

```
{ type: "custom-title", customTitle: string, sessionId: string }
```

### `tag`

```
{ type: "tag", tag: string, sessionId: string }
```

### `agent-name`

```
{ type: "agent-name", agentName: string, sessionId: string }
```

### `agent-color`

```
{ type: "agent-color", agentColor: string, sessionId: string }
```

### `agent-setting`

```
{ type: "agent-setting", agentSetting: object, sessionId: string }
```

### `mode`

```
{ type: "mode", mode: string, sessionId: string }
```

### `pr-link`

```
{ type: "pr-link", sessionId: string, prNumber: int, prUrl: string, prRepository: string, timestamp: string }
```

### `summary`

Written at session end. Keyed by `leafUuid` on read.

```
{ type: "summary", summary: string, leafUuid: string }
```

### `file-history-snapshot`

```
{ type: "file-history-snapshot", messageId: string, snapshot: object, isSnapshotUpdate: boolean }
```

The `snapshot` object contains:
- `messageId`: same UUID
- `trackedFileBackups`: object mapping file paths to backup data
- `timestamp`: ISO 8601

### `attribution-snapshot`

```
{ type: "attribution-snapshot", messageId: string, ...otherFields }
```

### `queue-operation`

```
{ type: "queue-operation", operation: string, timestamp: string, sessionId: string, content?: any }
```

Operations: `"enqueue"`, `"dequeue"`, `"remove"`, `"popAll"`.

### `speculation-accept`

```
{ type: "speculation-accept", timestamp: string, timeSavedMs: number }
```


---


## JSONL Parser

All JSONL files are parsed through `B76()` (line 56702):

| Runtime | Function | Method                                              |
| ------- | -------- | --------------------------------------------------- |
| Bun     | `cNK()`  | `Bun.JSONL.parseChunk` with error recovery          |
| Node (string) | `iNK()` | Split on `\n`, `JSON.parse` each line, skip empty/malformed |
| Node (Buffer) | `lNK()` | Split on byte 10, `JSON.parse` each line, skip empty/malformed |

Malformed lines are silently discarded.


## Read Path

`C26()` (line 517120) reads a full `.jsonl` file and returns:

```
{
  messages:              Map<uuid, MessageRecord>
  summaries:             Map<leafUuid, string>
  customTitles:          Map<sessionId, string>
  tags:                  Map<sessionId, string>
  agentNames:            Map<sessionId, string>
  agentColors:           Map<sessionId, string>
  agentSettings:         Map<sessionId, object>
  prNumbers:             Map<sessionId, int>
  prUrls:                Map<sessionId, string>
  prRepositories:        Map<sessionId, string>
  modes:                 Map<sessionId, string>
  fileHistorySnapshots:  Map<messageId, object>
  attributionSnapshots:  Map<messageId, object>
  leafUuids:             Set<uuid>
}
```

For files >100 MB: `vHz()` scans for the last `compact_boundary` entry and loads only
post-compaction content (controlled by `CLAUDE_CODE_SKIP_PRECOMPACT_LOAD` env var).

Lite mode (`$V6()`, line 517721) reads only filesystem metadata. Hydration (`CHz()`)
does fast string-scanning of head/tail bytes for key fields without full JSON parsing.


## Write Path

1. `recordTranscript(messages)` calls `gx()` (line 516585)
2. `gx()` calls `Vj().insertMessageChain()` which wraps each message with envelope fields
3. `appendEntry()` (line 516489) routes to `enqueueWrite()` or direct write
4. `drainWriteQueue()` (line 516351) batches entries up to 100 MB, writes via `fs/promises appendFile`
5. Drain interval: 100 ms (10 ms when remote ingress is active)
6. File mode: `0o600` (owner read/write only)

Metadata records use the synchronous path `Gb()` with `appendFileSync`.


## Compaction

When the conversation approaches context limits:

- A `compact_boundary` system record is written with `compactMetadata` (trigger reason,
  pre-compaction token count, number of messages summarized)
- `parentUuid` on the boundary is set to null, breaking the linked list
- `logicalParentUuid` preserves the logical chain across the boundary
- A user message with `isCompactSummary: true` follows, containing the summary
- `microcompact_boundary` is a lighter-weight compaction that trims specific tool
  results (`compactedToolIds`) and attachments (`clearedAttachmentUUIDs`)


## history.jsonl

Separate file at `~/.claude/history.jsonl` (line 171786). Different format from session
transcripts. Each line:

```
{
  display:        string               -- display text of the prompt
  pastedContents: {
    [id: number]: {
      id:          int
      type:        "text" | "image"
      content?:    string              -- inline if <= 1024 chars
      contentHash?: string             -- hash pointer if > 1024 chars
      mediaType:   string | undefined
      filename:    string | undefined
    }
  }
  timestamp:  number                   -- Date.now() in ms
  project:    string                   -- cwd path
  sessionId:  string                   -- session UUID
}
```


## MCP and Error Log Formats

MCP debug entry (line 541583):

```
{ debug: string, timestamp: string, sessionId: string, cwd: string }
```

MCP error entry (line 541571):

```
{ error: string, timestamp: string, sessionId: string, cwd: string }
```

General error entry (line 541566):

```
{ error: string }
```
