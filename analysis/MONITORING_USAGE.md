# Monitoring Token Usage and Cost

Behavioral model verified against 2.1.165. This document follows the landmark style in
`GUIDELINES.md`: it anchors on version-stable strings (slash-command names, `tengu_*` event names,
env var names, OTEL metric/attribute names, literal UI strings, JSONL field names, behavioral logic)
with grep re-location recipes, not on minified symbol names or line numbers, which churn every
release. Per-release changes are in the appendix.

This doc answers: how much usage is a given subagent or tool consuming, and where can that be read?
The short version is that there are four observation surfaces, each with a different granularity and
a different honesty caveat. Per-subagent attribution is possible; exact per-tool-call token cost is
not, because a tool call does not itself consume tokens — the assistant turns around it do.

## What this doc owns vs. cross-references

This doc owns the observation/attribution story: the OpenTelemetry surface, the `/usage` command
family, the per-subagent `<usage>` trailers and their snapshot semantics, and the SubagentStop
attribution recipe. It cross-references the field-level references that already live elsewhere:

| Topic                                              | Lives in                          |
|----------------------------------------------------|-----------------------------------|
| `message.usage` field reference (per-message)      | `SESSION_TRANSCRIPT.md`      |
| statusLine `context_window` input object           | `PROMPTS_RENDERED.md`             |
| `compactMetadata.preTokens`, microcompact tokens   | `CLEAR_COMPACT_FORK_CONTEXT.md`   |
| Session-memory background billing                  | `SESSION_MEMORY_AND_SUMMARY.md`   |
| Subagent output pipeline, the `Done (…)` summary    | `TASK_TOOL_AND_SUBAGENTS.md`      |
| SubagentStop hook input schema                     | `HOOKS.md`                        |

## The ground-truth token figure

Every assistant message record in the transcript JSONL carries a `message.usage` object with
`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, and the
`cache_creation.ephemeral_1h_input_tokens` / `ephemeral_5m_input_tokens` breakdown. Field reference:
`SESSION_TRANSCRIPT.md`.

The canonical "tokens for one usage object" sum used throughout the product is the four-term total:

```
input_tokens + (cache_creation_input_tokens ?? 0) + (cache_read_input_tokens ?? 0) + output_tokens
```

Re-locate it by grepping for a function body matching that shape (the
`cache_creation_input_tokens ?? 0` fragment is distinctive). This single-object sum feeds the
subagent token figure and the telemetry events below.

A subagent or session runs many turns, each a separate billed API request. The true total tokens it
consumed is the sum of that four-term value over every assistant record, not the value on any one
record. This distinction is the central gotcha of this doc, because the figure surfaced in the UI is
a single record's value, not the sum.

## Surface 1: live in-session usage

Two read points expose the current session's usage live.

The statusLine command input carries a `context_window` object: `total_input_tokens`,
`total_output_tokens`, `context_window_size`, `current_usage` (the raw last `message.usage`, or
null), `used_percentage`, `remaining_percentage`. `total_input_tokens` is the last call's
`input_tokens + cache_creation_input_tokens + cache_read_input_tokens`. This is session-level, last
API call, exposed to statusLine authors. Full field doc: `PROMPTS_RENDERED.md`. Re-locate the
builder by grepping `total_input_tokens` near `remaining_percentage`.

The `/usage` slash command (aliases `/cost` and `/stats`, grep `aliases: ["cost", "stats"]`) reports
session and plan usage. It has two forms:

- Interactive: opens the settings dialog on the `Usage` tab (or `Stats` when invoked as `/stats`).
  The Usage tab shows server-fetched plan usage with labels like `Current session`, `Current week
  (all models)`, `Current week (Sonnet only)`, `Usage credits`, `Unlimited`. The Stats tab shows
  local history: `Total tokens`, `Tokens per Day`, `Favorite model`, `Active days`, `Sessions`,
  with time toggles `All time` / `Last 30 days` / `Last 7 days`.
- Non-interactive (`--print` / `supportsNonInteractive`): prints a text block. Re-locate by grepping
  `Usage by model:`. Shape:

  ```
  Total cost:            {cost}
  Total duration (API):  {dur}
  Total duration (wall): {dur}
  Total code changes:    {N} lines added, {M} lines removed
  Usage by model:
    {model}:  {N} input, {N} output, {N} cache read, {N} cache write[, {N} web search] ({$cost})
  ```

  Followed by a one-line `breakdown · opus: N% · sonnet: N% · cache hit: N%` (grep `cache hit`).

Granularity caveat: `/usage` and `/stats` break usage down by model only. They do not show a
per-subagent, per-skill, per-plugin, or per-MCP breakdown. That granular attribution exists only via
OpenTelemetry (Surface 4).

## Surface 2: per-subagent attribution (the Agent tool result)

When a subagent finishes, the parent model's tool result carries a trailer with the subagent's
totals. Three distinct `<usage>` string shapes exist; grep accordingly.

Synchronous completion, the flat form the parent model receives (grep `subagent_tokens:`):

```
agentId: {id} (use SendMessage with to: '{id}' to continue this agent)
<usage>subagent_tokens: {N}
tool_uses: {N}
duration_ms: {N}</usage>
```

Background / teammate worker notification, a nested-tag form (grep `<subagent_tokens>`):

```
<usage><subagent_tokens>{N}</subagent_tokens><tool_uses>{N}</tool_uses><duration_ms>{N}</duration_ms></usage>
```

Collapsed human-facing one-liner in the terminal (grep `1 tool use`):

```
Done ({N} tool uses · {M} tokens · {time})
```

Snapshot, not sum. All three figures derive from the same value: the four-term token sum of the
subagent's last assistant message only. The completion record computes `total_tokens` from the
last `assistant` message picked by a `findLast` over the message list, not a sum across turns. So
`subagent_tokens`, the `Done (…)` token count, and the telemetry `total_tokens` all reflect the
final turn's footprint. Because each turn re-sends the growing context (mostly as cache reads), the
final turn's input side is roughly cumulative, but every prior turn's output is omitted. Treat these
figures as a footprint proxy that undercounts true consumption, not as a billed total.

For Explore and Plan subagents (grep the built-in set `new Set(["Explore", "Plan"])` and its
`.has(...)` check at the tool-result builder) the trailer is omitted entirely when no worktree is in
play: their result is the raw text content only, with no `agentId:` line and no `<usage>` block.

## Surface 3: exact per-subagent total via the SubagentStop hook

No hook input carries a token or cost field, verified by grepping the hook-schema block for
`token`/`usage`/`cost` (no matches). But the SubagentStop hook input carries
`agent_transcript_path`, a path to the subagent's own JSONL file, alongside `agent_id`,
`agent_type`, and an optional
`last_assistant_message` (describe string: "Text content of the last assistant message before
stopping. Avoids the need to read and parse the transcript file."). See `HOOKS.md` for the full
SubagentStop schema.

That path resolves to `<projectDir>/<sessionId>/subagents/[<key>/]agent-<agentId>.jsonl` (grep the
path builder via `subagents` joined with `agent-` and `.jsonl`). It is a real per-subagent
transcript with one `message.usage` per turn. Summing the four-term value over every assistant
record there gives the true cross-turn total, the figure the `<usage>` trailer cannot give. A
minimal hook:

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
printf '%s consumed %s tokens (summed across turns)\n' "$TYPE" "$TOTAL" >> ~/.claude/subagent-usage.log
```

This sums the per-call billed totals across the subagent's whole run, since each turn is a separate
API request. To attribute by your custom agent, branch on `agent_type`.

## Per-tool-call tokens are not available

A tool call has no token cost of its own. The cost is the input tokens of the assistant turn that
emitted the `tool_use` block, plus the input tokens of the next turn that carries the `tool_result`.
No field attributes tokens to a single tool call. What is available: the tool-lifecycle hooks
(PreToolUse, PostToolUse, PostToolUseFailure) carry `agent_id` and `agent_type` (grep their describe
strings in the base hook schema), so a tool call can be attributed to the subagent that issued it,
and the subagent total above is where those tokens land. OTEL `claude_code.tool` spans record tool
execution but not the call's token consumption.

## Surface 4: fleet and longitudinal monitoring via OpenTelemetry

OTEL is the only surface with built-in per-subagent and per-tool attribution. Enable it with the
`CLAUDE_CODE_ENABLE_TELEMETRY` env var (grep that name; the disable hint string is "Disable
OpenTelemetry by unsetting CLAUDE_CODE_ENABLE_TELEMETRY env var"). The bundle ships the
OpenTelemetry SDK and exports over OTLP; see `DEPENDENCIES.md`.

Metric instruments (grep `claude_code.token.usage`):

| Instrument                  | Unit     | Meaning                                   |
|-----------------------------|----------|-------------------------------------------|
| `claude_code.token.usage`   | tokens   | "Number of tokens used"                   |
| `claude_code.cost.usage`    | USD      | "Cost of the Claude Code session"         |
| `claude_code.session.count` | —        | session count                             |
| `lines_of_code.count`       | —        | lines added/removed                       |
| `commit.count`              | —        | git commits                               |
| `pull_request.count`        | —        | PRs                                       |
| `code_edit_tool.decision`   | —        | edit-tool permission decisions            |
| `active_time.total`         | —        | active time                               |

`claude_code.token.usage` is emitted four times per request, once per `type` attribute: `input`,
`output`, `cacheRead`, `cacheCreation` (grep `type: "cacheRead"`). Note these differ from the JSONL
field names. `claude_code.cost.usage` is added alongside.

Per-source attribution attributes are attached to each data point (grep `mcp_server.name`):
`agent.name`, `skill.name`, `plugin.name`, `marketplace.name`, `mcp_server.name`, `mcp_tool.name`.
They are derived from a `query_source` string whose prefixes (`agent:builtin:`, `agent:custom:`,
`skill:`, …) name the originating component. This is what lets you split token and cost metrics by
subagent and by MCP tool — the breakdown `/usage` does not provide.

Trace spans add request-level attribution. The `claude_code.llm_request` span (grep that name)
carries `model`, `gen_ai.system`, `gen_ai.request.model`, `llm_request.context`
(`tool`/`interaction`/`standalone`), `query_source`, and crucially `agent_id` and `parent_agent_id`.
A `claude_code.subagent.spawn` span carries `agent_id`, `agent_type`, `parent_agent_id`. Other
spans: `claude_code.hook`, `claude_code.tool`, `claude_code.interaction`,
`claude_code.bash.subprocess`, `claude_code.mcp.rpc`, `claude_code.compaction`.

Resource attributes are gated by env vars (grep `OTEL_METRICS_INCLUDE_`): `user.id` always present;
`session.id` (`OTEL_METRICS_INCLUDE_SESSION_ID`), `app.version` (`OTEL_METRICS_INCLUDE_VERSION`),
`app.entrypoint` (`OTEL_METRICS_INCLUDE_ENTRYPOINT`), account UUID
(`OTEL_METRICS_INCLUDE_ACCOUNT_UUID`, also reads `CLAUDE_CODE_ACCOUNT_TAGGED_ID`), and
`OTEL_METRICS_INCLUDE_RESOURCE_ATTRIBUTES`. Standard OTLP env vars are honored
(`OTEL_EXPORTER_OTLP_*`, `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER`,
`OTEL_METRIC_EXPORT_INTERVAL`), plus a `CLAUDE_CODE_OTEL_SHUTDOWN_TIMEOUT_MS` flush timeout.

Honesty boundary: the metric names, the `type` attribute values, the per-source attribution
attribute names, and the span `agent_id`/`parent_agent_id` attributes are all verifiable in the
2.1.165 source. Default OTLP endpoints and export intervals beyond the env-var fallbacks, and the
server-side billing treatment of background traffic, are not source-determinable.

## Anthropic-internal analytics events

These `tengu_*` / event-pipeline emissions are not a public consumption API, but they show what the
client measures. The subagent completion path emits two:

- `tengu_agent_tool_completed`: `agent_type`, `model`, `prompt_char_count`, `response_char_count`,
  `assistant_message_count`, `total_tool_uses`, `duration_ms`, `total_tokens`, `is_built_in_agent`,
  `is_async`. The `total_tokens` here is the last-message snapshot described in Surface 2.
- `subagent_completed`: `agent_type` (or `"custom"`), optional `agent.source`, `is_built_in`,
  `is_async`, `total_tokens`, `total_tool_uses`, `duration_ms`, `model`, plus `plugin_id_hash` /
  `plugin.name` for plugin agents.

Other token/cost-bearing events: `tengu_advisor_tool_token_usage` reports per-auxiliary-model usage
with `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, and
`cost_usd_micros` — a genuine per-call token-plus-cost event. Cost-ceiling events
`tengu_cost_threshold_reached` and `tengu_cost_threshold_acknowledged` fire around spend limits.

## Choosing a surface

| Need                                              | Use                                                       |
|---------------------------------------------------|-----------------------------------------------------------|
| Quick per-subagent read, no setup                 | The `Done (…)` summary / tool-result `<usage>` trailer    |
| Exact per-subagent total, attributable, logged    | SubagentStop hook over `agent_transcript_path` (Surface 3)|
| Per-subagent / per-MCP-tool split across sessions | OpenTelemetry metrics with the per-source attributes      |
| Session totals, by model                          | `/usage` (`/cost`, `/stats`)                              |
| Live in-turn budget                               | statusLine `context_window`                               |

## Per-release appendix

- 2.1.165: verified. `/usage` carries aliases `cost`, `stats`. OTEL token metric splits on a `type`
  attribute (`input`/`output`/`cacheRead`/`cacheCreation`); per-source attribution attrs include
  `agent.name`, `skill.name`, `plugin.name`, `mcp_server.name`, `mcp_tool.name`; spans carry
  `agent_id`/`parent_agent_id`. SubagentStop input carries `agent_transcript_path`; subagent
  transcripts live under `<sessionId>/subagents/agent-<agentId>.jsonl`. The `subagent_tokens`
  trailer and `Done (…)` token figure are the last assistant message's four-term sum (a snapshot,
  not a cross-turn total).
