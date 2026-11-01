# Session Resume: The "Resume as-is vs Summary" Prompt

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)
Verified against: cli.prettier.js 2.1.277 (2026-09-19)

When a user invokes `claude -r` / `claude --resume` and the selected conversation is both old enough
and large enough, Claude Code shows a post-resume overlay asking whether to compact the session or
keep it as-is.

## Locating it

Grep `tengu_resume_return_action`. The single hit is inside the handler that records the user's
choice; the gate function sits immediately above it in the same module. Grep
`resumeReturnDismissed` to land in the gate directly.

The gate is a plain predicate: it returns either `null` (do not show the overlay) or a
`{ sessionAgeMinutes, estimatedTokens }` payload that the overlay and the telemetry event both
consume.

## When the prompt is shown

Every one of these must hold. They are evaluated in this order, each returning early:

1. At least one of the feature gates `tengu_gleaming_fair` or `tengu_gleaming_fair_reuse` is on.
   Both are server-controlled.
2. The global config flag `resumeReturnDismissed` is not set.
3. A user or assistant message exists whose timestamp is older than one minute. The most recent such
   message is the one measured; anything inside the last minute is ignored so that a freshly written
   message cannot make the session look current.
4. That message's age in minutes is at least `CLAUDE_CODE_RESUME_THRESHOLD_MINUTES` (default 70).
5. The estimated token count of the loaded transcript is at least
   `CLAUDE_CODE_RESUME_TOKEN_THRESHOLD` (default `1e5`).

Tripwires for a future version:

    □ two gate names, OR-ed              □ minute threshold default 70
    □ dismissal flag checked before both thresholds
    □ token threshold default 1e5        □ one-minute recency floor on the measured message

## Outcomes

The overlay resolves to one of `compact`, `continue`, `dismiss`, `never`, `cancelled`. Grep the
option list to relocate the overlay definition; `cancelled` is its default.

`cancelled` returns without recording anything. `never` writes `resumeReturnDismissed` into the
global config, which is the "don't ask me again" path. `compact` runs compaction.

`tengu_gleaming_fair_reuse` adds a second path that reuses an already-computed summary instead of
compacting afresh. When that gate is on, two synthetic actions appear in telemetry in place of the
user's own choice: `skipped_no_summary` when no precomputed summary exists, recorded without showing
the overlay at all, and `summary_gone` when the user chose `compact` but the summary is no longer
available.

## Skipping the prompt permanently

There is no CLI flag. Three knobs, in order of preference:

1. Set `resumeReturnDismissed: true` in the global config file, which is `.claude.json` under
   `$CLAUDE_CONFIG_DIR` and defaults to `~/.claude.json`. This is what the `never` option writes.
   The gate returns before reading either threshold, so the session loads as-is on every resume.
2. Raise `CLAUDE_CODE_RESUME_TOKEN_THRESHOLD` far above typical session size.
3. Raise `CLAUDE_CODE_RESUME_THRESHOLD_MINUTES` similarly.

The feature gates are server-controlled and not user configurable, but any of the above renders them
moot.

## Telemetry

| Event                        | When                                      | Payload                                                          |
| ---------------------------- | ----------------------------------------- | ---------------------------------------------------------------- |
| `tengu_resume_return_action` | On overlay resolution, except `cancelled` | `action`, `sessionAgeMinutes`, `messageCount`, `estimatedTokens` |
| `tengu_session_resumed`      | On resume completion, overlay or not      | resume context                                                   |

`sessionAgeMinutes` is rounded before it is sent.

## Adjacent env vars

`CLAUDE_CODE_RESUME_SOURCE_ALIVE` and `CLAUDE_CODE_RESUME_TOLERATES_CONTEXT_APPENDS` share the
`CLAUDE_CODE_RESUME_` prefix but belong to SDK resume semantics, not to this overlay.

## Version history

- 2.1.87: the prompt does not exist.
- 2.1.104: prompt, `resumeReturnDismissed`, and both threshold env vars present. Single gate,
  `tengu_gleaming_fair`.
- 2.1.277: second gate `tengu_gleaming_fair_reuse` added, with the `skipped_no_summary` and
  `summary_gone` actions and the summary-reuse path. One-minute recency floor on the measured
  message.
