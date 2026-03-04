# Clear, Compact, and Fork: How Context Operations Work

Source: `cli.prettier.js` 2.1.63 (`work/2.1.63/package/cli.prettier.js`)

Three commands manipulate conversation context. All three preserve the full
JSONL history — they differ in what the model sees going forward and whether
the session continues or a new one is created.

## `/compact` — Summarize Within the Same Session

Compaction replaces the model's active context with a summary. The original
entries remain in the JSONL file at their original indices.

### What gets written to the JSONL

Two records are appended:

1. A `system` record with `"subtype": "compact_boundary"` — marks where the
   model's context was cut. Everything before this was summarized away.

2. A `user` record with `isCompactSummary: true` containing:
   ```
   This session is being continued from a previous conversation
   that ran out of context. The summary below covers the earlier
   portion of the conversation.
   ```
   Followed by the compaction agent's summary text.

### Source references

| What                     | Line    | Symbol     |
| ------------------------ | ------- | ---------- |
| compact_boundary write   | 520404  | system msg |
| Compaction summary entry | 518734  | `K8()`     |
| Compaction agent files   | subagent dir | `agent-acompact-*.jsonl` |

### Multiple compactions

A session can be compacted multiple times. Each compaction adds another
boundary+summary pair. The last `compact_boundary` marks where the current
active context begins. Everything before the last boundary is "lost" history.

### Microcompact

A lighter variant exists: `"subtype": "microcompact_boundary"`. Same mechanism,
smaller scope. Both are `system` records.

## `/clear` (Clear Context) — Start a New Session File

Clear context terminates the current session and starts a new one in a fresh
JSONL file. This is a UI-side action — it is not a distinct tool call.

### How it happens

Clear context occurs when the user approves an `ExitPlanMode` tool call and
selects an approval option that does not include "keep-context":

| Approval option                    | Clears context? | Permission mode      |
| ---------------------------------- | --------------- | -------------------- |
| `yes-bypass-permissions`           | yes             | bypassPermissions    |
| `yes-accept-edits`                 | yes             | acceptEdits          |
| `yes-accept-edits-keep-context`    | no              | bypassPermissions    |
| `yes-default-keep-context`         | no              | default              |
| `no`                               | no              | (rejected, feedback) |

Source: lines 571546-571625.

### The ExitPlanMode tool_use is identical either way

The JSONL `tool_use` block for ExitPlanMode looks the same regardless of
whether the user will clear context or keep it. The `input` field contains:

- `plan` — the plan text (injected from the plan file on disk by
  `normalizeToolInput`, not sent by the model)
- `allowedPrompts` — optional array of permission requests

There is no `clearContext` field in the tool_use record. The clear-vs-keep
decision is made in the UI after the tool call is written to the JSONL.

Source: input schema at line 447121 (`Y4q`), extended schema at 447133 (`UF_`).

### What happens when context is cleared

1. The UI constructs a new initial message (line 571576-571588):
   ```
   Implement the following plan:

   <plan text>

   If you need specific details from before exiting plan mode (like exact
   code snippets, error messages, or content you generated), read the full
   transcript at: <parent session JSONL path>
   ```

2. `clearConversation()` is called (line 593194, function `bg8` at 457755):
   - Wipes the message array: `setMessages(() => [])`
   - Generates a new conversation ID: `setConversationId(ZeY())`
   - Kills running background tasks
   - Resets attribution, file history, and other state

3. A new JSONL file is created for the new session ID.

4. The parent session's JSONL receives no special termination marker.
   It simply stops having new entries written to it.

### Cross-session links

The only link between parent and child sessions is the text pointer
`"read the full transcript at: <path>"` in the child's early entries
(typically entry [1] or [2]).

This is a `user` record containing the injected initial message with the
plan text and transcript path. It is not a system record or metadata record.

To detect clear-context relationships:

- From child: search first 5 entries for `read the full transcript at:`
  and extract the path.
- From parent: cannot be detected from the parent's JSONL alone. Must scan
  sibling JSONL files for references to the parent's session ID.

### What is NOT in the JSONL

- No `clearContext` field on any record in the parent session
- No termination marker in the parent session
- No system record marking the clear-context event
- The `ExitPlanMode` tool_use record is indistinguishable from a
  keep-context plan approval

## Telemetry

Both paths emit a `tengu_plan_exit` telemetry event (lines 571559, 571603,
571620) with:

```javascript
[source fragment removed]
```

This is sent to the telemetry system, not written to the JSONL.

## `/fork` — Copy the Conversation to a New Session

Fork creates a new JSONL file containing a copy of all main-chain conversation
records from the current session. The original session is unmodified and
continues independently.

### How it works

Function `Z2z` at line 501542:

1. Generate a new session UUID and JSONL path.
2. Read the current session's JSONL via `yO()` and parse with `B76()`.
3. Filter to main-chain conversation records: `!D.isSidechain && Oi(D)`.
   This keeps `user`, `assistant`, `progress`, `attachment`, and `system`
   records but excludes metadata-only records and sidechain entries.
4. Copy each record with:
   - `sessionId` set to the new session UUID
   - `parentUuid` re-linked sequentially (new chain)
   - `forkedFrom: { sessionId: <original>, messageUuid: <original uuid> }`
5. Write the copied records to the new JSONL file.
6. Write a `custom-title` metadata record: `"<title> (Fork)"` or
   `"<title> (Fork N)"` if forks already exist (function `f2z`, line 501584).
7. Resume into the forked session via `q.resume(w, M, "fork")`.

Source: lines 501538-501651.

### The `forkedFrom` field

Each record in the forked JSONL has an additional `forkedFrom` object:

```json
{
  "forkedFrom": {
    "sessionId": "<original session UUID>",
    "messageUuid": "<original message UUID>"
  }
}
```

This field is written but never read by Claude Code — it exists only as
provenance metadata. It is not present in the JSON Schema (not part of the
standard envelope).

### What happens to the original session

Nothing. The original session's JSONL is not modified. No marker, no
termination record, no reference to the fork. The original continues
as if nothing happened (unless the UI switches to the fork, in which case
the user is told `To resume the original: claude -r <session-id>`).

### Detecting forks

- From fork: every record has `forkedFrom.sessionId` pointing to the parent.
  This is a structured field, unlike `/clear`'s text pointer.
- From parent: cannot be detected from the parent's JSONL. Must scan sibling
  files for `forkedFrom.sessionId` matching the parent's session ID.

### Fork vs Clear context

| Aspect              | `/fork`                                | `/clear`                              |
| ------------------- | -------------------------------------- | ------------------------------------- |
| History copying     | Full copy of all messages              | No copy — just a text pointer         |
| Model sees          | Entire conversation (as if original)   | Plan text + transcript path           |
| Link field          | `forkedFrom` (structured, every record)| Text in `message.content` (entry 1-2) |
| Original continues? | Yes, independently                     | No, parent session stops              |
| Context preserved?  | Yes, full context                      | No, fresh context with plan only      |
| Triggered by        | `/fork` command                        | ExitPlanMode approval (UI choice)     |

## Telemetry

Both `/clear` and `/fork` emit telemetry events (not written to JSONL):

- `/clear`: `tengu_plan_exit` (lines 571559, 571603, 571620) with
  `clearContext`, `outcome`, `planLengthChars`
- `/fork`: `tengu_conversation_forked` (line 501623) with
  `message_count`, `has_custom_title`

## Summary

| Aspect                | `/compact`                       | `/clear` (clear context)          | `/fork`                           |
| --------------------- | -------------------------------- | --------------------------------- | --------------------------------- |
| JSONL file            | Same file                        | New file                          | New file (copy)                   |
| Marker in parent      | `compact_boundary` system record | None                              | None                              |
| Link to history       | Summary user record in same file | Text pointer in child entry       | `forkedFrom` field on every record|
| Original entries      | Preserved at original indices    | Preserved in parent file          | Preserved; also copied to fork    |
| Model sees            | Compaction summary               | Plan text + transcript path       | Full conversation (copy)          |
| Original continues?   | Yes (same session)               | No (parent stops)                 | Yes (independent)                 |
| Detectable from       | Same JSONL (system subtype)      | Child JSONL (text search)         | Fork JSONL (`forkedFrom` field)   |
| Can repeat?           | Yes, multiple times              | N/A (new session)                 | Yes, multiple forks               |
