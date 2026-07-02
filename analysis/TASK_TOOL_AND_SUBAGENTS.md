# The Agent Tool and Subagents

Behavioral model verified against 2.1.165. This document follows the landmark style in
`GUIDELINES.md`: it anchors on version-stable strings (tool names, the tool's `.describe(...)` and
prompt strings, config keys, `tengu_*` names, behavioral logic) with grep re-location recipes, not
on minified symbol names or line numbers, which churn every release. Verbatim prompt text lives in
`PROMPTS_RENDERED.md`; this doc references stable phrases as anchors rather than reproducing them.
Per-release changes are in the appendix.

## The rename: Task → Agent

The subagent tool's canonical name is `Agent`. `Task` is a retained back-compat alias. Re-locate the
two name constants by grepping `searchHint: "delegate work to a subagent"` — the tool object sits
beside them with `name` bound to the `Agent` constant and `aliases` to the `Task` constant. Every
dispatch site accepts either name: the analytics `subagent_type` extractor guards on `!== "Agent" &&
!== "Task"`, and the tool-stats switch lets both fall through together. Existing `Task`-keyed
configs still resolve; the tool presents itself as `Agent`.

## The Agent tool

Re-locate the tool object via `name:` bound to the Agent constant, or by `searchHint: "delegate
work to a subagent"`. Stable properties:

- `isReadOnly()` returns true and `isConcurrencySafe()` returns true — multiple Agent calls in one
  message run concurrently.
- `maxResultSizeChars` is 100,000 (see truncation below).
- `checkPermissions` returns `{ behavior: "allow" }` — spawning is always permitted; the spawned
  agent's own tool calls are gated normally.
- `userFacingName` renders the `subagent_type` as the displayed tool name, except `general-purpose`
  and `worker`, which both render as `Agent`. Re-locate via the `worker` → `Agent` special case.

### Input schema

Re-locate via the description string "A short (3-5 word) description of the task". Parameters:

| Param               | Type / values                  | Notes                                                    |
|---------------------|--------------------------------|----------------------------------------------------------|
| `description`       | string                         | "A short (3-5 word) description of the task"             |
| `prompt`            | string                         | "The task for the agent to perform"                      |
| `subagent_type`     | string, optional               | which agent type; omitted → general-purpose (or fork)    |
| `model`             | `sonnet` / `opus` / `haiku`, opt. | overrides the agent definition's `model` frontmatter   |
| `run_in_background` | boolean, optional              | detach; notified on completion                           |
| `name`              | string, optional               | teammate name, addressable via `SendMessage({to: name})` |
| `team_name`         | string, optional               | teammate team                                            |
| `mode`              | optional                       | permission mode for a spawned teammate                   |
| `isolation`         | `worktree`, optional           | run in a temporary git worktree                          |
| `cwd`               | string, optional               | working dir; mutually exclusive with `isolation`         |

`model` accepts only `sonnet`/`opus`/`haiku` here; `inherit` is an agent-definition frontmatter
value, not a tool parameter. `run_in_background` is dropped when
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` is set or in coordinator mode. `name` / `team_name` / `mode`
apply only when Agent Teams is enabled.

### The description prompt

The tool's description is assembled dynamically; grep the opening "Launch a new agent to handle
complex, multi-step tasks. Each agent type has specific capabilities and tools available to it."
Stable phrases worth anchoring on (full text in `PROMPTS_RENDERED.md`):

- "When using the Agent tool, specify a subagent_type parameter to select which agent type to use.
  If omitted, the general-purpose agent is used." (non-fork mode)
- "…or omit it to fork yourself — a fork inherits your full conversation context." (fork mode)
- "The agent's final message is returned to you as the tool result; it is not shown to the user —
  relay what matters."
- "Trust but verify: an agent's summary describes what it intended to do, not necessarily what it
  did."
- "If the user specifies that they want you to run agents 'in parallel', you MUST send a single
  message with multiple Agent tool use content blocks."
- A Pro-plan guard paragraph discouraging spawning (grep "Do not spawn agents unless the user
  asks").

## Agent definitions: sources and precedence

Agent definitions come from several sources, merged last-writer-wins by `agentType`. Re-locate the
merge by grepping `source: "built-in"`. Precedence, lowest to highest:

```
built-in  <  plugin  <  userSettings  <  projectSettings  <  flagSettings  <  policySettings
```

So a project agent overrides a user agent of the same type; policy settings override everything.
Loading locations: user/project agents live in a `.claude/agents` directory; plugin agents in the
plugin's `agents/` subdir (manifest-declared paths are validated with the recurring error fragment
"specified in manifest but"). Workflow subagents live under a `subagents/` directory.

Markdown frontmatter an agent definition supports (grep the validation strings 'Missing required
"name" field in frontmatter' / '…"description"…'): `name`, `description` (both required),
`tools` (`["*"]` = all), `disallowedTools`, `model` (`inherit` or a model name), `effort`,
`permissionMode`, `color` (from an allowed set), `mcpServers`, `hooks`, `maxTurns`, `skills`,
`initialPrompt`, `memory` (`user`/`project`/`local`), `background`, `isolation` (`worktree`).
JSON-sourced (flag) definitions supply `prompt` in place of the markdown body.

`memory` gives the subagent its own persistent memory directory and auto-appends `Read`/`Edit`/`Write`;
mechanics are in `AGENT_MEMORY.md` (shared machinery in `MEMORY_SYSTEM.md`).

## Availability in headless (`-p`) mode

Confirmed empirically against 2.1.186 (2026-07-02); this section is newer than the rest of the
document (see the top-of-file `Verified` line). The Agent tool works in `claude -p` the same as
interactive mode, gated by the same `--allowedTools`/`--disallowedTools` mechanism as any other tool
— include `Agent` (or its `Task` alias) and a nested `-p` session can spawn subagents. Custom agent
definitions load the same way too: both project-scoped (`.claude/agents/`) and user-global
(`~/.claude/agents/`) definitions are visible to a headless session, exactly as in interactive mode,
since headless mode reads the same `CLAUDE_CONFIG_DIR` and project directory unless a caller
overrides them. There is no headless-specific restriction on which `subagent_type` values are
listed or invocable.

One default worth designing around rather than assuming: an agent definition's own `background: true`
(see the frontmatter table above) is not overridden by headless mode — `run_in_background` is only
stripped from the tool schema by `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` or coordinator mode, neither
of which is specific to `-p`. A `-p` invocation is a single blocking round-trip with no later turn to
check a background task's result, so a script driving `claude -p` that needs a spawned subagent's
work (e.g. a commit) to have actually landed before the process exits should have the calling prompt
explicitly request synchronous execution (`run_in_background: false`, or an instruction to that
effect) rather than rely on the invoked agent type's own background default.

## Built-in agents

Grep `source: "built-in"` for the set. `Explore` and `Plan` are special-cased in output handling
(see below) — grep the set `new Set(["Explore", "Plan"])` and its `.has(...)` check.

| Agent type          | Model     | Tools                         | Role                                          |
|---------------------|-----------|-------------------------------|-----------------------------------------------|
| `Explore`           | haiku     | read-only (no edit/agent/bash)| fast read-only search; omits CLAUDE.md         |
| `Plan`              | inherit   | read-only (same as Explore)   | read-only planning                            |
| `general-purpose`   | parent    | `["*"]`                       | default when `subagent_type` omitted          |
| `worker`            | parent    | `["*"]`, maxTurns 200         | renders as `Agent`; bubble permission mode    |
| `claude`            | parent    | `["*"]`                       | catch-all; background-job narration           |
| `statusline-setup`  | —         | `Read`, `Edit`                | configures the status line                    |
| `claude-code-guide` | —         | —                             | answers Claude Code / SDK / API questions     |
| `fork`              | inherit   | `["*"]`, maxTurns 200         | not selectable; chosen by omitting `subagent_type` when the fork experiment is active |
| `workflow-subagent` | —         | —                             | internal: workflow-script orchestration       |
| `teammate`          | —         | —                             | internal: in-process teammate wrapper         |

## Subagent output pipeline

When a subagent finishes, its last assistant message is packaged into a `tool_result` for the
parent. Re-locate via `mapToolResultToToolResultBlockParam`, or by the trailer string "use
SendMessage with to". For a completed sync agent the result is the agent's text content plus a
trailer:

```
agentId: {id} (use SendMessage with to: '{id}' to continue this agent)
<usage>subagent_tokens: {N}
tool_uses: {N}
duration_ms: {N}</usage>
```

Explore and Plan agents (with no worktree) skip the trailer entirely: their result is the raw text
content, with no `agentId:` line and no `<usage>` block. Background and teammate launches return
different trailers: `async_launched` (with an `agentId`, an `output_file`, and a warning not to Read
the file, "it is the full subagent JSONL transcript and reading it will overflow your context"),
`teammate_spawned`, and `remote_launched`.

### Truncation and persistence

Results pass a size gate (grep "Output too large" and `maxResultSizeChars`). The Agent tool's
`maxResultSizeChars` is 100,000, but the effective persistence trigger is `min(maxResultSizeChars,
ceiling)` where the global ceiling is 50,000, so 50,000 chars in practice. Beyond that, the full
output is written to a file under a `tool-results` directory and the in-context content is replaced
with a `<persisted-output>` block carrying a preview (first ~2000 chars). Persistence emits
`tengu_tool_result_persisted` (with `originalSizeBytes`, `persistedSizeBytes`,
`estimatedOriginalTokens`, `thresholdUsed`); an empty result emits `tengu_tool_empty_result`.

### Completion metadata and the token figure

The completion record carries `agentId`, `agentType`, `content`, `totalDurationMs`, `totalTokens`,
`totalToolUseCount`, the raw `usage` object, and `toolStats`. Re-locate via the "No assistant
messages found" guard. `totalTokens` is the four-term sum (`input_tokens +
cache_creation_input_tokens + cache_read_input_tokens + output_tokens`) of the last assistant
message only, picked by a `findLast` over the message list, not summed across turns. So
`subagent_tokens`, the `Done (…)` token count, and the `total_tokens` telemetry are a final-turn
snapshot that undercounts the run. For the exact cross-turn total and the full accounting story, see
`MONITORING_USAGE.md`.

### What the human sees

The collapsed terminal line is `Done ({N} tool uses · {M} tokens · {time})` (grep "1 tool use").
Content is gated behind transcript mode: ctrl+o expands to show the prompt and progress messages.
The parent model is told the result "is not visible to the user" and that it "should send a text
message back to the user with a concise summary of the result", so it relays rather than dumps the
raw result. A backgrounded agent renders as "Backgrounded agent" with a manage/expand hint.

## Context isolation, fork, and worktrees

A plain subagent is a fresh API request: it receives a single user message (the `prompt`) and the
agent's own system prompt, with no parent history. This is the default isolation.

Fork. When the fork experiment is active (config `tengu_fork_subagent_enabled`) and `subagent_type`
is omitted, the built-in `fork` agent runs instead of general-purpose. A fork inherits the parent's
full message history and rendered system prompt and shares the parent's cache. Its preamble (grep
"You are a worker fork") tells it the transcript above is inherited reference, to execute one
directive then stop, and not to spawn subagents. Forking inside a fork throws "Fork is not available
inside a forked worker."

Worktree isolation. `isolation: "worktree"` (grep "gives the agent its own git worktree") creates a
temporary git worktree so the agent works on an isolated copy. For a fork it injects a context
message explaining paths must be translated. On completion, if the agent made no changes the
worktree is auto-removed; otherwise the worktree path and branch are returned in the result. `cwd`
is mutually exclusive with worktree isolation.

## Background and teammates

The Agent tool's `call` resolves to one of three modes:

- Synchronous subagent: runs inline, parent awaits, returns the completed metadata above.
- Background (`run_in_background: true`, or agent-def `background: true`, unless background tasks
  are disabled): returns immediately with `async_launched`; the query runs detached and enqueues a
  task-notification on completion (grep `Agent "${_}" completed`) carrying a nested-tag
  `<usage><subagent_tokens>…` block. A foreground agent that runs long shows a "you can background
  this" hint; auto-backgrounding is gated by `CLAUDE_AUTO_BACKGROUND_TASKS` /
  `tengu_auto_background_agents`.
- Teammate (`name` set, requires Agent Teams via env `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` or
  `--agent-teams`): spawns a long-running peer, returns `teammate_spawned`. Teammates communicate
  via the `SendMessage` tool (grep `name:` bound to the SendMessage constant), addressing peers by
  `to:` name or id. "Teammates cannot spawn other teammates — the team roster is flat." The Agent
  Teams hook set adds `TeammateIdle`, `TaskCreated`, `TaskCompleted` to the standard events (see
  `HOOKS.md`).

`SendMessage` also continues or resumes any previously spawned agent by id: a new Agent call starts
fresh, while `SendMessage` to an existing id continues it with its context intact.

## Stop becomes SubagentStop

A subagent emits the `SubagentStop` hook rather than `Stop`, and a `Stop` hook declared in
subagent-applicable frontmatter is rewritten to `SubagentStop` at registration (grep "Converting
Stop hook to SubagentStop"). Full schema and semantics in `HOOKS.md`.

## Telemetry

Subagent completion emits `tengu_agent_tool_completed` and `subagent_completed`, both carrying
`total_tokens` (the snapshot figure above), `total_tool_uses`, `duration_ms`, `agent_type`, `model`,
and built-in/plugin attribution. Spawn emits `tengu_agent_tool_selected` (with `is_fork`,
`is_resume`, `source`, `agent_system_prompt_chars`); cancellation emits
`tengu_agent_tool_terminated`. Subagent-type resolution emits `tengu_subagent_type_miss` /
`tengu_subagent_type_normalized`. Full usage/attribution story: `MONITORING_USAGE.md`.

## Regular tool vs. Agent subagent vs. teammate

| Aspect        | Regular tool              | Agent subagent                   | Teammate                          |
|---------------|---------------------------|----------------------------------|-----------------------------------|
| Execution     | Synchronous function call | Separate API request             | Separate API session, polling     |
| System prompt | Main session prompt       | Own agent prompt (or forked)     | Base prompt + teammate addendum   |
| Context       | Shares main session       | Isolated (unless fork)           | Isolated, message-passing         |
| Tools         | All available             | Filtered per definition          | All or filtered per definition    |
| Lifecycle     | Call → return             | Call → single final message      | Long-running, polls for work      |
| Communication | Direct return value       | Single final message + trailer   | `SendMessage`                     |
| Cost          | No extra API call         | Full API call(s) with tokens     | Multiple API calls over lifetime  |

## Per-release appendix

- 2.1.165: verified. Tool renamed to `Agent` with `Task` retained as an alias. Input schema gained
  `model` (`sonnet`/`opus`/`haiku`), `run_in_background`, `name`, `team_name`, `mode`, `isolation`
  (`worktree`), `cwd`. Built-in agents include `Explore`, `Plan`, `general-purpose`, `worker`,
  `claude`, `statusline-setup`, `claude-code-guide`, `fork`, plus internal `workflow-subagent` /
  `teammate`. `Explore`/`Plan` results omit the `agentId:`/`<usage>` trailer when no worktree is
  used. `maxResultSizeChars` 100,000, effective persistence trigger 50,000. Agent-definition
  precedence: built-in < plugin < user < project < flag < policy.
