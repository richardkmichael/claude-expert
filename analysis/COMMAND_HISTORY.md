# Command Input History

Claude Code maintains a global input history file separate from the JSONL
conversation transcripts. This file powers the up-arrow/down-arrow navigation
through previous inputs.


## History file

Location: `~/.claude/history.jsonl`

Format: append-only JSONL, one record per user input, written immediately
(not batched or flushed on exit).

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

| Field            | Description                                                      |
| :--------------- | :--------------------------------------------------------------- |
| `display`        | The input text as shown in the prompt                            |
| `pastedContents` | Map of pasted content (images, text); large items stored by hash |
| `timestamp`      | `Date.now()` at time of input                                   |
| `project`        | Absolute path to the project directory                           |
| `sessionId`      | UUID of the session that recorded the input                      |


## How history is read (up-arrow)

The history reader (`ej1()`, line ~222929 in cli.prettier.js 2.1.76) uses a
two-phase filter:

1. Read history backwards (most recent first)
2. Skip records from other projects (must match current project path)
3. Yield records matching the current sessionId first
4. Then yield records from other sessions in the same project
5. Cap at 100 total records

This means up-arrow history is scoped to the current project but spans
sessions within that project. A brand new session in the same project will
immediately have up-arrow access to inputs from previous sessions.

Records are loaded lazily in batches of 10 (`rjz()`, line ~574239), with a
caching layer keyed by mode.


## Mode filtering

There is an additional filter by input mode. The function `bm()` classifies
each history entry as either "bash" mode (entries starting with `!`) or
"prompt" mode (regular inputs). When navigating history:

- In prompt mode, bash-mode entries (`!echo hello`, `!git status`, etc.)
  are skipped
- In bash mode, prompt-mode entries are skipped

This means the two input modes maintain effectively separate history streams,
even though they're interleaved in the same file.


## Interaction with context operations

The input history is entirely independent of the JSONL conversation
transcript. Context operations (`/compact`, `/clear`, `/fork`, "Summarize
from here") affect what the model sees but have no effect on the input
history file.

However, `/clear` and `/fork` create new sessions with new sessionIds,
which changes the history reader's prioritization:

| Operation  | Effect on input history                                          |
| :--------- | :--------------------------------------------------------------- |
| `/compact` | None. Same session, same sessionId                               |
| `/clear`   | New sessionId. Previous session's inputs become lower priority   |
| `/fork`    | New sessionId. Previous session's inputs become lower priority   |
| Resume     | Same sessionId as the resumed session. History continues in-band |

After `/clear`, the new session has no same-session history entries yet, so
the reader falls through to other sessions in the same project. This means
you still see previous inputs via up-arrow, but they are deprioritized
relative to any inputs in the new session.


## Edge case: concurrent sessions with the same sessionId

When two Claude Code instances resume the same session (`claude --continue`
in the same project), both processes share the same sessionId. Since the
history file is append-only and written in real-time, both instances' inputs
are interleaved in the file under the same sessionId.

The result: each instance sees the other's inputs in its up-arrow history,
merged by timestamp. This is history contamination, not data loss -- both
inputs are preserved, but they appear as a single merged stream.

Contrast with bash history, where two shells reading the same history file
on startup and writing on exit causes "last writer wins" data loss. Claude
Code's append-only approach avoids that failure mode but introduces a
different one: merged history from concurrent sessions sharing an ID.


## Summary

| Aspect             | Input history (`history.jsonl`)  | Conversation transcript (session JSONL) |
| :----------------- | :------------------------------- | :-------------------------------------- |
| Scope              | Global, all sessions             | Per-session file                        |
| Written            | Immediately on each input        | Immediately on each message             |
| Affected by /clear | New sessionId changes priority   | New file created                        |
| Affected by /compact | No effect                      | Boundary + summary appended             |
| Cross-session      | Yes, falls through to same project | No, each file is independent          |
| Mode-filtered      | Yes (bash vs prompt)             | No                                      |
| Capacity           | 100 records loaded per project   | Entire visible chain loaded             |
