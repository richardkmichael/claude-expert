# How Claude Code Computes the Session Cost Figure

    Verified against: cli.prettier.js 2.1.295 (2026-10-08)

This doc covers how Claude Code arrives at `total_cost_usd`: the statusLine `cost.total_cost_usd`,
the `Total cost:` line of `/cost` (`/usage` in print mode), the SDK result's `total_cost_usd` and
`modelUsage[].costUSD`, `--max-budget-usd`, and the `claude_code.cost.usage` OTel metric. All of
these read one per-session accumulator. Where each figure is surfaced is in `MONITORING_USAGE.md`.
This doc follows the landmark style in `GUIDELINES.md`.

The figure is a client-side estimate. Claude Code multiplies the `usage` block of each API response
by a per-model USD-per-million-token rate card and adds the result to the session total. Nothing
reads a cost back from the API.

## Where the rates come from

Four sources, consulted in a fixed order per model (see "Lookup order" below).

### 1. The baked-in model catalog

The release embeds a hand-maintained model catalog. Grep `Hand-maintained baked-in model catalog`;
the object carries `schema_version`, a `pricing_tiers` map and a `models` array. Each model entry
names its tier by key in a `pricing` field. Every tier has the full rate-card shape (`input`,
`output`, `cache_write_5m`, `cache_write_1h`, `cache_read`, `web_search`); a catalog entry with an
incomplete card throws `has incomplete pricing`. A tier may also carry a `long_prompt` block: an
`above_prompt_tokens` threshold and a second set of rates (`input`, `output`, `cache_write_5m`,
`cache_write_1h`, `cache_read`; web search is inherited). See "The per-response formula".

Tiers in 2.1.295, in USD per million tokens. The columns are `input`, `output`, `cache_write_5m`,
`cache_write_1h`, `cache_read`, and `web_search` (USD per request):

| Tier                         | in  | out | write 5m | write 1h | read | search |
|------------------------------|-----|-----|----------|----------|------|--------|
| `haiku_35`                   | 0.8 | 4   | 1        | 1.6      | 0.08 | 0.01   |
| `haiku_45`                   | 1   | 5   | 1.25     | 2        | 0.1  | 0.01   |
| `haiku_55`                   | 0.1 | 0.5 | 0.125    | 0.2      | 0.01 | 0.01   |
| `haiku_55` over 100k prompt  | 0.5 | 2.5 | 0.625    | 1        | 0.05 | 0.01   |
| `tier_2_10`                  | 2   | 10  | 2.5      | 4        | 0.2  | 0.01   |
| `tier_3_15`                  | 3   | 15  | 3.75     | 6        | 0.3  | 0.01   |
| `tier_4_20_cache_read_0_20`  | 4   | 20  | 5        | 8        | 0.2  | 0.01   |
| `tier_5_25`                  | 5   | 25  | 6.25     | 10       | 0.5  | 0.01   |
| `tier_10_50`                 | 10  | 50  | 12.5     | 20       | 1    | 0.01   |
| `tier_10_50_cache_read_0_25` | 10  | 50  | 12.5     | 20       | 0.25 | 0.01   |
| `tier_15_75`                 | 15  | 75  | 18.75    | 30       | 1.5  | 0.01   |

Model-to-tier mapping in 2.1.295:

| Catalog id                                | Tier                         |
|-------------------------------------------|------------------------------|
| `claude-3-5-haiku`                        | `haiku_35`                   |
| `claude-haiku-4-5`                        | `haiku_45`                   |
| `claude-haiku-5-5`                        | `haiku_55`                   |
| `claude-3-5-sonnet`, `claude-3-7-sonnet`  | `tier_3_15`                  |
| `claude-sonnet-4-0`, `-4-5`, `-4-6`       | `tier_3_15`                  |
| `claude-sonnet-5`, `claude-sonnet-5-5`    | `tier_2_10`                  |
| `claude-opus-4-0`, `claude-opus-4-1`      | `tier_15_75`                 |
| `claude-opus-4-5`, `-4-6`, `-4-7`, `-4-8` | `tier_5_25`                  |
| `claude-opus-5`                           | `tier_5_25`                  |
| `claude-opus-5-5`                         | `tier_4_20_cache_read_0_20`  |
| `claude-fable-5`, `claude-mythos-5`       | `tier_10_50`                 |
| `claude-fable-5-1`, `claude-mythos-5-1`   | `tier_10_50_cache_read_0_25` |

Re-derive both tables each release: print the `pricing_tiers` object, then list each `id:` with its
`pricing:` line from the `models` array. Catalog ids are canonical. A provider-specific id (Bedrock
`us.anthropic.…`, Vertex `…@date`, dated first-party ids) is normalized to the catalog id before
lookup, so every provider form of a model gets the same card.

Separate fast-mode rate cards sit next to the catalog-derived table. Grep the object literal with
`promptCacheWrite1hTokens: 60`. Fast mode applies only on first-party
(`CLAUDE_CODE_DISABLE_FAST_MODE` unset) and only to a response whose `usage.speed` is `"fast"`.
In 2.1.295 the fast cards are: Opus 5.5 at $8/$40 (cache read $0.4), Opus 4.8 and Opus 5 at
$10/$50, and Opus 4.6 and 4.7 at $30/$150. Each fast card keeps the 1.25× and 2× cache-write and
the 0.1× cache-read ratios to its input rate (Opus 5.5 is an exception at 0.05×).

There is no general long-context multiplier. Only a tier with a `long_prompt` block switches
rates by prompt size; in 2.1.295 that is `haiku_55` alone. Every other model prices a 1M-context
request at the same per-token rates as a short one. The `/model` price label shows the second rate
set, for example `$0.10/$0.50 per Mtok ($0.50/$2.50 for prompts over 100K)` (grep
`for prompts over`).

### 2. `additional_model_costs` from the bootstrap endpoint (network)

On startup, Claude Code calls `GET /api/claude_cli/bootstrap` (grep `api/claude_cli/bootstrap`).
The response schema includes `additional_model_costs`, a map of model id to
`input_tokens` / `output_tokens` / `prompt_cache_write_tokens` / `prompt_cache_write_1h_tokens` /
`prompt_cache_read_tokens` / `web_search_requests` (the last defaults to 0.01). The map is persisted
in the global config as `additionalModelCostsCache` and reused on later runs. It prices models that
the baked-in catalog does not know, which lets the server add pricing for a model without a client
release.

It cannot reprice a catalog model. The catalog lookup runs first and wins for any plain catalog id
(see "Lookup order"). The bootstrap schema also has no `long_prompt` field, so a model priced this
way gets flat rates.

The fetch runs for OAuth logins and API keys alike. It is skipped on third-party providers
(`[Bootstrap] Skipped: 3P provider`), when nonessential traffic is disabled
(`[Bootstrap] Skipped: Nonessential traffic disabled`), and when no credential is usable.

### 3. A time-limited price alias in bootstrap `client_data`

On first-party, a bootstrap `client_data` key named `alder_ford` can map a model id to
`{ as: <other model id>, ends_at: <epoch seconds> }`. Until `ends_at`, the model is priced at the
`as` model's baked-in card, and only when `as` names a catalog entry. The alias never applies to a
fast-mode response. Grep `alder_ford`. This is a server-controlled repricing switch, for example
for introductory pricing. It can only select a whole card that already ships in the release. It
cannot change one rate of a card, such as a single model's cache-read price.

### 4. `modelPricing` in managed settings

The `modelPricing` setting (grep `Price usage at your organization's contracted rates`) carries a
`multiplier` in (0, 10] and an `overrides` map of model id to `input` / `output` / `cacheRead` /
`cacheWrite`. One `cacheWrite` rate covers both TTLs, web search keeps $0.01, and there is no
long-prompt rate set, so an override row is flat. It is honored only from managed settings, or
from a host application that manages the model provider. An override row
is charged exactly as written: no fast-mode or data-residency surcharge is added. The multiplier
scales every computed cost, overridden or not. While a table is in effect, `/cost` appends
`at your organization's configured rates` to `Total cost:`. The debug log reports a bad table as
`modelPricing: … pricing at list`.

## The per-response formula

Grep `cache_creation?.ephemeral_1h_input_tokens` to land on the cache-write helper; the formula
function sits right after it. For one API response:

```
base = input_tokens               / 1e6 × input
     + output_tokens              / 1e6 × output
     + cache_read_input_tokens    / 1e6 × cache_read
     + cache_write                                       (below)
cost = base × geo + server_tool_use.web_search_requests × web_search
```

- Long prompts: when the card has a `longPrompt` set and `input_tokens + cache_read_input_tokens +
  cache_creation_input_tokens` exceeds its `abovePromptTokens`, every rate in the formula comes
  from the long-prompt set instead. The whole request switches, not only the tokens above the
  threshold. Output is included in the switch, while output tokens do not count toward the
  threshold.
- `cache_write`: `usage.cache_creation.ephemeral_1h_input_tokens` (capped at
  `cache_creation_input_tokens`) at the 1-hour rate, and the rest of `cache_creation_input_tokens`
  at the 5-minute rate. If the card has no 1-hour rate, all cache writes are at the 5-minute rate.
- `geo`: 1.1 when `usage.inference_geo === "us"` (US data residency), otherwise 1. The web-search
  charge is not multiplied.
- Output tokens include thinking tokens. `output_tokens_details.thinking_tokens` is recorded
  separately as `thinkingTokens` but not priced again.
- `server_tool_use.web_fetch_requests` and other server tool counters are not priced.
- With `modelPricing` in effect, the result is multiplied by its `multiplier`.

Advisor-tool iterations (`usage.iterations[]` entries of type `advisor_message`) are priced
separately at the advisor model's card and added to the session total. Each one also emits
`tengu_advisor_tool_token_usage` with `cost_usd_micros`. When the server answers a refusal with a
fallback model, the `fallback_message` iterations are priced at their own model's card.

## Lookup order and unknown models

For a non-fast response, the lookup tries in order: the `alder_ford` alias; for an alias or
overridden model name, `additionalModelCostsCache` under the identity-resolved name; the fast-mode
card (fast responses only); the baked-in catalog by canonical id; `additionalModelCostsCache` by
raw or canonical id.

When all of these miss, the model is unknown. Claude Code then:

- emits `tengu_unknown_model_cost` with the model and its short name,
- sets a session flag that makes `/cost` append
  `costs may be inaccurate due to usage of unknown models` to `Total cost:`,
- prices the response at the card of the session's default model setting, or at the $5/$25 Opus
  card (`tier_5_25` rates) if that also misses.

The cost is therefore never zero and never null for an unknown model. It is a substitute rate with a
warning. The flag persists with the session's cost state, so it survives resume. SDK
`modelUsage[].costBasis` reports `unknown` for such a model, `managed` for a `modelPricing` row or a
non-1 multiplier, and `list` otherwise.

## Subscription logins vs. API keys

The calculation does not branch on auth type. A Pro, Max, Team or Enterprise login accumulates the
same list-price estimate as an API key, and statusLine `cost.total_cost_usd` carries it unchanged.

Only the `/cost` text differs. For a claude.ai subscriber, non-interactive `/cost` prints
`You are currently using your subscription to power your Claude Code usage` (or the overages
variant) plus the limits-attribution block, instead of the `Total cost:` block. The estimate is
still computed, and it does not reflect what the subscriber pays.

## What feeds the total

Every model call that goes through the client's core streaming query adds its cost to the
session-wide ledger as its response completes. This covers:

- main-loop turns,
- in-process subagents started through the Agent tool, since they share the session's ledger,
- background helper calls that use the same query path. These include `generate_session_title`,
  `away_summary`, `tool_use_summary_generation` and other small-model helpers, each priced at its
  own model's card. Since 2.1.293, Haiku 5.5 is the default Haiku model on the Anthropic API, so
  these calls are priced at `haiku_55` there, versus $1/$5 for Haiku 4.5,
- compaction calls,
- advisor-tool iterations, as above,
- remote (`isolation: remote`) agents, whose reported `modelUsage[].costUSD` is folded in when they
  finish.

The ledger keys usage by model id, which produces the per-model lines under `Usage by model:`.

A few direct SDK calls bypass the ledger and are not counted: API-key verification (a 1-token
`messages.create`) and the token-count fallback that issues a `max_tokens: 1` request when
`countTokens` is unavailable. Separate processes, such as tmux-spawned teammates, keep their own
ledgers.

`/clear` starts a fresh session, so its total starts at 0. Resume restores the saved
`totalCostUSD` and per-model usage from the session's cost state.

## Relocation recipe

- Rate cards and formula: grep `promptCacheWrite1hTokens:` for the fast-mode literals; the
  formula function multiplies `n.input_tokens / 1e6` and sits a few lines below. The long-prompt
  switch is the helper just above it that compares the summed prompt tokens with
  `abovePromptTokens`.
- Accumulator: the function that adds `server_tool_use?.web_search_requests` into a `costUSD`
  per-model record, called once per completed response from the core streaming query.
- Unknown-model path: grep `tengu_unknown_model_cost`.
- `/cost` text: grep `costs may be inaccurate due to usage of unknown models` and
  `at your organization's configured rates`.
- statusLine payload: grep `total_cost_usd:` next to `total_lines_added:`.

## Drift from the published docs

The published docs (`costs`, `statusline`, `agent-sdk/cost-tracking`, `settings-reference`)
match the source on the points they cover: list-price estimate, `modelPricing`, the 1.1×
data-residency rate, and `costBasis`. They do not mention the baked-in catalog, the
bootstrap-fetched `additional_model_costs`, the substitute rate for unknown models, the
whole-request `long_prompt` switch, or the inclusion of background helper calls.

## Per-release appendix

- 2.1.295: new `haiku_55` tier and `claude-haiku-5-5` catalog entry (the changelog places the
  model's addition at 2.1.293). Introduces the optional `long_prompt` tier block and the formula's
  whole-request switch to it. Other tiers, the model mapping, the fast cards, the 1.1×
  data-residency multiplier and the bootstrap cost schema are unchanged from 2.1.289. Sonnet 5.5
  stays on `tier_2_10` (cache read $0.20).
- 2.1.289: first written.
