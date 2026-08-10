# Monitoring Token Usage and Cost

Behavioral model verified against 2.1.220, with the window-geometry, feature-flag, and monthly-spend
sections re-verified against 2.1.226. This document follows the landmark style in
`GUIDELINES.md`: it anchors on version-stable strings (slash-command names, `tengu_*` event names,
env var names, OTEL metric/attribute names, literal UI strings, JSONL field names, behavioral logic)
with grep re-location recipes, not on minified symbol names or line numbers, which churn every
release. Per-release changes are in the appendix.

This doc answers: how much usage is a given subagent or tool consuming, and where can that be read?
The short version is that there are six observation surfaces, each with a different granularity and
a different honesty caveat. Per-subagent attribution is possible; exact per-tool-call token cost is
not, because a tool call does not itself consume tokens — the assistant turns around it do.

A separate question this doc also answers: how much of a *plan's* rate limit has been consumed — the
5-hour session window and the 7-day weekly window that `/usage` renders. That number does not exist
anywhere in OpenTelemetry. Live utilization is exposed only to the statusLine command (Surface 1);
caps already hit are recoverable from the transcript (Surface 5). See "Plan rate limits are not in
telemetry" under Surface 4 for why the obvious place to look is empty, and "Org-level visibility is
not a product surface" for why there is no server-side alternative on most plans.

## What this doc owns vs. cross-references

This doc owns the observation/attribution story: the OpenTelemetry surface, the `/usage` command
family, the per-subagent `<usage>` trailers and their snapshot semantics, and the SubagentStop
attribution recipe. It cross-references the field-level references that already live elsewhere:

| Topic                                            | Lives in                        |
| ------------------------------------------------ | ------------------------------- |
| `message.usage` field reference (per-message)    | `SESSION_TRANSCRIPT.md`         |
| statusLine `context_window` input object         | `PROMPTS_RENDERED.md`           |
| `compactMetadata.preTokens`, microcompact tokens | `CLEAR_COMPACT_FORK_CONTEXT.md` |
| Session-memory background billing                | `SESSION_MEMORY_AND_SUMMARY.md` |
| Subagent output pipeline, the `Done (…)` summary | `TASK_TOOL_AND_SUBAGENTS.md`    |
| SubagentStop hook input schema                   | `HOOKS.md`                      |

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

The same input also carries a `cost` object (`total_cost_usd`, `total_duration_ms`,
`total_api_duration_ms`, `total_lines_added`, `total_lines_removed`) and, for claude.ai
subscribers, a `rate_limits` object — the only programmatic exposure of plan-limit utilization
in the product:

```jsonc
"rate_limits": {          // Optional. Only present for subscribers after the first API response.
  "five_hour": { "used_percentage": number,   // 0-100
                 "resets_at": number },       // Unix epoch seconds
  "seven_day": { "used_percentage": number,
                 "resets_at": number }
}
```

Re-locate the documented shape by grepping the statusLine setup prompt for
`Claude.ai subscription usage limits`; re-locate the builder by grepping for a spread guarded on
`five_hour ||` alongside `seven_day`. Both sub-objects are individually optional. Underlying
source: the `anthropic-ratelimit-unified-5h-*` / `-7d-*` response headers (grep
`anthropic-ratelimit-unified-`), parsed per API response, so the value is as fresh as the last
request.

Two properties matter when choosing between this and the `/usage` probe below, and they pull in
opposite directions.

Precision: the builder computes `used_percentage` as `utilization * 100` with no rounding, whereas
the display paths floor — grep for a `Math.floor(utilization * 100)` on the rendering side, and the
`/usage` text output floors the same way. So statusLine preserves whatever precision the header
carries while the rendered figures do not, which matters to anything differencing two samples,
since integer percent quantises a small delta into uselessness.

How much that is worth in practice is unconfirmed. Observed values from the usage endpoint are
whole numbers (`16`, `21`, `23`), so if the `anthropic-ratelimit-unified-*` headers are likewise
integral then the unrounded arithmetic preserves nothing extra and the advantage is theoretical.
Treat statusLine as no worse than the alternatives on precision, and verify against real header
values before relying on sub-point resolution.

Coverage: the statusLine payload carries only `five_hour` and `seven_day`. The model-scoped weekly
buckets that `/usage` displays (`Current week (Sonnet only)`, and the per-model rows built from the
server `limits[]` array via `model_scoped[]`) are absent from it entirely. On a plan where a
model-scoped weekly is the binding constraint rather than the all-models weekly, statusLine cannot
see the window that actually matters. Sample with statusLine for resolution; read `/usage` for
completeness.

Because the statusLine command is an arbitrary shell command receiving this JSON on stdin, it is
the practical hook for exporting plan-limit utilization to an external system: read stdin, emit the
numbers somewhere, print the status line. The input also carries `prompt_id`, documented as "same
as OTel prompt.id" — the join key between a statusLine sample and the OTel event stream.

Invocation cadence matters when treating it as a sampler. The command is not run per render. It is
run on a 300 ms debounce, triggered when the message id changes or when one of a fixed dependency
set changes — token usage, permission mode, vim mode, main-loop model, fast mode, effort, thinking,
PR status. `rate_limits` is not itself in that set, but token usage changes on every API response,
which is also when the rate-limit headers refresh, so samples track responses closely. The
`statusLine.refreshInterval` setting (seconds, minimum 1, described as "Re-run the status line
command every N seconds in addition to event-driven updates") adds time-based polling and is the
lever for a steady sampling rate. A previous still-running invocation is aborted when a new one
starts, so a slow exporter drops samples rather than queueing them.

### `/usage` in print mode is a free, out-of-session quota probe

The most useful property of the non-interactive form is that it costs nothing and needs no running
session:

```
claude -p "/usage" --output-format json
```

The JSON envelope reports `total_cost_usd: 0`, `num_turns: 0`, `duration_api_ms: 0`, and an
all-zero `usage` object, with the human-readable report in `result` — measured at well under a
second end to end. The command is a `local` slash command whose plan figures come from a server
fetch, not from the model, so nothing is billed. This is the only way to read plan utilization
without a live session, which makes it the right source for scheduled polling; the statusLine
(above) only samples while Claude Code is actually running, and therefore goes quiet exactly when
someone has stopped working and their quota is going unused.

Three caveats. The rate-limit figures arrive as prose inside `result` (`Current session: 12% used ·
resets Aug 9 at 10pm (America/Vancouver)`), not as structured fields, so a consumer must parse
them — and the reset string omits the year. The zero-cost property is a current fact, not a
guarantee; a probe running on a schedule should assert on `total_cost_usd` / `num_turns` and warn
rather than assume it stays free.

The third caveat is the one that will actually bite a scheduled job. When the OAuth credential
lookup fails, `/usage` does not error — it silently degrades to its API-key output form, the
`Total cost: / Usage by model:` block with no plan-limit lines at all. On macOS, where credentials
live in the Keychain rather than a `.credentials.json`, that lookup requires `USER` to be set in
the environment. Bisected on 2.1.226: with `HOME` and a correct `PATH` but no `USER`, the probe
exits 0 and reports no plan limits; adding `USER` alone restores them, and `LOGNAME` does not
substitute. Since launchd and cron both supply a stripped environment, a naive scheduled probe
reports "no limits" forever and looks like an account without a subscription. Any consumer should
treat zero parsed windows as a configuration failure to investigate rather than as an absence of
limits.

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

Metric instruments — all eight are registered in one function; grep `claude_code.session.count` and
read the adjacent registrations. Every name carries the `claude_code.` prefix:

| Instrument                            | Unit     | Registered description                       |
|---------------------------------------|----------|----------------------------------------------|
| `claude_code.token.usage`             | tokens   | "Number of tokens used"                      |
| `claude_code.cost.usage`              | USD      | "Cost of the Claude Code session"            |
| `claude_code.session.count`           | —        | "Count of CLI sessions started"              |
| `claude_code.lines_of_code.count`     | —        | lines modified, `type` = added/removed       |
| `claude_code.commit.count`            | —        | "Number of git commits created"              |
| `claude_code.pull_request.count`      | —        | "Number of pull requests created"            |
| `claude_code.code_edit_tool.decision` | —        | accept/reject for Edit, Write, NotebookEdit  |
| `claude_code.active_time.total`       | s        | "Total active time in seconds"               |

The registration helper takes an `omitUnits` flag that suppresses the `unit` field, so the `USD`,
`tokens`, and `s` units are not guaranteed to reach every exporter.

`claude_code.token.usage` is emitted four times per request, once per `type` attribute: `input`,
`output`, `cacheRead`, `cacheCreation` (grep `type: "cacheRead"`). Note these differ from the JSONL
field names. `claude_code.cost.usage` is added alongside.

There is no gauge or counter for plan-limit utilization, quota, or seat consumption. The eight
above are the complete set.

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

### Log events

Events are emitted through one helper that stamps `event.name`, `event.timestamp`, an incrementing
`event.sequence`, and (when a prompt is in flight) `prompt.id`, then emits a log record whose body
is the literal `` `claude_code.${name}` ``. Because the body is interpolated, the full event name
never appears in the bundle — searching for `claude_code.user_prompt` returns nothing. Grep instead
for the body template `` body: `claude_code. `` to find the helper, then enumerate its call sites;
several are formatted across lines, so an `rg -U` multiline match is required to catch them all.

The complete 2.1.220 set, 25 names (prefix each with `claude_code.`):

- Prompt and API: `user_prompt`, `assistant_response`, `system_prompt`, `api_request`, `api_error`,
  `api_refusal`, `api_retries_exhausted`, `api_request_body`, `api_response_body`
- Tools: `tool`, `tool_result`, `tool_decision`
- Extensions: `skill_activated`, `subagent_completed`, `plugin_installed`, `plugin_loaded`,
  `mcp_server_connection`, `hook_registered`, `hook_execution_start`, `hook_execution_complete`,
  `hook_plugin_metrics`
- Session: `auth`, `permission_mode_changed`, `compaction`, `at_mention`, `feedback_survey`,
  `internal_error`

`api_request` attributes (grep the helper call with `cost_usd_micros`): `model`, `input_tokens`,
`output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd`, `cost_usd_micros`,
`duration_ms`, `request_id`, `client_request_id`, `speed` (`fast`/`normal`), `query_source`, and
optional `effort`. This is the per-request billing record and the highest-fidelity usage event.

`api_error` attributes: `model`, `error`, `status_code`, `duration_ms`, `attempt`, `request_id`,
`client_request_id`, `speed`, optional `query_source` / `effort`. When more than one attempt was
made, `api_retries_exhausted` follows with `total_attempts` and `total_retry_duration_ms`.

### Identity attributes

Attached to every metric data point and every event by the same attribute builder (grep
`"user.account_uuid"` and read the enclosing function):

| Attribute           | Gate                                                                               |
| ------------------- | ---------------------------------------------------------------------------------- |
| `user.id`           | always                                                                             |
| `organization.id`   | always, when an OAuth profile is present                                           |
| `user.email`        | always, when an OAuth profile is present                                           |
| `terminal.type`     | always, when the terminal is detected                                              |
| `session.id`        | `OTEL_METRICS_INCLUDE_SESSION_ID`                                                  |
| `ccr.session.id`    | with `session.id`, when `CLAUDE_CODE_REMOTE_SESSION_ID` is set                     |
| `app.version`       | `OTEL_METRICS_INCLUDE_VERSION`                                                     |
| `app.entrypoint`    | `OTEL_METRICS_INCLUDE_ENTRYPOINT`                                                  |
| `user.account_uuid` | `OTEL_METRICS_INCLUDE_ACCOUNT_UUID`                                                |
| `user.account_id`   | with `user.account_uuid`; `CLAUDE_CODE_ACCOUNT_TAGGED_ID` overrides                |
| custom attrs        | `OTEL_METRICS_INCLUDE_RESOURCE_ATTRIBUTES`, parsed from `OTEL_RESOURCE_ATTRIBUTES` |

`organization.id` and `user.email` are ungated by any `OTEL_METRICS_INCLUDE_*` flag — an OAuth
session always labels its telemetry with the operator's email address. That is what makes per-person
fleet attribution work without extra configuration, and it is also the privacy fact to disclose
before turning telemetry on for a team. Operator-supplied `OTEL_RESOURCE_ATTRIBUTES` keys beginning
`user.` or `identity.` are dropped when the profile already supplies identity attributes, so a
custom `user.*` label cannot shadow the real one.

### Configuration env vars

Standard OTLP env vars are honored (`OTEL_EXPORTER_OTLP_ENDPOINT` / `_HEADERS` / `_PROTOCOL` and
their per-signal `_METRICS_` / `_LOGS_` / `_TRACES_` variants, `OTEL_METRICS_EXPORTER`,
`OTEL_LOGS_EXPORTER`, `OTEL_TRACES_EXPORTER`, `OTEL_METRIC_EXPORT_INTERVAL`,
`OTEL_LOGS_EXPORT_INTERVAL`, `OTEL_TRACES_EXPORT_INTERVAL`, mTLS via
`OTEL_EXPORTER_OTLP_CLIENT_KEY` / `_CLIENT_CERTIFICATE` / `_CERTIFICATE`, and a Prometheus exporter
via `OTEL_EXPORTER_PROMETHEUS_HOST` / `_PORT`).

Claude Code adds its own (grep each name):

| Env var                                       | Effect                                                        |
| --------------------------------------------- | ------------------------------------------------------------- |
| `CLAUDE_CODE_ENABLE_TELEMETRY`                | master switch                                                 |
| `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`         | detailed tracing; also reads `ENABLE_ENHANCED_TELEMETRY_BETA` |
| `CLAUDE_CODE_PROPAGATE_TRACEPARENT`           | force W3C traceparent propagation                             |
| `CLAUDE_CODE_OTEL_SHUTDOWN_TIMEOUT_MS`        | shutdown flush timeout                                        |
| `CLAUDE_CODE_OTEL_FLUSH_TIMEOUT_MS`           | flush timeout                                                 |
| `CLAUDE_CODE_OTEL_CONTENT_MAX_LENGTH`         | truncation limit for logged content                           |
| `CLAUDE_CODE_OTEL_DIAG_STDERR`                | SDK diagnostics to stderr                                     |
| `CLAUDE_CODE_OTEL_HEADERS_HELPER_DEBOUNCE_MS` | refresh interval for the `otelHeadersHelper`                  |
| `CLAUDE_CODE_ENABLE_FEEDBACK_SURVEY_FOR_OTEL` | enables the `feedback_survey` event                           |
| `CLAUDE_CODE_ACCOUNT_TAGGED_ID`               | overrides the derived `user.account_id`                       |

Content capture is opt-in per class: `OTEL_LOG_USER_PROMPTS`, `OTEL_LOG_ASSISTANT_RESPONSES`,
`OTEL_LOG_TOOL_DETAILS`, `OTEL_LOG_TOOL_CONTENT`, `OTEL_LOG_RAW_API_BODIES`. With them unset the
corresponding fields carry the literal `<REDACTED>` (grep `"<REDACTED>"` near the
`assistant_response` emission).

`otelHeadersHelper` is a settings key, not an env var, and appears in the list of settings whose
values are command strings (grep `otelHeadersHelper` adjacent to `statusLine` and
`subagentStatusLine`) — the same list that managed policy can pin.

### Plan rate limits are not in telemetry

No metric, no event, and no span attribute carries 5-hour or weekly limit utilization, quota state,
or seat consumption. Verified three ways against 2.1.220: the eight metric registrations contain no
limit instrument; the 25 event names contain no limit event; and the `api_request` event's attribute
list carries tokens, cost, and duration but nothing derived from the
`anthropic-ratelimit-unified-*` response headers that populate `/usage`.

The available substitutes, in descending fidelity:

1. The statusLine `rate_limits` object (Surface 1). Real utilization percentages and reset
   timestamps, sampled per API response, per machine. Requires shipping a statusLine command.
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
`extra_usage`, plus a `behaviors` breakdown attributing local usage to `cache_miss`,
`long_context`, `subagent_heavy`, `high_parallel`, `cron` and to individual agents, skills,
plugins, and MCP servers. Grep `rate_limits_available` for the schema, whose own describe string
marks it "Experimental — the shape may change". This payload is not written to any file and is not
exported over OTLP; it is built for the dialog and the command's own output.

Honesty boundary: the metric names, the event names and their attributes, the identity attribute
gates, the statusLine `rate_limits` shape, and the absence of any limit-bearing telemetry are all
verifiable in the 2.1.220 source. Default OTLP endpoints and export intervals beyond the env-var
fallbacks, the server-side definition of limit utilization, and the server-side billing treatment
of background traffic are not source-determinable.

## Surface 6: the cached utilization blob in the config

The richest and most convenient plan-usage source is not a command output at all: it is a cache
written to the top-level config JSON (`~/.claude.json`, or `$CLAUDE_CONFIG_DIR`). Grep the config
for `cachedUsageUtilization`. It holds the claude.ai usage endpoint's response verbatim, alongside
`fetchedAtMs` and — the field that makes the rest usable — `accountUuid`.

Its `utilization` object carries `five_hour` and `seven_day` (each with `utilization`,
`resets_at`, and null-by-default `limit_dollars` / `used_dollars` / `remaining_dollars`),
`extra_usage` (with `currency`, `monthly_limit`, `used_credits`, `spend_limit_reached`,
`credits_ever_enabled`, `daily`, `weekly`), a `spend` object, and a long tail of
mostly-null named buckets — `seven_day_oauth_apps`, `seven_day_opus`, `seven_day_sonnet`,
`seven_day_cowork`, `seven_day_omelette`, `omelette_promotional`, `tangelo`, `iguana_necktie`,
`nimbus_quill`, `cinder_cove`, `amber_ladder`. The codenames are server-side buckets in the same
naming family as the GrowthBook flags; treat the set as unstable and read it dynamically.

The most useful member is `limits[]`, a normalised array that supersedes reading the individual
buckets. Each entry has `kind` (`session`, `weekly_all`, `weekly_scoped`), `group`, `percent`,
`severity`, `resets_at`, `is_active`, and for a scoped entry a `scope.model.display_name`. That is
the model-scoped weekly the statusLine object cannot express, in structured form.

Three practical advantages over the `/usage` text: reset times are ISO 8601 rather than a
year-less local string; every bucket is present rather than only those the dialog renders; and
`accountUuid` identifies whose figures these are.

Watch the units. This blob comes from the usage endpoint and its `utilization` / `percent` values
are already on a 0-100 scale, whereas the `anthropic-ratelimit-unified-*` response headers that
feed the statusLine object are 0-1 fractions scaled by 100 at the boundary. Two sources, two
scales, same nominal field name.

Refresh semantics: running the `/usage` probe updates `fetchedAtMs` and the payload, so
"probe, then read the config" is a reliable way to obtain fresh structured figures without parsing
any prose. Check `fetchedAtMs` rather than assuming — a failed refresh leaves the previous values
in place with no error.

### Account switching invalidates a naive series

`cachedUsageUtilization` is a single slot, not a per-account map. Authenticating as a different
account overwrites it, and `accountUuid` is the only marker of which plan the numbers describe.
Two consequences for anything that samples over time.

A sampled series must be partitioned by account before it means anything. Different accounts have
different allowances, so a utilization delta spanning a switch is not a consumption measurement,
and a ratio derived from such a pair is meaningless. Worse for reset detection: a switch produces
exactly the signature described above — utilization falling — so an unattributed series reports
every account switch as a mid-window grant.

The statusLine payload does not identify the account at all, so a statusLine-based sampler has to
read `oauthAccount.accountUuid` from the config itself to label its own samples. That object also
carries `emailAddress`, `organizationName`, `organizationUuid`, `seatTier`,
`organizationRateLimitTier`, `userRateLimitTier`, `billingType` and `hasExtraUsageEnabled` —
`seatTier` being the field that distinguishes one plan from another in a multi-account setup.

The hard limit: only the currently-authenticated account is observable. There is no cached copy of
any other account's utilization, so quota on an account you are signed out of cannot be read at
all — which is precisely the account most likely to be accruing unused quota.

## Window geometry and pacing

Everything needed to reason about *pace* — not just current utilization — is derivable client-side,
because the window lengths are compiled-in constants while only the utilization fraction comes from
the server. Grep `claimAbbrev: "5h"` for the table:

| Window      | `claimAbbrev` | `windowSeconds` | Warn thresholds (`utilization`, `timePct`) |
| ----------- | ------------- | --------------- | ------------------------------------------ |
| `five_hour` | `5h`          | 18000           | (0.90, 0.72)                               |
| `seven_day` | `7d`          | 604800          | (0.75, 0.60), (0.50, 0.35), (0.25, 0.15)   |

Byte-identical in 2.1.220 and 2.1.226, so treat the two window lengths as stable constants.

`timePct` is the fraction of the window elapsed, computed from the reset timestamp alone (grep the
small helper that computes `resets_at - windowSeconds` and clamps the result to 0..1):

```
elapsed = clamp((now - (resets_at - windowSeconds)) / windowSeconds, 0, 1)
```

The client fires its warning when `utilization >= threshold.utilization && elapsed <=
threshold.timePct` — that is, "you are this far ahead of pace this early". Reading the weekly row:
25% consumed in the first 15% of the week is already flagged. Two consequences worth recording.
First, any consumer of the statusLine `rate_limits` object can compute the same `elapsed` and
therefore a pace ratio `utilization / elapsed`, where 1.0 is exactly on pace — the client publishes
no such ratio itself, but the inputs are all present. Second, inverting the comparison
(`utilization <= X && elapsed >= Y`) detects the opposite condition, quota going *unused*, which
nothing in the product surfaces.

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
`anthropic-ratelimit-unified-grace-status` for the gate, alongside two companion headers,
`-grace-5h-utilization` and `-grace-7d-utilization`, each parsed as a 0..1 fraction. When either is
above zero the client sets an internal `rateLimitGraceActive` flag and shows a wrap-up prompt (grep
`grace window active`, whose text asks the user to finish or wind down rather than start new work).

Two things follow. Grace is a distinct pool with its own utilization, not a rollback of the main
window's counter — so a session can continue past an apparent 100%. And none of it is exposed:
`rateLimitGraceActive` reaches no statusLine field, no `/usage` line, and no telemetry, so a
consumer sees only its side effects.

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
indistinguishable from utilization alone — raising the denominator lowers the ratio just as
zeroing the numerator does — but either means allowance appeared that was not there before. The
detection needs only a monotonicity check over a sampled series.

Two limits worth stating. The change is invisible if utilization was at zero when it happened,
since there is nothing to drop from; a small nonzero reading suffices, but nothing at all does not.
And the sampled series must be dense enough that the drop is not masked by consumption in the same
interval — the scheduled `/usage` probe keeps sampling while idle and covers the model-scoped
buckets, whereas the statusLine sampler stops when work stops.

A second-order signal exists for capacity changes specifically: the 5-hour-to-weekly ratio derived
above shifts if one window's capacity is changed and the other's is not. Comparing that ratio
across weeks detects a rescaling that a utilization drop alone could not attribute.

### The monthly figure is a spend cap, not an allowance

Easy to misread as a third quota window, and the difference inverts any use-it-or-lose-it
reasoning. The monthly number is `extra_usage` — grep it in the `/usage` payload schema — with
fields `is_enabled`, `monthly_limit`, `used_credits`, `utilization`, and `currency`. The presence of
`currency` is the tell: this is money, the usage-credit overage budget, matched by UI strings like
"You're out of usage credits", `/usage-credits`, and "You've hit your monthly spend limit". The
server side is `anthropic-ratelimit-unified-overage-period-monthly-utilization`, surfaced as
`overagePeriodMonthly`.

So unspent monthly credit is money not spent, not allowance forfeited. Only the 5-hour and 7-day
windows are seat allowance already paid for under a subscription, and only those two are wasted by
going unused.

## Surface 5: cap hits recorded in the transcript

Every API error is persisted as an `assistant` record in the session JSONL with
`isApiErrorMessage: true`, and a rate-limit rejection carries `error: "rate_limit"` plus
`apiErrorStatus: 429`, a `requestId`, and the usual `sessionId` / `timestamp` / `cwd` /
`gitBranch` / `version` context. Field reference: `SESSION_TRANSCRIPT.md`. This makes the local
transcript corpus a complete, zero-configuration, retroactive history of every time a cap was hit —
available without OTel, without a statusLine, and for sessions that already happened.

The message text is the discriminator, and getting it wrong is the trap. `apiErrorStatus: 429` with
`error: "rate_limit"` covers two unrelated conditions:

| Message text                                                     | Meaning                         |
| ---------------------------------------------------------------- | ------------------------------- |
| `You've hit your session limit · resets …`                       | 5-hour window exhausted         |
| `You've hit your weekly limit · resets …`                        | 7-day window exhausted          |
| `You've hit your Opus limit` / `Sonnet limit` / `Fable 5 limit`  | model-scoped weekly window      |
| `You've hit your usage credit limit`                             | overage credits exhausted       |
| `Server is temporarily limiting requests (not your usage limit)` | server-side throttle, NOT a cap |

Counting raw 429s therefore overstates cap hits, and by a wide margin — in one real corpus the
server-throttle variant was about a third of all `error: "rate_limit"` records. The product itself
draws the same distinction: the overload string is a standalone constant (grep
`not your usage limit`), while the cap messages are built by a formatter (grep the template
`You've hit your ` returning an interpolation of a label plus a resets suffix) whose label map is
the `rateLimitType` → display-name table (grep `five_hour: "session limit"` and read the adjacent
`seven_day` / `seven_day_opus` / `seven_day_sonnet` / `seven_day_overage_included` / `overage`
entries). The lookup falls back to the raw type string when the label is unknown, so a parser must
tolerate unmapped labels rather than assume the five above.

Version drift is real here: the label wording has changed across releases, and older records carry
a bare `You've hit your limit` with no window named. Match on the presence of the negation
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

No hook fires on an API error — the 31 hook events (see `HOOKS.md`) contain no error-lifecycle
event. To act on cap hits without OTel, scan the transcript from a `Stop` or `SessionEnd` hook:
`transcript_path` is a base field present on every hook event, not a per-event extra.

## Fleet plan-limit tracking

For the "how close is each team member to their cap" question, the source supports exactly one
first-party path, and it is not OpenTelemetry.

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

Three properties to design around. `rate_limits` is absent until the first API response of a
session and absent entirely for API-key, Bedrock, and Vertex sessions, so a missing sample is not a
zero — the `/usage` payload's `rate_limits_available` flag names those cases explicitly ("False
when plan rate limits do not apply (API key, Bedrock, Vertex, or missing profile scope)"). The
command fires on a 300 ms debounce off token-usage changes, so an idle session stops emitting;
use `statusLine.refreshInterval` if the dashboard needs a heartbeat. And the numbers are per
machine: a seat used from two machines produces two independent sample streams for one server-side
limit, so deduplicate on identity and take the maximum rather than summing.

Distribution follows the normal settings precedence — `statusLine` is a policy-pinnable setting, so
managed settings can install it centrally (grep for the `policySettings` lookup of `statusLine`
guarded by the customization-lock predicate).

A plugin cannot do this job. Plugins are not a settings source: the resolution order is the array
`userSettings`, `projectSettings`, `localSettings`, `flagSettings`, `policySettings` (grep that
literal array), with no plugin tier. And the plugin manifest's contribution surface is a fixed list
— `commands`, `agents`, `skills`, `hooks`, `mcpServers`, `lspServers` (grep those keys as a schema
object) — which contains no `env` block, no `statusLine`, and no settings of any kind. The one
plugin-scoped configuration mechanism is `user_config`, described as "User-configurable values this
plugin needs. Prompted at enable time… Available as `${user_config.KEY}` in MCP/LSP server config,
hook commands, and (non-sensitive only) skill/agent content" — interpolation into a plugin's own
components, not into the process environment. So enabling OpenTelemetry, or installing a statusLine,
has to come from a settings file (`env` block) or the real process environment; a plugin can ship
the collector-side hook scripts but cannot switch telemetry on.

A plugin does remain useful for the parts that *are* hooks. `strictPluginOnlyCustomization`, the
managed lockdown that blocks user and project customization, explicitly exempts plugin-provided
customizations — its describe string reads "NOT blocked: managed (policySettings) sources,
plugin-provided customizations". So a company plugin can carry the collector-side hook scripts and
survive the strictest admin lockdown; it simply cannot be what turns telemetry on.

Hook delivery has one non-obvious semantic worth knowing before splitting hooks across sources.
Hooks do not merge the way other settings do: the resolver returns *either* the managed set or the
user-visible set, never their union. Grep the resolver by its `disableAllHooks` early return and
read the branch order — `policySettings.disableAllHooks` yields none; `allowManagedHooksOnly` (its
describe string: "When true (and set in managed settings), only hooks from managed settings run.
User, project, and local hooks are ignored") or a hooks lockdown yields the managed set alone;
otherwise the merged user/project/local set is returned. Plan for one side of that switch, not both.

Two hook types make this pipeline shorter than it first appears. An `http` hook takes a `url`
described as "URL to POST the hook input JSON to" plus `headers` whose values may interpolate
environment variables listed in the hook's own `allowedEnvVars` — so a hook can ship JSON to a
collector with an auth header and no local script at all. Managed settings can fence this with
`allowedHttpHookUrls` (wildcard URL allowlist; empty array blocks all HTTP hooks) and
`httpHookAllowedEnvVars` (intersected with each hook's own list). The caveat for this use case is
that the POSTed body is the hook input, which carries `transcript_path` but not the transcript, so
cap-hit extraction still needs a local `command` hook to read and summarize the file first.

Hooks do not help with utilization, though: no hook input carries `rate_limits`. Grep `rate_limits`
across the bundle and every hit is the statusLine setup prompt, the statusLine input builder, or
the `/usage` payload schemas.

## The `tengu_*` namespace is two things

Worth stating plainly because it is easy to mistake one for the other: `tengu_*` is a shared
namespace covering both analytics event names and GrowthBook feature-flag keys. Around 1,700
distinct names appear in the bundle; roughly 260 of them are flag lookups.

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
| Plan limit utilization, per person                | statusLine `rate_limits` (nothing in OTel carries it)     |
| All buckets, structured, account-tagged           | `cachedUsageUtilization` in the config (Surface 6)        |
| History of caps already hit, no setup             | Transcript `error: "rate_limit"` records (Surface 5)      |
| Detecting a cap live                              | OTel `claude_code.api_error`, but discriminate the text   |

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

## Per-release appendix

- 2.1.226: partial re-verification, covering the sections this release was consulted for. The
  window-geometry table (`five_hour`/18000 with one threshold pair, `seven_day`/604800 with three)
  is byte-identical to 2.1.220, as is the elapsed-fraction helper — treat both window lengths as
  stable constants. Newly documented from this release: the `tengu_*` namespace carries both
  analytics event names and GrowthBook feature-flag keys (~1,700 names, ~260 of them flag lookups),
  distinguished by whether a client-side default follows the name, with remote evaluation meaning
  gated behavior can differ between users on one version; `extra_usage` (with its `currency` field)
  is an overage spend cap rather than a plan allowance; and `claude -p "/usage"
  --output-format json` is a zero-cost, out-of-session quota probe. Not re-checked against this
  release: the metric/event inventories, identity attributes, and transcript cap-hit records, which
  remain stamped at 2.1.220.
- 2.1.220: verified, with the OpenTelemetry surface re-derived rather than spot-checked. Confirmed
  unchanged from 2.1.165: the eight metric instruments, the `input`/`output`/`cacheRead`/
  `cacheCreation` token `type` split, the per-source attribution attributes, and the span set with
  `agent_id`/`parent_agent_id`. Newly documented here: the complete 25-name log-event set (the
  event body is interpolated as `` `claude_code.${name}` ``, so full names are ungreppable and an
  `rg -U` multiline scan of the emitter's call sites is required); `api_request` / `api_error`
  attribute lists; the identity attribute table, in which `organization.id` and `user.email` are
  ungated by any `OTEL_METRICS_INCLUDE_*` flag; the `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`,
  `CLAUDE_CODE_OTEL_*`, and `OTEL_LOG_*` env var families; the statusLine `rate_limits` object
  (`five_hour` / `seven_day`, each `used_percentage` + `resets_at`), sourced from
  `anthropic-ratelimit-unified-*` response headers; and the statusLine invocation cadence (300 ms
  debounce over a fixed dependency set, plus optional `statusLine.refreshInterval` polling).
  Established as a negative result: no metric,
  event, or span attribute carries plan-limit utilization, and plugins cannot contribute `env` or
  `statusLine` settings. Also added: Surface 5, cap hits persisted to the transcript as
  `error: "rate_limit"` / `apiErrorStatus: 429` records, with the discrimination table separating
  real cap hits from the `not your usage limit` server throttle (the label map anchored on
  `five_hour: "session limit"`); hook-resolution semantics (managed and user hook sets replace
  rather than merge, gated by `allowManagedHooksOnly`); the `http` hook type as a
  no-local-script export path, fenced by `allowedHttpHookUrls` and `httpHookAllowedEnvVars`; and
  `strictPluginOnlyCustomization` exempting plugin-provided customizations from admin lockdown.
  Version-specific: the `/usage` structured payload
  (`rate_limits_available`, `model_scoped[]`, `extra_usage`, `behaviors`) is marked experimental in
  its own schema and should be re-checked each release. Cap-message wording has changed across
  releases (older records carry a bare `You've hit your limit`), so text-matching parsers need to
  stay version-tolerant.
- 2.1.165: verified. `/usage` carries aliases `cost`, `stats`. OTEL token metric splits on a `type`
  attribute (`input`/`output`/`cacheRead`/`cacheCreation`); per-source attribution attrs include
  `agent.name`, `skill.name`, `plugin.name`, `mcp_server.name`, `mcp_tool.name`; spans carry
  `agent_id`/`parent_agent_id`. SubagentStop input carries `agent_transcript_path`; subagent
  transcripts live under `<sessionId>/subagents/agent-<agentId>.jsonl`. The `subagent_tokens`
  trailer and `Done (…)` token figure are the last assistant message's four-term sum (a snapshot,
  not a cross-turn total).
