# Command Input History

Verified against: cli.prettier.js 2.1.317 (2026-11-03)

Claude Code keeps a global input history file separate from the JSONL conversation transcripts. It
powers up-arrow/down-arrow recall of previous inputs and the ctrl+r prompt search.


## History file

Location: `~/.claude/history.jsonl`, created with mode `0600`. When a host supplies its own storage
interface, reads and appends go through that interface's `history` namespace instead of the file.

Format: append-only JSONL, one record per recorded input.

Record structure:

```json
{
  "display":        "the user's input text",
  "pastedContents": {},
  "timestamp":      1773264920443,
  "project":        "/Users/you/your-project",
  "sessionId":      "7643d55f-0c2f-4e0d-b9d6-81b37495d4e0"
}
```

| Field            | Description                                                              |
| :--------------- | :----------------------------------------------------------------------- |
| `display`        | The input text; a bash-mode input is stored with a leading `!`           |
| `pastedContents` | Pasted text keyed by placeholder number (see Pasted content)             |
| `timestamp`      | `Date.now()` at recording, forced strictly increasing within one process |
| `project`        | Absolute path to the project directory                                   |
| `sessionId`      | UUID of the session that recorded the input; optional when read          |

On read, a line that fails to parse or fails the record schema is skipped
(`Skipping malformed history line`), and a malformed paste record is dropped from its line on its
own. Relocate the reader and schema with `rg -n 'Skipping malformed history line'`; the record
schema, the 100-record cap and the 1024-character inline-paste threshold are defined just above it
in the same module.


## Pasted content

Only pasted text is recorded, and only pastes whose `[Pasted text #N ...]` placeholder is still in
the input. Pasted images are not recorded. Each paste record carries `id`, `type` (`text`), and
optional `mediaType` and `filename`, plus the text in one of two forms:

| Paste size       | Stored as                                                |
| :--------------- | :------------------------------------------------------- |
| Up to 1024 chars | `content`: the text inline in the history line           |
| Over 1024 chars  | `contentHash`: first 16 hex digits of the text's SHA-256 |

A hashed paste's text goes to `~/.claude/paste-cache/<hash>.txt` (`rg -n '"paste-cache"'`;
`rg -n 'invalid paste-content hash'` finds the path builder). The history line is appended only
after the pending paste writes finish. A paste that can no longer be resolved is recalled as
unavailable, and telemetry reports `paste_store_content_lost`.


## When an input is recorded

`rg -n 'Failed to write prompt history'` relocates the writer. Recording an input:

1. Skips it when `CLAUDE_CODE_SKIP_PROMPT_HISTORY` is truthy, and in a child session started under
   `CLAUDE_CODE_CHILD_SESSION` unless `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE` is set.
2. Skips it when it looks sensitive: the typed text (after a leading `!`) or any pasted text matches
   the secret-pattern detector, or it is a slash command defined as sensitive and called with
   arguments.
3. Skips it when it equals the previous recorded input in the same project and session and neither
   has pastes (consecutive duplicate).
4. Queues the record and starts an asynchronous flush at once. The flush takes a lock on
   `history.jsonl` (lock-file based, stale after 10 s) and appends every queued record. A failed
   flush retries after 500 ms, giving up after five consecutive failures; queued records are flushed
   again on exit (`history_save_exit_flush_failed` if that fails). Telemetry outcome names are
   `history_save`, `history_save_lock_failed` and `history_save_write_failed`.

Readers in the same process see queued records before flushed ones. When a submission is undone, its
record is withdrawn: dropped from the queue, or skipped on read if it was already written.

Cleared drafts: an input the user clears from the prompt is kept in memory (at most 10, and at most
10,000,000 characters in all) and offered in up-arrow recall for the same project and session. It is
never written to `history.jsonl`.


## Up-arrow recall

The up-arrow reader reads the file backwards (most recent first) and:

1. Skips records from other projects (`project` must equal the current project path).
2. Yields records with the current `sessionId` first, interleaving cleared drafts by timestamp.
3. Then yields the buffered records from other sessions in the same project.
4. Stops after 100 project records in all.

Up-arrow history is therefore scoped to the project but spans its sessions: a brand-new session in
the same project can recall inputs from earlier sessions at once.

Records load lazily in pages, each request rounded up to a multiple of 10. The page loader sits in
the module just above the navigation hook, which posts the `search-history-hint` notification
(`rg -n 'search-history-hint'`) after two steps back. That hint names the ctrl+r search.

Mode filter: the mode the prompt is in when navigation starts decides. In bash mode only records
whose `display` starts with `!` are offered. In prompt mode no filter applies, and bash-mode records
appear alongside prompts.

The loaded list is reloaded when this process records a new entry or the mode changes, so inputs
another process appends appear only after such a reload.


## Ctrl+r prompt search

ctrl+r (`history:search`) opens a picker titled `Search prompts · <scope>` with the placeholder
`Filter history…` (`rg -n 'Search prompts '`). ctrl+s (`historySearch:cycleScope`,
`rg -n 'historySearch:cycleScope'`) cycles the scope through `session`, `project` and `everywhere`;
it starts at `everywhere`, and telemetry reports the change as `tengu_history_picker_scope`.

Unlike up-arrow recall, the search is not capped at 100 records. It reads the whole file newest
first, drops repeats of the same text with the same paste references, and stops at a 16 MiB text
budget, marking the list truncated (`history_search_scan` outcome `text_limit_reached`). Pasted text
is expanded into the searchable text up to 4 MiB in all, each paste clipped to 32,768 characters.


## Size and retention

`history.jsonl` has no size cap and is not pruned by age by default. The retention sweep (the
`cleanupPeriodDays` setting, default 30) deletes only leftover `history.jsonl.tmp.<8 hex>` staging
copies older than the cutoff. Entries older than the cutoff are pruned from the file only for a
HIPAA-flagged organization with `tengu_hipaa_history_retention_prune` on
(`rg -n 'tengu_hipaa_history_retention_prune'`). The count is reported as `historyEntriesPruned` in
`tengu_retention_sweep`.

`claude purge [path]` (`rg -n 'prompt\(s\) typed in this project'`) removes that project's lines
from `history.jsonl`; `claude purge --all` deletes the file (`prompt history across all projects`).


## Interaction with context operations

The input history is independent of the conversation transcript. `/compact`, `/clear`, `/branch`,
`/fork` and "Summarize from here" change what the model sees but do not modify `history.jsonl`.
Their only effect is through `sessionId`, which decides the up-arrow ordering. See
`CLEAR_COMPACT_FORK_CONTEXT.md` for the operations themselves.

| Operation  | Effect on input history                                                          |
| :--------- | :------------------------------------------------------------------------------- |
| `/compact` | None. Same session, same `sessionId`                                             |
| `/clear`   | New `sessionId`; earlier inputs drop to the other-sessions tier                  |
| `/branch`  | Moves into a copy with a new `sessionId`; same effect as `/clear`                |
| `/fork`    | None for the current session: the copy runs as a separate background session     |
| Resume     | Same `sessionId` as the resumed session, unless `--fork-session` gives a new one |

After `/clear` or `/branch`, the session has no same-session records yet, so up-arrow falls through
to other sessions in the project: previous inputs are still recalled, ranked below anything typed in
the new session. Cleared drafts are tied to the old `sessionId` and are no longer offered.


## Edge case: concurrent sessions with the same sessionId

When two Claude Code instances resume the same session (`claude --continue` in two terminals in the
same project), both record under the same `sessionId`. Appends are serialized by the history lock,
so both instances' inputs land interleaved in the file under that one ID.

Each instance then recalls the other's inputs as same-session history, in file order, once its list
reloads. This is history contamination, not data loss: both inputs are kept, but they read as one
merged stream.

Contrast with bash history, where two shells that read the file on startup and write it on exit lose
entries to the last writer. Claude Code's locked append avoids that failure mode but merges the
history of concurrent sessions that share an ID.


## Summary

| Aspect               | `history.jsonl`                        | Session transcript JSONL     |
| :------------------- | :------------------------------------- | :--------------------------- |
| Scope                | Global, all projects and sessions      | One file per session         |
| Written              | Queued, flushed at once under a lock   | Per message                  |
| Affected by /clear   | New `sessionId` changes up-arrow order | New file created             |
| Affected by /compact | No effect                              | Boundary + summary appended  |
| Cross-session        | Yes, within the project (up-arrow)     | No, each file is independent |
| Mode-filtered        | Bash mode shows only `!` records       | No                           |
| Capacity             | Up-arrow: 100 per project; search: all | Entire visible chain loaded  |


## Tripwires

- □ `history.jsonl` record keys are `display`, `pastedContents`, `timestamp`, `project`, `sessionId`
- □ up-arrow cap is 100 project records, current session first
- □ text pastes over 1024 characters go to `paste-cache/<16 hex>.txt`; images are not recorded
- □ `CLAUDE_CODE_SKIP_PROMPT_HISTORY` disables recording
- □ ctrl+r search scopes are `session`, `project`, `everywhere`, starting at `everywhere`
- □ entry-level age pruning is gated by `tengu_hipaa_history_retention_prune`
