# Background Bash Tasks

Verified against: cli.prettier.js 2.1.316 (2026-10-31)

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
  process-group leader with no controlling terminal. A `-c` shell is non-interactive, so job control
  is off and everything it starts stays in its process group. No setting enables job control.
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

Whether a shell returns when a child is stopped is shell behavior, not Claude Code's. A shell
without job control normally keeps waiting for a stopped foreground child, so the task stays
running. If the shell does exit while a group member is stopped, the group is orphaned (its members
are reparented outside the session) and the kernel sends that group SIGHUP then SIGCONT. Claude Code
sends neither signal itself.

## Stopping

TaskStop, a timeout, and session exit all use one kill: collect the shell's descendants, send
SIGTERM to the process group and each descendant, then after 1500 ms send SIGKILL to the group and
the descendants. A stopped process does not act on SIGTERM until continued, so it dies at the
SIGKILL. There is no pause or resume tool. TaskStop only stops.

At session exit, background shells are killed, unless the exit hands them off to a following process
(background sessions; `CLAUDE_CODE_DISABLE_BG_EXIT_HANDOFF` turns the handoff off).

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

- 2.1.316: first written.
