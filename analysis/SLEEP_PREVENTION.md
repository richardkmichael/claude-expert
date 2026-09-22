Verified against: cli.prettier.js 2.1.280 (2026-09-22)

# Sleep prevention (`caffeinate`)

How the CLI keeps a Mac awake while it works, and which kinds of work it does not cover. The public
Claude Code docs do not describe this behavior. The only documented sleep control is the Desktop
app's "Keep computer awake" setting, which is a separate implementation.

## Behavioral model

- One sleep inhibitor per process. It is reference-counted: the first acquire starts it, and the
  last release schedules it to stop.
- macOS only. It spawns `caffeinate -i -t 300`. `-i` asserts `PreventUserIdleSystemSleep`, so it
  blocks idle system sleep only. It does not block display sleep, lid-close sleep, or a sleep the
  user requests. `-t 300` makes each `caffeinate` exit on its own after 5 minutes if Claude Code
  dies without cleaning up.
- Renewal. While the inhibitor is held, a 240 s interval kills the current `caffeinate` with
  SIGKILL and spawns a new one, so there is always a live process with a fresh 300 s timeout. In
  `pmset -g log`, this shows as a `ClientDied` entry every 4 minutes with a duration of `00:03:59`.
- Release. When the reference count reaches zero, a 30 s grace timer starts. If nothing acquires
  the inhibitor again before the timer fires, the renewal interval stops and `caffeinate` is
  killed. The last `ClientDied` in `pmset -g log` then reports `[System: No Assertions]`.
- Exit. A cleanup handler registered on first spawn force-stops the inhibitor when the process
  exits.
- Other platforms. The class has a `linuxInhibitor = "systemd-inhibit"` field, but spawn-argument
  selection returns nothing for any platform other than macOS. Linux and Windows get no sleep
  prevention.

## When it is held

There is exactly one acquire site: the interactive session-status hook. The same hook also writes
the session-presence PID-file status and the terminal-title spinner. The hook acquires when the
session status becomes `busy` and releases when the status leaves `busy`.

The status is determined in this order:

1. `waiting` if anything is waiting on the user: a queued elicitation, a top-level dialog, a
   pending worker or sandbox request, or a local JSX command that is open while no response is
   streaming and no delegated work is active.
2. Otherwise `busy` if the main turn is loading, or if delegated work is active.
3. Otherwise `idle`. An `idle` session that has a running `local_bash` task is reported as `shell`
   for presence and title only. `shell` does not acquire the inhibitor.

Delegated work is active when any task in app state matches all of these conditions:

- The type is one of `local_agent`, `remote_agent`, `in_process_teammate` or `local_workflow`.
- The status is not terminal.
- It is not an `in_process_teammate` with `isIdle` set. A teammate is marked idle at the end of
  each of its turns, including a turn that ends while the teammate waits on its own background
  Bash task.
- It is not a `remote_agent` with `isLongRunning` set.

These do not hold the inhibitor:

- Background Bash tasks (`run_in_background`, type `local_bash`), in the main session or started by
  a teammate.
- Monitors (`monitor_mcp`, `monitor_ws`), MCP tasks (`mcp_task`), and `dream`.
- Idle in-process teammates, and long-running remote agents.
- A session that is waiting on a permission prompt or dialog (`waiting`).
- An open Remote Control connection. Nothing in the remote-control path calls the inhibitor.
- Non-interactive runs (`-p`, SDK). The only acquire site is in the interactive UI.

A turn that ends while a background task is still running therefore releases the inhibitor. With
a short `pmset` idle-sleep timer, the Mac can sleep about 30 s after that, plus the system's own
idle timeout. A sleeping Mac drops the Remote Control connection.

## Relocation recipe

- Inhibitor class: `rg -n 'Restarting sleep inhibitor to maintain prevention'`. The enclosing class
  also contains `Started ${...} to prevent sleep`, `Stopped sleep inhibitor, allowing sleep`,
  `sleep inhibitor spawn error:` and `linuxInhibitor = "systemd-inhibit"`. The three numeric
  constants just above it are the `-t` seconds (300), the renewal interval (240000) and the release
  grace (30000).
- Spawn args: `rg -n '"caffeinate", \["-i", "-t"'`.
- Acquire site: the class module exports none of the inhibitor functions. Find the acquire and
  release wrappers directly after the class, then search for the effect that calls the acquire
  wrapper when the status equals `"busy"`. The same component logs
  `session presence: PID-file status write failed:`.
- Status function: returns `{ status: "waiting", waitingFor: ... }`, or `busy`/`idle` from
  `isLoading || delegatedActive`. The waiting reasons are the literals `"input needed"`,
  `"worker request"`, `"sandbox request"` and `"dialog open"`.
- Delegated-work predicate: search for a `Set` of `"local_agent"`, `"remote_agent"`,
  `"in_process_teammate"` and `"local_workflow"`. The predicate next to it excludes idle teammates
  and `isLongRunning` remote agents. The `local_bash` predicate right after it feeds the `shell`
  status.
- Teammate idle flag: `rg -n 'turn-end result delivery failed'`. The code nearby sets `isIdle: !0`
  on the teammate task at the end of its turn.

## Tripwires

- □ `caffeinate` args are exactly `-i -t 300`.
- □ Renewal interval 240000 ms. Release grace 30000 ms.
- □ Spawn args are returned only for `macos`.
- □ Exactly one acquire site, keyed on status `busy`.
- □ The delegated-work set is `local_agent`, `remote_agent`, `in_process_teammate`,
  `local_workflow`, and does not include `local_bash`.

## Diagnosing an unexpected sleep

`pmset -g log` shows the sequence. `ClientDied` for `caffeinate` every 4 minutes means Claude Code
held the inhibitor. A `ClientDied` with `[System: No Assertions]` followed by
`Entering Sleep state due to 'Idle Sleep'` means Claude Code released it. A release that happens
while background Bash or Monitor work is still running is expected behavior under the model above.

Workarounds, none of which Claude Code provides:

- Wrap the long command itself: `caffeinate -i <command>`.
- Hold an assertion for the life of the session: `caffeinate -i -w <claude PID>`.
- Raise the AC idle-sleep timer (`pmset -c sleep`) so that a short gap in coverage does not put the
  Mac to sleep.

## Version history

- 2.1.277: first documented. The inhibitor class and status mapping are the same in 2.1.280.
