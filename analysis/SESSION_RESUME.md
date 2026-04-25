# Session Resume: The "Resume as-is vs Summary" Prompt

Source: `cli.prettier.js` 2.1.104 (`work/2.1.104/package/cli.prettier.js`)

When a user invokes `claude -r` / `claude --resume` and the selected
conversation is both old enough and large enough, Claude Code shows a
post-resume overlay asking whether to compact the session or keep it
as-is.

The prompt is a UI overlay, not a load-time gate. Messages from the
resumed transcript are already set into React state before the overlay
renders; choosing "Resume full session as-is" just dismisses. Choosing
"Resume from summary" runs `/compact` after the fact. This means the
full context has already been counted toward usage by the time the
choice is presented.

## The Prompt Component

Component `leK` at line 594419, three options:

| value      | label                              | effect                                             |
|------------|------------------------------------|----------------------------------------------------|
| `compact`  | Resume from summary (recommended)  | Runs `/compact` after resume                       |
| `continue` | Resume full session as-is          | Dismisses; session stays as loaded                 |
| `never`    | Don't ask me again                 | Dismisses and persists `resumeReturnDismissed`     |

Rendered at line 638082-638118 (overlay dispatch `qY === "resume-return"`).

## When the Prompt Is Shown

From the resume `useEffect` at line 635931-635963, all of the following
must hold:

1. Statsig gate `tengu_gleaming_fair` returns true (server-side).
2. The last non-recent user/assistant message is older than
   `CLAUDE_CODE_RESUME_THRESHOLD_MINUTES` (default: 70).
3. Estimated tokens in the loaded transcript are at least
   `CLAUDE_CODE_RESUME_TOKEN_THRESHOLD` (default: 100000).
4. Global config flag `resumeReturnDismissed` is not set.

Relevant excerpt:

```js
[source fragment removed]
```

`J8()` reads the global config file (line 181476); `v0()` resolves the
path at line 53185: `$CLAUDE_CONFIG_DIR/.claude.json`, defaulting to
`~/.claude.json`, with `.config.json` in the CWD taking precedence if
present.

## Skipping the Prompt Permanently

There is no CLI flag. Three knobs exist, in order of preference:

1. Set `resumeReturnDismissed: true` in `~/.claude.json`. Written by `B8`
   (line 181362) via a locked config write. Equivalent to clicking
   "Don't ask me again" once in the UI. The entire gating block is
   skipped; session loads as-is on every resume.

2. `CLAUDE_CODE_RESUME_TOKEN_THRESHOLD` - raise far above typical
   session size (e.g. `999999999`).

3. `CLAUDE_CODE_RESUME_THRESHOLD_MINUTES` - raise similarly.

The `tengu_gleaming_fair` gate is server-controlled and not user
configurable, but setting any of the above also renders the gate moot
for the user.

## Telemetry

- `tengu_resume_return_action` - emitted on selection, payload
  `{ action, sessionAgeMinutes, messageCount, estimatedTokens }` (line
  638091).
- `tengu_session_resumed` - emitted on resume completion irrespective of
  the prompt (line 635902).

## Version History

The prompt did not exist in 2.1.87. It was introduced between 2.1.87
and 2.1.104. The related app-state flag `resumeReturnDismissed` and the
environment variables above are also new in this range.
