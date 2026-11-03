---
verified: 2.1.207
section: Tools, skills, and execution
style: landmark
scope: Bash tool, shell snapshots, search-tool wrappers
landmarks:
  - shell-snapshots
  - SNAPSHOT_FILE=
  - RIPGREP_FUNC_END
---
# Claude Code Bash Tool Execution Analysis

This document follows the landmark style in `GUIDELINES.md`: it anchors on version-stable strings
(env vars, log/telemetry names, literal shell tokens, behavioral logic) and gives grep re-location
recipes instead of minified names or line numbers, which churn every release. Per-release specifics
live in the appendix.

For the Bash tool's `description` field — the prompt text the model sees, including the Git Safety
Protocol, commit instructions, and PR instructions — see `PROMPTS.md` (section "Tool-description
channel") and `GIT_USAGE.md`. The verbatim rendered text is in `PROMPTS_RENDERED.md`.

For ripgrep binary selection (the resolver, its modes, `USE_BUILTIN_RIPGREP`, and failure
handling), see `RIPGREP.md`. The Bash-tool-specific behaviour is under "Search-tool wrappers"
below.

## Behavioral model

How a Bash tool call runs:

- Each command runs in a freshly spawned shell invoked with `-c`. There is no long-lived shell
  process. Working directory persists across calls through a temp cwd file; environment, functions,
  and aliases persist through a per-session snapshot that every command sources.
- Before the command runs, the shell sources a generated snapshot that restores the user's
  functions, aliases, shell options, and PATH, plus Claude Code's own search-tool wrappers.
- The command is run via `eval`, with stdin redirected from `/dev/null` so a command that reads
  stdin cannot block — except when the command is a heredoc or already redirects stdin, where the
  redirect is omitted.
- The child inherits the full parent environment; Claude-specific variables are added and none are
  stripped.

## Shell snapshot lifecycle

The snapshot is generated once per shell session and sourced on every command. It is not a static
file shipped in the binary — the binary embeds the generator and the wrapper templates, and the
snapshot is written to disk at runtime.

Generation: a login shell sources the user's real config (`.zshrc` / `.bashrc` / `.profile`), then
dumps the resulting functions (completion functions filtered out, double-underscore helpers kept),
shell options, aliases, and PATH into a snapshot file under a `shell-snapshots` directory, named
`snapshot-<shell>-<timestamp>-<random>.sh`. Claude Code's `rg` wrapper and, on the native build, the
`find`/`grep` wrappers are appended.

Per command: the snapshot path is cached for the session and reused. Each command string is
assembled roughly as — source the snapshot (ignoring failure), disable extended globbing, `eval` the
command with its stdin redirect, then record the post-command directory with `pwd -P` into the cwd
file — joined with ` && `. The shell is spawned with `-c`, and without `-l` (login) when a snapshot
exists, because the snapshot already captured the login environment. If the snapshot file has gone
missing, it falls back to a login shell.

Re-location:
- `rg -n 'shell-snapshots'` and `rg -n 'SNAPSHOT_FILE='` — the snapshot directory and the generator
  script. Expect a generator that sources the user config, then writes a `# Functions` /
  `# Shell Options` / `# Aliases` section sequence, with an `unalias -a` line near the top of the
  produced file.
- `rg -n 'snapshot-'` — the per-session filename pattern `snapshot-<shell>-<ts>-<rand>.sh`.
- Telemetry: `rg -n 'shell_snapshot_create'`.

Tripwire: □ snapshot generated per session under `shell-snapshots/` □ sourced on every command
□ login shell used only to generate, not to run commands □ command shell spawned with `-c`, no `-l`
when a snapshot exists.

## stdin and pipe handling

The eval'd command gets `< /dev/null` appended so its stdin is empty, for both simple and piped
commands. The redirect is omitted when the command contains a heredoc (`<<word`) or already
redirects stdin (a `<` that is not `<<` or `<(`). Piped commands are single-quoted as a whole so
`eval` interprets the pipeline; simple commands are shell-quoted.

Re-location: `rg -n '< /dev/null'` in the bash-tool command builder. Expect a helper that decides
whether the redirect is safe (rejecting heredocs and existing stdin redirects) and two quoting paths
(piped vs simple).

Tripwire: □ `< /dev/null` appended to safe commands □ omitted for heredocs □ omitted when the
command already has a `<` redirect □ pipelines preserved (single-quoted, not shell-escaped).

## Environment

The child inherits the full parent environment: the common path passes it through unchanged, and
remote / OpenTelemetry / background-session setups add keys but remove none. Added or overridden
keys: `CLAUDECODE`, `GIT_EDITOR=true`, `CLAUDE_CODE_EXECPATH` (the claude binary, used by the
search-tool wrappers), a session id, and `SHELL` for bash. Sandboxed runs add `TMPDIR` /
`CLAUDE_CODE_TMPDIR` / `TMPPREFIX`.

Caveats:
- The snapshot re-exports `PATH` only. Other variables (e.g. `RIPGREP_CONFIG_PATH`) reach the child
  only via inherited parent environment — i.e. only if they were exported in the environment that
  launched Claude Code; the snapshot does not re-derive them from sourcing the user's rc files.
- `CLAUDE_CODE_DONT_INHERIT_ENV` drops inheritance for the snapshot generator and the env probe; the
  main command spawn still inherits.

Relevant env vars (anchors): `CLAUDECODE`, `CLAUDE_CODE_EXECPATH`, `CLAUDE_CODE_DONT_INHERIT_ENV`,
`CLAUDE_CODE_REMOTE`, `CLAUDE_CODE_SHELL_PREFIX`, `CLAUDE_CODE_TMPDIR`, `BUN_OPTIONS`.

Re-location / tripwire: `rg -n 'CLAUDECODE'`, `rg -n 'GIT_EDITOR'`, `rg -n 'CLAUDE_CODE_DONT_INHERIT_ENV'`.
□ full inheritance on the main spawn □ `GIT_EDITOR=true` □ `CLAUDE_CODE_EXECPATH` set □ snapshot
exports `PATH` only.

## Search-tool wrappers (rg / find / grep)

The snapshot injects shell functions named `rg`, `find`, and `grep` that shadow PATH and re-exec the
`claude` binary with a forced `argv[0]`, so that one multi-call (busybox-style) binary acts as
ripgrep, bfs, or ugrep:

    rg --version    -> ripgrep
    grep --version  -> ugrep
    find --version  -> bfs

"Shadow" means shell-function precedence: a function named `grep` is resolved before any `grep` on
PATH. `type -a grep` shows the function first, then the system grep; `command grep` still reaches the
real tool. The three tools are compiled into the single claude executable — there are no separate
`bfs`/`ugrep`/`rg` binaries on disk.

Wrapper shape (inspect at runtime with `declare -f rg find grep` inside the Bash tool):

- The wrapper resolves the claude binary via `CLAUDE_CODE_EXECPATH`, falling back to the native
  install location (`~/.local/bin/claude`); if neither is executable it falls back to
  `command <name>` (the real tool). It re-execs the binary with `exec -a <argv0>` (bash) or
  `ARGV0=<argv0>` (zsh / Windows). The `argv[0]` values are the implementation names — `rg`,
  `ugrep`, `bfs` — which are the multi-call binary's dispatch keys; invoking the binary with an
  `argv[0]` of `grep` or `find` does not dispatch.
- `grep` preset flags: `-G --ignore-files --hidden -I`, plus `--exclude-dir=` for each of
  `.git .svn .hg .bzr .jj .sl`. It also has a `case` guard that defers to system `grep` for
  ugrep-only / config-style flags (`-*-filter*`, `-*-pager*`, `-*-view*`, `-*-config*`, `---*`,
  `-@*`, and similar).
- `find` preset flags: `-S dfs -regextype findutils-default`.
- `rg` carries no preset flags.

Gating and asymmetry:
- `find`/`grep` shadowing requires the native build, an entrypoint other than `local-agent`, and
  the first-class search tools not being opted in: naming `Grep` or `Glob` in `--tools` /
  `--allowedTools` sets a `searchToolsOptIn` flag (grep that name) that suppresses the shadowing.
  When enabled, they shadow the system tools unconditionally (each preceded by `unalias find` /
  `unalias grep`). Installing a standalone `bfs` or `ugrep` does not change `find`/`grep` here —
  the wrappers are hardwired to the embedded ones; the installed copies are reachable only by
  their own names. The npm build does not bundle bfs/ugrep.
- `rg` is a fallback, not a shadow: the snapshot's guard writes the fallback only when no `rg` is
  on PATH (the generated snapshot line is
  `if ! (unalias rg 2>/dev/null; command -v rg) >/dev/null 2>&1; then`). A user's own ripgrep wins.
  The fallback's shape follows the resolver mode (`RIPGREP.md`): embedded mode injects a wrapper
  function (heredoc marker `RIPGREP_FUNC_END`); system mode injects `alias rg='<absolute path>'`
  pointing at the rg the resolver found. Rationale: system find/grep vary across platforms (BSD vs
  GNU) so a consistent implementation is forced; ripgrep behaves the same everywhere, so a
  user-installed copy is fine.

Re-location: `rg -n 'exec -a'`, `rg -n 'ignore-files'`, `rg -n 'regextype'`,
`rg -n 'FIND_GREP_FUNC_END'`, `rg -n 'RIPGREP_FUNC_END'`, `rg -n 'searchToolsOptIn'`.
Tripwire: □ find/grep are functions in the Bash tool (native build, no Grep/Glob opt-in)
□ they re-exec via `CLAUDE_CODE_EXECPATH` with `~/.local/bin/claude` fallback □ grep excludes the
six VCS dirs □ find uses bfs dfs □ rg fallback written only when absent on PATH (function or alias
by resolver mode) □ `command grep` reaches the system tool.

## Ripgrep config: Bash-tool rg vs the Search tool

On the native build the resolver (see `RIPGREP.md`) yields embedded ripgrep invoked with
`--no-config`, which suppresses the user's `~/.ripgreprc` / `RIPGREP_CONFIG_PATH`. That
`--no-config` reaches the internal Grep/Glob tools and the `@`-file suggestion fallback, but not
the Bash-tool `rg` wrapper, which is built from the binary's `argv0` alone and carries no extra
args. Consequences:

- Claude's Search tool ignores the user's ripgrep config — an intentional isolation of internal
  search from arbitrary user config.
- The Bash-tool `rg` honours the user's ripgrep config, when `RIPGREP_CONFIG_PATH` is present in
  Claude's launch environment.
- `USE_BUILTIN_RIPGREP=0` (with `rg` on PATH) forces system mode for both, so the user's config
  applies everywhere; it only takes effect when a system `rg` is actually found.

Re-location: `rg -n 'no-config'`, `rg -n 'USE_BUILTIN_RIPGREP'`, plus `declare -f rg` in the Bash
tool to confirm the wrapper carries no `--no-config`.

## Landmark index

| Concept              | Grep anchor                              | Expected shape                                            |
|----------------------|------------------------------------------|----------------------------------------------------------|
| Snapshot generator   | `shell-snapshots`, `SNAPSHOT_FILE=`      | sources user config; `# Functions`/`# Aliases` sections  |
| Snapshot filename    | `snapshot-`                              | `snapshot-<shell>-<ts>-<rand>.sh`                        |
| Snapshot telemetry   | `shell_snapshot_create`                  | emitted after generation                                 |
| Search wrappers      | `CLAUDE_CODE_EXECPATH`, `FIND_GREP_FUNC_END` | function templates re-execing the claude binary       |
| rg fallback          | `RIPGREP_FUNC_END`                       | function (embedded) or alias (system), PATH-guarded      |
| shadowing opt-out    | `searchToolsOptIn`                       | Grep/Glob CLI opt-in disables find/grep shadowing        |
| grep presets         | `ignore-files`                           | `-G --ignore-files --hidden -I --exclude-dir=…`          |
| find presets         | `regextype`                              | `-S dfs -regextype findutils-default`                    |
| stdin redirect       | `< /dev/null`                            | appended at eval level for safe commands                 |
| extglob disable      | `extglob` / `NO_EXTENDED_GLOB`           | prepended before eval                                    |
| env additions        | `CLAUDECODE`, `GIT_EDITOR`               | added on the command spawn                               |
| ripgrep config       | `no-config`, `USE_BUILTIN_RIPGREP`       | embedded mode passes `--no-config`; see RIPGREP.md       |

## Tripwire checklist (re-verify on a new version)

□ command runs via a `-c` shell, no `-l` when a snapshot exists
□ snapshot generated per session under `shell-snapshots/`, sourced per command
□ stdin `< /dev/null` for safe commands; skipped for heredocs / existing `<`
□ full env inheritance; `GIT_EDITOR=true`, `CLAUDECODE=1`, `CLAUDE_CODE_EXECPATH` set
□ rg/find/grep wrappers present (native build); grep excludes six VCS dirs; find uses bfs dfs
□ rg fallback only when absent on PATH; find/grep shadowed unless Grep/Glob opted in via CLI
□ embedded ripgrep gets `--no-config`; Bash-tool `rg` does not

## Per-release notes

- 2.1.207: behavioral model above verified. The `searchToolsOptIn` gate is present since at least
  2.1.165; the alias-form rg fallback and the `~/.local/bin/claude` wrapper fallback since at
  least 2.1.119 (earliest local version). The earlier revision of this doc predates documenting
  them.
- 2.1.165: behavioral model above verified.
- ≤ 2.1.76: piped commands used a token-level `< /dev/null` insertion before the first pipe, which
  mis-redirected the pipeline; superseded by the current eval-level redirect.
- ≤ 2.1.116: the npm build did not bundle bfs/ugrep, so it did not shadow `find`/`grep`.
