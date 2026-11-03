---
verified: 2.1.317
verified_on: 2026-11-03
section: Hooks
style: landmark
scope: >-
  Mods: sources, the 14 built-in plugins, refusal order, reloads, rollout gate (bounded wait, late
  load, mid-session follow), `plugin test`, dev mods
landmarks:
  - tengu_plugin_hooks_modules
  - as loadPluginHooks
  - which governs installed plugins
  - builtinPluginsInitialized
  - hooksModulesSwitchJoin
---
# Mods (Plugin Hooks Modules)

A mod is a plugin's hooks module: the JavaScript or TypeScript file that a plugin's
`hooks/hooks.json` names under `modules`, whose `register(on, options)` adds hooks and calls the `$`
API. The source calls it a "hooks module", its telemetry calls it "function hooks"
(`plugin_function_hooks_*`), and its user-facing text calls it a "mod".

The public docs cover authoring, drawing, the API, events, testing, administration and
troubleshooting: [overview](https://code.claude.com/docs/en/plugins/mods/overview.md),
[create](https://code.claude.com/docs/en/plugins/mods/create.md),
[interface](https://code.claude.com/docs/en/plugins/mods/interface.md),
[gallery](https://code.claude.com/docs/en/plugins/mods/gallery.md),
[reference](https://code.claude.com/docs/en/plugins/mods/reference.md),
[api](https://code.claude.com/docs/en/plugins/mods/api.md),
[events](https://code.claude.com/docs/en/plugins/mods/events.md),
[test](https://code.claude.com/docs/en/plugins/mods/test.md),
[admin](https://code.claude.com/docs/en/plugins/mods/admin.md) and
[troubleshoot](https://code.claude.com/docs/en/plugins/mods/troubleshoot.md). This doc records what
the source shows beyond them: which processes and plugins load a module and in what order the
refusals apply, which built-in plugins ship a mod, the `tengu_plugin_hooks_modules` rollout gate,
and how a session follows that switch while it runs. The `$` API surfaces are in the docs listed
under "Mod surfaces in other docs".

## Summary

- Hooks modules come from installed plugins, `--plugin-dir` / `CLAUDE_CODE_PLUGIN_DIRS`, the
  session's dev-mods folder, plugins the organization's managed settings enable, and 14 built-in
  plugins (`<name>@builtin`), 13 of which carry a mod; all but two are on by default.
- One registration pass decides which modules load. It is memoized and re-run by `/reload-plugins`,
  a plugin-affecting settings change, and a change of the rollout switch.
- The rollout switch is the GrowthBook flag `tengu_plugin_hooks_modules`, default `true`, read live
  on every check. When it reads off, every hooks module that is not built in is refused, the
  organization's included. Built-in modules still load.
- A saved off (read from the disk cache of an earlier session) holds the load for a bounded wait, up
  to 1.5 s, for this session's fetch. If the fetch then answers on, installed modules load late.
- A served change mid-session loads or unloads installed modules: an interactive session acts on the
  GrowthBook refresh once the current turn ends, a headless one at the next turn start.
- An off is set aside, so the switch reads on, in a process that holds no credential at all.
- No local override exists. How the value reaches the process, the disk cache, and when GrowthBook
  is off are generic: see `FEATURE_FLAGS.md`.

## Where hooks modules come from

| Source                    | Plugin id              | Notes                                       |
| ------------------------- | ---------------------- | ------------------------------------------- |
| Installed plugin          | `<name>@<marketplace>` | In `enabledPlugins`; a person's mod         |
| `--plugin-dir`            | `<name>@inline`        | Also `CLAUDE_CODE_PLUGIN_DIRS`; hot-reloads |
| Dev mods (Claude-written) | session folder         | `<config dir>/dev-mods/<session id>`        |
| Organization's plugin     | `<name>@<marketplace>` | Enabled by managed settings, vouched for    |
| Built-in plugin           | `<name>@builtin`       | `cc-plugin-*`, in the binary (below)        |

- `--plugin-dir` hot reloading stops in a long headless run unless `CLAUDE_CODE_PLUGIN_DIR_WATCH` is
  set.
- The dev-mods folder is recorded in the transcript as a `dev-mods` entry.
- A plugin enabled by managed settings is not automatically the organization's. When it is loaded
  from a copy rather than read in place from a registered local marketplace folder, the loader logs
  `is enabled by managed settings, but it is not read in place` and runs its module in the user
  tier. The admin doc's "Install your organization's mods and set the order" covers the rules.

### Built-in plugins

One initializer, guarded by `builtinPluginsInitialized` (`rg -n 'builtinPluginsInitialized'`),
registers 14 built-in plugins, each a lazily required module whose `"cc-plugin-…"` id is a literal
at its registration call. Every one except `cc-plugin-claude-platform` carries a hooks module.

A built-in is enabled by `enabledPlugins` under `cc-plugin-<name>@builtin`, else by its own
`defaultEnabled`, else on. Only `cc-plugin-you-should-know` and `cc-plugin-responsive-mode` default
off. `cc-plugin-sec-default` is enabled from managed settings only (`enabledFromPolicyOnly`) and
`cc-plugin-privacy` from trusted settings only (`enabledFromTrustedSettingsOnly`). Each also has an
availability check; an unavailable built-in is not listed at all. A flag default below is the flag's
code default, before GrowthBook answers.

| Plugin             | Registered on                 | Availability check, among others         |
| ------------------ | ----------------------------- | ---------------------------------------- |
| `sec-default`      | every entrypoint              | seated outermost (`prependPlugins`)      |
| `agents-md`        | every entrypoint              | `tengu_agents_md_mod` (flag default on)  |
| `telemetry`        | every entrypoint              | an analytics check, no flag              |
| `privacy`          | every entrypoint              | `tengu_wise_newt` (flag default on)      |
| `plugin-authoring` | not `local-agent`             | the rollout switch                       |
| `mods-guide`       | not `local-agent`             | `tengu_linen_acorn` (flag default off)   |
| `tips`             | not `local-agent`, `remote*`  | `tengu_tips_mod` (flag default off)      |
| `mermaid`          | not `local-agent`, `remote*`  | rollout switch, `tengu_mermaid_mod`      |
| `responsive-mode`  | as `tips`, or `remote`        | `tengu_quiet_ember` (flag default off)   |
| `diff`             | not `local-agent`, `remote*`  | `tengu_quiet_dolphin` (flag default on)  |
| `you-should-know`  | not `local-agent`             | `tengu_jolly_dewdrop` (flag default off) |
| `easel`            | as `tips`, or `remote_cowork` | `tengu_joyful_otter` (flag default off)  |
| `claude-platform`  | not `local-agent`, `remote*`  | `tengu_peppy_crescent`; no mod           |
| `claude-test`      | not `local-agent`, `remote*`  | several session checks                   |

"Registered on" reads `CLAUDE_CODE_ENTRYPOINT`; `remote*` is any entrypoint starting with `remote`.
The `diff` mod and the native sidebar it displaces are in `NATIVE_DIFF_SIDEBAR.md` and
`PLUGIN_PANES_AND_COMPOSER.md`; the skills the built-ins carry are in `SKILLS.md`.

A built-in's hooks module loads regardless of the rollout switch, `disableAllHooks`,
`allowManagedHooksOnly`, `--bare` and safe mode (row 1 of the ladder below). Only the two hosted
processes keep it out. Two built-ins still follow the switch through their availability:
`plugin-authoring` and `mermaid` are not listed while it reads off.

### The registration pass

The loader lives in a lazily imported module whose export list carries readable aliases. Relocate it
with `rg -n ' as loadPluginHooks,'`. The same list has `clearPluginHookCache`,
`setupPluginHookHotReload`, `standDownInstalledHooksModules` and `loadHooksModulesHeldForTrust`.

- `loadPluginHooks` memoizes one registration pass. `clearPluginHookCache` drops the memo.
- `/reload-plugins` runs `refreshActivePlugins`, which logs
  `refreshActivePlugins: clearing all plugin caches`, clears the memo and re-runs the pass.
- `setupPluginHookHotReload` subscribes to settings changes. A policy-settings change, or a
  user-settings change that moves a plugin's tier, logs
  `Plugin hooks: reloading due to plugin-affecting settings change` and re-runs the pass. When
  nothing plugin-affecting changed it logs `Plugin hooks: skipping reload` instead. It also installs
  the rollout-switch follow described below.
- `standDownInstalledHooksModules` unloads the modules of every plugin that is not built in. The
  rollout follow uses it when the switch turns off.

### Process-level refusals

These apply before any per-plugin decision. Each line is a log anchor.

- A claude-code-server tenant (a diskless host): no hooks module loads, built-ins included.
  `no hooks module loads in a claude-code-server tenant`.
- `claude mcp serve --transport http` (a tool server's daemon): no hooks module loads, built-ins
  included. `no hooks module loads in a tool server's daemon`.
- Either of the above, at load: the pass logs what it kept out,
  `no switch lifts it and no built-in plugin loads`.
- `--safe-mode` or `CLAUDE_CODE_SAFE_MODE`: installed plugins are dropped whole; built-ins load.
  `Safe mode: installed plugins are disabled, none of their hooks or hooks modules load`.
- Workspace trust not yet accepted: modules wait, and `loadHooksModulesHeldForTrust` loads them once
  it is. `hooks modules not loaded until workspace trust is accepted: `.

### Per-plugin refusals, in order

For each remaining plugin with a hooks module, the first matching row decides. A refusal is logged
as `hooks module <id> not loaded: <reason>`. Relocate the ladder with
`rg -nF 'disableAllHooks in managed settings, which governs installed plugins'`; the function
holding it returns each reason below in this order.

| #   | Condition                                                         | Result | Reason |
| --- | ----------------------------------------------------------------- | ------ | ------ |
| 1   | Built-in plugin                                                   | load   |        |
| 2   | Carries claude.ai uploads; `CLAUDE_CODE_RESTRICT_PERSONAL_CONFIG` | refuse | a      |
| 3   | Rollout switch off, or a cloud wake has no answer yet             | refuse | b      |
| 4   | `disableAllHooks` in managed settings                             | refuse | c      |
| 5   | The organization's plugin                                         | load   |        |
| 6   | A person's plugin in a cloud wake waiting for the switch          | refuse | d      |
| 7   | `--bare` or `CLAUDE_CODE_SIMPLE`                                  | refuse | e      |
| 8   | `allowManagedHooksOnly`, or `disableAllHooks` outside managed     | refuse | f      |
| 9   | The organization's managed settings are not read yet              | refuse | g      |

Each reason text starts with:

- a: `it carries your claude.ai uploads`
- b: `hooks modules are turned off for installed plugins in this process: `
- c: `disableAllHooks in managed settings, which governs installed plugins`
- d: `hooks modules a person installed wait for the rollout switch in this process`
- e: `installed plugins that are not managed load no hooks module in this mode (--bare)`
- f: `only managed plugins and built-in plugins run (allowManagedHooksOnly / disableAllHooks)`
- g: `this session has not read your organization's managed settings`

A plugin that passes all rows can still lose to an earlier plugin of the same name:
`another plugin of that name loads first`. The built-in guard's `allowManagedModsOnly` refusal is
separate: the guard is itself a mod and refuses later (see the admin doc).

Rows 3 and 4 come before row 5, so the rollout switch and managed `disableAllHooks` stop the
organization's modules too. Only built-in modules survive them.

## The rollout gate

The flag name is a module-level constant in the GrowthBook client module:
`rg -n '"tengu_plugin_hooks_modules"'`. Its default (`true`) and the rollout predicates live in a
small module that imports it; relocate that module with
`rg -nF "no hooks module loads in a tool server's daemon"`. Expected shape:

- Rollout on: not a hosted process (the two process-level refusals above) and the switch reads on.
- Hooks allowed: rollout on, not `--bare`, not safe mode. Gates `claude plugin test`'s visibility in
  help.
- User modules allowed: that, plus no `disableAllHooks` in any settings file and no
  `allowManagedHooksOnly`. Gates `claude plugin test` and the `content-link-mods` tip.

The switch reads `tengu_plugin_hooks_modules` live through the generic resolver on every check,
never pinned per session. The flag is not in the never-from-disk set, so the disk cache applies to
it (see `FEATURE_FLAGS.md` for the resolver order).

### An off set aside for lack of credentials

When the switch reads off from this session's payload or from the disk cache, the predicate reads
the credential stores once. The off is set aside, and the switch reads on, when all of these hold:

- No credential source: not `--bare`, no host-managed provider, no `ANTHROPIC_API_KEY` in the
  environment or the settings `env`, no stored API key, no `apiKeyHelper`, no OAuth access token in
  hand, and the GrowthBook client never fetched with a credential.
- No stored claude.ai OAuth record in any credential store, and on macOS the keychain lookup reports
  the item not found.

A read error logs `credential stores not read strictly:` and leaves the off in force.
`claude plugin test --file` children never set an off aside; when the parent did, it starts them
with `DISABLE_GROWTHBOOK=1` so they read the default too.

### What the switch covers

| Consumer                     | Effect when off               | `rg -nF`                      |
| ---------------------------- | ----------------------------- | ----------------------------- |
| Registration pass            | Non-built-ins refused (row 3) | `rollout flag (` (below)      |
| `claude plugin test`         | Refuses; hidden from help     | `pluginTestRefusal`           |
| Dev-mod hot reloading        | Refused, `hooks_modules_off`  | `mod hot-reloading is off`    |
| `cc-plugin-plugin-authoring` | Not available                 | `cc-plugin-plugin-authoring`  |
| `cc-plugin-mermaid`          | Not available                 | `tengu_mermaid_mod`           |
| `content-link-mods` tip      | Not shown                     | `content-link-mods`           |
| `claude plugin` early access | `plugin test` not listed      | `earlyAccess: "hooksModules"` |

The registration pass's line is
`rg -nF "installed plugins' hooks modules not loaded: rollout flag ("`: 3 hits, the off line below
and the two cloud-wake lines.

Dev-mod hot reloading checks its refusals in this order, first match wins, each logged as
`dev mods: mod hot-reloading is off here (<reason>)` with a `plugin_dev_mods` telemetry outcome:
`diskless`, `hooks_modules_off`, `all_hooks_disabled`, `sideload_disabled`, `local_dirs_blocked`,
`managed_hooks_only`, `hooks_disabled_in_settings`, `safe_mode`, `bare_mode`, `untrusted`.

### At session load: the bounded wait

Before the per-plugin decision, if at least one non-built-in module would otherwise load, the pass
may hold for the flag's answer. It holds when one of these is true, outside a cloud wake:

- Saved off: the switch reads off from the disk cache while the GrowthBook client is initializing.
- Cold cache: no payload yet and no saved value, in a non-interactive session or while the startup
  fetch hold is pending.
- Saved on during a pending startup fetch hold.

The hold first waits, up to 30 s, for a pending startup fetch hold to end, then waits for the client
to initialize. Its budget is 1500 ms (in a cloud wake, `CLAUDE_CODE_FLAG_FETCH_WAIT_MS`, default
3000 ms) less the time startup already waited for the flag fetch. For a saved off it awaits
initialization again if the switch still reads saved off and an initialization is in flight. One
line reports the outcome:

```
installed plugins' hooks modules held <ms>ms for the rollout flag (tengu_plugin_hooks_modules):
  <outcome>
```

(one line in the log; wrapped here).

`<outcome>` is `the flag payload landed`, `the fetch settled with no payload`, or
`no answer within <budget>ms`.

The pass then decides. With the switch off, it logs:

```
installed plugins' hooks modules not loaded: rollout flag (tengu_plugin_hooks_modules) is off,
  <source>; built-in plugins load regardless
```

(one line in the log; wrapped here). `<source>` is one of:

- `override`: `from a local override` (unreachable in the public build).
- `payload`: `from GrowthBook (this session's payload)`.
- `disk`: `from GrowthBook (the disk cache of an earlier session)`.
- `disabled`: `from the default (GrowthBook is off for this session: a third-party provider, or`
  `telemetry opted out)` (one string).
- `fallback`: `from the default (a cold GrowthBook cache, no payload yet)`.

Only `payload` and `disk` can carry an off in practice; the other sources yield the default, on.

Each refused module's own line then gives a state from a fixed table, after
`hooks modules are turned off for installed plugins in this process: `.

| State        | Text                                                                              |
| ------------ | --------------------------------------------------------------------------------- |
| served       | `the rollout switch served off`                                                   |
| saved        | `the rollout switch was saved off by an earlier session and is not refreshed yet` |
| unanswered   | `this wake's flag fetch has not answered the rollout switch; ...`                 |
| unfetched    | `this wake fetches no rollout switch; an organization's load at once, ...`        |
| unfetchedOut | `this wake fetches no rollout switch and the organization's settings ...`         |

### Late load after a saved off

When the hold ends with the switch still saved off, the pass subscribes to the next GrowthBook
refresh. When that refresh brings this session's payload and the switch now reads on, it logs
`installed plugins' hooks modules load late: the rollout flag (tengu_plugin_hooks_modules)` followed
by `answered on after the load went on over a saved off`, and re-runs the registration pass.

### Mid-session changes

After each pass, the session records what the switch read (`hooksModulesSwitchRead`). When the live
value differs and does not come from the disk cache, the session follows it:

- Interactive: `setupPluginHookHotReload` watches GrowthBook refreshes. On a difference it waits
  until the current foreground turn ends, then follows.
- Headless (`-p`, SDK): the turn loop's `hooksModulesSwitchJoin` follows at each turn start, waiting
  at most 10 s before the turn proceeds.

Following logs `installed plugins' hooks modules load|unload: the rollout flag`
`(tengu_plugin_hooks_modules) reads on|off in a running session` (one line). On is a fresh
registration pass. Off calls `standDownInstalledHooksModules` first, then re-runs the pass. Each
follow is capped at 60 s and reports `tengu_feature_ok` or `tengu_feature_bad` with feature name
`plugin_function_hooks_switch_followed` and `is_turned_on`. A failure logs
`installed plugins' hooks modules: the load that follows the rollout flag failed:` and leaves the
load owed for the next follow. When an off unloads something, the user sees
`installed mods are off for now: the rollout switch for them reads off; they load again when it`
`reads on, and built-in mods keep running` (one sentence; a notice in the terminal UI, a system
warning message in a headless stream).

Interactive sessions refresh GrowthBook on its periodic timer (see `FEATURE_FLAGS.md`), so a served
change reaches a running interactive session at the next refresh, not at once.

### Cloud wakes

A cloud wake is a non-interactive session with `CLAUDE_CODE_REMOTE` set and
`CLAUDE_CODE_ENVIRONMENT_KIND` unset, before the flag has a decided value (or with GrowthBook off).
There the organization's modules load at once at what the switch reads, while a person's wait:

- Logs: `the rollout flag (tengu_plugin_hooks_modules) is not answered within this wake's wait`,
  `rollout flag (tengu_plugin_hooks_modules) is not answered yet in this wake`, and
  `a person's installed plugins' hooks modules not loaded: rollout flag (...) is not answered`
  `within this wake's wait; an organization's and built-in plugins load regardless` (one line).
- The flag is re-fetched at a turn start at most once per 60 s.
- While the organization's modules are owed, a turn waits up to 300 s with
  `Waiting for your organization's mods to load.`, then fails with
  `Your organization's mods could not be loaded, so this turn was not run.` or
  `Your organization's policy could not be read, so this session cannot run a turn.` (telemetry
  `plugin_function_hooks_turn_gate`, `policy_unread`).

## `claude plugin test`

The command is dispatched in the entry module, before the full CLI loads, when the first two
arguments are `plugin test`. Relocate with `rg -nF 'pluginTestRefusal'`; the module exporting it
also exports `pluginTestFormOf`, `pluginTestGatesOf` and `switchFetched`.

- The form is `run` (a directory or none), `file` (`--file`, the per-test-file child) or `other`.
- A `run` whose switch has no decided value holds for the flag (the hold line above), stops the
  periodic refresh, then waits up to 1500 ms for the fetched value to be saved to the global config,
  because the per-file children read the saved value. If the switch reads on but the saved value
  does not, it fails with
  `the rollout switch was fetched, but its value could not be saved for the test files to read`. It
  skips the hold when the early fetch is vetoed (a policy helper is configured, or settings `env` is
  still pending) or the sign-in expires within 60 s. A hold failure logs
  `claude plugin test: the hold for the rollout flag failed: `.
- Children run with a small environment allowlist (`PATH`, `HOME`, `CLAUDE_CONFIG_DIR`, the
  GrowthBook-related env vars and a few others).

Refusals, each printed as `claude plugin test: <text>` with exit status 1 (a `--file` child reports
it in its JSON result instead):

- Switch off, from a saved value: `hooks modules are turned off in this process: the rollout switch
  was saved off by an earlier session and is not refreshed yet.`, then advice to start `claude` once
  with network access (anchor `once with network access, then run the tests again`), ending
  `if this message returns, installed mods are turned off remotely`.
- Switch off, served: `hooks modules are turned off in this process: the rollout switch served off,
  and a plugin's tests run only while it is on`.
- User modules not allowed:
  `hooks modules are turned off here (disableAllHooks, allowManagedHooksOnly or a policy)`.

## Telling a served off from a fetch problem

- A failed fetch yields off only when the disk cache already holds off. With no cached value the
  switch reads the default, on.
- In a debug log, the `rollout flag (...) is off, <source>` line says whether the value came from
  this session's payload or from the disk cache. A `disk` source follows a `held <ms>ms` line:
  `no answer within ...` or `the fetch settled with no payload` is a fetch problem;
  `the flag payload landed` with a `disk` source cannot occur, because a landed payload that carries
  the flag wins.
- A later `load late` line means this session's fetch answered on after the load went ahead.
- Without a session, run `claude plugin test` in a directory that holds no mod:
  `saved off by an earlier session` means the fetch did not answer; `served off` is the served
  value.
- This shows the last saved value and when it was written:

  ```
  jq '.cachedGrowthBookFeatures.tengu_plugin_hooks_modules, .cachedGrowthBookFeaturesAt' \
    ~/.claude.json
  ```

  Editing it matters only for a process whose fetch fails; the next successful fetch rewrites it.

## Mod surfaces in other docs

| Topic                                                         | Doc                            |
| ------------------------------------------------------------- | ------------------------------ |
| Pane render site, the `$` API, composer, focus, `$.ui.status` | `PLUGIN_PANES_AND_COMPOSER.md` |
| `$.ui.selection`, `$.prompt.fill` and `$.prompt.paint`        | `PLUGIN_PANES_AND_COMPOSER.md` |
| The `diff` mod, the native `/diff` sidebar, API mapping       | `NATIVE_DIFF_SIDEBAR.md`       |
| Settings hooks (`hooks/hooks.json` `hooks`) and events        | `HOOKS.md`                     |
| The skills the built-in plugins carry                         | `SKILLS.md`                    |
| `plugin_notification`, a mod's desktop notification           | `NOTIFICATIONS.md`             |
| GrowthBook fetch, disk cache, resolver order, GrowthBook off  | `FEATURE_FLAGS.md`             |

## Tripwires

- `□` `"tengu_plugin_hooks_modules"` is defined once, default `true`; the rollout predicate reads no
  env var.
- `□` The five source texts and the five state texts are unchanged.
- `□` The per-plugin ladder keeps rollout and managed `disableAllHooks` ahead of the organization's
  plugins, so those two stop the organization's modules.
- `□` The load hold budget is 1500 ms outside a cloud wake; the follow cap is 60 s; the headless
  turn-start wait is 10 s.
- `□` `installed plugins' hooks modules held `, `load late`, and `in a running session` each have
  one emitter.
- `□` The dev-mod refusal list still starts `diskless`, `hooks_modules_off`.
- `□` `rg -n 'builtinPluginsInitialized'`: the initializer registers 14 `"cc-plugin-…"` ids; only
  `cc-plugin-you-should-know` and `cc-plugin-responsive-mode` set `defaultEnabled` off.
- `□` Both override readers return nothing in the public build (`FEATURE_FLAGS.md`).
