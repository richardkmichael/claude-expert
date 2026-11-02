# Feature Flags

Verified against: cli.prettier.js 2.1.316 (2026-11-02)

How Claude Code receives, caches and reads its `tengu_*` feature flags. The flags come from a
GrowthBook client that Anthropic's servers answer per account; nothing in the CLI decides a flag's
value from targeting rules. For one flag followed end to end, see `MODS.md`.

## Fetching

The client uses remote evaluation: it sends the account's attributes and receives finished values,
so the targeting rules never reach the machine.

- Request: `POST https://api.anthropic.com/api/eval/<client key>`, where the client key is a
  constant `sdk-…` string in the bundle. Relocate with `rg -n '/api/eval/\$\{e.clientKey\}'`.
- Attributes include the account UUID and organization UUID, whether Slack (Claude Tag) is
  connected, and several surface and cache-partition fields. The client is created with
  `remoteEval: !0` and a `cacheKeyAttributes` list; grep `cacheKeyAttributes: [`.
- Timing: once when a process starts, then on a timer. The interval is 360 minutes unless the
  `tengu_gb_refresh_interval_minutes` flag is served, in which case it is clamped to 5–360 minutes
  and jittered by ±10%. Grep `"tengu_gb_refresh_interval_minutes"`. No command forces a refresh.
- The flags are not part of model API requests or responses. A flag check never makes a request.

Each successful fetch is held in memory for the process and written to the global config
(`~/.claude.json`, or under `CLAUDE_CONFIG_DIR`) as `cachedGrowthBookFeatures`, a map of every flag
served to the account, with `cachedGrowthBookFeaturesAt` set to the write time in epoch
milliseconds. `cachedExperimentFeatures` lists the flags that belong to experiments, for exposure
logging.

```bash
jq '.cachedGrowthBookFeatures | length, .cachedGrowthBookFeaturesAt' ~/.claude.json
jq '.cachedGrowthBookFeatures.tengu_birch_kettle' ~/.claude.json
```

## Reading a flag

Code reads a flag through a helper that takes the flag name and a default, as in
`k("tengu_birch_kettle", !1)` (the helper's name is minified; the call shape is stable). The
resolver behind it returns a value and a source. Relocate it with
`rg -n 'getFeatureValueWithSource\(e, n\) \{'`. Order:

1. An environment override, then a config override (source `override`). Both readers return nothing
   in the public build, so no local override exists. `CLAUDE_INTERNAL_FC_OVERRIDES` is wired into
   the client's dependencies, but the client's `getEnvironmentOverrides()` returns `null`.
2. If GrowthBook is off for the process and the disk cache is not readable while off: the default
   (`disabled`).
3. This process's fetched values, if they include the flag (`payload`). If values have arrived but
   lack the flag: the default (`fallback`).
4. A fixed set of flags is never read from disk; for those, the default (`fallback`). The set is a
   `new Set([` literal of `tengu_*` names next to the client code.
5. `cachedGrowthBookFeatures[flag]` from the global config (`disk`).
6. The default (`fallback`).

So the disk cache matters only between process start and the first fetch, or for the whole process
when the fetch fails. Editing a value in `~/.claude.json` changes behavior only in that window: the
fetched values take precedence once they arrive, and the next fetch rewrites the file.

Boolean gates have a second reader, `checkGateCachedOrBlocking`, which returns `true` early from the
fetched values or a cached `true`, and otherwise waits for the fetch.

## When GrowthBook is off

GrowthBook is off for a process when any of these holds. Relocate the predicate with
`rg -n 'return !i.DISABLE_GROWTHBOOK &&'`:

- `DISABLE_GROWTHBOOK` is set.
- Telemetry is reduced: `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_TELEMETRY`, or a truthy
  `DO_NOT_TRACK`.
- The provider is not first-party, unless `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST` is set.
- The session signed in through an LLM gateway.
- `CLAUDE_CODE_CUSTOM_OAUTH_URL` is set.

With GrowthBook off, every flag reads its default. The exception is
`CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF` on a first-party provider with telemetry reduced: the
disk cache stays readable, so cached values still apply.

## Tripwires

- `□` The fetch is `POST <api host>/api/eval/<client key>` with remote evaluation on.
- `□` Default refresh interval 360 minutes; served interval clamped to 5–360 with ±10% jitter.
- `□` The resolver order is override, disabled, payload, fallback, disk, fallback.
- `□` Both override readers return nothing in the public build.
- `□` The off predicate still names `DISABLE_GROWTHBOOK` and the telemetry level.
