# Claude Code Bash Tool Execution Analysis

Version pinned: 2.1.165 (`work/2.1.165/package/cli.prettier.js`). Anchor on the quoted strings, not
the minified identifiers — the identifiers churn between versions.

For the Bash tool's `description` field -- the prompt text the model sees, including the Git Safety Protocol, commit instructions, and PR instructions -- see `PROMPTS.md` (section "Tool-description channel") and `GIT_USAGE.md`. The verbatim rendered text is in `PROMPTS_RENDERED.md` (sections "Bash tool — terse description", "Bash tool — legacy description", "Bash tool — # Git block", and "Git workflow — commit & PR").

For ripgrep binary selection (the `USE_BUILTIN_RIPGREP` env var and the system/embedded modes), see
`FILE_INCLUSION.md` (section "Ripgrep Binary Selection"). The Bash-tool-specific behaviour is
summarised under "Search-tool wrappers and ripgrep config" below.

## Executive Summary

The Bash tool runs each command in a fresh shell spawned with `-c`. Before the command runs, the
shell sources a generated snapshot that restores the user's functions, aliases, options, and PATH
plus Claude Code's own search-tool wrappers. The command itself is `eval`'d, with stdin redirected
from `/dev/null` (unless it is a heredoc or already redirects stdin) so a command that reads stdin
cannot block. The child inherits the full parent environment.

The execution core is `D9H` (413071). It gets the assembled command string from a shell-session
object (`f4K`, 412761) and spawns it with Node's `child_process.spawn` (`R4K`, 413351).

## Command Execution Method

The orchestrator `D9H(H, _, q, K)` (413071) takes the command `H`, an abort signal, a shell kind
(`"bash"` / `"powershell"`), and options (timeout, sandbox, onProgress, sessionEnvVars, …). It:

1. resolves the shell-session provider `f` (from `f4K`) for the shell kind,
2. builds the command string via `f.buildExecCommand(H, {...})` (413098),
3. spawns the shell via `R4K.spawn(E, h, {...})` (413194).

The spawn call (413194):

```javascript
[source fragment removed]
```

Key points:

- `R4K` is `require("child_process")` (413351); `R4K.spawn` is Node's built-in spawn — no execa
  wrapper.
- `E` is the shell executable (the resolved bash/zsh path, or `/bin/sh` for sandboxed powershell).
- `h` is the argument array from `f.getSpawnArgs(W)` (412830): `["-c", ...(snapshot ? [] : ["-l"]), W]`.
  The `-l` login flag is dropped when a snapshot exists, because the snapshot already captured the
  login environment.
- `cwd` (`Z`) is set explicitly; the working directory persists across calls via a temp cwd file
  (see "Command string assembly"), not via a long-lived shell.

## Stdin and Pipe Handling

The command is wrapped so its stdin comes from `/dev/null` unless that would be wrong. This prevents
a command that reads stdin (the first stage of a pipeline, or a bare `cat`) from blocking forever
waiting on a terminal that isn't there.

`buildExecCommand` (412782) computes the eval payload `X`:

```javascript
[source fragment removed]
```

The safety check `A4K(H)` (412741) returns false — i.e. do not redirect — when either:

- `Bg8(H)` (412715): the command contains a heredoc (`<<word`). The heredoc is the command's stdin.
- `TBO(H)` (412738): the command already redirects stdin (`<` not part of `<<` or `<(`).

Quoting differs by shape:

- Non-piped (`z4K`, 412729): shell-quote via `VK([H])` (or single-quote for heredocs / multi-line
  quoted strings), then append ` < /dev/null` when `M` is true.
- Piped (`q4K`, 412275): `rpO(H) + " < /dev/null"`, where `rpO` (412278) single-quotes the whole
  command (`'…'`, with internal `'` escaped as `'"'"'`). Single-quoting keeps the `|` literal so the
  later `eval` interprets the pipeline; shell-escaping it with `VK` would escape the pipes and break
  the pipeline.

The redirect attaches to the `eval`, so it applies to the whole pipeline's stdin:

```bash
eval 'echo hello | wc -l' < /dev/null
```

Heredocs and commands that already redirect stdin are left alone (`M` false → no ` < /dev/null`).

## Environment Variable Inheritance

The base environment is `wN()` (223746). In the common case `wN()` returns `process.env` unchanged
— full inheritance, no filtering. For remote / background-session / OpenTelemetry setups it returns
`process.env` plus added keys; it never removes keys. On top of the base the spawn sets:

- `GIT_EDITOR: "true"` — keep git from opening an interactive editor.
- `SHELL` — the resolved bash path for bash; left to default for other shells.
- `getEnvironmentOverrides()` (412835) → `CLAUDE_CODE_EXECPATH = process.execPath` (the claude
  binary, used by the search-tool wrappers), plus `TMUX`, and for sandboxed runs `TMPDIR` /
  `CLAUDE_CODE_TMPDIR` / `TMPPREFIX`, plus any caller-supplied session env vars.
- `pH_()` (412254) → `CLAUDECODE: "1"`, `CLAUDE_CODE_SESSION_ID`, and conditionally `AI_AGENT`,
  `CLAUDE_EFFORT`, `TRACEPARENT`.

Notes:

- The snapshot re-exports `PATH` only; other variables (e.g. `RIPGREP_CONFIG_PATH`) reach the child
  only through inherited `process.env`, i.e. only if they were exported in the environment that
  launched Claude Code.
- `CLAUDE_CODE_DONT_INHERIT_ENV` is honoured by the snapshot generator and the spawn-env probe (they
  use `{}` instead of `wN()`), but the main command spawn always uses `...wN()`.

## Command String Assembly

`buildExecCommand` (412782) joins steps with ` && ` (412810–412825):

1. `source <snapshot> 2>/dev/null || true` — when a snapshot path exists (`A`).
2. Windows only: `export TEMP=… TMP=…`.
3. An optional prefix from `Px7()`, and `export BUN_OPTIONS=…` when `CLAUDE_CODE_REMOTE` is set.
4. `zBO(H)` (412753): disable extended globbing — `shopt -u extglob` (bash) /
   `setopt NO_EXTENDED_GLOB NO_BARE_GLOB_QUAL` (zsh).
5. `eval ${X}` — the quoted command with its `< /dev/null` (from the previous section).
6. `pwd -P >| <cwdfile>` — write the post-command cwd to a temp file so the next command can resume
   in the same directory.

If `CLAUDE_CODE_SHELL_PREFIX` is set, the whole string is wrapped by `C06` (412706).

The result, for a typical piped command with a snapshot present (non-Windows, non-remote):

```bash
bash -c "source <snapshot> 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && eval 'echo hello | wc -l' < /dev/null && pwd -P >| <cwdfile>"
```

## Execution Flow

```
User command: "echo hello | wc -l"
                      ↓
Y4K: normalise ">nul" (no-op here)
A4K: no heredoc, no existing stdin redirect → safe (M = true)
                      ↓
Contains "|" and M → X = q4K(D) = 'echo hello | wc -l' < /dev/null
                      ↓
buildExecCommand joins with " && ":
  source <snapshot> ... && shopt -u extglob ... && eval 'echo hello | wc -l' < /dev/null && pwd -P >| <cwdfile>
                      ↓
getSpawnArgs: ["-c", <string>]   (no "-l" because a snapshot exists)
                      ↓
R4K.spawn(bash, args, { env: {...wN(), GIT_EDITOR, EXECPATH, CLAUDECODE, ...}, cwd, detached })
                      ↓
Child shell sources snapshot (restores functions/aliases/PATH + rg/find/grep wrappers),
evals the pipeline with stdin from /dev/null, writes cwd for the next command
```

## Environment Variable Handling Summary

| Aspect              | Details                                                                       |
|---------------------|------------------------------------------------------------------------------|
| Inheritance         | Full — `wN()` returns `process.env` (common case); never strips keys         |
| Filtering           | None in the common case; `wN()` may add remote/session/OTEL keys             |
| Added keys          | `GIT_EDITOR`, `SHELL` (bash), `CLAUDE_CODE_EXECPATH`, `CLAUDECODE`, session   |
| Sandbox impact      | Adds `TMPDIR` / `CLAUDE_CODE_TMPDIR` / `TMPPREFIX`; command wrapped by sandbox |
| Config via env      | `RIPGREP_CONFIG_PATH` etc. inherited only if in Claude's launch env          |
| CWD                 | Set via the `cwd` spawn option; persisted across calls via a temp cwd file   |

## Shell Snapshot and Injected Search-Tool Wrappers

The `source <snapshot>` step is not a static file shipped inside the binary. The binary embeds the
generator that produces the snapshot, plus the templates for Claude Code's own wrapper functions.
The snapshot file is generated at runtime, once per shell session, and written to disk.

### What you see at runtime

Inside the Bash tool, `declare -F` lists functions that are not in the user's dotfiles:

    rg, find, grep      # Claude Code search-tool wrappers
    cd, pushd, popd     # captured from the user's environment (e.g. mise / dotfiles)

`rg`/`find`/`grep` re-exec the `claude` binary with a forced `argv[0]`. That binary is a multi-call
(busybox-style) binary bundling ripgrep, bfs, and ugrep, and dispatches on `argv[0]`:

    rg --version    -> ripgrep 14.1.1
    grep --version  -> ugrep 7.5.0
    find --version  -> bfs 4.1.1

"Shadow", below, means shell-function precedence: bash resolves a function named `grep` before any
`grep` on PATH, so the function wins. `type -a grep` shows the function first, then `/usr/bin/grep`.
The real tool is not removed — `command grep` still reaches it.

The tools are bundled, not downloaded. A version "install" is a single multi-call Mach-O executable
(219,526,944 bytes for the 2.1.165 arm64 build) at `<dataDir>/versions/<version>`; ripgrep, bfs, and
ugrep are compiled into it. There are no separate `ugrep`/`bfs`/`rg` binaries on disk — all three
wrappers exec that one file with a different `argv[0]`. `strings` on the binary shows the embedded
`ugrep 7.5.0` marker.

### Lifecycle: generated once per session, sourced on every command

Anchor strings: `shell-snapshots`, `snapshot-`, `CLAUDE_CODE_EXECPATH`, `SNAPSHOT_FILE=`.

The snapshot creator (`O4K`, ~412563) runs once per shell session:

- picks the user config file by shell — `.zshrc` / `.bashrc` / `.profile` (`ug8`, ~412357)
- creates `<dataDir>/shell-snapshots/` and a file `snapshot-<shell>-<timestamp>-<rand>.sh`
- builds a generator script (`qBO`, ~412491) and runs it with `shell -c -l <generator>` (~412585)

The generator script, when run, sources the user's real config in a login shell
(`source "$K" < /dev/null`), writes `unalias -a`, then dumps into the snapshot file: user functions
(filtered to drop single-underscore completion funcs, keep double-underscore helpers), shell
options, aliases, and the captured PATH (`HBO`, ~412365; `_BO`, ~412424). It then appends Claude
Code's `rg` wrapper, and the `find`/`grep` wrappers when enabled.

Per command, the shell-session factory (`f4K`, ~412761) caches the snapshot path in a promise and
reuses it:

- `buildExecCommand` (~412782) prepends `source <snapshot> 2>/dev/null || true`, then `eval <cmd>`,
  then `pwd -P >| <cwdfile>` (cwd persisted for the next command), joined with ` && ` (~412811)
- `getSpawnArgs` (~412830) runs `shell -c <string>` and drops the `-l` login flag when a snapshot is
  present — the snapshot already captured the login environment, so each command shell is a fresh
  non-login shell that restores state by sourcing the snapshot
- if the snapshot file has gone missing, it falls back to a login shell (~412786)

Each Bash command spawns a fresh shell, and each fresh shell sources the same per-session generated
snapshot. The snapshot is the captured user environment plus Claude Code's wrappers, not a static
embedded blob.

### The wrapper template

The wrapper text is produced by `xg8` (~412281). For one tool it emits (shown for `grep`):

```bash
function grep {
  local _cc_a
  for _cc_a in "$@"; do
    case "$_cc_a" in -*-filter*|-*-pager*|-*-view*|-*-format-open*|-*-config*|---*|-@*|-*-save-config*) command grep "$@"; return ;; esac
  done
  local _cc_bin="${CLAUDE_CODE_EXECPATH:-}"
  [[ -x $_cc_bin ]] || _cc_bin=<path to claude binary>
  if [[ ! -x $_cc_bin ]]; then command grep "$@"; return; fi
  if [[ -n $ZSH_VERSION ]]; then
    ARGV0=ugrep "$_cc_bin" <preset flags> "$@"
  elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    ARGV0=ugrep "$_cc_bin" <preset flags> "$@"
  elif [[ $BASHPID != $$ ]]; then
    exec -a ugrep "$_cc_bin" <preset flags> "$@"
  else
    (exec -a ugrep "$_cc_bin" <preset flags> "$@")
  fi
}
```

Two escape hatches: the leading `case` guard (emitted only for `grep`) falls back to system `grep`
for ugrep-only / config-style flags; and `command grep` runs the real tool if the claude binary is
not executable. The zsh and msys/cygwin/win32 branches use `ARGV0=` because `exec -a` is not
available there; the bash branches use `exec -a`, in a subshell when `$BASHPID == $$`.

The three wrappers and their presets (`apO`, `tpO`, ~412314):

| Wrapper | argv[0] | Preset flags                                                              |
|---------|---------|---------------------------------------------------------------------------|
| `rg`    | `rg`    | none                                                                       |
| `find`  | `bfs`   | `-S dfs -regextype findutils-default`                                      |
| `grep`  | `ugrep` | `-G --ignore-files --hidden -I --exclude-dir={.git,.svn,.hg,.bzr,.jj,.sl}` |

The exclude-dir set is `spO` (~412703): `.git`, `.svn`, `.hg`, `.bzr`, `.jj`, `.sl`.

### Gating and the rg-vs-find/grep asymmetry

`find`/`grep` shadowing is gated on `PP()` (~283922): the native ("ant") build, and not the
`local-agent` entrypoint. The npm build (<= 2.1.116) does not bundle bfs/ugrep, so it does not
shadow them. Source comment: "Shadow find/grep with embedded bfs/ugrep (ant-native only)".

`find` and `grep` are shadowed unconditionally (each preceded by `unalias find` / `unalias grep`)
whenever `PP()` holds, overriding the system `/usr/bin/find` and `/usr/bin/grep`. There is no
discovery step — the wrappers are hardwired to `exec -a bfs/ugrep "$_cc_bin"` (the claude binary), so
installing a standalone `bfs` or `ugrep` does not change `find`/`grep` in the Bash tool; those
binaries are reachable only by their own names.

`rg` is a fallback, not a shadow. The snapshot wraps the rg definition in:

    if ! (unalias rg 2>/dev/null; command -v rg) >/dev/null 2>&1; then ... fi

so the `rg` function is defined only when no `rg` is on PATH; if the user has their own ripgrep,
Claude defers to it. Likely rationale: system find/grep vary across platforms (BSD vs GNU), so Claude
forces consistent bfs/ugrep; ripgrep behaves the same everywhere, so a user-installed copy is fine.

On the multi-call native build, `rg` resolves to a function (argv0 set). On the npm build it
resolves to an alias pointing at a bundled ripgrep path (`apO` / `chH`, ~249436).

### Search-tool wrappers and ripgrep config

The resolver `AP_` (~249686, feeding `chH` ~249436) returns one of two relevant shapes and is shared
by the Bash-tool `rg` wrapper and Claude's internal Grep/Glob (Search) tool. See
`FILE_INCLUSION.md` ("Ripgrep Binary Selection") for the full mode list; the part that matters here:

- system mode `{command: <your rg>, args: []}` — chosen when a standalone `rg` is on PATH and either
  the build is non-native or `USE_BUILTIN_RIPGREP` parses falsy (`0`/`false`/`no`/`off`, via `M4`
  ~1921). No flags are added, so the user's ripgrep config (`RIPGREP_CONFIG_PATH` / `.ripgreprc`)
  applies.
- embedded mode `{command: <claude binary>, args: ["--no-config"], argv0: "rg"}` — the native-build
  default. `--no-config` suppresses the user's ripgrep config.

`--no-config` only reaches one of the two consumers:

- The Search tool (`vA7`, ~249447) builds its argv as `[...rgArgs, ...]`, so it includes
  `--no-config`. Claude's own Search tool ignores the user's ripgrep config. This is the documented
  isolation behind the `.ripgreprc`-breaks-search failure mode (GitHub issue #7156): the internal
  search must not be affected by an arbitrary user config.
- The Bash-tool `rg` wrapper (`apO`) takes the function form `xg8("rg", argv0)` when `argv0` is set,
  which drops `rgArgs` entirely. The Bash-tool `rg` therefore has no `--no-config` — `declare -f rg`
  confirms it (`exec -a rg "$_cc_bin" "$@"`, no flags). Even the embedded rg, run via the Bash tool,
  loads `RIPGREP_CONFIG_PATH` if it is present in the environment.

In short: the Search tool treats ripgrep as an internal implementation detail and pins it with
`--no-config`; the Bash-tool `rg` is a user-facing command and honours config (when the config env
var is inherited from Claude's launch environment). To use a personal rg + config everywhere,
including the Search tool, set `USE_BUILTIN_RIPGREP=0` with `rg` on PATH (forces system mode,
`args: []`) — note the switch only takes effect if a system `rg` is actually found, otherwise it
falls back to embedded.

## Code References

| Symbol  | Line   | Anchor string                  | Purpose                                          |
|---------|--------|--------------------------------|--------------------------------------------------|
| `D9H`   | 413071 | `buildExecCommand` call        | main command execution orchestrator              |
| `f4K`   | 412761 | `buildExecCommand`             | shell session factory; caches snapshot path      |
| `R4K`   | 413351 | `child_process`                | spawn module; `R4K.spawn` at 413194              |
| `wN`    | 223746 | `process.env`                  | env base (full inheritance)                      |
| `pH_`   | 412254 | `CLAUDECODE`                   | session env additions                            |
| `Y4K`   | 412746 | `/dev/null` normalise          | normalise Windows `>nul` to `>/dev/null`         |
| `A4K`   | 412741 | heredoc / stdin check          | safe to redirect stdin from `/dev/null`?         |
| `Bg8`   | 412715 | `<<`                           | heredoc detection                                |
| `TBO`   | 412738 | `<` redirect                   | existing stdin-redirect detection                |
| `z4K`   | 412729 | `< /dev/null`                  | quote command for eval (non-piped)               |
| `q4K`   | 412275 | `< /dev/null`                  | quote command for eval (piped)                   |
| `rpO`   | 412278 | `'"'"'`                        | single-quote escaping                            |
| `zBO`   | 412753 | `extglob`                      | disable extended globbing before eval            |
| `xg8`   | 412281 | `function ${H} {`              | wrapper-function text generator                  |
| `apO`   | 412314 | rg availability check          | rg wrapper (function or alias)                   |
| `tpO`   | 412324 | `Shadow find/grep`             | find (bfs) + grep (ugrep) wrappers               |
| `spO`   | 412703 | `.git`, `.jj`                  | grep exclude-dir list                            |
| `HBO`   | 412365 | `# Functions`                  | dump user funcs/options/aliases into snapshot    |
| `_BO`   | 412424 | `RIPGREP_FUNC_END`             | append rg + find/grep wrappers + PATH            |
| `qBO`   | 412491 | `SNAPSHOT_FILE=`               | assemble the generator script                    |
| `O4K`   | 412563 | `shell-snapshots`, `snapshot-` | create snapshot once per session                 |
| `PP`    | 283922 | `local-agent`                  | gate for find/grep shadowing                     |
| `AP_`   | 249686 | `--no-config`                  | ripgrep binary/mode resolver                     |
| `chH`   | 249436 | `rgPath` / `argv0`             | resolve rg path / argv0                          |

## Conclusion

1. Each command runs in a fresh shell (`bash -c`); cwd persists via a temp file, environment via the
   sourced snapshot, not via a long-lived process.
2. Stdin is redirected from `/dev/null` at the `eval` level for both piped and simple commands,
   except heredocs and commands that already redirect stdin. This prevents stdin blocking and keeps
   pipelines intact.
3. The environment is inherited in full (`wN()` → `process.env`), with Claude-specific keys added and
   none removed.
4. The Search tool pins ripgrep with `--no-config`; the Bash-tool `rg` does not, so user ripgrep
   config applies to `rg` in the Bash tool (when the config env var is inherited) but not to the
   Search tool.
