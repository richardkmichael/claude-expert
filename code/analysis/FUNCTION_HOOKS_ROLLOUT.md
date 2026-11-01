# Function Hooks (Mods) Rollout Gate

Verified against: cli.prettier.js 2.1.286 (2026-10-01); 2.1.287 checked by string search of the
native binary

Whether installed plugins may load hooks modules ("mods", function hooks) is decided by one
GrowthBook flag. This doc covers the flag, what it gates, the env var that used to override it,
how the served value reaches a process, and how to tell a served "off" from a fetch problem.

## Summary

- The flag is `tengu_plugin_hooks_modules`, default `true`.
- Up to 2.1.286, `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` (a tri-state env var) wins over the flag in
  both directions. In 2.1.287 the gate reads only the flag; the env var no longer affects it.
- No local override exists in external builds. The GrowthBook client's environment and config
  override readers return nothing.
- The gate covers installed plugins' hooks modules at session load and reload, `claude plugin
  test`, and dev-mod hot reloading. Built-in plugins load regardless.
- A served `false` comes from this session's fetch or from the disk cache of an earlier session.
  A failed fetch with no cached value falls back to `true`.
- When GrowthBook is off for the process (see below), the flag reads its default, `true`.

## Locating the gate

- `rg -n 'var \w+ = "tengu_plugin_hooks_modules"'` finds the module that defines the flag name,
  the default (`!0`), and three predicates: rollout on, rollout on and hooks allowed here, and
  that plus not managed-only. The module exports them as `hooksModulesRolloutOn` and
  `canLoadUserHooksModules`.
- `rg -n 'overridden by the CLAUDE_CODE_ENABLE_FUNCTION_HOOKS environment variable'` (2.1.286
  only) finds the source-description table used in log lines.

Expected shape, 2.1.286:

```
rolloutOn = () => env.CLAUDE_CODE_ENABLE_FUNCTION_HOOKS ?? flag("tengu_plugin_hooks_modules", true)
```

Expected shape, 2.1.287 (minified, from the binary):

```
rolloutOn = () => flag("tengu_plugin_hooks_modules", true)
```

In 2.1.287 `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` survives only in env-var name lists. In 2.1.286,
`claude plugin test` also sets it to `1` for the per-file `plugin test --file` child processes it
spawns; in 2.1.287 that no longer reaches the gate.

## What the gate covers

| Consumer                          | Effect when off                                                      | Relocate                                       |
| --------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------- |
| Plugin hooks load (start, reload) | installed plugins' hooks modules are skipped; built-ins still load   | `rg -nF 'rollout flag ('`                      |
| `claude plugin test`              | refuses with the message below                                       | `rg -nF 'pluginTestRefusal'`                   |
| Dev-mod hot reloading             | refused with reason `hooks_modules_off`                              | `rg -nF 'mod hot-reloading is off here'`       |

The test refusal text:

| Version | Text                                                                                      |
| ------- | ----------------------------------------------------------------------------------------- |
| 2.1.286 | `... CLAUDE_CODE_ENABLE_FUNCTION_HOOKS is 0 in a settings file or in its environment, or` |
|         | `the rollout switch served off; ... set CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 over a`       |
|         | `served off, to run a plugin's tests`                                                     |
| 2.1.287 | `hooks modules are turned off in this process: the rollout switch served off, and a`      |
|         | `plugin's tests run only while it is on`                                                  |

The loader log line names the flag and where its value came from:
`installed plugins' hooks modules not loaded: rollout flag (tengu_plugin_hooks_modules) is off,
<source>; built-in plugins load regardless`. `<source>` is one of:

| Source     | Text                                                                                      |
| ---------- | ----------------------------------------------------------------------------------------- |
| `override` | `from a local override` (unreachable in external builds)                                  |
| `payload`  | `from GrowthBook (this session's payload)`                                                |
| `disk`     | `from GrowthBook (the disk cache of an earlier session)`                                  |
| `disabled` | `from the default (GrowthBook is off for this session: a third-party provider, or ...)`   |
| `fallback` | `from the default (a cold GrowthBook cache, no payload yet)`                              |

2.1.286 adds a sixth text, `overridden by the CLAUDE_CODE_ENABLE_FUNCTION_HOOKS environment
variable`, used whenever the env var is set.

### Timing inside a running session

The flag is read live on every check, not pinned per session. The plugin hooks loader memoizes
its registration, and that memo is cleared by `/reload-plugins` and by a change to
plugin-affecting settings (log line `Plugin hooks: reloading due to plugin-affecting settings
change`). Each reload re-reads the flag. No GrowthBook-refresh listener re-runs the loader, so
modules loaded at session start keep running after the served value changes, until the next
reload.

## How the value reaches the process

Relocate the resolver with `rg -n 'getFeatureValueWithSource\(e, n\) \{'`. Order:

1. Environment overrides, then config overrides. Both readers return nothing in external builds,
   although a `CLAUDE_INTERNAL_FC_OVERRIDES` reader is wired into the client's dependencies.
2. If GrowthBook is off and the disk cache is not readable while off: the default (`disabled`).
3. This session's remote-eval payload, if it has the flag (`payload`). If a payload arrived
   without the flag: the default (`fallback`).
4. `cachedGrowthBookFeatures[flag]` in the global config file (`disk`).
5. The default (`fallback`).

The client initializes with a 5000 ms timeout and writes each successful payload to the global
config (`~/.claude.json`, or under `CLAUDE_CONFIG_DIR`) as `cachedGrowthBookFeatures`, with
`cachedGrowthBookFeaturesAt` set to the write time. A periodic refresh follows. Its interval is
`tengu_gb_refresh_interval_minutes` when served (clamped to 5–360, jittered ±10%), else 360
minutes; relocate with `rg -n '"tengu_gb_refresh_interval_minutes"'`. There is no command that
forces a refresh. A new process fetches at startup.

GrowthBook is off for a process when any of these holds (relocate the predicate with
`rg -n 'return !a.DISABLE_GROWTHBOOK &&'`):

- `DISABLE_GROWTHBOOK` is set.
- The provider is not first-party (unless `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST`).
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`, `DISABLE_TELEMETRY`, or a truthy `DO_NOT_TRACK`.
- `CLAUDE_CODE_CUSTOM_OAUTH_URL` is set.

With GrowthBook off, every flag reads its default, so `tengu_plugin_hooks_modules` reads `true`.
The exception is `CLAUDE_CODE_GB_DISK_CACHE_WHEN_TELEMETRY_OFF` on a first-party provider with
telemetry off: the disk cache stays readable, so a cached `false` still applies.

## Telling a served "off" from a fetch problem

- A fetch failure alone yields `false` only when the disk cache already holds `false`. With no
  cached value it yields `true`.
- `jq '.cachedGrowthBookFeatures.tengu_plugin_hooks_modules, .cachedGrowthBookFeaturesAt'
  ~/.claude.json` shows the last served value and when it was written.
- In a debug log, the loader's `rollout flag (...) is off, <source>` line says whether the value
  came from this session's payload or from the disk cache.
- Editing the cached value only matters for a process whose fetch fails. A payload that carries
  the flag wins, and the next successful fetch rewrites the cache.

□ Tripwire: the flag name and default are unchanged; the rollout predicate reads no env var (in
  2.1.286 it reads `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` first); both override readers return
  nothing; the five source texts are unchanged. If any of these changes, this doc is stale.

## Version notes

- 2.1.287: `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` no longer overrides `tengu_plugin_hooks_modules`;
  the refusal texts drop the env-var advice.
- 2.1.286: the env var wins over the flag in both directions; `claude plugin test` per-file
  children get `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`.
