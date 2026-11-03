---
verified: 2.1.316
verified_on: 2026-10-31
section: Tools, skills, and execution
style: landmark
scope: >-
  `run_in_background` prompt text, detached `-c` spawn, task end on shell exit, group kill, hook
  visibility
landmarks:
  - runs the command detached
  - Stops a running background task by its ID
  - '"group_kill"'
  - background_tasks
---
# Background Bash Tasks

This doc covers `run_in_background` Bash commands: what the model is told, how the shell is spawned,
how the harness decides a task has ended and how it stops one, and what hooks can see. The general
Bash spawn model (snapshot, `eval`, `< /dev/null`) is in `BASH_TOOL_EXECUTION.md`. The Stop-hook
`background_tasks` array is in `HOOKS.md`.

## Re-location recipes

| Behavior                          | Grep                                                       |
| --------------------------------- | ---------------------------------------------------------- |
| Bash description, background line | `runs the command detached`                                |
| Parameter describe                | `Set to true to run this command in the background`        |
| No-notification variant           | `Nothing notifies you when the command finishes`           |
| Long-tool-call guidance           | `use Bash with run_in_background instead`                  |
| Start result text                 | `resultType: "task"` beside `statusMessage`                |
| TaskStop prompt                   | `Stops a running background task by its ID`                |
| Shell spawn args                  | `Spawning shell without login (-l flag skipped)`           |
| Command string                    | \`pwd -P >                                                 |
| Shell task class                  | `Command killed: output file exceeded`                     |
| Group kill                        | `"group_kill"`                                             |
| Output directory                  | `.output` beside `"tasks"` in the task-output path helpers |

## What the model is told

The Bash tool description carries one background bullet, with variants chosen by session kind. The
common interactive variant:

```
- `run_in_background` runs the command detached: it keeps running across turns and re-invokes
  you when it exits. With it, `timeout` is how long the command may run in the background
  (default <d>, max <m>); at that limit it is stopped and you are re-invoked. No `&` needed.
```

Additions in some sessions: `Foreground \`sleep\` is blocked; use Monitor with an until-loop to wait
on a condition.`, `You will be notified when it exits — do not poll its output file while
waiting.`, and, where the session keeps running after a reply, `A command started with
run_in_background keeps running after your reply ends, until it finishes or reaches its timeout; a
process the shell itself detaches (nohup, &) is usually stopped a few minutes after the
reply.`When completion notices are off, the bullet instead says`Nothing notifies you when the
command finishes: read the output file that the result names to check on it.\`

The parameter describe is `Set to true to run this command in the background. With it, \`timeout\`
limits how long the command may run in the background before it is stopped (default … ms, max …
ms).`The start result is a`{"resultType":"task", "taskId", "status":"working", "statusMessage"}\`
object saying the result is delivered automatically.

TaskStop (aliases `KillShell`, `KillBash`) is described as
`Stops a running background task by its ID`, with `task_id` (and deprecated `shell_id`).

No model-facing text mentions job control, process groups, `bash -c`, how the harness detects the
end of a task, or SIGSTOP / SIGTSTP / SIGCONT. The only SIGTSTP / SIGCONT code is Claude Code's own
Ctrl+Z suspend of its UI.

## Spawn

- The shell is the user's bash or zsh, started as `<shell> -c "<command string>"`, with `-l` only
  when no snapshot exists. The command string is the snapshot `source`, env exports, then
  `eval <command>` and `pwd -P >| <cwd file>`, joined with `&&`. `CLAUDE_CODE_SHELL_PREFIX` wraps
  the whole string.
- The POSIX shell provider spawns with `detached: true`. The shell is therefore a session leader and
  process-group leader with no controlling terminal.
- For bash, job control is on. The snapshot always contains `set -o monitor` (see Snapshot shell
  options), and sourcing it turns monitor mode on in the `-c` shell, so each command the shell runs
  gets its own process group. For zsh, the snapshot replays `setopt` output, so `monitor` is on only
  if the user's config turned it on.
- Stdout and stderr go to the task output file
  `<project temp dir>/<session id>/tasks/<task id>.output`.
- The shell is a direct child of the Claude Code process, except when a sandbox wrapper argv is used
  (the wrapper is then the child). On Linux, cgroup placement uses an `exec` trampoline that keeps
  the same PID.
- The same spawn serves foreground and background commands. Backgrounding changes only bookkeeping
  (status `backgrounded`, output kept in the file).

## When a task ends

The task ends on the shell process's `exit` event, nothing else. On exit the status becomes
`completed`, the result records the exit code, and the completion notification is queued. Where
process following is active (Linux), a process group still alive after the shell exited is recorded
as `leftRunningPgid`.

Whether a shell returns when a child is stopped is shell behavior, not Claude Code's. With monitor
mode on, which the bash snapshot forces, bash's wait returns for a stopped job (status 128 + the
signal number), the shell runs its next command and exits, and the task is marked ended. The stopped
job's process group is then orphaned and the kernel sends it SIGHUP then SIGCONT. Claude Code sends
neither signal itself. Without monitor mode, a shell keeps waiting for a stopped child, so the task
stays running.

## Snapshot shell options

The bash snapshot dump is `set -o | awk '$2 == "on" || $1 == "monitor" {print "set -o " $1}'`, so it
records every option that is on, plus `set -o monitor` whatever monitor's state. The snapshot is
generated by a non-interactive `bash -c -l` (execFile, pipes, no `-i`), where monitor is off, so the
line comes from the explicit `monitor` clause, not from the user's config. zsh uses
`setopt | sed 's/^/setopt /'`, which records only what is set. The previous filter,
`set -o | grep "on"`, matched by substring and so also emitted `set -o monitor` (and
`set -o onecmd`) whatever their state.

Nothing in the command string turns monitor back off: the bundle contains no `set +m`. The snapshot
is not configurable (no setting skips it, and `.bashrc` cannot keep the line out because the clause
ignores the option's state). Snapshot generation runs with `CLAUDECODE=1`, `GIT_EDITOR=true` and
`SHELL` set over Claude Code's child environment, so an rc file can detect it.

The session environment script is the one user-controlled hook point after the snapshot. Each bash
command string runs `source <snapshot>`, then the concatenated contents of the file named by
`CLAUDE_ENV_FILE` (when set in Claude Code's environment) and of the hook env files under
`session-env/<session id>/` (`setup|sessionstart|cwdchanged|filechanged-hook-<n>.sh`), then
`eval <command>`. For bash the contents are inserted verbatim (only the PowerShell path requires
plain assignments), so a `set +m` line there turns monitor off for every command. It is skipped when
the sandbox scrubs credential env.

## Stopping

TaskStop, a timeout, and session exit all use one kill: collect the shell's descendants, send
SIGTERM to the process group and each descendant, then after 1500 ms send SIGKILL to the group and
the descendants. A stopped process does not act on SIGTERM until continued, so it dies at the
SIGKILL. There is no pause or resume tool. TaskStop only stops.

At session exit, background shells are killed, unless the exit hands them off to a following process
(background sessions; `CLAUDE_CODE_DISABLE_BG_EXIT_HANDOFF` turns the handoff off).

## Moving a running command to the background

Every route into the background calls `background()` on the same live shell-command object. The
process, its process group and the snapshot's monitor mode are unchanged. Only the status
(`backgrounded`) and the output handling change. The foreground tool call then returns, and
PostToolUse fires for it with the result. No hook fires when the command later ends.

| Route                                  | Marker in the Bash result (`tool_response`)        |
| -------------------------------------- | -------------------------------------------------- |
| Model passed `run_in_background: true` | `backgroundTaskId` only                            |
| User pressed Ctrl+B                    | `backgroundTaskId`, `backgroundedByUser`           |
| Queued message sent now (send-now)     | `backgroundTaskId`, `backgroundedToDeliverMessage` |
| Foreground timeout                     | `backgroundTaskId`, `timedOutAfterMs`              |
| A plugin's turn abort                  | `backgroundTaskId`, `backgroundedByTurnAbort`      |

`tool_input` is the input as the model sent it, so `run_in_background` is not rewritten after a
Ctrl+B. `tool_response.backgroundTaskId` being set is the one test that covers every route.
`backgroundOutputPath` is set only when the shells are kept by another process.
`CLAUDE_AUTO_BACKGROUND_TASKS` does not apply to Bash: it auto-backgrounds subagents and MCP tool
calls.

Ctrl+B backgrounds every foreground task at once: each foreground shell, then each foreground
subagent.

The key is the `task:background` action in the `Task` context, bound by default to both `ctrl+b`
and `ctrl+x ctrl+b`, and remappable in `keybindings.json`. One press that reaches Claude Code is
enough. The hint reads `ctrl+b to run in background`, or `ctrl+b ctrl+b (twice) to run in
background` (the status-line form omits `(twice)`) when the detected terminal is `tmux` and the
binding is still `ctrl+b`. The doubled form only accounts for tmux consuming the first press as its
default prefix. It does not read the tmux prefix and does not consult the attacher's mux. With
`CLAUDE_CODE_KB_COHESION_FIXES` set and the default bindings, the hint shows `ctrl+x ctrl+b`
instead, with the `ctrl+b` doubled under tmux.

## What hooks can see

- PreToolUse / PostToolUse carry only the current call. A background Bash call's PostToolUse
  `tool_response` has its own `backgroundTaskId` and `backgroundOutputPath`. No hook input carries
  other tasks, PIDs or process groups.
- Stop and SubagentStop carry `background_tasks`: `id`, `type`, `status`, `description`, and
  `command` for shells. There are no PIDs or output paths.
- No environment variable lists background shells. The output files under the session's `tasks`
  directory are on disk, but they give task ids, not PIDs.
- Process-tree discovery works. Shells are direct children of `$CLAUDE_PID`, each a session and
  group leader (`sid == pgid == pid`) whose command line starts with the snapshot `source` and
  contains `eval`. Hook shells are also children of the same process, so filter on the command line.

## Version history

- 2.1.316: first written. Corrected the same day: the bash snapshot forces `set -o monitor`, so job
  control is on for bash commands. Added the move-to-background routes, result markers and the
  Ctrl+B binding and hint.
