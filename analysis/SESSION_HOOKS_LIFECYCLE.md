# SessionStart / SessionEnd Lifecycle and the Hook Process

Verified against: cli.prettier.js 2.1.316 (2026-10-31)

This doc covers when SessionStart and SessionEnd fire, how shutdown reaches SessionEnd, how a
command hook process is spawned, and how background (agent-view) sessions change the process and
environment a hook sees. It is written for using these hooks to supervise an external per-session
process. Event schemas and the general hook environment are in `HOOKS.md`. Background-session
respawn is in `BACKGROUND_SESSIONS_RESPAWN.md`.

## Re-location recipes

| Behavior                     | Grep                                                                    |
| ---------------------------- | ----------------------------------------------------------------------- |
| SessionStart input builder   | `hook_event_name: "SessionStart"`                                       |
| SessionEnd executor          | `hook_event_name: "SessionEnd", reason:`                                |
| SessionEnd time budget       | `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS` (the budget functions follow) |
| Shutdown sequence            | `executeSessionEndHooks: ` (dynamic import inside the shutdown method)  |
| Signal handlers              | `"shutdown_signal", { signal: "SIGHUP"`                                 |
| Orphan check                 | `signal: "orphan_detected"`                                             |
| Interactive startup dispatch | `kind: "session-start",` with `source: "startup"`                       |
| First-prompt wait spinner    | `Running SessionStart hooks`                                            |
| Command hook spawn           | `has both "args" and whitespace in "command"` (runner prologue)         |
| Per-spawn hook env           | `CLAUDE_CODE_CHILD_SESSION: "1"`                                        |
| Attended predicate           | `CLAUDE_CODE_SESSION_KIND` compared with `"daemon-worker"`              |
| Background worker env        | `CLAUDE_CODE_SESSION_KIND: "bg"` beside `CLAUDE_BG_BACKEND: "daemon"`   |

## Source and reason values

SessionStart `source` is one of `startup`, `resume`, `clear`, `compact`, `fork`. SessionEnd `reason`
is one of `clear`, `resume`, `logout`, `prompt_input_exit`, `other`.

| Trigger                                     | Events, in order                                                       |
| ------------------------------------------- | ---------------------------------------------------------------------- |
| Fresh `claude`                              | SessionStart `startup`                                                 |
| `claude --resume` / `--continue`            | SessionStart `resume`, or `fork` with `--fork-session`                 |
| `/clear`                                    | SessionEnd `clear` (old id), then SessionStart `clear` (new id)        |
| `/resume` to another conversation           | SessionEnd `resume` (old id), then SessionStart `resume` or `fork`     |
| Compaction (manual or auto)                 | SessionStart `compact` only; no SessionEnd                             |
| `/exit`, double Ctrl+C, double Ctrl+D       | SessionEnd `prompt_input_exit`                                         |
| `/logout`                                   | SessionEnd `logout`                                                    |
| SIGINT / SIGTERM / SIGHUP, orphan detection | SessionEnd `other`                                                     |
| Plugin installed mid-session                | SessionStart again, for the new plugin's hooks only (`newPluginsOnly`) |

`/clear` and `/resume` stay in the same process, so the process id does not change while the session
id does. The SessionEnd for `/clear` and `/resume` is bounded by the same time budget as the exit
path.

## Shutdown and signals

All exits go through one shutdown method whose reason defaults to `other`. It arms a failsafe
force-exit at `max(5000, budget + 5000)` ms, flushes, then runs SessionEnd hooks under
`AbortSignal.timeout(budget)`, then exits. SessionEnd is skipped only for a warm spare that was
never claimed.

Signal handling:

- SIGINT: shutdown, exit 0. In the TUI, Ctrl+C is read as a key in raw mode, so this handler matters
  only for an externally sent SIGINT.
- SIGTERM: shutdown, exit 143.
- SIGHUP in a foreground session: shutdown, exit 129. A closed terminal therefore runs SessionEnd
  with reason `other`.
- SIGHUP in a background worker (`CLAUDE_BG_BACKEND=daemon`): ignored, unless the worker owns its
  controlling terminal.
- Orphan check: every 30 s while stdin is a TTY, a non-writable stdout or non-readable stdin
  triggers shutdown with exit 129.
- Print mode registers its own SIGINT/SIGTERM handlers, which take precedence.

SessionEnd budget:

- Per hook: the hook's own `timeout` (seconds) if set, else 1500 ms, or
  `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS` when set.
- Overall: `max(1500, min(largest configured SessionEnd timeout, 60000), env override)`, with the
  env override capped at one hour. When an organization defines SessionEnd hooks, the env value is
  read through the managed path.
- A hook still running at the deadline is aborted. A SessionEnd hook that does more than a quick
  call needs an explicit `timeout`.

## SessionStart blocking

Interactive startup dispatches SessionStart `startup` early and does not await it before the first
render. The TUI renders and accepts typing. Submitting the first prompt while the hooks are still
running shows `Running SessionStart hooks…` and holds the query until they finish. A quick hook
completes before the first model request, not necessarily before the prompt is drawn.

Print mode and SDK sessions also run SessionStart: `-p` dispatches `startup` (or the resume path's
`resume` / `fork`), and SDK hosts start it at session claim. Hooks are skipped entirely in bare
mode.

## Command hook process

Shell form (no `args`): `spawn(command, [], { shell: true, detached: true, … })` on macOS and Linux,
so the command runs under `/bin/sh -c`, optionally wrapped by `CLAUDE_CODE_SHELL_PREFIX`. Exec form
(`args` present) spawns the program directly. On Windows, `detached` is false and the shell is Git
Bash or PowerShell.

Consequences on POSIX:

- `detached: true` puts the hook in its own session and process group, so it has no controlling
  terminal. `/dev/tty` is unavailable.
- The hook's parent is either `/bin/sh` or, when the shell execs a single simple command, the Claude
  Code process itself. `$PPID` is therefore not a reliable Claude PID.
- `CLAUDE_PID` in the hook env is `process.pid` of the process that runs the hooks, the session's
  own process. Use it.

The hook env is Claude Code's environment (credential and telemetry scrubs applied, and the
background-session variables `CLAUDE_CODE_SESSION_KIND`, `CLAUDE_BG_*`, `CLAUDE_CODE_SESSION_NAME`
removed), plus the per-spawn variables listed in `HOOKS.md`. `TMUX` and `TMUX_PANE` pass through
when the session process has them.

Distinguishing session kinds from a hook. The hook input has no interactive flag.

| Signal                         | TUI   | `-p`      | SDK (TS/Py)         | VS Code / Desktop | Background worker |
| ------------------------------ | ----- | --------- | ------------------- | ----------------- | ----------------- |
| `CLAUDE_CODE_SESSION_ATTENDED` | `1`   | `0`       | `0`                 | `1`               | `0`               |
| `CLAUDE_CODE_ENTRYPOINT`       | `cli` | `sdk-cli` | `sdk-ts` / `sdk-py` | host value        | inherited         |

`CLAUDE_CODE_SESSION_ATTENDED` is `0` whenever `CLAUDE_CODE_SESSION_KIND` is `bg`, `daemon` or
`daemon-worker`. Otherwise it is `1` for an interactive session or an attended host entrypoint.

## Background sessions

A background session runs as its own Claude Code process under a per-user supervisor, inside a
terminal host (`ptyHost`) the supervisor creates. The pane the user looks at runs an attach client
(`claude attach`, agent view, or the original process after it hands off) that relays keys and
output. Entry points:

- `claude --bg`, and sessions dispatched from `claude agents`.
- `/background` (`/bg`), `←` on an empty prompt, and `Move to background and exit` in the exit
  dialog.
- `/resume` or `claude --resume` naming a session that is already running in the background.
- `/fork` (a copy runs in the background).

`disableAgentView` (setting) or `CLAUDE_CODE_DISABLE_AGENT_VIEW` turns all of this off.

Environment of the worker:

- Built from the supervisor's own environment plus an allowlisted dispatch env. The terminal
  variable list (`TERM_PROGRAM`, `TMUX`, `TMUX_PANE`, `STY`, `ZELLIJ`, `SSH_*`, and others) is
  deleted unless the dispatch env supplies it, and the dispatch allowlist does not include them.
  `TMUX` and `TMUX_PANE` are therefore absent in hooks of a background session.
- `CLAUDE_CODE_SESSION_KIND=bg` and `CLAUDE_BG_BACKEND=daemon` are set on the worker, but child
  processes, hooks included, have them removed.
- The attaching terminal's mux and tmux socket reach the worker as attacher state, which Claude Code
  uses for its own escape-sequence wrapping. Hooks cannot read it.

Lifetime: the worker PID (`CLAUDE_PID` in its hooks) is the session's process, unrelated to any
pane. It outlives detach. The supervisor stops an idle unattached worker after about an hour, which
runs SessionEnd in the worker. A later attach or reply starts a new worker with a new PID and a new
SessionStart. Backgrounding a foreground session ends the foreground process with SessionEnd
`prompt_input_exit`, and the worker then runs its own SessionStart.

## Version history

- 2.1.316: first written. Recorded event order, signal handling and SessionEnd budget, interactive
  SessionStart non-blocking render, hook spawn mode (`detached`, `/bin/sh -c`), `CLAUDE_PID`,
  attended/entrypoint discriminators, and the background worker's terminal-env stripping.
