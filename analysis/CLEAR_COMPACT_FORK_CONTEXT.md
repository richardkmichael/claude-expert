# Clear, Compact, Fork, and Rewind: How Context Operations Work

Source: `cli.prettier.js` 2.1.71 (`work/2.1.71/package/cli.prettier.js`)

Four mechanisms manipulate conversation context. They differ in what the model
sees going forward, whether the session continues or a new one is created, and
whether file changes are affected.

## `/compact` -- Summarize Within the Same Session

Compaction replaces the model's active context with a summary. The original
entries remain in the JSONL file at their original indices.

### What gets written to the JSONL

Two records are appended:

1. A `system` record with `"subtype": "compact_boundary"` -- marks where the
   model's context was cut. Everything before this was summarized away. The
   record includes a `compactMetadata` object:

   ```json
   {
     "trigger": "auto" | "manual",
     "preTokens": 12345,
     "userContext": null,
     "messagesSummarized": null
   }
   ```

   Source: `Al6()` at line 537965.

2. A `user` record with `isCompactSummary: true` containing:
   ```
   This session is being continued from a previous conversation
   that ran out of context. The summary below covers the earlier
   portion of the conversation.
   ```
   Followed by the compaction agent's summary text.

### Multiple compactions

A session can be compacted multiple times. Each compaction adds another
boundary+summary pair. The last `compact_boundary` marks where the current
active context begins. Everything before the last boundary is "lost" history.

### Microcompact

A lighter variant exists: `"subtype": "microcompact_boundary"`. Same mechanism,
smaller scope. Both are `system` records.

## `/clear` (Clear Context) -- Start a New Session File

Clear context terminates the current session and starts a new one in a fresh
JSONL file. This is a UI-side action -- it is not a distinct tool call.

### How it happens

Clear context occurs when the user approves an `ExitPlanMode` tool call and
selects an approval option that clears context:

| Approval option                 | Clears context? | Permission mode   |
| ------------------------------- | --------------- | ----------------- |
| `yes-bypass-permissions`        | yes             | bypassPermissions |
| `yes-accept-edits`              | yes             | acceptEdits       |
| `yes-accept-edits-keep-context` | no              | bypassPermissions |
| `yes-default-keep-context`      | no              | default           |
| `yes-resume-auto-mode`          | no              | auto              |
| `no`                            | no              | (rejected)        |

Source: lines 582860-582965.

The `yes-resume-auto-mode` option (new vs 2.1.63) keeps context and re-enters
auto-accept mode. It is shown when `isAutoModeAvailable` is true (line 583143).

### The ExitPlanMode tool_use is identical either way

The JSONL `tool_use` block for ExitPlanMode looks the same regardless of
whether the user will clear context or keep it. The `input` field contains:

- `plan` -- the plan text (injected from the plan file on disk by
  `normalizeToolInput`, not sent by the model)
- `allowedPrompts` -- optional array of permission requests

There is no `clearContext` field in the tool_use record. The clear-vs-keep
decision is made in the UI after the tool call is written to the JSONL.

### What happens when context is cleared

1. The UI constructs a new initial message (line 582877-582894):
   ```
   Implement the following plan:

   <plan text>

   If you need specific details from before exiting plan mode (like exact
   code snippets, error messages, or content you generated), read the full
   transcript at: <parent session JSONL path>
   ```

   If teams are enabled, a hint about `TeamCreate` for parallelization is
   appended (line 582882).

2. `clearConversation()` is called (`Si8` at line 459783):
   - Wipes the message array: `setMessages(() => [])`
   - Generates a new conversation ID: `setConversationId(l2z())`
   - Kills running background tasks
   - Resets attribution, file history, and other state

3. A new JSONL file is created for the new session ID.

4. The parent session's JSONL receives no special termination marker.

### Cross-session links

The only link between parent and child sessions is the text pointer
`"read the full transcript at: <path>"` in the child's early entries
(typically entry [1] or [2]).

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

## `/rewind` (ESC ESC) -- The Message Selector

The `/rewind` command and double-tap ESC both open the same "message selector"
UI. The `/rewind` slash command (line 511601) simply calls
`openMessageSelector()` (line 511595).

Source: `C1A` component at line 570447. The selector is rendered when
`jw === "message-selector"` (line 606476).

### What the user sees

The message selector displays a scrollable list of user messages (filtered by
`yu1()` at line 571180), plus a synthetic empty entry at the end representing
"now". The user navigates with arrow keys and selects with Enter.

Tip hints vary based on whether file checkpointing (`aw()`) is enabled:
- Without checkpoints: "Double-tap esc to rewind the conversation" (line 556217)
- With checkpoints: "Double-tap esc to rewind the code and/or conversation"
  (line 556224)

### After selecting a message

If file checkpointing is enabled and file changes exist at that point, the user
is shown a confirmation dialog with these options:

| Option                             | Value            | What it does                          |
| ---------------------------------- | ---------------- | ------------------------------------- |
| Restore code and conversation      | `both`           | Rewind files + truncate messages      |
| Restore conversation               | `conversation`   | Truncate messages only                |
| Restore code                       | `code`           | Rewind files only                     |
| Summarize from here                | `summarize`      | Partial compaction (see below)        |
| Never mind                         | `nevermind`      | Cancel                                |

If checkpointing is disabled, only "Restore conversation", "Summarize from
here", and "Never mind" are shown (line 570479).

Source: `F()` at line 570472.

### "Restore conversation" and "Restore code"

Restore conversation (the `onRestoreMessage` callback at line 606546):
1. Truncates the in-memory message array to everything before the selected
   message: `F4.slice(0, S8)` (line 606548)
2. Emits `tengu_conversation_rewind` telemetry (line 606553)
3. Restores the user's original input text from the selected message
4. If the selected message had images, restores those to the paste buffer

Restore code (the `onRestoreCode` callback at line 606480):
- Calls `Ry1()` to rewind file history checkpoints to the selected message's
  UUID

"Both" performs both operations sequentially (lines 570563-570574).

The conversation truncation is destructive to the in-memory state -- messages
after the selected point are dropped. However, the JSONL file is append-only,
so the original records remain on disk. No marker is written to indicate the
rewind happened.

### "Summarize from here" -- Partial Compaction

This option is distinct from a full `/compact`. Instead of summarizing the
entire conversation, it summarizes only the messages after the selected point,
keeping earlier messages intact.

Source: `onSummarize` callback at line 606485, calling `VZ4()` at line 287028.

How it works:

1. The user optionally provides context text (the input field, line 570485).
2. `VZ4()` splits the messages at the selected index:
   - `_` = messages to keep (before selected point): `A.slice(0, q)` (line 287031)
   - `w` = messages to summarize (after selected point): `A.slice(q)` (line 287030)
3. A compaction agent summarizes only the `w` messages.
4. The result contains:
   - `boundaryMarker`: a `compact_boundary` system record with
     `trigger: "manual"` and `compactMetadata` including `userContext` and
     `messagesSummarized` count (line 287122)
   - `messagesToKeep`: the earlier messages (preserved intact)
   - `summaryMessages`: a `user` record with `isCompactSummary: true` and
     a `summarizeMetadata` field:
     ```json
     {
       "summarizeMetadata": {
         "messagesSummarized": 5,
         "userContext": "optional user text"
       }
     }
     ```
     Source: line 287130.
   - `attachments`: re-read file contents, hook results, etc.
5. The in-memory messages are replaced with:
   `[boundaryMarker, ...messagesToKeep, ...summaryMessages, ...attachments, ...hookResults]`
   (line 606520)
6. A toast is shown: "Conversation summarized (Ctrl+O for history)" (line 606541)

Telemetry: `tengu_partial_compact` (line 287111) with trigger `"message_selector"`.

### JSONL persistence and recoverability

The JSONL file is append-only. No records are deleted or moved. When
"Summarize from here" runs, only new records are appended -- the
`compact_boundary`, summary, attachments, and hook results. The kept and
summarized messages remain at their original positions in the file.

The resulting JSONL layout:

```
[...kept msgs...] [...summarized msgs...] [compact_boundary] [summary] [metadata]
                                           ^--- resume loads from here
```

On resume, `umK()` (line 52787) finds the last `compact_boundary` and loads
only records after it. The model does not see the kept or summarized messages
directly -- only the summary. But the full history is still in the file.

Session metadata (title, tag, agent name, etc.) is re-appended after the
boundary via `OT1()` / `reAppendSessionMetadata()` (line 539420), ensuring
metadata survives the boundary cut.

### Finding the summarized records

The `compact_boundary` record contains a `logicalParentUuid` field (line
537980) pointing to the UUID of the last kept message. This field is written
but never read by Claude Code -- it is provenance metadata, like `forkedFrom`
on fork records.

To reconstruct the full history from the JSONL:

1. Parse all records (ignoring the boundary offset optimization)
2. Find the `compact_boundary` record
3. Look up `logicalParentUuid` -- the record with that UUID is the last
   message before the summarized region
4. Everything between that record and the `compact_boundary` is the
   summarized content

Verified empirically against session `53a3602b` (started at v2.1.47,
summarized at v2.1.71):

```
Records 0-408:   kept messages (before logicalParentUuid, inclusive)
Records 409-748: summarized messages (between logicalParentUuid and boundary)
Record  749:     compact_boundary (with logicalParentUuid, compactMetadata)
Record  750:     compact summary  (with summarizeMetadata)
Records 751-752: post-summarize activity (local commands)
```

### How this compares to the other operations

All four context operations preserve full history and write enough information
to reconstruct what happened:

| Operation   | Where history lives          | How to find it                                                                       |
| ----------- | ---------------------------- | ------------------------------------------------------------------------------------ |
| `/compact`  | Same JSONL file              | `compact_boundary` record; all earlier records are the compacted history              |
| Summarize   | Same JSONL file              | `compact_boundary` with `logicalParentUuid`; records between that UUID and the boundary are the summarized messages |
| `/clear`    | Parent session (separate file) | Text pointer `"read the full transcript at: <path>"` in the child session's early entries |
| `/fork`     | Parent session (separate file) | `forkedFrom.sessionId` on every record in the fork's JSONL                          |

`/compact` and "Summarize from here" stay in the same file -- the old records
are still there, just behind the boundary marker. `/clear` and `/fork` create
new session files and write a reference back to the parent.

### Summarize from here vs /compact

| Aspect              | `/compact` (full)                      | Summarize from here (partial)              |
| ------------------- | -------------------------------------- | ------------------------------------------ |
| What gets summarized| Entire conversation                    | Only messages after the selected point     |
| Messages kept       | None (all summarized)                  | Messages before the selected point         |
| Trigger value       | `"auto"` or `"manual"`                 | `"manual"` (with `message_selector` event) |
| `summarizeMetadata` | Not present                            | Present on summary record                  |
| User context input  | No                                     | Yes (optional text field)                  |
| How activated       | `/compact` command or auto-compaction  | Message selector UI only                   |

### Summarize from here vs Restore conversation

| Aspect              | Restore conversation                   | Summarize from here                        |
| ------------------- | -------------------------------------- | ------------------------------------------ |
| Messages after      | Dropped from memory                    | Summarized into compact summary            |
| Model sees          | Only earlier messages                  | Earlier messages + summary of later ones   |
| Knowledge preserved | No                                     | Yes (in summary form)                      |
| JSONL boundary      | No marker written                      | `compact_boundary` record written          |
| Input text restored | Yes (original prompt text)             | No                                         |

## `/fork` -- Copy the Conversation to a New Session

Fork creates a new JSONL file containing a copy of all main-chain conversation
records from the current session. The original session is unmodified and
continues independently.

### How it works

Function `jVz` at line 506821:

1. Generate a new session UUID and JSONL path.
2. Read the current session's JSONL and parse it.
3. Filter to main-chain conversation records: `!M.isSidechain && Fn(M)`
   (line 506835). This keeps `user`, `assistant`, `progress`, `attachment`,
   and `system` records but excludes metadata-only records and sidechain
   entries.
4. Copy each record with:
   - `sessionId` set to the new session UUID
   - `parentUuid` re-linked sequentially (new chain)
   - `forkedFrom: { sessionId: <original>, messageUuid: <original uuid> }`
5. Write the copied records to the new JSONL file.
6. Write a `custom-title` metadata record: `"<title> (Fork)"` or
   `"<title> (Fork N)"` if forks already exist (function `JVz`, line 506863).
7. Resume into the forked session via `q.resume(w, X, "fork")`.

Source: lines 506821-506930.

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

This field is written but never read by Claude Code -- it exists only as
provenance metadata.

### What happens to the original session

Nothing. The original session's JSONL is not modified. No marker, no
termination record, no reference to the fork. The user is told
`To resume the original: claude -r <session-id>`.

### `--fork-session` CLI flag

The `--fork-session` flag (line 610678) can be combined with `--resume` or
`--continue` to resume a session into a new session ID rather than reusing the
original. When `forkSession` is set, the session ID is not re-registered as
active (line 576199). This is distinct from the `/fork` slash command -- it
creates a fresh session ID but reuses the loaded messages without copying them
to a new JSONL file with `forkedFrom` metadata.

### Detecting forks

- From fork: every record has `forkedFrom.sessionId` pointing to the parent.
  This is a structured field, unlike `/clear`'s text pointer.
- From parent: cannot be detected from the parent's JSONL. Must scan sibling
  files for `forkedFrom.sessionId` matching the parent's session ID.

## `--rewind-files` -- Standalone File Rewind (CLI only)

The `--rewind-files <user-message-id>` flag (line 610707) performs a file-only
rewind without entering an interactive session.

Source: lines 574311-574328.

1. Requires `--resume` (validated at line 574211).
2. Looks up the user message UUID in the session (line 574312).
3. Calls `bQq()` to rewind files to the checkpoint state at that message
   (line 574321).
4. Checks `canRewind` -- if false, exits with an error (line 574322).
5. Prints confirmation and exits (line 574328).

This is a non-interactive operation -- it modifies files on disk and exits.
File rewinding must be enabled (`aw()` returns true), otherwise it returns
`{ canRewind: false, error: "File rewinding is not enabled." }` (line 576017).

## Telemetry

| Operation            | Event name                     | Key fields                                           |
| -------------------- | ------------------------------ | ---------------------------------------------------- |
| `/compact`           | (inline in compaction code)    | `preCompactTokenCount`, `postCompactTokenCount`      |
| Summarize from here  | `tengu_partial_compact`        | `trigger`, `messagesKept`, `messagesSummarized`      |
| `/clear`             | `tengu_plan_exit`              | `clearContext`, `outcome`, `planLengthChars`         |
| `/fork`              | `tengu_conversation_forked`    | `message_count`, `has_custom_title`                  |
| Rewind (restore)     | `tengu_conversation_rewind`    | `preRewindMessageCount`, `postRewindMessageCount`    |
| Message selector     | `tengu_message_selector_*`     | `_opened`, `_selected`, `_restore_option_selected`   |

All telemetry is sent externally, not written to the JSONL.

## Summary

| Aspect                | `/compact`                       | `/clear` (clear context)          | `/fork`                            | `/rewind` (restore)                | Summarize from here                |
| --------------------- | -------------------------------- | --------------------------------- | ---------------------------------- | ---------------------------------- | ---------------------------------- |
| JSONL file            | Same file                        | New file                          | New file (copy)                    | Same file                          | Same file                          |
| Marker in JSONL       | `compact_boundary` system record | None                              | None                               | None                               | `compact_boundary` system record   |
| Link to history       | All records before boundary      | Text pointer in child entry       | `forkedFrom` on every record       | Records remain in JSONL            | `logicalParentUuid` on boundary    |
| History preserved?    | Yes (same file, before boundary) | Yes (parent JSONL unmodified)     | Yes (parent JSONL unmodified)      | Yes (records still in JSONL)       | Yes (same file, before boundary)   |
| Model sees            | Compaction summary               | Plan text + transcript path       | Full conversation (copy)           | Only messages before selected      | Partial summary only (on resume)   |
| Original continues?   | Yes (same session)               | No (parent stops)                 | Yes (independent)                  | Yes (same session)                 | Yes (same session)                 |
| Files affected?       | No                               | No                                | No                                 | Yes (if "code" or "both")          | No                                 |
| Can repeat?           | Yes, multiple times              | N/A (new session)                 | Yes, multiple forks                | Yes                                | Yes                                |
