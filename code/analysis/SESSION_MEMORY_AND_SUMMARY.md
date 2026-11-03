---
verified: 2.1.76
section: Sessions, context, and history
style: landmark
scope: Background summary compaction (removed by 2.1.138)
landmarks:
  - tengu_session_memory
  - session-memory/summary.md
---
# Session Memory: Background Note-Taking Pipeline in Claude Code

Status: REMOVED. This feature no longer ships. The strings `summary.md`, `session-memory`,
`tengu_session_memory`, and `tengu_sm_compact` are all absent from current bundles. Bisecting the
local corpus: present in 2.1.119 (`session-memory`=7, `tengu_session_memory`=4) and gone from
2.1.138 onward, so it was removed between 2.1.119 and 2.1.138. The content below is retained as a
historical record of the experiment and is not verifiable against the current source. Re-confirm
removal with
`rg -c session-memory work/<latest>/package/cli.prettier.js` (expect 0).

This is unrelated to the durable memory family (auto / agent / team) documented in
`MEMORY_SYSTEM.md`. Session memory was a per-session compaction optimization, not cross-session
memory — it shared only the word "memory."

With it gone, compaction reverted to the standard on-demand path it always layered on top of: when
context fills (or `/compact` runs), a single LLM call summarizes the earlier conversation into one
summary message (preamble: "This session is being continued from a previous conversation that ran
out of context."), with recent messages kept verbatim. The summary is generated on demand instead of
pre-built; no capability was lost. See `CLEAR_COMPACT_FORK_CONTEXT.md` for the current mechanics.

Last verified present against: cli.prettier.js 2.1.76. Removal window confirmed against 2.1.119 →
2.1.138 (checked 2026-06-26). Line numbers and minified names below are from 2.1.76 and will not
match any current bundle.


## Overview

Session memory is an undocumented, feature-flagged alternative compaction strategy. Instead of
summarizing the conversation in one expensive LLM call when context fills up (the standard
compaction path), session memory builds the summary incrementally throughout the session via
smaller background LLM calls. When compaction is triggered -- either automatically or via
`/compact` -- the pre-built summary is used in place of the standard LLM compaction call.

The pipeline runs as a post-sampling hook on the main REPL thread, periodically forking an LLM
call that reads the conversation and edits a structured markdown file (`summary.md`) using the
Edit tool. Both the background summarization and its use as a compaction fast path are gated by
feature flags (`tengu_session_memory` and `tengu_sm_compact`, both default off), making this an
A/B testable alternative to standard compaction.

This is distinct from auto-memory (`MEMORY.md`), which persists across sessions and is
documented. Session memory is per-session and not publicly documented.


## Two Memory Systems

| Aspect                | Auto-Memory (MEMORY.md)                                 | Session Memory (summary.md)                                        |
| --------------------- | ------------------------------------------------------- | ------------------------------------------------------------------ |
| Location              | `~/.claude/projects/<slug>/memory/MEMORY.md`            | `~/.claude/projects/<slug>/<session-id>/session-memory/summary.md` |
| Scope                 | Cross-session, persists indefinitely                    | Per-session, tied to one session ID                                |
| Documented            | Yes, in official docs at code.claude.com                | No                                                                 |
| Disable env var       | `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`                     | (no dedicated env var; gated by feature flag)                      |
| Feature flag          | None (always available if enabled)                      | `tengu_session_memory` (default: off)                              |
| Loaded into context   | First 200 lines at session start                        | On demand (e.g., by Skillify's `{{sessionMemory}}` template var)   |
| Written by            | The main model during conversation                      | A forked background LLM call                                       |


## Pipeline Architecture

### Registration

A startup registration function installed the pipeline. It returned early for a non-interactive
session, returned early when auto-compact was disabled, and otherwise registered the pipeline
callback as a post-sampling hook.

Registration pushed the callback onto a module-level array. After every model response in the main
conversation loop, a dispatcher iterated that array and called each registered hook.


### Trigger Conditions

The pipeline callback runs after each model response but only proceeds when
all conditions are met:

1. `querySource === "repl_main_thread"` -- only the main conversation, not subagents
2. the feature-flag check returns true -- the `tengu_session_memory` feature flag is enabled
3. `Lyz(messages)` returns true -- the conversation meets the update thresholds

The threshold check checks two threshold conditions via the message-count threshold and the token
threshold:

| Threshold                      | Default   | Config key (server-side)         | Meaning                                     |
| ------------------------------ | --------- | -------------------------------- | ------------------------------------------- |
| `minimumMessageTokensToInit`   | 10,000    | `tengu_sm_config` object field   | First update: min tokens in conversation    |
| `minimumTokensBetweenUpdate`   | 5,000     | `tengu_sm_config` object field   | Subsequent: min new tokens since last       |
| `toolCallsBetweenUpdates`      | 3         | `tengu_sm_config` object field   | Subsequent: min tool calls since last       |

Thresholds are overridable via server-side config `tengu_sm_config` (fetched by the config fetcher
at line. Local defaults in the local defaults are used as fallbacks.

The update also triggers when enough tokens have accumulated and the conversation has no remaining
tool use (end of a model turn without pending tool calls).


### Execution Flow

When triggered, the pipeline callback calls the update preparer to prepare the update:

1. Create the session-memory directory:
   `~/.claude/projects/<slug>/<session-id>/session-memory/`

2. Seed `summary.md` with the template if it doesn't exist (using `flag: "wx"` for atomic
   create-if-absent):
   - Load custom template from `~/.claude/session-memory/config/template.md`
   - Fall back to built-in template the built-in template if no custom template exists

3. Read the current `summary.md` content via the Read tool (`r9.call`)

4. Build the update prompt via the prompt builder:
   - Load custom prompt from `~/.claude/session-memory/config/prompt.md`
   - Fall back to built-in prompt the built-in prompt if no custom prompt exists
   - Expand `{{notesPath}}` and `{{currentNotes}}` template variables
   - Append token-budget warnings if the file is approaching the limit

5. Send as a forked LLM call via the forked LLM call:
   - `querySource: "session_memory"`
   - `forkLabel: "session_memory"`
   - The model receives the full conversation as context
   - Only the Edit tool is available, constrained to the `summary.md` path


## The Summary Template

The built-in template the built-in template seeds each new `summary.md` with these sections:

```markdown
# Session Title
_A short and distinctive 5-10 word descriptive title for the session. Super info dense, no filler_

# Current State
_What is actively being worked on right now? Pending tasks not yet completed. Immediate next steps._

# Task specification
_What did the user ask to build? Any design decisions or other explanatory context_

# Files and Functions
_What are the important files? In short, what do they contain and why are they relevant?_

# Workflow
_What bash commands are usually run and in what order? How to interpret their output if not obvious?_

# Errors & Corrections
_Errors encountered and how they were fixed. What did the user correct? What approaches failed and should not be tried again?_

# Codebase and System Documentation
_What are the important system components? How do they work/fit together?_

# Learnings
_What has worked well? What has not? What to avoid? Do not duplicate items from other sections_

# Key results
_If the user asked a specific output such as an answer to a question, a table, or other document, repeat the exact result here_

# Worklog
_Step by step, what was attempted, done? Very terse summary for each step_
```


## The Update Prompt

The built-in prompt the built-in prompt instructs the model to:

- Update the session notes file based on the conversation above
- Use the Edit tool to modify `summary.md` in place
- Preserve the exact structure: section headers and italic description lines must not change
- Only update the content below each section's italic description
- Write detailed, info-dense content with file paths, function names, exact commands
- Keep each section under ~`XG1` tokens (a constant set during initialization)
- Always update "Current State" to reflect the most recent work
- Focus on actionable information that would help recreate the work
- Not add filler content; skip sections with nothing substantial to add


## Configuration

Two files in `~/.claude/session-memory/config/` allow customization:

| File            | Purpose                                                      | Fallback                       |
| --------------- | ------------------------------------------------------------ | ------------------------------ |
| `template.md`   | Seed content for new `summary.md` files (section structure)  | Built-in the built-in template |
| `prompt.md`     | Instructions sent to the LLM for updating the summary        | Built-in the built-in prompt   |

Both are loaded by the custom-template loader and the custom-prompt loader respectively. If the
custom file does not exist (ENOENT), the built-in default is used. If the file exists but fails to
read for other reasons, the error is logged and the default is used.

The template supports any markdown structure. The prompt should use `{{notesPath}}` and
`{{currentNotes}}` template variables, which are expanded by the template expander before being sent
to the model.

Note: these config files are not documented. The `~/.claude/session-memory/config/` directory is
not mentioned in the official Claude Code documentation.


## Token Billing

Session memory LLM calls use the same API key and model as the main conversation. Token usage is
tagged with `querySource: "session_memory"` in telemetry. Whether the server-side
accounting charges these against the user's quota is unknown from client code alone -- the server
could exempt, discount, or separately bucket traffic tagged `session_memory`.

The client-side treatment suggests special handling:

1. Blocking limit bypass: the blocking limit check explicitly skips
   `session_memory` and `compact` query sources. The client does not enforce its local quota
   ceiling on these calls, which would be unnecessary if they counted normally against quota.
2. Auto-compaction exclusion: session memory calls don't trigger auto-compaction of
   the main conversation.

The official docs mention background token usage of ~$0.04 per session for "conversation
summarization", but do not specifically identify session memory as a contributor.


## How the Summary Is Used: Compaction Fast Path

The summary is never loaded proactively into the conversation during normal use. Its primary
consumer is the standard compaction system -- both auto-compact and manual `/compact`.

The summary fast path is a fast path within the existing compaction code. It is not a separate
compaction mechanism; it is a try-first optimization that avoids the expensive LLM-based
compaction call (the LLM compaction call) when a pre-built summary is available:

Auto-compaction called the fast path first, passing the session, the agent id and the auto-compact
threshold. A non-null result short-circuited the whole compaction: it cleared the pending-compaction
state and returned `wasCompacted` with the summary as the compaction result. A null result fell
through to the LLM compaction call.

Manual `/compact` attempted the fast path only when the user supplied no instructions, since
instructions have to be honored by an actual model call. Same shape otherwise: non-null returned a
`compact` result immediately, null fell through.

Both paths returned the same `compactionResult` shape. When the summary fast path succeeds, the
standard LLM compaction call is skipped entirely. When the summary fast path returns
null (no summary, feature disabled, or summary would exceed the token threshold), the normal
compaction runs as usual.

The fast path reads `summary.md` through the summary reader, truncates it if too long with a
per-section budget, then wraps it in the standard compaction preamble:

> "This session is being continued from a previous conversation that ran out of context.
> The summary below covers the earlier portion of the conversation."

The result is injected as a compaction summary message with `isCompactSummary` set and
`isVisibleInTranscriptOnly: !0`. Recent messages after the compaction boundary
are preserved verbatim alongside the summary.

The fast path is gated by the fast-path gate, which requires both feature flags:
- `tengu_session_memory` -- the base session memory feature
- `tengu_sm_compact` -- the compaction integration specifically

Both default to off. The env vars `ENABLE_CLAUDE_CODE_SM_COMPACT` and
`DISABLE_CLAUDE_CODE_SM_COMPACT` can override the flags.

The design amortizes summarization cost: instead of paying for one large LLM compaction call
when context fills up, the summary is built incrementally by smaller background calls throughout
The session. When compaction is needed, the pre-built summary is ready to use immediately.


## Other Consumers

The summary reader is the only reader for `summary.md`. Besides the compaction system,
it is referenced by the disabled Skillify prompt template (`_Rz`) via the
`{{sessionMemory}}` code-level template variable. No other consumers exist in the codebase.


## File Path Construction

The full path to the summary file:

```
~/.claude/projects/<slugified-project-dir>/<session-id>/session-memory/summary.md
```

Path construction:
- the config-dir accessor = `~/.claude` (config dir, or `CLAUDE_CONFIG_DIR`)
- the projects-dir accessor = `~/.claude/projects`
- `qf(path)` = slugifies a filesystem path (replace non-alphanumeric with `-`, truncate + hash)
- `yH(projectDir)` = `~/.claude/projects/<slugified-project-dir>`
- the session-dir accessor = `~/.claude/projects/<slug>/<session-id>/session-memory/`
- the summary-path accessor = `~/.claude/projects/<slug>/<session-id>/session-memory/summary.md`
