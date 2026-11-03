# Clear, Compact, Fork, and Rewind: How Context Operations Work

Verified against: cli.prettier.js 2.1.317 (2026-11-03)

Five user-facing operations manipulate conversation context. They differ in what the model sees
going forward, whether the session continues or a new one is created, and whether file changes are
affected:

| Operation           | Effect                                                            |
| ------------------- | ----------------------------------------------------------------- |
| `/compact`, auto    | Summarize the conversation within the same session                |
| `/clear`            | Start a new session with empty context                            |
| `/branch`           | Copy the conversation into a new session file and switch to it    |
| `/fork`             | Copy the conversation into a new background session, keep working |
| `/rewind` (Esc Esc) | Truncate the conversation and/or restore files; partial summarize |

## `/compact` -- Summarize Within the Same Session

Command: `rg -n 'Free up context by summarizing the conversation so far'`. Argument hint
`<optional custom summarization instructions>`; disabled when `DISABLE_COMPACT` is truthy.

Compaction replaces the model's active context with a summary. In an interactive session the
original records stay in the JSONL file (see "JSONL persistence" below for the one exception).

### What gets written to the JSONL

1. A `system` record with `"subtype": "compact_boundary"` and `content: "Conversation compacted"`.
   Relocate the builder with `rg -n 'content: "Conversation compacted"'` (the hit preceded by
   `subtype: "compact_boundary"`). On disk the boundary's `parentUuid` is `null`, and
   `logicalParentUuid` names the last message before the boundary. Its `compactMetadata`:

   ```json
   {
     "trigger": "auto" | "manual",
     "preTokens": 12345,
     "userContext": "...",
     "messagesSummarized": 5
   }
   ```

   `userContext` and `messagesSummarized` are set only by partial compaction ("Summarize from here"
   / "Summarize up to here"); a full compaction leaves them undefined, so the keys are absent from
   the JSON. Optional fields added after construction include `postTokens`, `durationMs`,
   `precomputed`, `preCompactDiscoveredTools`, and, when messages were kept verbatim,
   `preservedSegment` (`headUuid`, `anchorUuid`, `tailUuid`) and `preservedMessages`
   (`rg -n 'preservedSegment: \{ headUuid'`).

2. A `user` record with `isCompactSummary: true`. Relocate the message builder from
   `rg -n 'The summary below covers the earlier portion'` by following the constant to its use. The
   text, in order:

   ```
   This session is being continued from a previous conversation that ran out of context.
   The summary below covers the earlier portion of the conversation.

   Summary:
   <summary, with the <analysis> block stripped>

   If you need specific details from before compaction (like exact code snippets, error
   messages, or content you generated), read the full transcript at: <path>
   ```

   - The transcript pointer appears when a transcript path is available.
   - When the oldest content had to be truncated, a `Note:` says part of the earlier conversation
     `was too large to include and is NOT covered by this summary`. When oversized tool results were
     left out, a further `Note:` says how many and that their calls may have had effects.
   - Full compactions only: a closing paragraph that starts
     `Continue the conversation from where it left off` followed by
     `without asking the user any further questions.`, and ends
     `Pick up the last task as if the break never happened.` (relocate with the first phrase). Every
     full-compaction path sets it, manual `/compact` included; partial compaction does not.
   - When messages were kept verbatim after the summary, the summary ends with a paragraph starting
     `The messages after this summary are the most recent messages` that says they are kept verbatim
     and that the summary was written without seeing them.

### Multiple compactions

A session can be compacted many times. Each compaction adds another boundary+summary pair; the last
`compact_boundary` marks where the current active context begins.

### Microcompact

Microcompact is not a summary. It replaces the content of older tool results with
`[Old tool result content cleared]` while keeping the most recent ones
(`rg -n 'tengu_time_based_microcompact'`). 2.1.317 writes no `microcompact_boundary` record; the
subtype is still recognized when reading a transcript (`rg -n 'microcompact_boundary'` finds readers
only).

### When auto-compaction fires

Auto-compaction (`trigger: "auto"`) has three triggers: the token threshold, the API rejecting a
request as prompt-too-long, and idle compaction. Which of the first two applies depends on the
compaction-window source.

#### The compaction window and its source

Relocation: `rg -n 'source: "model-default"'` lands in the window resolver. It returns a window,
always clamped to the model's context window, and a `source`, checked in this order:

| Source          | Origin                                                                |
| --------------- | --------------------------------------------------------------------- |
| `env`           | `CLAUDE_CODE_AUTO_COMPACT_WINDOW`                                     |
| `settings`      | `autoCompactWindow`, per model under `modelSettings` or top level     |
| `clientdata`    | Server-provided window (only while auto-compact is enabled)           |
| `experiment`    | Feature-flag window for some models and the Claude Desktop entrypoint |
| `model-default` | Built-in default for the model, including 1M for 1M-capable models    |
| `unknown-model` | Unrecognized model (see below)                                        |
| `auto`          | None of the above                                                     |

`CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT` skips the `unknown-model` source.

`CLAUDE_CODE_AUTO_COMPACT_WINDOW` accepts `<n>k`, `<n>m`, or a raw token count between 100k and 1M;
a value outside the range is clamped to it, and an unparseable value (including `auto`) is ignored
with a warning naming the variable.

`/autocompact [auto|<tokens>]` (`rg -n 'Set how full the context gets before auto-summarizing'`)
shows the current window and its source, and saves the value per model as
`modelSettings.<model>.autoCompactWindow` in user settings. It accepts `auto` (also `reset`,
`unset`, `default`), `100k` to `1M`, or a bare 100 to 1000 as thousands. It refuses to save while
`CLAUDE_CODE_AUTO_COMPACT_WINDOW` is set, since the env var takes precedence.

#### Threshold or prompt-too-long

When reactive compaction is available (always outside `CLAUDE_CODE_REMOTE`; in a remote session only
with the `tengu_reactive_compact_remote` gate), a window source of `auto` disables the threshold
check entirely: Claude Code sends the request and compacts only when the API rejects it as
prompt-too-long. Every other source enforces the threshold below. The worker-state schema states the
same rule (`rg -n "defers to the API's prompt-too-long"`). The threshold check logs
`autocompact: tokens=<n> level=<level> effectiveWindow=<n>` (`rg -n 'autocompact: tokens='`).

#### The threshold

Relocation: `rg -n '\- 13000'` finds the threshold function.
`rg -n 'CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE'` finds the config reader beside it, which also reads
`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` into a `testPctOverride` field (`parseFloat`, honored only when
`> 0 && <= 100`).

```
usable    = window − min(max_output_tokens, 20000)
threshold = min( floor(usable × pct/100),  usable − 13000 )     # pct valid
          = usable − 13000                                       # pct absent/invalid
```

- `window` is the resolved compaction window above, not necessarily the raw model window.
  `max_output_tokens` honors `CLAUDE_CODE_MAX_OUTPUT_TOKENS`; for large-output models the reserve
  caps at 20,000.
- The operator is `min`, so `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` can only lower the threshold. A
  percentage above roughly 93 does nothing on a 200K window, and above roughly 98.7 does nothing on
  a 1M one. The one exception is a `CLAUDE_CODE_REMOTE` session on a 200K window, where the
  `tengu_peppy_gosling` flag may substitute a higher percentage.
- The variable is read from `process.env`, so the `env` block of `settings.json` sets it as well as
  the shell does. There is no `CODE_` segment: `CLAUDE_CODE_AUTOCOMPACT_PCT_OVERRIDE` does not
  exist.
- The field names `testPctOverride` and `testBlockingOverride` mark both overrides as test hooks
  rather than a supported settings surface.
- Levels: `warn` at `threshold − 20000`, `compact` at the threshold, and `blocked` at the model's
  own window minus the output reserve minus 3000 (not the compaction window), or at
  `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE`. Reaching `blocked` also triggers compaction.
- From `warn` on, the result carries `pctLeft = round((threshold − used) / threshold × 100)`, the
  figure the UI counts down. A status line showing progress toward compaction should divide by the
  threshold for the same reason.
- Auto-compaction requires `autoCompactEnabled` (default `true`) and neither `DISABLE_COMPACT` nor
  `DISABLE_AUTO_COMPACT`. With it off there is no `compact` level: `warn` is measured from the
  usable window, and the session hits the hard `blocked` limit instead.

Worked example, a model whose resolved window is 1,000,000 (source `model-default`, no server or
experiment override, reserve 20,000):

| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | usable  | threshold (compaction fires at) |
| --------------------------------- | ------- | ------------------------------- |
| unset (default)                   | 980,000 | 967,000 (`usable − 13000`)      |
| 75                                | 980,000 | 735,000 (`floor(0.75×980000)`)  |
| 76.5                              | 980,000 | 749,700                         |

Because the percentage multiplies the 980K usable window, not the raw 1,000,000, `75` lands at
735,000, not 750,000.

#### Precomputed summaries and idle compaction

- Precompute. Behind the `tengu_sepia_moth` flag (default off) and the `precomputeCompactionEnabled`
  setting (default on), a background job can build a summary before it is needed. It arms at
  `min(usable − round(usable × fraction), threshold)`, the fraction defaulting to 0.2 from feature
  flags (`rg -n 'precomputeBufferFraction'`). It uses the round-grouped engine and the same prompt,
  and fires PreCompact as `auto` (`tengu_precomputed_compact_*` events). A later compaction swaps it
  in when it still matches the conversation.
- Idle compaction (`rg -n 'Compacted while idle'`). With a 1-hour prompt-cache TTL, Claude Code
  schedules a compaction at 90% of the way from the last activity to the cache's expiry, so the next
  turn does not pay to re-cache a large context. It runs only when auto-compaction and the
  `idleCompaction` setting (default `true`) are on, and the context holds at least
  `max(100000, CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS ?? 200000)` tokens. The notice reads
  `Compacted while idle, before the prompt cache expired`, followed by how to turn it off. Events:
  `tengu_idle_compact_fired`, `tengu_idle_compact_settled`.

Tripwire checklist:

- □ `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` read beside `CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE` into
  `testPctOverride`, guarded `0 < pct <= 100`
- □ threshold = `min(floor(usable*pct/100), usable − 13000)`
- □ usable = window − `min(maxOutput, 20000)`
- □ warn at threshold − 20000; blocked at the model's usable window − 3000
- □ window source `auto` skips the threshold when reactive compaction is available
- □ `CLAUDE_CODE_AUTO_COMPACT_WINDOW` clamped to 100k–1M
- □ gated on `autoCompactEnabled`, `DISABLE_AUTO_COMPACT`, `DISABLE_COMPACT`

### The summarization prompt

Auto-compaction and `/compact` with no argument send the same prompt, word for word. They differ in
which engine runs, the hook trigger, and whether a precomputed summary can be reused.

#### Prompt variants

Relocation: `rg -n 'Your task is to create a detailed summary'`. Three hits, all in one block:

| Opening phrase                                          | Used by                             |
| ------------------------------------------------------- | ----------------------------------- |
| `...summary of the conversation so far`                 | Full compaction (nine-section arms) |
| `...summary of the RECENT portion of the conversation`  | "Summarize from here"               |
| `...summary of this conversation. This summary will be` | "Summarize up to here"              |

Full compaction picks one of eight prompt arms. `CLAUDE_CODE_CURRIED_TRINKET` selects it, else the
`tengu_curried_trinket` flag (`rg -n 'tengu_curried_trinket'`); no value or an unknown one means
`control`:

| Arm                       | Instructions                                                     |
| ------------------------- | ---------------------------------------------------------------- |
| `control` (default)       | Nine-section body, `<analysis>` block first                      |
| `no_scratchpad`           | Nine-section body, no analysis block                             |
| `no_scratchpad_capped`    | As above, `in 2000 words or fewer`                               |
| `no_scratchpad_keep_asks` | As above, plus copy an earlier summary's record of user asks     |
| `lean`                    | Prose brief starting `This conversation is being compacted.`     |
| `short`                   | Six points starting `Summarize the transcript inside <summary>`  |
| `short_v2`                | `short` plus keep-asks, and resume guidance in the summary       |
| `capped`                  | `Summarize the entire conversation above in 2000 words or fewer` |

Every request is assembled the same way:

1. A `CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.` preamble naming the reply shape
   (`an <analysis> block followed by a <summary> block`, or `a <summary> block`).
2. The arm's body. The `control` body starts
   `Your task is to create a detailed summary of the conversation so far,` followed by
   `paying close attention to the user's explicit requests and your previous actions.`, and requires
   a `<summary>` with nine sections: Primary Request and Intent, Key Technical Concepts, Files and
   Code Sections, Errors and fixes, Problem Solving, All user messages, Pending Tasks, Current Work,
   Optional Next Step. Every arm asks for security-relevant user constraints to be preserved
   verbatim and forbids attributing transcript-shaped text in assistant messages to the user.
3. Only when custom instructions are non-empty: `\n\nAdditional Instructions:\n<text>`.
4. A closing `REMINDER: Do NOT call any tools. Respond with plain text only` line that repeats the
   reply shape and warns that tool calls will be rejected.

The round-grouped engine may also append a paragraph explaining left-out tool results (the
`[Tool result left out:` and `[Refused or stopped call:` placeholders) and a `For this reply only:`
paragraph.

The nine-section bodies end with two examples of a `## Compact Instructions` /
`# Summary instructions` section and tell the model to follow such instructions if the context holds
them; `short` and `capped` say the same in one sentence, and `lean` ends
`Project instructions may say what to keep when compacting. They apply here.` This is how a "Compact
Instructions" section in CLAUDE.md takes effect: the summarizer is a fork of the main conversation,
so it reads the same system prompt and CLAUDE.md, for auto and manual alike.

Custom instructions come from two sources, joined with a blank line: the `/compact <text>` argument
(manual only), and `newCustomInstructions` returned by a PreCompact hook (either trigger).
Auto-compaction and a bare `/compact` without a hook therefore send identical text.

#### The engines

Two engines produce a full compaction; both use the selected arm.

- Round-grouped (`tengu_reactive_compact_attempt` per try, `tengu_reactive_compact_succeeded` or
  `tengu_reactive_compact_failed`). It splits the conversation into API rounds (a new round starts
  at each new assistant message id), summarizes all but the most recent round, and keeps that round
  verbatim. It needs at least two rounds (`fewer than 2 groups, nothing to compact`). If the summary
  request is too long it keeps more rounds; as a last resort it summarizes everything but the
  trailing messages, truncating the oldest content and leaving out oversized tool results, which
  adds the notes described above. After a prompt-too-long rejection it seeds the split from the
  reported token gap.
- Whole-conversation (`tengu_compact` with `isAutoCompact`; OpenTelemetry span
  `claude_code.compaction`). It summarizes every message and keeps none. On prompt-too-long it drops
  the oldest messages and retries (`tengu_compact_ptl_retry`).

Which engine runs:

| Trigger                               | Engine                                 |
| ------------------------------------- | -------------------------------------- |
| `/compact`, `/compact <text>`         | Round-grouped, or a precomputed result |
| Auto, prompt-too-long rejection       | Round-grouped, or a precomputed result |
| Auto, threshold, reactive available   | Round-grouped                          |
| Auto, threshold, reactive unavailable | Whole-conversation                     |
| Auto, threshold, no query source      | Whole-conversation                     |
| Auto, in-process teammate             | Whole-conversation                     |
| Idle compaction                       | Same path as `/compact`, as `auto`     |

The routed case logs `autocompact: routing through reactive (thresholdSource=...)` and emits
`tengu_auto_compact_routed_reactive` (`rg -n 'routing through reactive'`). There is no fallback to
the whole-conversation engine when it fails. When the last assistant reply came from a model with a
larger window than the current one, and the conversation would be `blocked` in the current window,
auto-compaction first summarizes with that larger model (`rg -n 'compact_larger_model'`).

#### Other differences

- Hooks. PreCompact and PostCompact fire with `trigger: "manual"` for `/compact` and `"auto"` for
  auto-compaction. A PreCompact hook can block compaction; manual compaction then shows
  `compaction blocked by PreCompact hook`, auto-compaction suppresses that notification.
- Precomputed summaries. A bare `/compact` reuses a ready precomputed summary, but `/compact <text>`
  never does (`miss_custom_instructions`), and neither does a `/compact` whose PreCompact hook
  returns instructions (`miss_hook`).
- Gating. `DISABLE_COMPACT` removes `/compact`, the summarize options of `/rewind`, and
  auto-compaction. `autoCompactEnabled: false` or `DISABLE_AUTO_COMPACT` disables only
  auto-compaction. Auto-compaction also stops on a consecutive-failure breaker (three failures) and
  a rapid-refill breaker (`autocompact: rapid-refill breaker tripped`).
- Boundary record. `compactMetadata.trigger` is `"auto"` or `"manual"` accordingly.

Tripwire checklist:

- □ three `Your task is to create a detailed summary` variants
- □ eight arms, default `control`, chosen by `CLAUDE_CODE_CURRIED_TRINKET`, then
  `tengu_curried_trinket`
- □ request = CRITICAL preamble + body + optional `Additional Instructions:` + REMINDER
- □ `/compact` uses the round-grouped engine
- □ window source `auto` waits for prompt-too-long
- □ full compactions append the `without asking the user any further questions` suffix; partial ones
  do not
- □ precompute reuse refused for custom and hook instructions

## `/clear` -- Start a New Session

`/clear` ends the current session and starts a new one in a fresh JSONL file. Context is also
cleared by approving a plan with a clear-context option, and by implementing an Ultraplan in a fresh
session. All three run the same reset, exported as `clearConversation`
(`rg -n 'clearConversation'`), with a `resetTrigger` of `clear`, `plan_mode_exit`, or
`fresh_session`.

### The `/clear` command

`rg -n 'Start a new session with empty context'`. The description continues
`previous session stays on disk (resumable with /resume)`; aliases `/reset` and `/new`; argument
`[name]`.

The reset:

1. Runs SessionEnd hooks with `reason: "clear"`.
2. Empties the message array; clears the read-file state, file history (checkpoints), attribution,
   session env vars, and the plan doc.
3. Kills tasks running in the foreground. Backgrounded tasks keep running into the new session.
4. Generates a new session ID and records the old one as its parent in memory (telemetry carries it
   as `parent_session_id`).
5. Titles. With `/clear <name>`, a `custom-title` record with that name is appended to the old
   session's transcript. Without a name, a custom title the old session had (and its agent name) is
   carried to the new session.
6. Runs SessionStart hooks with source `clear` (`rg -n 'SessionStart hooks after /clear'`).

### Clear context from plan approval

The plan-approval dialog offers a clear-context option only when the setting
`showClearContextOnPlanAccept` is `true` (default `false`; `rg -n 'showClearContextOnPlanAccept'`).
The first option then clears context; its label is `Yes, clear context (<n>% used) and ...`
(`rg -n 'Yes, clear context'`). The rest keep it:

| Approval option                 | Clears? | Permission mode   | Offered when                 |
| ------------------------------- | ------- | ----------------- | ---------------------------- |
| `yes-bypass-permissions`        | yes     | bypassPermissions | bypass mode is available     |
| `yes-auto-clear-context`        | yes     | auto              | else, auto mode is available |
| `yes-accept-edits`              | yes     | acceptEdits       | otherwise                    |
| `yes-accept-edits-keep-context` | no      | bypassPermissions | bypass mode is available     |
| `yes-resume-auto-mode`          | no      | auto              | else, auto mode is available |
| `yes-accept-edits-keep-context` | no      | acceptEdits       | otherwise                    |
| `yes-default-keep-context`      | no      | default           | unless the model needs auto  |
| `ultraplan`                     | no      | (cloud session)   | Ultraplan is available       |
| `no`                            | no      | (stays in plan)   | always; takes feedback text  |

Bypass takes precedence over auto mode in both the clear and keep rows. The clear options emit
`tengu_plan_exit` with `clearContext: true`; the keep options emit it with `clearContext: false`.

The new session starts with this message
(`rg -n 'If you need specific details from before exiting plan mode'`):

```
Implement the following plan:

<plan text>

If you need specific details from before exiting plan mode (like exact code snippets, error
messages, or content you generated), read the full transcript at: <parent session JSONL path>
```

When teams are enabled and the permission mode is `default`, a hint to spawn named teammates is
appended, and when the user typed feedback, `User feedback on this plan: <text>`.

### The ExitPlanMode tool_use is identical either way

The JSONL `tool_use` block for ExitPlanMode looks the same whether the user clears or keeps context.
In the CLI the `plan` (and `planFilePath`) are injected from the plan file on disk by
`normalizeToolInput`, not sent by the model; `allowedPrompts` is accepted but described as
`Deprecated: no longer used.` There is no `clearContext` field: the choice is made in the UI after
the tool call is written.

### Cross-session links

| Path                 | Link from child to parent                                 |
| -------------------- | --------------------------------------------------------- |
| Plan approval, clear | `read the full transcript at: <path>` in the first prompt |
| `/clear`             | None on disk                                              |

In the process that ran `/clear`, the `/rewind` selector offers a `/resume <id> (previous session)`
row that resumes the parent (`rg -n '" \(previous session\)"'`). From the parent, a clear cannot be
detected from its JSONL; scan sibling JSONL files for the transcript pointer.

### What is NOT in the JSONL

- No `clearContext` field on any record
- No termination marker or system record in the parent session; the only possible addition is the
  `custom-title` record from `/clear <name>`
- The ExitPlanMode `tool_use` record is indistinguishable from a keep-context approval

## `/rewind` (Esc Esc) -- The Message Selector

`/rewind` (aliases `/checkpoint`, `/undo`) emits an `open_message_selector` event
(`rg -n 'type: "open_message_selector"'`), which opens the same selector as double-tapping Esc. It
is not available non-interactively.

### What the user sees

A scrollable list of user messages plus a synthetic empty entry for "now", and, after `/clear`, the
`/resume <id> (previous session)` row at the top. Tips (`rg -n 'Double-tap esc to rewind'`):

- File checkpointing off: `Double-tap esc to rewind the conversation to a previous point in time`
- File checkpointing on:
  `Double-tap esc to rewind the code and/or conversation to a previous point in time`

File checkpointing is on when `fileCheckpointingEnabled` (default `true`) and not
`CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING`; in the SDK it needs
`CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING`.

### After selecting a message

With checkpointing off, selecting a message restores the conversation immediately, with no option
list. With checkpointing on, a dialog offers:

| Option                        | Value             | What it does                | Shown when    |
| ----------------------------- | ----------------- | --------------------------- | ------------- |
| Restore code and conversation | `both`            | Rewind files and messages   | files changed |
| Restore conversation          | `conversation`    | Truncate messages only      | always        |
| Restore code                  | `code`            | Rewind files only           | files changed |
| Summarize from here           | `summarize`       | Summarize it and later ones | compaction on |
| Summarize up to here          | `summarize_up_to` | Summarize earlier messages  | compaction on |
| Never mind                    | `nevermind`       | Cancel                      | always        |

"Files changed" means files changed since the selected message. The summarize options take optional
`add context (optional)` text and are hidden when `DISABLE_COMPACT` is set
(`rg -n 'Summarize up to here'`).

### "Restore conversation" and "Restore code"

Restore conversation:

1. Truncates the in-memory message array to everything before the selected message.
2. Emits `tengu_conversation_rewind` (`preRewindMessageCount`, `postRewindMessageCount`,
   `messagesRemoved`, `rewindToMessageIndex`, `source`).
3. Restores the selected message's text, and any images, to the prompt input.

Restore code rewinds the file-history checkpoints to the selected message. Files at a tracked path
that became a symlink or other non-regular file are skipped and reported. "Both" does both.

The truncation drops later messages from memory only; their records remain in the JSONL, and no
record marks the rewind itself.

### Partial compaction: "Summarize from here" and "Summarize up to here"

Relocation: `rg -n '"tengu_partial_compact"'`. Both run PreCompact and PostCompact hooks with
`trigger: "manual"`, and pass the optional text to the summarizer as `User context: <text>`.

| Direction | Summarized                       | Kept verbatim       | Prompt opening          |
| --------- | -------------------------------- | ------------------- | ----------------------- |
| `from`    | The selected message and later   | Messages before it  | `...the RECENT portion` |
| `up_to`   | Messages before the selected one | It and all after it | `...this conversation.` |

The result:

- A `compact_boundary` with `trigger: "manual"`, `userContext`, `messagesSummarized`, and
  `preservedSegment` / `preservedMessages` naming the kept messages. `logicalParentUuid` is the last
  kept message (`from`) or the last message before the selected one (`up_to`).
- A `user` summary record with `isCompactSummary: true` and, when anything is kept,
  `summarizeMetadata: { messagesSummarized, userContext, direction }`. It has no "Continue the
  conversation" suffix.
- Re-read file attachments and hook results.

In memory the conversation becomes boundary, kept messages, summary (`from`) or boundary, summary,
kept messages (`up_to`), then attachments and hook results. A `Conversation summarized` toast
follows, and `from` also restores the selected prompt's text to the input. Telemetry:
`tengu_partial_compact` with `trigger: "message_selector"`, `direction`, `messagesKept`,
`messagesSummarized`, `hasUserFeedback`.

### JSONL persistence and recoverability

Compaction, partial or full, appends records; it moves and deletes none. The kept and summarized
messages stay at their original positions:

```
[...kept msgs...] [...summarized msgs...] [compact_boundary] [summary] [later records]
```

On resume, the loader starts at the last `compact_boundary`, then restores the kept messages that
its `preservedSegment` (a parent-chain walk from `tailUuid` back to `headUuid`) or
`preservedMessages` (an explicit list) names, re-linking them after `anchorUuid`. The model
therefore sees the summary plus the kept messages, as it did before the restart, but not the
summarized ones.

The exception: with `CLAUDE_CODE_TRANSCRIPT_LOCAL_GC` in a non-interactive (`-p`) session, or in a
remote-worker session with that env var or its `tengu_transcript_local_gc` flag, the transcript is
rewritten after a boundary to drop rows the loader would skip
(`rg -n 'CLAUDE_CODE_TRANSCRIPT_LOCAL_GC'`). Interactive sessions never enable it.

Session metadata (title, tag, agent name) is re-appended after the boundary, so it survives the cut.

### Finding the summarized records

- Partial vs full: `compactMetadata.messagesSummarized` is present on partial compaction and absent
  on full compaction. `logicalParentUuid` appears on both and does not discriminate.
- Summarized region of a partial `from` compaction: the records after the one named by
  `logicalParentUuid` and before the boundary.
- Kept messages of any compaction that kept some: those named by `preservedSegment` or
  `preservedMessages`.

### Summarize vs `/compact` vs Restore conversation

| Aspect              | `/compact` (full)      | Summarize from/up to here  | Restore conversation |
| ------------------- | ---------------------- | -------------------------- | -------------------- |
| What is summarized  | All but latest round   | One side of the selection  | Nothing              |
| Kept verbatim       | Latest round           | The other side             | Messages before      |
| Trigger value       | `"auto"` or `"manual"` | `"manual"`                 | (no boundary)        |
| `summarizeMetadata` | Absent                 | Present when anything kept | Absent               |
| User text input     | `/compact <text>`      | Optional context field     | No                   |
| Input text restored | No                     | `from` only                | Yes                  |
| How activated       | `/compact` or auto     | Message selector           | Message selector     |

The `/compact` column describes the round-grouped engine; the whole-conversation engine keeps no
messages.

## `/branch` -- Copy the Conversation and Switch to the Copy

`rg -n 'Create a branch of the current conversation'`:
`Create a branch of the current conversation at this point`, argument `[name]`. The original
session's file is not modified and stays resumable.

### How it works

1. Generate a new session ID and transcript path.
2. Stream the current transcript and keep the non-sidechain conversation records whose UUIDs are in
   the in-memory conversation (so after a compaction, only what the model currently sees).
3. Write each kept record with `sessionId` set to the new ID, `parentUuid` re-linked sequentially
   (progress records do not advance the chain), `isSidechain: false`, and
   `forkedFrom: { sessionId: <original>, messageUuid: <original uuid> }`. A `model_refusal_fallback`
   system record gets `neutralizedByFork: true`.
4. Carry over `content-replacement`, `memory-mode`, and `relocated` records, and add `atis-latch`
   and `tools-used` records.
5. Name the branch: the `[name]` argument, else `<first prompt> (Branch)`, or `(Branch N)` when that
   title exists (`rg -n ' \(Branch\)'`; the first-prompt fallback is `Branched conversation`). Both
   a `custom-title` and an `agent-name` record are written.
6. Resume into the branch in `fork` mode and print a message starting
   `Branched conversation. You are now in the new branch (session <id>).`, which names
   `/resume <original>` and `claude -r <original>` as the ways back
   (`rg -n 'You are now in the new branch'`).

Telemetry: `tengu_conversation_forked` (`message_count`, `has_custom_title`).

### Detecting branches

- From the branch: every copied record has `forkedFrom.sessionId` pointing to the parent, a
  structured field unlike the plan-approval transcript pointer.
- From the parent: not detectable from its JSONL; scan sibling files for a matching
  `forkedFrom.sessionId`.

## `/fork` -- Copy the Conversation into a Background Session

`/fork` has two definitions. Which one registers depends on the agent view, which is enabled unless
`CLAUDE_CODE_DISABLE_AGENT_VIEW` or the `disableAgentView` setting turns it off (`IS_DEMO` also
selects the second):

| Agent view | Description                                                                  |
| ---------- | ---------------------------------------------------------------------------- |
| enabled    | `Copy this conversation into a new background session and keep working here` |
| disabled   | `Spawn a background agent that inherits the full conversation`               |

The first takes an optional `[prompt]`, the second a required `<directive>`. With the agent view
enabled, `/subtask` (`Send a subagent off with your full context; its result comes back here`) is
also registered.

The default `/fork` (`rg -n 'Copy this conversation into a new background session'`):

- Refuses in coordinator mode, when session persistence is off, and when the session was started
  with safe or bare mode or similar launch flags the copy would not inherit (`Can't fork: ...`).
- Copies the current transcript file byte for byte to a new session ID, and appends a `last-prompt`
  record pinning the fork point. When the original is working in the same checkout or a linked
  worktree, it also appends a `fork_briefing` telling the fork to use its own worktree.
- Launches a background `claude --resume <copy> --fork-session [-- <prompt>]` session.
- The current session continues unchanged. The fork's name gets a fork marker; it appears in the
  agent listing, and the two sessions can message each other there.
- Telemetry: `tengu_session_fork` (`had_prompt`, `message_count`, `had_worktree`, `relocated`).

The copy is not rewritten per record, so its records carry no `forkedFrom` field.

### `--fork-session` CLI flag

`rg -n 'When resuming, create a new session ID'`: `--fork-session` resumes under a new session ID
instead of reusing the original, with `--resume` or `--continue`. It does not do the per-record
`forkedFrom` rewrite that `/branch` does.

## `--rewind-files` -- Standalone File Rewind (CLI only)

`--rewind-files <user-message-id>` (hidden; `rg -n 'rewind-files <user-message-id>'`) restores files
to the state at a user message and exits:

1. Requires `--resume`, and refuses a prompt
   (`is a standalone operation and cannot be used with a prompt`).
2. Requires the ID to be a user message in the session.
3. Restores files to that message's checkpoint; reports skipped non-regular paths as a warning.
4. Prints `Files rewound to state at message <id>` and exits.

File rewinding must be enabled (the same checkpointing rule as `/rewind`), else it fails with
`File rewinding is not enabled.`; a message without a checkpoint fails with
`No file checkpoint found for this message.`

## Telemetry

| Operation          | Event                                | Key fields                     |
| ------------------ | ------------------------------------ | ------------------------------ |
| Whole-conversation | `tengu_compact`                      | `isAutoCompact`, token counts  |
| Round-grouped      | `tengu_reactive_compact_succeeded`   | `trigger`, `summaryPromptArm`  |
| Routed auto        | `tengu_auto_compact_routed_reactive` | `thresholdSource`              |
| Idle compaction    | `tengu_idle_compact_fired`           | `outcome`, `contextTokens`     |
| `/autocompact`     | `tengu_autocompact_command`          | `action`, `tokens`             |
| Summarize          | `tengu_partial_compact`              | `direction`, message counts    |
| Plan approval      | `tengu_plan_exit`                    | `clearContext`, `outcome`      |
| `/branch`          | `tengu_conversation_forked`          | `message_count`                |
| `/fork`            | `tengu_session_fork`                 | `had_prompt`, `message_count`  |
| Rewind (restore)   | `tengu_conversation_rewind`          | message counts, `source`       |
| Message selector   | `tengu_message_selector_*`           | `_opened`, `_selected`, others |

`/clear` has no dedicated event. All telemetry is sent externally, not written to the JSONL.

## Summary

| Operation  | JSONL file      | Marker in JSONL       | Link to history                          |
| ---------- | --------------- | --------------------- | ---------------------------------------- |
| `/compact` | Same file       | `compact_boundary`    | Records before the boundary              |
| Summarize  | Same file       | `compact_boundary`    | `messagesSummarized`, `preservedSegment` |
| `/clear`   | New file        | None                  | Plan path: transcript pointer; else none |
| `/branch`  | New file (copy) | None                  | `forkedFrom` on every record             |
| `/fork`    | New file (copy) | `last-prompt` trailer | Byte copy of the parent's records        |
| `/rewind`  | Same file       | None                  | Records remain in the JSONL              |

| Operation  | Model sees afterwards                 | Original continues?   | Files affected? |
| ---------- | ------------------------------------- | --------------------- | --------------- |
| `/compact` | Summary + latest round                | Yes (same session)    | No              |
| Summarize  | Summary + the kept side               | Yes (same session)    | No              |
| `/clear`   | Empty, or plan text + transcript path | No (new session)      | No              |
| `/branch`  | In-memory conversation (copy)         | Not active; resumable | No              |
| `/fork`    | Original: unchanged                   | Yes (fork runs apart) | No              |
| `/rewind`  | Messages before the selected one      | Yes (same session)    | If code chosen  |
