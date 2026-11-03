---
verified: 2.1.207
section: Tools, skills, and execution
style: landmark
scope: Ripgrep bundling, embedded/system selection, config
landmarks:
  - USE_BUILTIN_RIPGREP
  - tengu_ripgrep_availability
  - no-config
---
# Ripgrep: Bundling, Binary Selection, and Configuration

This document follows the landmark style in `GUIDELINES.md`: anchors are version-stable strings (env
vars, log lines, `tengu_*` telemetry names, literal error text) with grep re-location recipes, never
minified symbol names or line numbers. Per-release facts live in the appendix.

Ripgrep powers all of Claude Code's internal file search: the Grep and Glob tools, the `@`-file
suggestion fallback, markdown discovery scans, bounded directory listings, and file-count
telemetry. This doc covers how the binary ships, how one is chosen at runtime, how that choice is
configured, and what happens when a search fails. The Bash tool's `rg`/`find`/`grep` shell wrappers
are a separate mechanism, covered in `BASH_TOOL_EXECUTION.md` ("Search-tool wrappers"); the
`@`-file pipeline that consumes the fallback is in `FILE_INCLUSION.md`.

## How ripgrep ships

Native (bun-compiled) build: a real ripgrep is compiled into the single `claude` executable as a
multi-call binary. Dispatch happens on `argv[0]` in the native entry stub, before the JavaScript
app runs — invoking the binary with `argv[0]` of `rg` runs ripgrep directly:

    (exec -a rg ~/.local/share/claude/versions/<version> --version)   # prints "ripgrep <x.y.z>"

The same mechanism embeds ugrep (`argv[0]` = `ugrep`) and bfs (`argv[0]` = `bfs`). The dispatch
keys are the tool implementation names — `argv[0]` of `grep` or `find` does not dispatch; the
binary starts as normal Claude Code. There are no separate rg/ugrep/bfs files on disk, and the
JavaScript bundle contains no dispatch logic for them.

npm build: nothing is vendored — no `vendor/ripgrep` directory and no embedded binary. Search
requires a system `rg` on PATH; a missing one surfaces the install-hint error below.

## Binary selection (the resolver)

A memoised resolver returns `{ mode, command, args, argv0? }` with two modes:

1. System — `{ mode: "system", command: <absolute rg path>, args: [] }`. `args` is empty, so the
   user's `~/.ripgreprc` / `RIPGREP_CONFIG_PATH` applies.
2. Embedded —
   `{ mode: "embedded", command: process.execPath, args: ["--no-config"], argv0: "rg" }`.
   Re-execs the running executable as ripgrep via the `argv[0]` dispatch above. `--no-config`
   suppresses the user's ripgrep config — an intentional isolation of internal search from
   arbitrary user configuration.

Decision order:

1. If `USE_BUILTIN_RIPGREP` parses as disabled (`0`/`false`/`no`/`off`, case-insensitive, trimmed)
   and `rg` resolves on PATH (`Bun.which`), pick system mode.
2. Else, on a packaged native build (`Bun.isStandaloneExecutable === true`): embedded mode,
   provided `process.execPath` resolves as an executable; otherwise prefer a system `rg` if one is
   found, and fall back to embedded anyway when none is.
3. Else (npm / dev build): system mode with whatever `rg` resolves to — the bare string `rg` when
   nothing is on PATH, so the eventual spawn fails with `ENOENT` and gets the install-hint error.

Re-location: `rg -n 'USE_BUILTIN_RIPGREP'` (the resolver is the hit inside an `Or(() => ...)`
memoiser); `rg -n 'no-config'` (single hit — the embedded args). Expect a truthy/falsy env parser
pair nearby: enabled set `{1,true,yes,on}`, disabled set `{0,false,no,off}`.

## Configuration

`USE_BUILTIN_RIPGREP` is the only switch. The name is counter-intuitive: setting it to
`0`/`false`/`no`/`off` disables the embedded binary and switches to the system one. It only takes
effect when a system `rg` is actually found on PATH. It is a registered env var (present in the
env-var registry and the documented env-var name list), so it can be set in the environment that
launches Claude Code or via the `env` block of `settings.json`.

Effects of switching to system mode:

- All internal consumers run the system binary with no `--no-config`, so the user's ripgrep
  configuration applies to internal search too.
- The Bash tool stops injecting any `rg` fallback (a real `rg` is on PATH, which already suppressed
  it — see `BASH_TOOL_EXECUTION.md`).

There is no flag forcing the reverse direction (embedded rg when a build lacks one), and no setting
that changes the resolved binary path to an arbitrary location. SDK callers can override the
`{ command, args, argv0 }` handed to the sandbox runtime via a `sandbox.ripgrep` option, but that
affects only sandbox wiring, not the internal search resolver.

Official docs cross-check (current as of the verification date): the troubleshooting page
("Search and discovery issues") and the setup page (Alpine / musl-based distributions) both
document installing the platform ripgrep and setting `USE_BUILTIN_RIPGREP=0`; the setup page shows
the `settings.json` `env` form. The musl case is the motivating one: the native installer there
needs `libgcc`, `libstdc++`, and a system `ripgrep`.

## First-use health check

The first internal search of a session fires a memoised, fire-and-forget probe: run the resolved
binary with `--version` (spawned with the embedded `argv0` re-exec, or with a 5-second timeout in
system mode) and check that it exits 0 with stdout starting `ripgrep `. The result is cached as
`{ working, lastTested, config }`.

- Log line: `Ripgrep first use test: PASSED` / `FAILED (mode=..., path=...)`.
- Telemetry: `tengu_ripgrep_availability` with `working` and `using_system`.
- `/doctor` surfaces the cached state as `ripgrepStatus: { working, mode, systemPath }` (grep
  `ripgrepStatus`).

## Failure handling at spawn time

ENOENT — the resolver cache and health-check state are cleared (unless the health check already
recorded a failure), so the next search re-resolves from scratch; this recovers from PATH changes
or an uninstalled system rg mid-session. In system mode the raw error is replaced with an
install hint (grep this literal):

    ripgrep not found on PATH. Install it (brew install ripgrep / apt install ripgrep / winget
    install BurntSushi.ripgrep.MSVC) or use the native claude binary which embeds it.

Timeout — searches are killed after 20 seconds (60 on WSL) with SIGTERM, then SIGKILL 5 seconds
later. `CLAUDE_CODE_GLOB_TIMEOUT_SECONDS` (integer seconds > 0) overrides the limit for these rg
spawns. A timed-out search raises a `RipgrepTimeoutError` carrying any partial results; its message
starts `Ripgrep search timed out after`.

EAGAIN — when stderr contains `os error 11` or `Resource temporarily unavailable`, the search is
retried once single-threaded (`-j 1`), with telemetry `tengu_ripgrep_eagain_retry`.

Output — stdout and stderr are each capped at 20 MB. Exit codes 0 and 1 both count as success
(1 is ripgrep's no-matches code).

## Consumers

Internal consumers spawn the resolved `command` with the resolver `args` prepended (so embedded
mode's `--no-config` reaches all of them):

- Grep tool (all output modes) and Glob tool (`--sort=modified` argument build).
- The `@`-file suggestion fallback (`tengu_file_suggestions_ripgrep`; see `FILE_INCLUSION.md`).
- Markdown discovery scans (`--glob` `*.md`) and bounded directory listings
  (`--files --hidden --max-depth N`).
- Rounded file-count telemetry (`countFilesRoundedRg` appears in its error log).
- The sandbox runtime receives the resolved `{ command, args, argv0 }` in its config
  (`sandbox.ripgrep`).

The Bash tool is not a consumer of the resolver args: its `rg` is a snapshot-injected fallback
built from the resolver's mode alone, and it never carries `--no-config`. Consequence: internal
search ignores the user's ripgrep config on the native build, while Bash-tool `rg` honours it —
see `BASH_TOOL_EXECUTION.md` ("Ripgrep config: Bash-tool rg vs the Search tool").

## Landmark index

| Concept              | Grep anchor                          | Expected shape                                     |
|----------------------|--------------------------------------|----------------------------------------------------|
| Resolver             | `USE_BUILTIN_RIPGREP`                | memoised, two `{ mode, command, args }` shapes     |
| Embedded args        | `no-config`                          | single hit, inside the embedded-mode object        |
| Health check         | `Ripgrep first use test`             | memoised `--version` probe, caches `working`       |
| Availability telem.  | `tengu_ripgrep_availability`         | `{ working, using_system }`                        |
| Install hint         | `ripgrep not found on PATH`          | wraps system-mode ENOENT                           |
| Timeout override     | `CLAUDE_CODE_GLOB_TIMEOUT_SECONDS`   | parsed as seconds; default 20s, 60s on WSL         |
| Timeout error        | `Ripgrep search timed out after`     | `RipgrepTimeoutError` with partial results         |
| EAGAIN retry         | `tengu_ripgrep_eagain_retry`         | single `-j 1` retry on `os error 11`               |
| Doctor status        | `ripgrepStatus`                      | `{ working, mode, systemPath }`                    |

## Tripwire checklist (re-verify on a new version)

□ resolver returns exactly the two mode shapes; disabled set is `{0,false,no,off}`
□ `--no-config` present only in embedded-mode args
□ `USE_BUILTIN_RIPGREP` only honoured when a system rg is found
□ health check probes `--version`, expects stdout starting `ripgrep `
□ ENOENT clears resolver + health caches; system-mode ENOENT gets the install hint
□ 20s/60s(WSL) timeout, `CLAUDE_CODE_GLOB_TIMEOUT_SECONDS` override, SIGTERM→SIGKILL
□ EAGAIN retried once with `-j 1`
□ `exec -a rg <native binary> --version` prints a ripgrep version string
□ `argv[0]` of `grep`/`find` does not dispatch (keys are `rg`/`ugrep`/`bfs`)

## Per-release notes

- 2.1.207: behavioral model above verified. The embedded ripgrep on the contemporaneous macOS
  binary (2.1.209) reports `ripgrep 14.1.1` with `+pcre2`; a homebrew rg on the same machine was
  newer (15.1.0) — version skew between embedded and system rg is normal.
- 2.1.154: the system-mode ENOENT install-hint error text added (absent in 2.1.143).
- 2.1.119 (earliest local): health check, availability telemetry, and EAGAIN retry already present.
- This doc consolidates and extends the former "Ripgrep Binary Selection" section of
  `FILE_INCLUSION.md`.
