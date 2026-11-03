---
verified: 2.1.317
verified_on: 2026-11-03
section: Observability
style: landmark
scope: >-
  Where token, cost and plan-limit usage can be observed (statusLine, `/usage`, subagent `<usage>`,
  OTel, cached blob, usage endpoint); cap-hit records, grace, auto-continue, `cedar_ember` resets
landmarks:
  - What's contributing to your usage?
  - claude_code.session.count
  - cachedUsageUtilization
  - api/oauth/usage
  - 'hook_event_name: "StopFailure"'
  - cedar_ember
---
# Monitoring Token Usage and Cost

This document follows the landmark style in `GUIDELINES.md`: it anchors on version-stable strings
(slash-command names, `tengu_*` event and flag names, env var names, OTEL metric and attribute
names, literal UI strings, JSONL field names, behavioral logic) with grep re-location recipes, not
on minified symbol names or line numbers, which churn every release. Strings the product renders
with a non-ASCII character (`·`, `—`) are stored escaped in the bundle (`\xB7`, `\u2014`), so the
recipes below grep an ASCII substring.

This doc answers: how much usage is a given subagent or tool consuming, and where can that be read?
The short version is that there are seven observation surfaces, each with a different granularity
and a different honesty caveat. Per-subagent attribution is possible; exact per-tool-call token cost
is not, because a tool call does not itself consume tokens — the assistant turns around it do.

A separate question this doc also answers: how much of a *plan's* rate limit has been consumed — the
5-hour session window and the 7-day weekly window that `/usage` renders. That number does not exist
anywhere in OpenTelemetry. Live utilization is exposed to the statusLine command (Surface 1) and to
the Agent SDK / `stream-json` message stream (see "Plan rate limits are not in telemetry"); caps
already hit are recoverable from the transcript (Surface 5). See "Org-level visibility is not a
product surface" for why there is no server-side alternative on most plans.

## What this doc owns vs. cross-references

This doc owns the observation/attribution story: the OpenTelemetry surface, the `/usage` command
family, the per-subagent `<usage>` trailers and their snapshot semantics, and the SubagentStop
attribution recipe. It cross-references the field-level references that already live elsewhere:

| Topic                                            | Lives in                        |
| ------------------------------------------------ | ------------------------------- |
| `message.usage` field reference (per-message)    | `SESSION_TRANSCRIPT.md`         |
| statusLine `context_window` input object         | `PROMPTS_RENDERED.md`           |
| `compactMetadata.preTokens`, microcompact tokens | `CLEAR_COMPACT_FORK_CONTEXT.md` |
| Subagent output pipeline, the `Done (…)` summary | `SUBAGENTS.md`                  |
| Hook input schemas, including SubagentStop       | `HOOKS.md`                      |

## The ground-truth token figure

Every assistant message record in the transcript JSONL carries a `message.usage` object with
`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, and the
`cache_creation.ephemeral_1h_input_tokens` / `ephemeral_5m_input_tokens` breakdown. Field reference:
`SESSION_TRANSCRIPT.md`.

The canonical "tokens for one usage object" sum used throughout the product is the four-term total:

```
input_tokens + cache_creation_input_tokens + cache_read_input_tokens + output_tokens
```

Re-locate it with
`rg -n 'input_tokens \+ \w+\.cache_creation_input_tokens \+ \w+\.cache_read_input_tokens'` (one
line): expect a three-term input helper and, directly above it, a caller that normalises the usage
object and adds `output_tokens`. This single-object sum feeds the subagent token figure and the
telemetry events below.

A subagent or session runs many turns, each a separate billed API request. The true total tokens it
consumed is the sum of that four-term value over every assistant record, not the value on any one
record. This distinction is the central gotcha of this doc, because the figure surfaced in most of
the UI is a single record's value, not the sum.

## Surface 1: live in-session usage

The statusLine command input carries a `context_window` object: `total_input_tokens`,
`total_output_tokens`, `context_window_size`, `current_usage` (the raw last `message.usage`, or
null), `used_percentage`, `remaining_percentage`. `total_input_tokens` is the last call's
`input_tokens + cache_creation_input_tokens + cache_read_input_tokens`. This is session-level, last
API call, exposed to statusLine authors. Full field doc: `PROMPTS_RENDERED.md`. Re-locate the
builder by grepping `total_input_tokens` near `remaining_percentage`.

The same input also carries a `cost` object (`total_cost_usd`, `total_duration_ms`,
`total_api_duration_ms`, `total_lines_added`, `total_lines_removed`), a `prompt_cache` object
(warmth, TTL, `hit_ratio`, miss counts and causes), and a `rate_limits` object — the only plan-limit
utilization handed to a user-configured command:

```jsonc
"rate_limits": {            // Optional. Subscribers, or behind a gateway that sets a spend limit,
                            // after the first API response, while at least one window is present.
  "five_hour":   { "used_percentage": number,   // 0-100, one decimal place, capped at 100
                   "resets_at": number },       // Unix epoch seconds
  "seven_day":   { "used_percentage": number,
                   "resets_at": number },
  "spend_limit": { "used_percentage": number,   // gateway only; can exceed 100
                   "resets_at": number,
                   "used_usd": number,          // optional, with limit_usd and period
                   "limit_usd": number,
                   "period": "daily" | "weekly" | "monthly" }
}
```

Re-locate the documented shape by grepping the statusLine setup prompt for
`Claude.ai subscription usage limits`; re-locate the builder by grepping for the spread guarded on
`five_hour ||` alongside `seven_day` and `spend_limit`. Every sub-object is individually optional,
and a window drops out once its `resets_at` has passed. Underlying source: the
`anthropic-ratelimit-unified-5h-*` / `-7d-*` response headers (grep `anthropic-ratelimit-unified-`),
parsed per API response, so the value is as fresh as the last request. `spend_limit` comes from the
`-overage-*` headers and is present only when the provider is a Claude gateway.

Two properties matter when choosing between this and the `/usage` probe below, and they pull in
opposite directions.

Precision: the builder converts the header fraction to a percentage rounded to one decimal place
(`rg -n 'Math.round\(\w+ \* 1000\) / 10'` finds the helper; a sibling caps it at 100), whereas the
rendered figures floor to whole percent — the `/usage` text output prints `Math.floor(utilization)`
and the threshold warning floors too. So statusLine carries a tenth of a point where the rendered
figures do not, which matters to anything differencing two samples, since integer percent quantises
a small delta into uselessness. Whether the headers themselves carry more than whole-percent
precision is not source-determinable; observed values from the usage endpoint are whole numbers
(`16`, `21`, `23`), so verify against real header values before relying on sub-point resolution.

Coverage: the statusLine payload carries only `five_hour`, `seven_day` and the gateway
`spend_limit`. The model-scoped weekly buckets that `/usage` displays (`Current week (Sonnet only)`,
and the per-model rows built from the server `limits[]` array) are absent from it. On a plan where a
model-scoped weekly is the binding constraint rather than the all-models weekly, statusLine cannot
see the window that actually matters. Sample with statusLine for resolution; read `/usage` for
completeness.

Plugin code running through the in-process `$` API has a sibling read point: `$.session.usage()`
answers the context window, a `rateLimits` list (`five_hour`, `seven_day`, gateway `spend_limit`,
each with `percentUsed` and an ISO `resetsAt`), and the session cost in USD (grep
`$.session.usage (` for its debug line).

### The statusLine failure contract

Anything built on this surface has to satisfy a contract that is only partly documented, and whose
failure mode is silent by design.

Exit 0 is mandatory. Grep `StatusLine [` for the executor's debug lines: stdout is used only on a
zero exit, is trimmed line by line with empties dropped, and a non-empty result becomes the line.
Every other outcome returns undefined, and the caller invokes its result handler unconditionally —
so the rendered text is cleared rather than left stale. The published docs say the same thing in one
sentence: scripts that exit non-zero or produce no output cause the status line to go blank.

The rest is observable only in the source. stderr is captured and written to the debug log, never to
the UI. A non-zero exit records one `status_line_command` failure classified `spawn_failed`,
`timeout`, or `nonzero_exit` (a thrown error is `exec_error`) — behind a once-per-process latch, so
a command failing on every render reports exactly once. There is no retry, no backoff, and no
disabling after repeated failures. The constant separating `timeout` from `nonzero_exit` is 600000
ms, though the practical bound is much tighter because a still-running invocation is aborted when
the next one starts. An aborted run returns silently and is not counted as a failure.

Consequences for a recorder built on this surface: never exit non-zero, since doing so blanks the
user's status line rather than merely losing a sample; treat everything after reading stdin as
best-effort; and in a pipeline remember the last command's exit status is the one Claude Code sees.

Adjacent settings on the same object: `padding`, `refreshInterval` (seconds, minimum 1),
`hideVimModeIndicator` for a command that renders `vim.mode` itself, and a separate
`subagentStatusLine` whose contract differs — it receives the visible subagent rows as one JSON
object and emits one JSON line per row, each `{"id", "content"}` (grep
`subagentStatusLine emitted invalid schema`). Execution also requires workspace trust, the same gate
hooks pass through.

Because the statusLine command is an arbitrary shell command receiving this JSON on stdin, it is
the practical hook for exporting plan-limit utilization to an external system: read stdin, emit the
numbers somewhere, print the status line. The input also carries `prompt_id`, documented as "same
as OTel prompt.id" — the join key between a statusLine sample and the OTel event stream.

Invocation cadence matters when treating it as a sampler. The command is not run per render. It is
run on a 300 ms debounce, triggered when the last assistant message id changes or when one of a
fixed dependency set changes — token usage, permission mode, vim mode, main-loop model, fast mode,
effort, thinking, PR status, remote session name. `rate_limits` is not itself in that set, but the
message id and token usage change on every API response, which is also when the rate-limit headers
refresh, so samples track responses closely. Two timers add runs without activity: one fires a
second after the earliest `resets_at` in `rate_limits` or the warm prompt cache's expiry, so a
window rolling over is reflected without a new request; and `statusLine.refreshInterval` (described
as "Re-run the status line command every N seconds in addition to event-driven updates") adds steady
polling. A previous still-running invocation is aborted when a new one starts, so a slow exporter
drops samples rather than queueing them.

### `/usage` in print mode is a free, out-of-session quota probe

The most useful property of the non-interactive form is that it costs nothing and needs no running
session:

```
claude -p "/usage" --output-format json
```

The command is a `local` slash command whose plan figures come from a server fetch, not from the
model, so no model request is made and nothing is billed: the JSON envelope's `total_cost_usd`,
`num_turns` and `usage` stay at zero, with the human-readable report in `result`. This is the only
way to read plan utilization without a live session, which makes it the right source for scheduled
polling; the statusLine (above) only samples while Claude Code is actually running, and therefore
goes quiet exactly when someone has stopped working and their quota is going unused.

Three caveats. The rate-limit figures arrive as prose inside `result`
(`Current session: 12% used · resets Aug 9 at 10pm (America/Vancouver)`), not as structured fields,
so a consumer must parse them — and the reset string omits the year. With
`--output-format stream-json` the same result also carries a structured `usage_report` (see "Plan
rate limits are not in telemetry"). The zero-cost property is a current fact, not a guarantee; a
probe running on a schedule should assert on `total_cost_usd` / `num_turns` and warn rather than
assume it stays free.

The third caveat is the one that will actually bite a scheduled job. When the OAuth credential
lookup fails, `/usage` does not error — it silently falls through to its API-key output form, the
`Total cost:` / `Usage by model:` block with no plan-limit lines at all. Empirically, a probe on
macOS run from a stripped environment (`HOME` and a correct `PATH`, no `USER`) has been seen to exit
0 and report no plan limits until `USER` was added. The source reads `USER` first for the Keychain
account name and falls back to the OS user name, so that dependency is not explained by the
account-name lookup alone; re-test before relying on either outcome. Since launchd and cron both
supply a stripped environment, a naive scheduled probe can report "no limits" forever and look like
an account without a subscription. Any consumer should treat zero parsed windows as a configuration
failure to investigate rather than as an absence of limits.

The `/usage` slash command (aliases `/cost` and `/stats`, grep `aliases: ["cost", "stats"]`) reports
session and plan usage. It has two forms:

- Interactive: opens the settings dialog on the `Usage` tab (or `Stats` when invoked as `/stats`).
  The Usage tab shows server-fetched plan usage with labels like `Current session`,
  `Current week (all models)`, `Current week (Sonnet only)`, per-model `Current week (<name>)` rows,
  credit rows (`Claude Code and Cowork credit` from the `cinder_cove` bucket, and a server-labelled
  row from `wattle_ember`), `Usage credits`, `Unlimited`. The Stats tab shows local history:
  `Total tokens`, `Tokens per Day`, `Favorite model`, `Active days`, `Sessions`, with time toggles
  `All time` / `Last 30 days` / `Last 7 days`.
- Non-interactive (`--print`): the output depends on the login. A claude.ai subscriber gets a
  sentence saying whether the subscription or overage is powering usage, one line per plan window
  (`Current session: N% used · resets …`, `Current week (all models): …`, the Sonnet and per-model
  rows), and the limits-attribution block below; a
  `breakdown · opus: N% · sonnet: N% · cache hit: N%` line follows only under the `tengu_amber_lark`
  flag (grep `cache hit:`). Any other login gets the cost block (grep `Usage by model:`), plus a
  `Spend limit:` line behind a Claude gateway:

  ```
  Total cost:            {cost}
  Total duration (API):  {dur}
  Total duration (wall): {dur}
  Total code changes:    {N} lines added, {M} lines removed
  Usage by model:
    {model}:  {N} input, {N} output, {N} cache read, {N} cache write[, {N} web search] ({$cost})
  Prompt cache (main):   {N} requests · {N}% of input tokens from cache · …
  ```

Granularity: the `Usage by model:` block breaks session cost down by model only. Attribution comes
from the limits-attribution block headed `What's contributing to your usage?` (grep that string),
computed for the last 24 hours and the last 7 days from a scan of local transcripts. Each period
leads with its request and session counts and carries two kinds of row.

Behavior rows are recommendations, each a percentage share and an imperative title — for example
`Compact before you step away` for prompt-cache misses, `Start fresh when you switch tasks` for long
context, `Run fewer sessions at once` for parallel sessions (grep `Compact before you step away` and
read the switch around it). The behavior keys are `cache_miss`, `long_context`, `subagent_heavy`,
`high_parallel`, `cron`, `max_effort`, `workflow`, `always_on_context`, `large_tool_results`. They
overlap, and the product says so: the print form's caveat ends `shares overlap`.

Named-entity rows do attribute usage, at the granularity the OpenTelemetry surface offers: grep
`Top skills`, `Top subagents`, `Top plugins`, `Top MCP servers`. Each lists entities with a percent,
capped at eight with a `+N more` tail.

The reason to still prefer Surface 4 is the caveat the block prints about itself:
`Approximate · sessions on this machine only` (grep `sessions on this machine only`). This is
computed from local session history, not from server accounting, so it cannot see a teammate's
machine or the same account used elsewhere.

### Where the plan-limit bars come from

The bars are server figures, not local accounting. Nothing in Claude Code counts tokens toward a
plan limit; it fetches percentages and reset times and renders them. The fetch is
`GET /api/oauth/usage` (grep `api/oauth/usage`, and `fetchUtilization: GET` for the debug line),
OAuth-authenticated with a 5-second timeout and a 401-refresh retry. The response object is kept
verbatim and cached to `cachedUsageUtilization` (Surface 6); a read made within a minute of the last
cached fetch is answered from that snapshot without asking the endpoint (grep
`Usage read answered from a snapshot`).

Three of the bars read named top-level fields of that response: `five_hour` is `Current session`,
`seven_day` is `Current week (all models)`, and `seven_day_sonnet` is `Current week (Sonnet only)`,
the last rendered only when `subscription_type` is `max`, `team`, or null.

Every other per-model row — `Current week (Opus)`, `Current week (Fable)`, and any name Anthropic
introduces next — comes from the response's `limits[]` array instead, and is entirely
server-driven. Relocate the builder by grepping `weekly_scoped`; it filters `limits[]` down to
entries whose `kind` is `weekly_scoped` and which carry a string `scope.model.display_name`, then
builds each row as:

| Rendered part | Source                                             |
| ------------- | -------------------------------------------------- |
| Title         | `` `Current week (${scope.model.display_name})` `` |
| Percentage    | the entry's `percent`, already on a 0-100 scale    |
| Reset line    | the entry's `resets_at`                            |

So the label is a string the server chose. There is no local table mapping a model to a bucket, no
`seven_day_fable` field to go with `seven_day_sonnet`, and no dependence on which model the session
is configured to use: a row appears because the account has that scoped weekly window, and it is
named whatever the server called it. This is why the row can read `Fable` while the local model
catalogue calls the same model `Fable 5` (grep `display_name: "Fable 5"`).

One local gate decides whether a scoped row is shown at all: the GrowthBook flag
`tengu_usage_overage_included_models`, a list of model display names, matched case-insensitively
against `scope.model.display_name`. With no flag value the client falls back to a built-in list
(`Fable`, `Fable 5`, `Fable 5.1`; grep `Object.freeze(["Fable"`); an explicit empty list renders no
per-model rows however many the server returned. Because a stale list would silently drop rows,
opening the dialog first waits up to 1.5 seconds for GrowthBook to settle when the value is still
coming from the fallback or disk source; grep `overage-included models allowlist` for both the
settled and timed-out debug lines, the latter noting that per-model rows fall back to the cached
list.

There are two degraded paths. When the endpoint answers with an error or an unusable body, the
client seeds utilization from the `anthropic-ratelimit-unified-*` response headers it has already
seen (`source: "headers"`), or, when there are none, from the cached `cachedUsageUtilization`
(`source: "persisted"`). On the header path a scoped entry is synthesised from the
`seven_day_overage_included` header bucket (`-7d_oi-` in the header names). The headers carry no
model name, so the label is recovered indirectly: from the cached `limits[]` if exactly one scoped
entry survives the gate filter, otherwise from the first name in the gate list. A row rendered this
way can therefore be labelled with the right percentage and the wrong model.

The `+50% weekly limits promo` line under a bar is unrelated to any of this: it is remote copy from
the `tengu_rate_limit_promo_notices` flag, whose entries carry `bar`, `text` and `variant` and are
matched to a bar by name. For a scoped row the `bar` matched against is the model display name.

## Surface 2: per-subagent attribution (the Agent tool result)

When a subagent finishes, the parent model's tool result carries a trailer with the subagent's
totals. Four `<usage>` string shapes exist; grep accordingly.

Synchronous completion, the flat form the parent model receives (grep `subagent_tokens:`):

```
agentId: {id} (use SendMessage with to: '{id}', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: {N}
tool_uses: {N}
duration_ms: {N}</usage>
```

The parenthetical is omitted when the agent cannot be continued.

Background / teammate worker notification, a nested-tag form inside `<task-notification>` (grep
`<usage><subagent_tokens>`):

```
<usage><subagent_tokens>{N}</subagent_tokens><tool_uses>{N}</tool_uses>
<duration_ms>{N}</duration_ms></usage>
```

The bundle emits it as one line; it is wrapped here for width.

Workflow-run notification, the same nested form with `<agent_count>` and per-state agent counts
(`<agents_done>`, `<agents_error>`, `<agents_skipped>`, `<agents_empty_result>`) in front (grep
`<usage><agent_count>`).

Collapsed human-facing one-liner in the terminal (grep `1 tool use`):

```
Done ({N} tool uses · {M} tokens · {time})
```

Snapshot, not sum. The synchronous trailer, the `Done (…)` token count, and the telemetry
`total_tokens` all come from one value: the four-term token sum of the subagent's last metered
assistant message only, picked by a `findLast` over the message list (grep `isUnmetered !== !0`
beside `tengu_agent_tool_completed`), not a sum across turns. Because each turn re-sends the growing
context (mostly as cache reads), the final turn's input side is roughly cumulative, but every prior
turn's output is omitted. Treat these figures as a footprint proxy that undercounts true
consumption, not as a billed total.

The background notification's figure is slightly better: it is the larger of that snapshot and the
live progress tracker's count, which is the latest input footprint plus output summed over every
turn plus a streamed-token estimate (grep `latestInputTokens \+ \w+\.cumulativeOutputTokens`). It
includes every turn's output but still counts only the last turn's input. The same tracker figure
feeds the SDK `task_progress` messages' `usage.total_tokens` and the `subagentStatusLine` rows'
`tokenCount`.

For Explore and Plan subagents (grep `new Set(["Explore", "Plan"])` and its `.has(...)` check at the
tool-result builder) the synchronous trailer is omitted entirely when no worktree is in play: their
result is the raw text content only, with no `agentId:` line and no `<usage>` block.

## Surface 3: exact per-subagent total via the SubagentStop hook

No hook input carries a subagent's token consumption. A few carry a context-size estimate instead:
SessionStart on resume or fork (`context_tokens`, `estimated_cache_write_usd`), and PreModelSwitch
and PostModelSwitch (`context_tokens`, `prompt_cache_warm`, `estimated_cache_write_usd`) — the
prompt the next request re-sends and what re-caching it would cost, not usage (grep
`estimated_cache_write_usd`). The SubagentStop hook input carries `agent_transcript_path`, a path to
the subagent's own JSONL file, alongside `agent_id`, `agent_type`, and an optional
`last_assistant_message` (describe string: "Text content of the last assistant message before
stopping. Avoids the need to read and parse the transcript file."). See `HOOKS.md` for the full
SubagentStop schema.

That path resolves to `<projectDir>/<sessionId>/subagents/[<key>/]agent-<agentId>.jsonl` (grep
`"subagents"` and follow it to the builder that appends `` `agent-${…}.jsonl` ``). It is a real
per-subagent transcript with one `message.usage` per turn. Summing the four-term value over every
assistant record there gives the true cross-turn total, the figure the `<usage>` trailer cannot
give. A minimal hook:

```bash
# .claude/settings.json -> hooks.SubagentStop -> a command hook.
# Hook input arrives as JSON on stdin; read agent_transcript_path from it, then sum usage.
read -r INPUT
TP=$(jq -r .agent_transcript_path <<<"$INPUT")
TYPE=$(jq -r .agent_type <<<"$INPUT")
TOTAL=$(jq -rs '
  [ .[] | select(.type=="assistant") | .message.usage
    | (.input_tokens // 0) + (.output_tokens // 0)
      + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0) ]
  | add // 0' "$TP")
printf '%s consumed %s tokens (summed across turns)\n' "$TYPE" "$TOTAL" \
  >> ~/.claude/subagent-usage.log
```

This sums the per-call billed totals across the subagent's whole run, since each turn is a separate
API request. To attribute by your custom agent, branch on `agent_type`.

## Per-tool-call tokens are not available

A tool call has no token cost of its own. The cost is the input tokens of the assistant turn that
emitted the `tool_use` block, plus the input tokens of the next turn that carries the `tool_result`.
No field attributes tokens to a single tool call. What is available: the tool-lifecycle hooks
(PreToolUse, PostToolUse, PostToolUseFailure) carry `agent_id` and `agent_type` (grep their describe
strings in the base hook schema), so a tool call can be attributed to the subagent that issued it,
and the subagent total above is where those tokens land. The OTEL `claude_code.tool`,
`claude_code.tool.execution` and `claude_code.tool.blocked_on_user` spans record tool execution and
time spent waiting on the user, but not the call's token consumption.

## Surface 4: fleet and longitudinal monitoring via OpenTelemetry

OTEL is the only surface with built-in per-subagent and per-tool attribution. Enable it with the
`CLAUDE_CODE_ENABLE_TELEMETRY` env var (grep that name; the disable hint string is "Disable
OpenTelemetry by unsetting CLAUDE_CODE_ENABLE_TELEMETRY env var"). The bundle ships the
OpenTelemetry SDK and exports over OTLP; see `DEPENDENCIES.md`.

Metric instruments — all eight are registered in one function; grep `claude_code.session.count` and
read the adjacent registrations. Every name carries the `claude_code.` prefix:

| Instrument                            | Unit   | Registered description                          |
| ------------------------------------- | ------ | ----------------------------------------------- |
| `claude_code.token.usage`             | tokens | "Number of tokens used"                         |
| `claude_code.cost.usage`              | USD    | "Cost of the Claude Code session"               |
| `claude_code.session.count`           | —      | "Count of CLI sessions started"                 |
| `claude_code.lines_of_code.count`     | —      | lines modified, `type` = added/removed, `model` |
| `claude_code.commit.count`            | —      | "Number of git commits created"                 |
| `claude_code.pull_request.count`      | —      | "Number of pull requests created"               |
| `claude_code.code_edit_tool.decision` | —      | accept/reject for Edit, Write, NotebookEdit     |
| `claude_code.active_time.total`       | s      | "Total active time in seconds"                  |

The registration helper takes an `omitUnits` flag that suppresses the `unit` field, so the `USD`,
`tokens`, and `s` units are not guaranteed to reach every exporter.

`claude_code.token.usage` is emitted four times per request, once per `type` attribute: `input`,
`output`, `cacheRead`, `cacheCreation` (grep `type: "cacheRead"`). Note these differ from the JSONL
field names. `claude_code.cost.usage` is added alongside with the same attributes minus `type`. The
shared attribute set is built right above those four `add` calls: `model`, `speed: "fast"` (present
only in fast mode), `query_source`, `effort` (when an effort level is set), and the per-source
attribution attributes below. Advisor-model calls are recorded through the same path under the
advisor's model. There is no thinking-token `type`: thinking tokens are counted inside `output`, and
no attribute carries a thinking budget. `effort` is the only reasoning-level attribute.

There is no gauge or counter for plan-limit utilization, quota, or seat consumption. The eight
above are the complete set.

Per-source attribution attributes are attached to each data point (grep `"mcp_server.name",`):
`agent.name`, `skill.name`, `plugin.name`, `marketplace.name`, `mcp_server.name`, `mcp_tool.name`.
They are derived from a `query_source` string whose prefixes (`agent:builtin:`, `agent:custom:`,
`skill:`, …) name the originating component. This is what lets you split token and cost metrics by
subagent and by MCP tool, on every session rather than only from one machine's local scan. Custom
and third-party names are redacted to the placeholders `custom` / `third-party` unless
`OTEL_LOG_TOOL_DETAILS` is set (the placeholder map sits beside the attribute-name list).

Trace spans add request-level attribution. The `claude_code.llm_request` span (grep that name)
carries `model`, `gen_ai.system`, `gen_ai.request.model`, `llm_request.context`
(`tool`/`interaction`/`standalone`), `speed`, `query_source`, `agent_id` and `parent_agent_id`, and
on completion `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens` and
`stop_reason`. A `claude_code.subagent.spawn` span carries `agent_id`, `agent_type`,
`parent_agent_id`. Other spans: `claude_code.interaction`, `claude_code.tool`,
`claude_code.tool.execution`, `claude_code.tool.blocked_on_user`, `claude_code.hook`,
`claude_code.bash.subprocess`, `claude_code.mcp.rpc`, `claude_code.compaction`.

### Log events

Events are emitted through one helper that stamps `event.name`, `event.timestamp`, an incrementing
`event.sequence`, `prompt.id` when a prompt is in flight, `workspace.host_paths` when
`CLAUDE_CODE_WORKSPACE_HOST_PATHS` is set, and `agent_id` / `parent_agent_id` for events raised
inside a subagent, then emits a log record whose body is the literal `` `claude_code.${name}` ``.
Because the body is interpolated, the full event name never appears in the bundle — searching for
`claude_code.user_prompt` returns nothing. Grep instead for the body template
`` body: `claude_code. `` to find the record builder; the emitting helper is the async function a
few lines above it that sets `"event.sequence"`. Enumerate its call sites with an `rg -U` multiline
match, since several are formatted across lines, and discard matches of the same minified name used
as an unrelated constructor elsewhere in the bundle (focus and blur events).

The complete set, 30 names (prefix each with `claude_code.`). 28 are called with a string-literal
first argument; `api_request_body` / `api_response_body` arrive through a wrapper that passes the
name as a variable (grep `e === "api_request_body"`).

- Prompt and API: `user_prompt`, `assistant_response`, `system_prompt`, `api_request`, `api_error`,
  `api_refusal`, `api_retries_exhausted`, `api_request_body`, `api_response_body`
- Tools: `tool`, `tool_result`, `tool_decision`, `safety_event` (a tool-safety classifier or
  sandbox-violation event, the OTLP twin of `tengu_safety_event`)
- Extensions: `skill_activated`, `subagent_completed`, `plugin_installed`, `plugin_loaded`,
  `mcp_server_connection`, `hook_registered`, `hook_execution_start`, `hook_execution_complete`,
  `hook_plugin_metrics`
- Session: `auth`, `permission_mode_changed`, `compaction`, `at_mention`, `feedback_survey`,
  `internal_error`
- Administration: `managed_settings_resolved` (which managed sources are active, policy-helper
  state, and with `OTEL_LOG_MANAGED_SETTINGS` the resolved settings and their SHA-256; grep
  `"managed_settings.sources"`), `retention_sweep` (transcript cleanup results; grep
  `transcripts_deleted`)

`api_request` attributes (grep `cache_creation_5m_tokens`): `model`, `input_tokens`,
`output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cache_creation_5m_tokens`,
`cache_creation_1h_tokens`, `cost_usd`, `cost_usd_micros`, `duration_ms`, optional `ttft_ms`,
`request_id`, `client_request_id`, `speed` (`fast`/`normal`), `query_source`, optional `effort`, and
the per-source attribution attributes. This is the per-request billing record and the
highest-fidelity usage event. As with the metric, there is no thinking-token field. Every event can
also carry `workflow.run_id` / `workflow.name` when emitted inside a workflow run.

`api_error` attributes: `model`, `error`, `status_code`, `duration_ms`, `attempt`, `request_id`,
`client_request_id`, `speed`, optional `query_source` / `effort`, and the attribution attributes.
When more than one attempt was made, `api_retries_exhausted` follows with `total_attempts` and
`total_retry_duration_ms`. `error` is the message text, so a 429 can be classified only by matching
that text (see Surface 5).

### Identity attributes

Attached to every metric data point and every event by the same attribute builder (grep
`"user.account_uuid"` and read the enclosing function):

| Attribute                   | Gate                                                  | Default |
| --------------------------- | ----------------------------------------------------- | ------- |
| `user.id`                   | always (the device ID)                                | on      |
| `organization.id`           | always, when an OAuth profile is present              | on      |
| `user.email`                | always, when an OAuth profile is present              | on      |
| `terminal.type`             | always, when the terminal is detected                 | on      |
| `anthropic.provider`        | always                                                | on      |
| `anthropic.custom_base_url` | always; true for a gateway or custom endpoint         | on      |
| `anthropic.plan`            | claude.ai login: `pro`, `max`, `team`, `enterprise`   | on      |
| `anthropic.seat_type`       | claude.ai login with a known seat tier                | on      |
| `session.id`                | `OTEL_METRICS_INCLUDE_SESSION_ID`                     | on      |
| `ccr.session.id`            | with `session.id`, if `CLAUDE_CODE_REMOTE_SESSION_ID` | on      |
| `user.account_uuid`         | `OTEL_METRICS_INCLUDE_ACCOUNT_UUID`                   | on      |
| `user.account_id`           | with `user.account_uuid` (tagged-ID env overrides)    | on      |
| custom attrs                | `OTEL_METRICS_INCLUDE_RESOURCE_ATTRIBUTES`            | on      |
| `app.version`               | `OTEL_METRICS_INCLUDE_VERSION`                        | off     |
| `app.entrypoint`            | `OTEL_METRICS_INCLUDE_ENTRYPOINT`                     | off     |
| `vcs.*`                     | `OTEL_METRICS_INCLUDE_REPOSITORY`                     | off     |

The defaults come from a literal map of the six flags (grep `OTEL_METRICS_INCLUDE_REPOSITORY: !1`).
An unset flag takes its default; a set flag is parsed as a boolean. The `anthropic.*` attributes are
built by a small helper the builder calls last (grep `"anthropic.plan"`); the seat-type map turns
seat tiers such as `team_standard` or `enterprise_tier_1` into the coarse values (`premium`,
`standard`, `usage_based`, `other`). Custom attributes come from `OTEL_RESOURCE_ATTRIBUTES`;
`CLAUDE_CODE_ACCOUNT_TAGGED_ID` overrides the derived `user.account_id`; and `vcs.*` is the
repository URL, owner, name and provider, from `OTEL_RESOURCE_ATTRIBUTES` when set there or else
from the git remote.

`organization.id` and `user.email` are ungated by any `OTEL_METRICS_INCLUDE_*` flag — a local OAuth
session always labels its telemetry with the operator's email address. That is what makes per-person
fleet attribution work without extra configuration, and it is also the privacy fact to disclose
before turning telemetry on for a team. Operator-supplied `OTEL_RESOURCE_ATTRIBUTES` keys beginning
`user.` or `identity.` are dropped when the profile already supplies identity attributes, so a
custom `user.*` label cannot shadow the real one.

On a session signed in through a gateway with an OIDC token, the builder merges the token's claims
last: `user.id` becomes the JWT `sub`, `user.email` the token email, `user.groups` the
comma-joined groups, and `identity.source` is `gateway-oidc` (grep `"gateway-oidc"`).

The customer-facing export does carry the plan (`anthropic.plan`) and a coarse seat type, but
nothing about how much of the plan is used. `user.subscription_type` and `user.customer_type` exist
only on the first-party exporter below.

### Configuration env vars

Standard OTLP env vars are honored (`OTEL_EXPORTER_OTLP_ENDPOINT` / `_HEADERS` / `_PROTOCOL` and
their per-signal `_METRICS_` / `_LOGS_` / `_TRACES_` variants, `OTEL_METRICS_EXPORTER`,
`OTEL_LOGS_EXPORTER`, `OTEL_TRACES_EXPORTER`, `OTEL_METRIC_EXPORT_INTERVAL`,
`OTEL_LOGS_EXPORT_INTERVAL`, `OTEL_TRACES_EXPORT_INTERVAL`, mTLS via
`OTEL_EXPORTER_OTLP_CLIENT_KEY` / `_CLIENT_CERTIFICATE` / `_CERTIFICATE`, and a Prometheus exporter
via `OTEL_EXPORTER_PROMETHEUS_HOST` / `_PORT`).

Claude Code adds its own (grep each name):

| Env var                                       | Effect                                          |
| --------------------------------------------- | ----------------------------------------------- |
| `CLAUDE_CODE_ENABLE_TELEMETRY`                | master switch                                   |
| `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`         | detailed tracing (see below)                    |
| `CLAUDE_CODE_PROPAGATE_TRACEPARENT`           | force W3C traceparent propagation               |
| `CLAUDE_CODE_OTEL_SHUTDOWN_TIMEOUT_MS`        | shutdown flush timeout                          |
| `CLAUDE_CODE_OTEL_FLUSH_TIMEOUT_MS`           | flush timeout                                   |
| `CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH`         | truncation limit for logged content             |
| `CLAUDE_CODE_OTEL_DIAG_STDERR`                | SDK diagnostics to stderr                       |
| `CLAUDE_CODE_OTEL_HEADERS_HELPER_DEBOUNCE_MS` | refresh interval for the `otelHeadersHelper`    |
| `CLAUDE_CODE_ENABLE_FEEDBACK_SURVEY_FOR_OTEL` | enables the `feedback_survey` event             |
| `CLAUDE_CODE_ACCOUNT_TAGGED_ID`               | overrides the derived `user.account_id`         |
| `CLAUDE_CODE_WORKSPACE_HOST_PATHS`            | paths stamped on events, `workspace.host_paths` |

`CLAUDE_CODE_ENHANCED_TELEMETRY_BETA` also answers to `ENABLE_ENHANCED_TELEMETRY_BETA`;
`CLAUDE_CODE_WORKSPACE_HOST_PATHS` is `|`-separated.

Content capture is opt-in per class: `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_ASSISTANT_RESPONSES`,
`OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT`, `OTEL_LOG_RAW_API_BODIES`. With them unset the
corresponding fields carry the literal `<REDACTED>` (grep `"<REDACTED>"` near the
`assistant_response` emission).

`otelHeadersHelper` is a settings key, not an env var, and appears in the list of settings whose
values are command strings (grep `"otelHeadersHelper",` adjacent to `"statusLine",` and
`"subagentStatusLine",`) — the same list that managed policy can pin.

### Central configuration through managed settings

An admin can turn telemetry on and point it at a collector for every user, through the `env` block
of managed settings (the on-disk `managed-settings.json` and its drop-ins, MDM, or server-managed
settings fetched from `/api/claude_code/settings`). Four mechanisms make that stick:

- The settings env applier writes every scope's `env` into `process.env`, policy last, so a managed
  `CLAUDE_CODE_ENABLE_TELEMETRY` or `OTEL_*` value overrides the same key in the user's shell or
  user settings.
- When managed `env` sets an `OTEL_EXPORTER_OTLP_*` endpoint, headers, or client certificate, or
  managed settings set `otelHeadersHelper`, the applier deletes any per-signal endpoint override a
  lower-trust scope set, so a user cannot redirect one signal elsewhere. Landmark: the warning
  template containing `is claimed by` and `so lower-trust scopes cannot redirect`, in the function
  that names `enforceManagedOtelFamilyDominance`.
- When the session is eligible for server-managed settings, telemetry initialization waits for that
  fetch to settle. Landmark: `[3P telemetry] Waiting for remote managed settings fetch before
  telemetry init`.
- Server-managed settings are fetched for first-party sessions authenticated by a claude.ai Team or
  Enterprise OAuth login, a Console API key, a workload-identity profile, or an accepted gateway.
  Pro and Max logins are ineligible (`unsupported_subscription`), as are third-party providers and
  custom base URLs (grep `"unsupported_subscription"` and `"third_party_provider"` in the
  eligibility function).

Server-delivered settings that could run code or redirect traffic need the user's approval once per
organization and settings hash (recorded in `remote-settings-consent.json`). Most telemetry
variables are on the consent-free env allowlist (grep `"CLAUDE_CODE_ENABLE_TELEMETRY",` in the large
`new Set([` of safe keys): the enable switch, exporters, protocols, headers, compression, intervals,
the `OTEL_METRICS_INCLUDE_*` flags, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_SERVICE_NAME`, and the
`OTEL_LOG_*` content flags. The `OTEL_EXPORTER_OTLP_*ENDPOINT` variables are not on it, so a
server-managed endpoint shows a dedicated dialog: "Your organization has configured Claude Code to
send telemetry to the destination below." with the list label `Telemetry destination:`. Rejecting
the dialog refuses the session and emits `managed_settings_resolved` with trigger `refused` and
`error.type: "consent_rejected"`.

### First-party metrics export to Anthropic

Separately from the customer OTLP export, the same eight metric instruments feed a second reader
that posts to `/api/claude_code/metrics` on the OAuth base API URL (log prefix `BigQuery metrics`).
It does not need `CLAUDE_CODE_ENABLE_TELEMETRY`. It runs for a claude.ai OAuth login on a Team or
Enterprise subscription, or a first-party non-OAuth (API key) login, unless `DISABLE_TELEMETRY`,
`DO_NOT_TRACK`, or `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` is set. Before each export it checks
`/api/claude_code/organizations/metrics_enabled` and skips with
`BigQuery metrics export disabled by organization setting` when the org has turned it off. Its
resource attributes add `user.customer_type` (`claude_ai`/`api`) and `user.subscription_type`. Where
this data surfaces on Anthropic's side is not source-determinable. The admin does not choose its
endpoint, and it carries no plan-limit data either.

### Plan rate limits are not in telemetry

No metric, no event, and no span attribute carries 5-hour or weekly limit utilization, quota state,
or seat consumption: the eight metric registrations contain no limit instrument; the 30 event names
contain no limit event; and the `api_request` event's attribute list carries tokens, cost, and
duration but nothing derived from the `anthropic-ratelimit-unified-*` response headers that populate
`/usage`. The trace-span module has no rate-limit attribute either.

Outside OTel, the Agent SDK / `--output-format stream-json` message stream carries a
`rate_limit_event` message (grep `type: "rate_limit_event"`) whose `rate_limit_info` has `status`,
`resetsAt`, `rateLimitType`, `utilization`, overage fields, and — marked `@internal` in its schema —
`unifiedWindows`: per-window `utilization`, `resetsAt`, `status` and `surpassedThreshold` for
`five_hour`, `seven_day` and `seven_day_overage_included`, read from the response headers (grep
`Per-window usage for the session`). `utilization` there is the header fraction (usually 0-1, above
1 when usage runs past a cap). A frame is emitted whenever the limit state changes, which includes
any whole-percent change in a window's utilization, so an SDK host gets a live utilization feed.
That is a per-process stream, not an export.

The available substitutes, in descending fidelity:

1. The statusLine `rate_limits` object (Surface 1), or the SDK `rate_limit_event` frames for a
   process you host. Real utilization percentages and reset timestamps, sampled per API response,
   per machine. Requires shipping a statusLine command or owning the SDK process.
2. Cap-hit records in the transcript JSONL (Surface 5). Retroactive and exact about *when* a cap was
   hit and which window it was, with no configuration at all — but nothing about the approach.
3. `claude_code.api_error` with `status_code` = 429. The same event, live over OTLP, but see the
   discrimination warning in Surface 5: this status code alone does not mean a plan cap.
4. `claude_code.token.usage` and `claude_code.cost.usage` summed per `user.email` over a rolling
   5-hour or 7-day window. A proxy for load, not for utilization: the server's limit accounting is
   not a token count and is not published, so this cannot be calibrated against the real percentage.

The `/usage` command itself computes a richer structured payload than it prints — session cost
totals, `subscription_type`, `rate_limits_available`, a `rate_limits` object with `five_hour`,
`seven_day`, `seven_day_oauth_apps`, `seven_day_opus`, `seven_day_sonnet`, `model_scoped[]` and
`extra_usage`, plus a `behaviors` object for `day` and `week` with request and session counts,
behavior shares, recommendations, and per-agent, skill, plugin and MCP-server attribution. Grep
`rate_limits_available` for the schema, whose describe string marks it "Experimental — the shape may
change". It is not exported over OTLP, but an SDK host can read it two ways: the `get_usage` control
request returns the whole payload (grep `"get_usage"`; `skip_behaviors` skips the local transcript
scan), and a `/usage` result in the stream carries a smaller `usage_report` twin — session totals,
the raw `limits[]` rows and `extra_usage` — on its synthetic assistant message (grep
`Structured twin of the /usage report`).

Honesty boundary: the metric names, the event names and their attributes, the identity attribute
gates, the statusLine `rate_limits` shape, the SDK frame shapes, and the absence of any
limit-bearing OTLP telemetry are all verifiable in the source. Default OTLP endpoints and export
intervals beyond the env-var fallbacks, the server-side definition of limit utilization, and the
server-side billing treatment of background traffic are not source-determinable.

## Surface 6: the cached utilization blob in the config

The richest and most convenient plan-usage source is not a command output at all: it is a cache
written to the top-level config JSON (`~/.claude.json`, or `$CLAUDE_CONFIG_DIR`). Grep the config
for `cachedUsageUtilization`. It holds the claude.ai usage endpoint's response verbatim, alongside
`fetchedAtMs` and — the field that makes the rest usable — `accountUuid`.

The client's schema for the blob names `five_hour`, `seven_day`, `seven_day_oauth_apps`,
`seven_day_opus`, `seven_day_sonnet` (each with `utilization` and `resets_at`), `cinder_cove`,
`wattle_ember` (a labelled credit bucket with dollar amounts and periods), `extra_usage`
(`is_enabled`, `monthly_limit`, `used_credits`, `utilization`, `currency`, `disabled_reason`) and
`limits[]`, and passes every other key through untouched. Real responses also carry a `spend`
object, `daily` / `weekly` sub-objects under `extra_usage`, null `limit_dollars` / `used_dollars` /
`remaining_dollars` on the window objects, and a long tail of mostly-null named buckets such as
`seven_day_cowork`, `seven_day_omelette`, `omelette_promotional`, `tangelo`, `iguana_necktie`,
`nimbus_quill` and `amber_ladder`. The codenames are server-side buckets in the same naming family
as the GrowthBook flags; treat the set as unstable and read it dynamically.

The most useful member is `limits[]`, a normalised array that supersedes reading the individual
buckets. Each entry has `kind` (`session`, `weekly_all`, `weekly_scoped`), `group`, `percent`,
`severity`, `resets_at`, `is_active`, and for a scoped entry a `scope` naming a `model.display_name`
or a `surface.display_name`. That is the model-scoped weekly the statusLine object cannot express,
in structured form.

Three practical advantages over the `/usage` text: reset times are ISO 8601 rather than a
year-less local string; every bucket is present rather than only those the dialog renders; and
`accountUuid` identifies whose figures these are.

Watch the units. This blob comes from the usage endpoint and its `utilization` / `percent` values
are already on a 0-100 scale, whereas the `anthropic-ratelimit-unified-*` response headers that
feed the statusLine object are 0-1 fractions scaled by 100 at the boundary. Two sources, two
scales, same nominal field name.

Refresh semantics: a successful endpoint read rewrites the blob only when the cached copy for the
same account is at least a minute old, and a read within that minute is answered from the cache
without asking the endpoint, so "probe, then read the config" yields figures at most about a minute
old. The client ignores a blob older than an hour when it falls back to it. Check `fetchedAtMs`
rather than assuming — a failed refresh leaves the previous values in place with no error.

### Account switching invalidates a naive series

`cachedUsageUtilization` is a single slot, not a per-account map. Authenticating as a different
account overwrites it, a read under a different account deletes it, and logging out clears it along
with the other account-scoped config fields; `accountUuid` is the only marker of which plan the
numbers describe. Two consequences for anything that samples over time.

A sampled series must be partitioned by account before it means anything. Different accounts have
different allowances, so a utilization delta spanning a switch is not a consumption measurement, and
a ratio derived from such a pair is meaningless. Worse for reset detection: a switch produces
exactly the signature described below — utilization falling — so an unattributed series reports
every account switch as a mid-window grant.

The statusLine payload does not identify the account at all, so a statusLine-based sampler has to
read `oauthAccount.accountUuid` from the config itself to label its own samples. That object also
carries `emailAddress`, `organizationName`, `organizationUuid`, `seatTier`,
`organizationRateLimitTier`, `userRateLimitTier`, `billingType` and `hasExtraUsageEnabled` —
`seatTier` being the field that distinguishes one plan from another in a multi-account setup.

The hard limit: only the currently-authenticated account is observable. There is no cached copy of
any other account's utilization, so quota on an account you are signed out of cannot be read at
all — which is precisely the account most likely to be accruing unused quota.

### Per-account probing via isolated config directories

The way around that limit is one config directory per account, because `CLAUDE_CONFIG_DIR` isolates
credentials as well as state — which is not obvious, since the default install leaves a single
Keychain entry named `Claude Code-credentials` with no directory component in sight.

Grep the service-name builder: a function returning `` `Claude Code${…OAUTH_FILE_SUFFIX}${…}${…}` ``
(grep `OAUTH_FILE_SUFFIX}\$\{`), adjacent to the `-credentials` constant and the Keychain account
helper. The trailing segment is empty when `CLAUDE_CONFIG_DIR` is unset and otherwise `-` plus the
first 8 hex characters of the SHA-256 of the NFC-normalised config directory path. So
`CLAUDE_CONFIG_DIR=/some/dir` reads and writes `Claude Code-credentials-<sha8>`, a different item
from the default, and authenticating in one directory cannot overwrite another's credentials. The
paired account name for the Keychain item is `$USER` (falling back to the OS username, then the
literal `claude-code-user` if it fails a character check).

`CLAUDE_SECURESTORAGE_CONFIG_DIR` overrides just the credential scope, independently of
`CLAUDE_CONFIG_DIR`; setting it to the empty string forces the unsuffixed service name, which
deliberately shares the default directory's credentials with an otherwise-isolated config
directory.

Behaviours observed in use, worth knowing before building on this. A fresh config directory does not
inherit the default login: the probe still exits 0 but degrades to the no-subscription output, so
each directory needs its own interactive login once. `CLAUDE_CONFIG_DIR` relocates the whole tree —
the config JSON, `projects/`, `sessions/`, `backups/` — so an isolated directory keeps its own
transcripts and does not pollute the main corpus that Surface 5 reads. It is not transcript-free,
though: each probe writes a small session JSONL under the isolated `projects/`, so a directory used
purely for polling still accumulates files and wants occasional pruning.

Because the probe costs nothing, polling several accounts this way does not perturb the quantity
being measured, and utilization is account-wide server state rather than per-process — so a probe
from a polling-only directory returns exactly what a working session on that account would see.
What such a directory cannot supply is anything session-scoped: no cost delta for absolute
calibration, and no statusLine samples, since nothing is configured to run there.

## Window geometry and pacing

Everything needed to reason about *pace* — not just current utilization — is derivable client-side,
because the window lengths are compiled-in constants while only the utilization fraction comes from
the server. Grep `windowSeconds: 18000` for the table:

| Window      | `windowSeconds` | Warn thresholds (`utilization`, `timePct`) |
| ----------- | --------------- | ------------------------------------------ |
| `five_hour` | 18000           | (0.90, 0.72)                               |
| `seven_day` | 604800          | (0.75, 0.60), (0.50, 0.35), (0.25, 0.15)   |

`timePct` is the fraction of the window elapsed, computed from the reset timestamp alone (the small
helper right below the table subtracts `windowSeconds` from the reset time and clamps to 0..1):

```
elapsed = clamp((now - (resets_at - windowSeconds)) / windowSeconds, 0, 1)
```

The client raises its early warning when
`utilization >= threshold.utilization && elapsed <= threshold.timePct` — that is, "you are this far
ahead of pace this early". Reading the weekly row: 25% consumed in the first 15% of the week is
already flagged. The table is the fallback: when a response carries an
`anthropic-ratelimit-unified-*-surpassed-threshold` header for a window, that server verdict is used
first. Two consequences worth recording. First, any consumer of the statusLine `rate_limits` object
can compute the same `elapsed` and therefore a pace ratio `utilization / elapsed`, where 1.0 is
exactly on pace — the client publishes no such ratio itself, but the inputs are all present. Second,
inverting the comparison (`utilization <= X && elapsed >= Y`) detects the opposite condition, quota
going *unused*, which nothing in the product surfaces.

What is not derivable is any absolute quantity. No token count, request count, or currency amount
for a plan allowance appears anywhere in the bundle; the wire protocol carries only
`anthropic-ratelimit-unified-{5h,7d}-utilization` fractions and `-reset` timestamps. So the size of
a plan's quota is unknowable client-side by construction, and it can be changed server-side without
a client release. Anything reasoning in absolute terms — "how many tokens are left", "how much of
the week can one 5-hour window consume" — has to estimate it from observation rather than read it.
The ratio between the two windows is the practically important one, and it is measurable: within a
single 5-hour window both utilizations advance on the same consumption, so `Δ(7d) / Δ(5h)` across
two samples is the fraction of the weekly allowance one full 5-hour window represents.

### Grace windows

The server can hand back a temporary allowance after a cap is reached. Grep
`anthropic-ratelimit-unified-grace-5h-utilization` for the reader: on any response the limiter ran
on (one carrying `anthropic-ratelimit-unified-status`), it reads that header and
`-grace-7d-utilization`, each clamped to a 0..1 fraction. When either is above zero the client
enters a grace zone tied to that window's reset time, sets an internal `rateLimitGraceActive` flag,
and owes the model a wrap-up note (grep `grace window active`; see the next section). The zone ends
when a later response reports no grace usage or the window's reset passes.

The client asks for the grace pool rather than merely observing it. Grep `"anthropic-usage-limit"`
for the request header, set to `extended` on eligible requests: the gate is `tengu_lantern_spool`
(default off), and the surrounding condition restricts it to first-party auth, non-auxiliary query
sources (compaction excepted), and in the main mostly to continuation requests inside a turn. A turn
already in progress is what gets to overrun the cap; a fresh turn started after the wall does not.
The same header carries `slow` while the session runs in lower-priority mode.

Two things follow. Grace is a distinct pool with its own utilization, not a rollback of the main
window's counter — so a session can continue past an apparent 100%. And it is barely exposed:
`rateLimitGraceActive` reaches no statusLine field, no `/usage` line, and no OTLP telemetry; the
only outside view is the `@internal` `rateLimitGraceActive` field on SDK `rate_limit_event` frames.

### The model is told about the cap, in the conversation

The system prompt carries no plan-limit section, and nothing numeric reaches the model: no
utilization percentage, no reset timestamp, no `anthropic-ratelimit-unified-*` header value, and
none of the statusLine `rate_limits` object. What the model receives is a small set of fixed
bracketed notes, injected into the message array as `isMeta` user records (tagged internally with a
`usageLimitNote` of `wrap_up`, `near_limit` or `release`), plus one queued resume prompt. Re-locate
the injector by grepping `usage_limit_near_wrapup`; it runs for the main loop and for `agent:*`
subagents, never for teammates, workflow subagents, or while a resume is active.

| Note          | Gate (default)                      | Text (grep)               |
| ------------- | ----------------------------------- | ------------------------- |
| near-limit    | `tengu_vellum_anchor` (off)         | `Usage limit approaching` |
| grace wrap-up | `tengu_lantern_wick_mode` (`off`)   | `grace window active`     |
| release       | `tengu_lantern_wick_release` (none) | server-supplied only      |
| resume        | `autoContinueAtUsageLimit` (on)     | `usage limit has reset`   |

Near-limit. The threshold is 0.95, raised to 0.99 for `default_claude_max_5x` and 0.9975 for
`default_claude_max_20x` (grep `case "default_claude_max_5x"` next to the `0.9975`). It arms once
per 5-hour window, keyed on that window's `resets_at`, and does not arm when the
`anthropic-ratelimit-unified-overage-status` header is `allowed` or `allowed_warning` (extra usage
would absorb the overrun) or while lower-priority mode is active. It is delivered only on a
continuation request inside a turn (query-chain depth above zero), alongside a UI notice,
`Approaching your 5-hour usage limit — Claude will wrap up the current step.`, and a
`performRateLimitCheckpoint` of the todo list. The 7-day window has no near-limit note at all.

Grace wrap-up. `tengu_lantern_wick_mode` is three-valued (`off`, `wrap-up`, `next-steps`). Both live
texts open with `[Usage limit reached — grace window active.` and forbid subagents and long-running
work; `next-steps` additionally asks for up to three bullets of the most impactful remaining work,
the same wording the near-limit note uses. A server-supplied string replaces the built-in text:
`tengu_lantern_wick_text_by_model` (an object keyed by model, canonical model name, or `default`),
falling back to `tengu_lantern_wick_text`. Server text is sanitised before injection while
`bot_protected_tengu_hazy_waterfall` is on (default on); rejected or altered text is counted as
`usage_limit_served_text_rejected` / `_altered`. The note is owed at most once per user turn, and
not at all when the grace usage is covered by extra usage (overage status `allowed` /
`allowed_warning`, or `anthropic-ratelimit-unified-overage-in-use: true`). Subagents get it only
under `tengu_lantern_wick_braid` (default false), with their own text override
`tengu_lantern_wick_braid_text`.

Release. After a wrap-up or near-limit note, the next user turn carries a release note once the
grace zone has ended or become covered by extra usage. It has no built-in text: the content comes
only from `tengu_lantern_wick_release_by_model` / `tengu_lantern_wick_release` (subagents:
`tengu_lantern_wick_braid_release`), so with no server value nothing is injected.

Resume. See "Continuing after a cap" below. It is the only one of the four that runs by default.

UI-only, never in the model's context:

- The threshold warning, built from the window's label: `You've used N% of your <limit>`, or
  `Over N% of your <limit> used` when the server sends only a surpassed threshold, or
  `Approaching <limit>`, then ` · resets …` and sometimes an upgrade or `/usage-credits` hint (grep
  `` `You've used ${ `` for the builder, `rate-limit-warning` for the notification key). It shows
  when the server reports `allowed_warning` and utilization is at least 0.7, and is suppressed for
  Team and Enterprise seats with extra usage enabled. Limit names come from the label map
  (`5-hour limit`, `weekly limit`, `Opus limit`, `Sonnet limit`, `Fable limit`,
  `usage credit limit`). Its overage sibling reads `You're close to your usage credit limit` or
  `Over N% of your usage credit limit used`.
- The cap line `You've hit your <limit> · resets …` and the throttle line containing
  `Server is temporarily limiting requests (not your usage limit)`. Both are synthetic assistant
  records (`isApiErrorMessage: true`, model `<synthetic>`), rendered and persisted to the transcript
  (Surface 5), but the API message normalizer drops them from every request: the exclusion predicate
  that skips `progress` and non-`local_command` system records also skips any assistant record that
  is an API error on the synthetic model. A 429 during a turn therefore ends or retries the turn
  without the model learning why. Retries, including the `CLAUDE_CODE_RETRY_WATCHDOG` wait, add
  nothing to the conversation either.
- Overage and model-scoped notices: the Fable credits dialog
  (`You've used your included Fable usage for this week`), the
  `is now using usage credits instead of your plan limits` notification, and the spend-limit and
  shared-budget messages.

A parent model can still read cap text indirectly. The cap line is what a failed subagent, workflow
stage, or teammate session reports back as its failure reason, and that text reaches the parent as a
tool result. That is the one route by which a reset time enters a conversation.

### Continuing after a cap

The client resumes by itself. The setting `autoContinueAtUsageLimit` (shown in `/config` as
`Continue automatically at usage limit`, default on; described as "wait for the limit to reset and
continue the task automatically") arms a wait when a claude.ai limit rejects the session. Arming
requires a `rejected` status with a finite `resetsAt`, no overage in use, an account whose
`billingType` is not `usage_based`, a reset within 24 hours, and the remote kill switch
`tengu_marble_heron` (default enabled; its object form also carries `autoArm` and jitter bounds). It
is not restricted to the 5-hour window, though automatic arming skips an Opus-only or Sonnet-only
weekly cap that the selected model is not bound by, and stops after three automatic continuations
since the last human prompt (cancel reason `continuation_cap`). It also arms after a grace wrap-up
note was placed and the turn completed.

It fires at `resetsAt` plus 30 to 90 seconds of jitter by enqueueing an `isMeta` prompt, so the
model receives this text as a user turn:

```
Your claude.ai usage limit has reset. Continue the task you were working on when the limit was
reached; do not repeat work that is already complete.
```

A server override keyed by model comes from `tengu_lantern_wick_resume_by_model`. When a quota probe
finds usage available before the reset, the early variant is sent instead:
`Your claude.ai usage is available again before the usage-limit reset. Continue the task …`.
Neither text carries a time or percentage. Escape, Ctrl-C, a manual submit, turning the setting off,
an account switch, or a relaunch cancels the wait; a machine that slept through the reset goes to a
`stale` state instead of firing. Telemetry: `tengu_quota_auto_resume_armed`, `_fired`, `_cancelled`
(with a reason), `_stale`, `_stale_resumed`, `_offer_armed`, `_setting_changed`.

The manual affordance remains. Grep `to continue after reset` for the hint line (rendered as
`Press ⏎ to continue after reset`) and `prefillRateLimitAutoQueueContinue` for the mechanism: on
hitting the cap the client writes the literal word `continue` into the prompt buffer for the user to
submit. It requires `tengu_vellum_anchor`, a `rejected` status with a finite `resetsAt`, the
`five_hour` window, no overage in play, and no auto-continue wait already armed for that reset.
Telemetry: `tengu_rl_checkpoint_auto_continue_queued` and `tengu_rl_checkpoint_copy_shown` on
arming, `tengu_rl_checkpoint_auto_continue_cancelled_by_upsell` when the user picks an upsell option
instead, which also clears the prefilled word. The same gate appends ` · progress saved` to the cap
line (grep `progressSavedSuffix`). `/rate-limit-options` carries a `Wait for limit to reset` entry
that triggers the prefill.

Independently of the setting, a model can resume itself at the reset with two ordinary primitives:
the reset time, read as text out of a failed subagent or workflow stage, and a backgrounded shell
command that exits at that time. Background completion wakes an idle session and re-invokes the
model, which is the Bash tool's documented contract (grep
`it keeps running across turns and re-invokes you when it exits`, and
`tengu_bg_attach_wake_after_reap` for the wake path). Sessions where this happened look like a
product feature and are not one. Foreground `sleep` is blocked in the Bash tool, so the working
spellings are a backgrounded until-loop, `Monitor`, or a scheduled wakeup.

### Unattended resume: the retry watchdog

One configuration does resume automatically, with no keystroke and no new turn. Grep the env var
`CLAUDE_CODE_RETRY_WATCHDOG`. When it is set, a 429, a 529 or an overload stops being a terminating
error: retries never exhaust, the delay for a quota 429 is taken from
`anthropic-ratelimit-unified-reset` rather than from backoff, and the same turn continues after the
sleep. A single delay is capped at six hours (grep `21600000` in the retry module), the sleep is
chunked so an abort or a wake subscription can cut it short, and waits above a minute emit
`tengu_api_persistent_retry_wait`. The watchdog also raises the default retry ceiling from 10 to 300
and lifts the clamp that otherwise limits `CLAUDE_CODE_MAX_RETRIES` to 15.

Companion variables bound it. `CLAUDE_CODE_RETRY_WATCHDOG_MAX_WAIT_MS` caps the total time spent
waiting; `CLAUDE_CODE_RETRY_WATCHDOG_MAX_USAGE_LIMIT_WAIT_MS` caps the time spent waiting on a
usage-limit 429 (one whose `anthropic-ratelimit-unified-status` is `rejected`), giving up instead
when the reset is further away; `CLAUDE_CODE_RETRY_WATCHDOG_USAGE_LIMIT_RECHECK_MS` sets how often
the wait re-checks whether the limit has lifted early; and
`CLAUDE_CODE_RETRY_WATCHDOG_SCOPE=capacity` keeps the default retry ceiling and the other 429
handling, leaving only the wait itself.

The client sets the watchdog for itself only on cloud and self-hosted runners, alongside
`CLAUDE_CODE_REMOTE=true` and `CLAUDE_ENABLE_STREAM_WATCHDOG=1` — grep the env block that carries
`CLAUDE_CODE_ENVIRONMENT_KIND: "byoc"`. Nothing restricts reading it to those runners, so exporting
it in a local terminal gets the same behavior. Two consequences worth stating before anyone does:
the session blocks silently for the whole window rather than returning control, and unless the scope
is `capacity` every other 429 path is suppressed too, including the fast-mode fallbacks that would
otherwise downgrade instead of waiting.

### Detecting mid-window resets and capacity grants

Server-side changes to an allowance mid-window are observable, and more cheaply than they look —
no absolute quota figure is needed. Within a single window `utilization = used / capacity` is
monotonically non-decreasing, so a *decrease* has only three causes, and the reset timestamp
separates them:

| Observation                                  | Cause                                         |
| -------------------------------------------- | --------------------------------------------- |
| utilization drops, `resets_at` moves forward | ordinary window rollover                      |
| utilization drops, `resets_at` unchanged     | `used` reset mid-window, or `capacity` raised |

The second row is the interesting one. A mid-window reset and a capacity increase are
indistinguishable from utilization alone — raising the denominator lowers the ratio just as zeroing
the numerator does — but either means allowance appeared that was not there before. The detection
needs only a monotonicity check over a sampled series. A limit reset the user claimed through the
`cedar_ember` program (Surface 7) produces the same signature.

Two limits worth stating. The change is invisible if utilization was at zero when it happened,
since there is nothing to drop from; a small nonzero reading suffices, but nothing at all does not.
And the sampled series must be dense enough that the drop is not masked by consumption in the same
interval — the scheduled `/usage` probe keeps sampling while idle and covers the model-scoped
buckets, whereas the statusLine sampler stops when work stops.

A second-order signal exists for capacity changes specifically: the 5-hour-to-weekly ratio derived
above shifts if one window's capacity is changed and the other's is not. Comparing that ratio
across weeks detects a rescaling that a utilization drop alone could not attribute.

### The monthly figure is a spend cap, not an allowance

Easy to misread as a third quota window, and the difference inverts any use-it-or-lose-it reasoning.
The monthly number is `extra_usage` — grep it in the `/usage` payload schema — with fields
`is_enabled`, `monthly_limit`, `used_credits`, `utilization`, and `currency`. The presence of
`currency` is the tell: this is money, the usage-credit overage budget (amounts in minor units of
the currency), matched by UI strings like "You're out of usage credits", `/usage-credits`, and
"You've hit your monthly spend limit". On the wire it rides the
`anthropic-ratelimit-unified-overage-*` headers.

So unspent monthly credit is money not spent, not allowance forfeited. Only the 5-hour and 7-day
windows are seat allowance already paid for under a subscription, and only those two are wasted by
going unused.

## Surface 7: the OAuth usage endpoint

The authoritative source, and the only one that needs neither a Claude Code process nor a cache.

```
GET https://api.anthropic.com/api/oauth/usage
  User-Agent: claude-cli/<version> (external, <entrypoint>)
  Authorization: Bearer <accessToken>
  anthropic-beta: oauth-2025-04-20
  Content-Type: application/json
```

Those are the headers Claude Code sets. The HTTP library (axios) adds its own defaults on top:
`Accept: application/json, text/plain, */*` (grep `application/json, text/plain, */*`) and
`Accept-Encoding`, plus the usual `Host` and `Connection`. The read goes through the first-party
request helper (debug prefix `firstPartyApi:`), not the Messages API client, so `x-app`,
`X-Claude-Code-Session-Id` and the `anthropic-client-*` headers are absent. The helper sets
`User-Agent` itself on every call; the format is grep `` `claude-cli/${ `` with
`(external, ${…CLAUDE_CODE_ENTRYPOINT ?? "cli"}…)`, where `<entrypoint>` is `cli` by default and
`, agent-sdk/<v>`, `, client-app/<name>` and `, workload/<name>` are appended when set. The bearer
and beta pair come from the shared auth-header builder (grep `"No OAuth token available"`). The read
is skipped unless the login is a claude.ai subscriber login holding the profile scope. The base URL
is `BASE_API_URL` from the OAuth config block (grep `BASE_API_URL: "https://api.anthropic.com"`).

Relocation: `rg -n 'api/oauth/usage'` in the bundle for the path table, which maps four read modes
to query strings — `plain` (no query), `at_wall` and `cedar_ember` (see "Limit resets" below), and
`starry_waterfall`, the usage-credit offer status read (debug prefix `[usage-credit-offer]`) — and
`fetchUtilization: GET` for the debug line.

The client paces itself against the endpoint. Under `tengu_federated_robin` (default on) a 429 or
403 answer is remembered per bearer token and the endpoint is not asked again until the
`Retry-After` time, or five minutes when none is sent, capped at an hour; a rejected token is
remembered for an hour (grep `remembered for this bearer`). A poller of its own should honour
`Retry-After` the same way.

### Getting the token

The bearer token is the one Claude Code already stores per config directory, under
`claudeAiOauth.accessToken`, alongside `refreshToken`, `expiresAt`, `refreshTokenExpiresAt`,
`scopes`, `subscriptionType` and `rateLimitTier`.

On macOS it lives in the Keychain, not on disk. The service name is built as
`Claude Code` + `OAUTH_FILE_SUFFIX` + `-credentials` + a directory discriminator, and the account
name is `$USER`. The discriminator is empty when `CLAUDE_CONFIG_DIR` is unset, and otherwise
`-sha256(NFC(dir))[:8]` — so several logins coexist, one per config directory:

```
security find-generic-password -s "Claude Code-credentials" -a "$USER" -w
security find-generic-password -s "Claude Code-credentials-<8 hex>" -a "$USER" -w
```

`CLAUDE_SECURESTORAGE_CONFIG_DIR` overrides which directory is hashed. On other platforms the same
object is a `.credentials.json` file inside the config directory.

### Response shape

Top-level keys are one object per bucket plus a flattened array:

- `five_hour`, `seven_day`: `utilization`, `resets_at`, and null dollar fields on a subscription
  seat.
- `limits[]`: one entry per active bucket, with `kind`, `group`, `percent`, `severity`, `resets_at`,
  `scope`, `is_active`.
- `extra_usage`: the overage budget; `monthly_limit` and `used_credits` in minor units.
- `spend`: structured money, `used` / `limit` as amount, currency and exponent, plus `cap`,
  `percent`, `severity`, `enabled`.
- `member_dashboard_available`: boolean.

`limits[]` is the part the cached blob does not improve on: a scoped weekly names itself, as
`scope.model.display_name`, instead of having to be inferred from a key. `is_active` marks the row a
single-value indicator should show. The client's schema names the `limits[]` fields and
`extra_usage`; `spend` and `member_dashboard_available` are observed in real responses and are not
read by the client.

Many bucket keys exist and read null on a normal seat — `seven_day_oauth_apps`, `seven_day_opus`,
`seven_day_sonnet`, `seven_day_cowork`, `seven_day_omelette`, and codenamed slots in the same
register as the bundle's feature-flag names. Treat the set as open and key off `limits[]`.

The bundle also ships the contract a Claude gateway must meet to answer this path (grep
`the path claude.ai serves Claude Code's usage data on`): `utilization` and `percent` are whole
percents from 0 to 100 (above 100 once over), `resets_at` is ISO 8601 UTC, money is in cents, and a
gateway `limits[]` row can have `kind: "spend"`.

### Practical notes

- `utilization` and `percent` are percentages (`41.0`), not fractions; the client renders them
  directly and converts header fractions to match.
- It reports live figures, so nothing equivalent to the cached blob's `fetchedAtMs` staleness
  applies — but a `/usage` probe may itself be answered from a cache under a minute old.

### Related endpoints on the same credential

These were observed by calling them, not derived from the bundle beyond the paths existing.

`GET /api/oauth/profile` returns `account` (uuid, email, display name, `has_claude_max`,
`has_claude_pro`, `created_at`) and `organization` (uuid, name, `organization_type`, `billing_type`,
`rate_limit_tier`, `seat_tier`, `has_extra_usage_enabled`) — the same identity the config file
caches under `oauthAccount`, but authoritative.

`POST /v1/oauth/token` is the refresh path, which is what makes a token-only deployment viable:
ship an access token to a machine that has no Claude Code install, and renew it before `expiresAt`.

`GET /api/claude_code/organizations/metrics_enabled` returns `400 Access Forbidden` for a
non-admin seat, which is consistent with the rest of this document: org-level usage visibility is
not a seat-holder surface. `GET /api/oauth/validate` and `GET /v1/organizations/spend_limits` both
return `405`, so they are not GETs.

### Limit resets: the `cedar_ember` program

Some seats are offered grants that refill rate limits on demand. The client reads them from the
usage endpoint and spends them with a separate POST. Landmarks: the GrowthBook flag
`tengu_cedar_ember`, the debug prefix `[cedar-ember]`, the hidden slash command `/limit-reset` (grep
`"limit-reset"`), and the `tengu_cedar_ember_*` events (`_asked`, `_wall`, `_shown`, `_selected`,
`_confirmed`, `_result`, `_give_back`).

The status read uses the same request as above with one of two query strings:

| Read mode     | Path                                          | When it is sent                 |
| ------------- | --------------------------------------------- | ------------------------------- |
| `at_wall`     | `/api/oauth/usage?at_wall=1&skip_spend=1`     | a rejection lands in a turn     |
| `cedar_ember` | `/api/oauth/usage?cedar_ember=1&skip_spend=1` | `/limit-reset`, dialog, startup |

The `at_wall` read fires when the session's limit state turns `rejected`, gated on
`tengu_cedar_ember` `enabled` or, for the wall alone, a `tengu_wise_bear_copy` value with
`only_if_unused_reset`; under the usage-credit offer flag it also appends
`starry_waterfall=<surface>`. Concurrent `at_wall` reads for one account are deduplicated, and a
failed read is retried at most three times per wall. The `cedar_ember` ("anytime") read is used when
the session is not currently rejected, which is why it can offer a reset before a limit is reached.
Both carry a 12-second client budget on top of the request's own 5-second timeout.

There is one background read. When a `tengu_startup_announcements` entry carries a
`textIfUnusedLimitReset` variant, the client makes a `cedar_ember` read at startup and caches
whether the account holds an unused reset in the config's `unusedLimitResetStatusCache` (valid for
up to three days, or until the earliest grant expires), so the announcement can swap its text.

The answer is the response's `cedar_ember` object. The client's schema parses `eligible`,
`ineligible_reason`, `at_limit`, `exhausted[]`, `grants[]`, `next_grant_id`, `weekly_resets_at`,
`cooldown_until`, and `event_props` (`surface`, `tier`, `tenure_bucket`, `billing_path`,
`billing_period`, `extra_usage_state`). A grant carries `id` (`^[a-z0-9_-]{1,40}$`), `label`,
`resets_total`, `resets_left`, `starts_at`, `ends_at`, `clears[]` (the limit buckets it refills),
`paused`, `usable_now`, `use_requires_limit`, `percent_used`, `blocking[]`, `type` (`session`,
`weekly`, `full`), `gives_back_weekly`, and `unavailable_reason`.

The client groups grants into four kinds: `session` (refills only `five_hour`), `weekly` (refills
weekly buckets only), `full` (both), and `fable`, a grant with `gives_back_weekly` that returns what
Fable used to the weekly limit. At a limit, each kind is offered through its first grant that is
`usable_now`, not `paused`, not past `ends_at`, and refills the limit that was hit; the kind that
matches the hit window is listed first. With several kinds on offer the user picks one
(`Which reset do you want to use?`). Kinds that cannot be used are listed with a reason such as
`doesn't refill your …` or `usable once you reach a limit it refills`.

`ineligible_reason` is an enum fixed in the client: `config_off`, `tier`, `seat`, `mobile`,
`surface`, `cli_version`, `no_grant`, `tenure`, `other_experiment`, `unavailable`, `unknown`.
`event_props.surface` is one of `claude_ai`, `claude_code_cli`, `unknown`. The client computes none
of these. It sends no surface or version field in the query or body, and it holds no minimum-version
constant for the program: the `tengu_cedar_ember` config keys are `enabled`, `version` (a config
revision reported in telemetry), `autoContinue`, and override strings for the UI text. The only
surface and version signal on the request is therefore the `User-Agent`. Observed behaviour: a
caller that reuses the same OAuth token with a non-`claude-cli/` agent string is answered
`ineligible_reason: "surface"`, and one sending `claude-cli/<version> (external, cli)` is answered
with grants, so the server classifies the surface from the agent string and applies its
`cli_version` floor to the version parsed from it. The floor value lives only on the server.

Grants surface in three places:

- The cap notice under a rate-limit error renders `noticeLine`, by default
  `/limit-reset to use your {kind} · {left} left · use by {date}` (`noticeLineMany` when several
  kinds are held).
- `/rate-limit-options` adds an entry whose label defaults to
  `Use a {kind} ({left} left, until {date})`, with event
  `tengu_rate_limit_options_menu_select_cedar_ember`.
- `/limit-reset` (hidden) runs the anytime read and then the same flow. The `tengu_nifty_lemur` flag
  drives a separate one-per-week 5-hour reset with its own strings (`Reset your 5-hour limit now`),
  claimed as program `juniper_tide`.

The confirmation dialog is titled `Use a {kind}?`, body
`Refills your {limits} now · {returns} · your weekly reset day stays {week}`, with
`Yes, use my {kind}` and `No, keep it`. When no limit is reached yet, it adds
`You still have {percent}% of your {limit} left — use your {kind} anyway?`. Declining sends no
request. Every string has a server override in the `tengu_cedar_ember` config, with the defaults in
the object next to `"limit-reset"`.

Before claiming at a limit, the client re-reads the status and aborts with a "nothing was used"
message (grep `A different reset is on offer now`) if the chosen kind is no longer offered or now
points at a different grant. The claim is:

```
POST https://api.anthropic.com/api/organizations/<organizationUuid>/reset_rate_limits
  (same User-Agent, Authorization and anthropic-beta headers)
  {"program": "cedar_ember", "grant_id": "<grant id>", "request_id": "<uuid>"}
```

`organizationUuid` comes from the stored OAuth account. `request_id` is a fresh `randomUUID()` per
attempt, except that a claim whose outcome was unconfirmed reuses the same `request_id` for the same
grant for ten minutes, which makes a retry idempotent. The request timeout is 25 seconds inside a
35-second client budget. The response schema is `result` (`reset`, `already_used`, `not_limited`,
`cooldown`, `ineligible`, `unavailable`), `reason`, `resets_left`, `cleared[]`, `weekly_resets_at`,
and `cooldown_until`. The client adds `rate_limited` for a 429, `auth_error` for 401/403, and
`error` otherwise.

On `reset`, the client marks the cleared buckets as allowed locally and prints `successLine`
(default `{done} · your weekly reset day stays {week} · {kindResets} left`, where `{done}` is, for
example, `5-hour limit reset` or `Limits reset`). When the grant did not itself refill the limit
that was hit (a Fable give-back at the weekly wall), the client re-checks quota and reports whether
the limit still binds (`tengu_cedar_ember_give_back`). At a limit it also cancels any armed
auto-continue wait; if the reset cleared the wall that stopped the turn and `autoContinue` is on,
the turn resumes, otherwise it appends `send a message to continue`. Most other outcomes trigger a
quota probe to refresh the local limit state rather than a second usage read. The sibling program
`juniper_tide` posts to the same endpoint with only `{"program": "juniper_tide"}` and no grant.

## When a window begins: the 5-hour window is anchored to activity, the weekly one is not

Neither `resets_at` value can be extrapolated the same way, and the difference decides what a
scheduling tool may legitimately predict. The anchoring rule is server-side, so it is not visible in
the bundle; the finding below is empirical, from recorded `statusLine` readings.

The 5-hour window is not a fixed grid. It begins when you next do something and its clock does not
advance while you are idle. Consecutive `five_hour.resets_at` values across observed transitions:

| Previous reset | Next reset | Delta  | What happened               |
| -------------- | ---------- | ------ | --------------------------- |
| 20:10          | 01:10      | +5.00h | working across the boundary |
| 01:10          | 06:50      | +5.67h | idle 40 min, then resumed   |
| 06:50          | 15:20      | +8.50h | idle 3h 30m, then resumed   |

A delta above five hours is exactly the idle gap. In every case the new window is first seen at 0%
used, which is self-consistent: your activity both starts the window and produces the reading.

The weekly window is a fixed seven-day grid. An observed rollover moved `seven_day.resets_at` by
exactly `+168.00h`, landing on local midnight, with no dependence on activity.

Consequences for anything built on these:

- Only the current 5-hour `resets_at` is knowable. Any tiling beyond it assumes uninterrupted
  back-to-back use and is a capacity estimate, not a schedule.
- Idle time does not consume 5-hour windows. It does consume wall-clock time before the fixed
  weekly reset, which is where the real cost of idling lands.
- A window is consumed by *starting* it. Beginning one and then stopping spends the whole slot for
  whatever was used in it.

Reproduction: record the `statusLine` payload's `rate_limits` over several days, then group by
`session_id` and walk each session's own `resets_at` transitions.

Two traps in that data. Readings from concurrent sessions interleave, and each session carries its
own snapshot refreshed only when it last called the API, so an idle session can report a stale
window — sorting the raw log by timestamp produces a sawtooth of contradictory values. And transient
one-off values occur: three weekly `resets_at` appeared exactly once each against ~104,000 readings
of the true value, so discard singletons rather than treating them as mid-week adjustments.

## Surface 5: cap hits recorded in the transcript

Every API error is persisted as an `assistant` record in the session JSONL with
`isApiErrorMessage: true`, and a rate-limit rejection carries `error: "rate_limit"` plus
`apiErrorStatus: 429`, a `requestId`, and the usual `sessionId` / `timestamp` / `cwd` /
`gitBranch` / `version` context. Field reference: `SESSION_TRANSCRIPT.md`. This makes the local
transcript corpus a complete, zero-configuration, retroactive history of every time a cap was hit —
available without OTel, without a statusLine, and for sessions that already happened.

The message text is the discriminator, and getting it wrong is the trap. `error: "rate_limit"`
covers unrelated conditions:

| Message text                                                     | Meaning                    |
| ---------------------------------------------------------------- | -------------------------- |
| `You've hit your 5-hour limit · resets …`                        | 5-hour window exhausted    |
| `You've hit your weekly limit · resets …`                        | 7-day window exhausted     |
| `You've hit your Opus limit` / `Sonnet limit` / `Fable limit`    | model-scoped weekly window |
| `You've hit your usage limit` / `You've hit your limit`          | cap hit, window not named  |
| `You're out of usage credits` and other overage messages         | overage credits exhausted  |
| `Server is temporarily limiting requests (not your usage limit)` | server throttle, not a cap |

Counting raw 429s therefore overstates cap hits, and by a wide margin — in one real corpus the
server-throttle variant was about a third of all `error: "rate_limit"` records. The product itself
draws the same distinction: the throttle string is a standalone constant (grep
`not your usage limit`), while the cap messages are built by a formatter (grep
`` `You've hit your ${ ``) whose label map is the `rateLimitType` → display-name table (grep
`five_hour: "5-hour limit"` and read the adjacent `seven_day` / `seven_day_opus` /
`seven_day_sonnet` / `seven_day_overage_included` / `overage` entries). A Sonnet-only weekly cap
reads `weekly limit` on Pro and Enterprise. A parser must tolerate unmapped labels rather than
assume the set above.

Two structured fields make text matching optional on records this version writes. A cap record built
from the limit headers carries `apiError: "usage_limit_reached"` and `apiErrorParams` with a
`rate_limit_info` object (`status`, `resetsAt`, `rateLimitType`, overage fields), plus
`quotaLimits`; a subscriber's throttle record carries `apiErrorIsTransient: true` (grep
`"usage_limit_reached"` and `apiErrorIsTransient`). Records written by other versions can carry
other wordings — the client's own classifier still accepts `session limit` for the 5-hour window,
and older records may carry neither structured field — so match on the presence of the negation
(`not your usage limit`) to exclude throttles first, then on the label keywords, and treat an
unrecognized cap message as "cap hit, window unknown" rather than dropping it.

Three limits on this surface. It is retroactive only — the record appears when the wall is hit, so
it can never warn of an approach; pair it with Surface 1 for that. And it is local: the corpus under
the projects directory covers only the machines whose transcripts you can read, so a seat used from
several machines needs its records unioned, keyed on something stable, before the counts mean
anything.

The third is an interpretation trap rather than a coverage gap. A cap-hit count is a function of
two things that both drift — how hard the account was used, and how large the allowance was — and
allowance changes are never announced or recorded anywhere on the client. So a total spanning any
such change describes two different plans at once and means nothing. Report per period, and
normalise by an activity denominator from the same corpus (active days, and record counts per day
as a crude intensity proxy) so periods are comparable at all. Even then the attribution is only
suggestive: a period with *higher* activity and *fewer* cap hits than a later one is evidence the
allowance tightened, but record counts are a poor stand-in for consumption because context size
dominates token cost, and this surface never reveals the size of a limit — only that one was
reached.

A hook does fire on it. `StopFailure` runs when a turn ends on an API error, with `error` set to the
error kind (`rate_limit`, `overloaded`, `billing_error`, …; it is also the matcher value) and
`last_assistant_message` holding the cap or throttle text (grep `hook_event_name: "StopFailure"`). A
`StopFailure` hook matching `rate_limit` therefore sees every cap hit live, without OTel, though it
still has to read the text to separate caps from throttles. `transcript_path` is a base field
present on every hook event, so the hook can also read the full record.

## Fleet plan-limit tracking

For the "how close is each team member to their cap" question, the source supports exactly one
first-party path for interactive seats, and it is not OpenTelemetry.

Ship a statusLine command to every seat and have it forward `rate_limits` alongside `session_id`,
`prompt_id`, and the identity you already know for that machine. The command receives the full JSON
on stdin and its stdout becomes the status line, so the export has to be a side effect:

```bash
# statusLine command. Reads the documented statusLine JSON on stdin.
input=$(cat)
jq -c '{
  ts: now, session: .session_id, prompt: .prompt_id,
  five_hour: .rate_limits.five_hour, seven_day: .rate_limits.seven_day,
  cost_usd: .cost.total_cost_usd
} | select(.five_hour != null or .seven_day != null)' <<<"$input" \
  >> ~/.claude/rate-limit-samples.jsonl
jq -r '"5h:\(.rate_limits.five_hour.used_percentage // 0 | floor)%"' <<<"$input"
```

Three properties to design around. `rate_limits` is absent until the first API response of a session
and absent entirely for API-key, Bedrock, and Vertex sessions, so a missing sample is not a zero —
the `/usage` payload's `rate_limits_available` flag names those cases explicitly ("False when plan
rate limits do not apply (API key, Bedrock, Vertex, or missing profile scope)"). The command fires
on a 300 ms debounce off message and token-usage changes, so an idle session stops emitting apart
from one run at each window reset; use `statusLine.refreshInterval` if the dashboard needs a
heartbeat. And the numbers are per machine: a seat used from two machines produces two independent
sample streams for one server-side limit, so deduplicate on identity and take the maximum rather
than summing.

Distribution follows the normal settings precedence — `statusLine` is a policy-pinnable setting, so
managed settings can install it centrally (grep `policySettings")?.statusLine` for the lookup
guarded by the customization-lock predicate).

A plugin cannot do this job. The settings resolution order is the array `userSettings`,
`projectSettings`, `localSettings`, `flagSettings`, `policySettings` (grep that literal array), with
no plugin tier. A plugin manifest does have a `settings` key ("Settings to merge into the user
settings while this plugin is enabled. Only the documented allowlisted keys are applied."), but the
allowlist is exactly `agent` and `subagentStatusLine` (grep `["agent", "subagentStatusLine"]`): no
`env` block and no `statusLine`. The one plugin-scoped configuration mechanism beyond that is
`user_config`, described as "User-configurable values this plugin needs. Prompted at enable time…
Available as `${user_config.KEY}` in MCP/LSP server config, hook commands, and (non-sensitive only)
skill/agent content" — interpolation into a plugin's own components, not into the process
environment. So enabling OpenTelemetry, or installing a statusLine, has to come from a settings file
(`env` block) or the real process environment; a plugin can ship the collector-side hook scripts but
cannot switch telemetry on.

A plugin does remain useful for the parts that *are* hooks. `strictPluginOnlyCustomization`, the
managed lockdown that blocks user and project customization, explicitly exempts plugin-provided
customizations — its describe string reads "NOT blocked: managed (policySettings) sources,
plugin-provided customizations". So a company plugin can carry the collector-side hook scripts and
survive the strictest admin lockdown; it simply cannot be what turns telemetry on.

Hook delivery has one non-obvious semantic worth knowing before splitting hooks across sources.
Hooks do not merge the way other settings do: the resolver returns *either* the managed set or the
merged set, never a union chosen per source. Grep the resolver by its
`disableAllHooks === !0) return {}` early return and read the branch order —
`policySettings.disableAllHooks` yields none; `allowManagedHooksOnly` (its describe string: "When
true (and set in managed settings), only hooks from managed settings and from plugins that managed
settings enable run. User, project, and local hooks and the hooks of plugins the user installed are
ignored") or a hooks lockdown yields the managed set alone; otherwise the merged settings hooks are
returned. Plan for one side of that switch, not both; under `allowManagedHooksOnly` the collector
plugin must be one that managed settings enable.

Two hook types make this pipeline shorter than it first appears. An `http` hook takes a `url`
described as "URL to POST the hook input JSON to" plus `headers` whose values may interpolate
environment variables listed in the hook's own `allowedEnvVars` — so a hook can ship JSON to a
collector with an auth header and no local script at all. Managed settings can fence this with
`allowedHttpHookUrls` (wildcard URL allowlist; empty array blocks all HTTP hooks) and
`httpHookAllowedEnvVars` (intersected with each hook's own list). For cap hits, a `StopFailure`
`http` hook posts the error kind and the cap text directly; anything needing the full transcript
record still needs a local `command` hook, since the POSTed body carries `transcript_path` but not
the transcript.

Hooks do not help with utilization, though: no hook input carries `rate_limits`. Grep `rate_limits`
across the bundle and every Claude Code hit is the statusLine setup prompt and builder, the `/usage`
payload schemas, the SDK retry frame's quota snapshot, or the limit-reset claim path.

## The `tengu_*` namespace is two things

Worth stating plainly because it is easy to mistake one for the other: `tengu_*` is a shared
namespace covering both analytics event names and GrowthBook feature-flag keys. Over 3,000 distinct
`tengu_*` literals appear in the bundle; several hundred of them are flag lookups (about 670 are
followed directly by a boolean default, and more flag names are hoisted into constants first).

The call shape separates them. A flag lookup passes a client-side default as the second argument —
`getFeatureValue`-style, e.g. `("tengu_gb_eval_authed_enable", !1)` — whereas an analytics emission
passes a properties object. Grep a name with `,\s*(!0|!1)` following it to test which kind it is.
Flag names also read differently: gates use opaque two-word codenames (`tengu_amber_lark`,
`tengu_alder_compass`) while analytics events are descriptive (`tengu_agent_tool_completed`).

The evaluation machinery is GrowthBook, not Statsig — grep the exported helpers
`getAllGrowthBookFeatures`, `hasFreshGrowthBookFeatures`, `checkGate_CACHED_OR_BLOCKING`,
`getDynamicConfig_CACHED_MAY_BE_STALE`, `getFeatureValue_CACHED_WITH_REFRESH`. The suffixes are the
useful part: they encode each lookup's staleness contract, and remote evaluation (grep
`eval-authed`) means server-side changes reach clients without a release. Consequence for this doc
and any tool built from it: a behavior gated this way can differ between two users on the same
version, and the literal in the bundle is only the fallback default.

## Anthropic-internal analytics events

These `tengu_*` / event-pipeline emissions are not a public consumption API, but they show what the
client measures. The subagent completion path emits two:

- `tengu_agent_tool_completed`: `agent_type`, `model`, `prompt_char_count`, `response_char_count`,
  `assistant_message_count`, `total_tool_uses`, `duration_ms`, `total_tokens`, `is_built_in_agent`,
  `is_async`, `agent_depth`, `final_model`, `model_swapped`. The `total_tokens` here is the
  last-message snapshot described in Surface 2.
- `subagent_completed`: `agent_type` (or `"custom"`), optional `agent.source`, `is_built_in`,
  `is_async`, `total_tokens`, `total_tool_uses`, `duration_ms`, `model`, `final_model`,
  `model_swapped`, plus `plugin_id_hash` / `plugin.name` for plugin agents.

Other token/cost-bearing events: `tengu_advisor_tool_token_usage` reports per-auxiliary-model usage
with `advisor_model`, `input_tokens`, `output_tokens`, `cache_read_input_tokens`,
`cache_creation_input_tokens`, and `cost_usd_micros` — a genuine per-call token-plus-cost event.
`tengu_cost_threshold_reached` and `tengu_cost_threshold_acknowledged` fire around the one-time
session-cost warning dialog, shown once session cost passes $5, mainly to API-key users, and
suppressed by `DISABLE_COST_WARNINGS`.

## Choosing a surface

| Need                                              | Use                                         |
| ------------------------------------------------- | ------------------------------------------- |
| Quick per-subagent read, no setup                 | `Done (…)` summary, `<usage>` trailer       |
| Exact per-subagent total, attributable, logged    | SubagentStop hook summing (Surface 3)       |
| Per-subagent / per-MCP-tool split across sessions | OTel metrics, per-source attributes         |
| Session totals, by model                          | `/usage` print form, non-subscriber login   |
| Live in-turn budget                               | statusLine `context_window`                 |
| Plan limit utilization, per person                | statusLine `rate_limits` (not in OTel)      |
| Plan limit utilization, in an SDK host            | `rate_limit_event` frames, `get_usage`      |
| All buckets, structured, account-tagged           | `cachedUsageUtilization` (Surface 6)        |
| History of caps already hit, no setup             | Transcript `rate_limit` records (Surface 5) |
| Detecting a cap live                              | `StopFailure` hook, or OTel `api_error`     |

## Org-level visibility is not a product surface

Worth recording because it is the first thing anyone asks and the answer is a dead end for most
plans. Nothing in the client reports usage to an org-facing store that an admin can query; every
surface in this doc is local to the machine. Anthropic's own admin-side offerings, which are
server-side and therefore outside what this bundle can verify, are documented as tiered: the Admin
API and the Enterprise Analytics API are Enterprise-only, and the Claude Code Analytics API is for
Console/API-key organizations. Team-plan seats using Claude Code over OAuth spend against a seat
allowance rather than a metered API key, so their usage is documented as not appearing in spend
reports at all unless it overflows into usage credits.

The consequence for this doc: on a Team plan, the surfaces described here are not a supplement to a
first-party dashboard, they are the only implementation available, and OpenTelemetry with managed
settings is the only route that streams per-user figures off the machine without bespoke scripting.
None of the admin surfaces expose limit utilization on any tier. Treat the tiering specifics as
external and re-check them against the published docs rather than this file; only the client-side
half is source-verifiable.
