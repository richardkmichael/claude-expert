# Claude Code Analysis - Notification System

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

## Overview

Claude Code has two independent notification paths that both fire on every
notification event:

1. Notification hook — a user-configured shell command
2. Built-in terminal notification — OSC escape codes written to stdout

The entry point is `Bg()` at line 348327:

```
Bg(notificationObject, context)
 ├─ await Mg()    →  Notification hook (fires if configured; independent of channel)
 └─ await H0Y()  →  Built-in terminal notification (OSC escape codes to stdout)
```

The hook fires first, then the built-in. Neither path depends on or replaces the
other.

## Notification Types

Notifications are triggered by several events (line 500415):

| notification_type    | Trigger                                 |
|----------------------|-----------------------------------------|
| `idle_prompt`        | Claude waiting for user input (60s idle)|
| `permission_prompt`  | Tool use requires permission            |
| `auth_success`       | Authentication completed                |
| `elicitation_dialog` | Elicitation dialog shown                |
| `elicitation_complete` | Elicitation completed                 |

The `idle_prompt` notification fires via a `setTimeout` of `messageIdleNotifThresholdMs`
(default 60 000 ms). It also re-checks elapsed time inside the callback before
firing. See `SETTINGS.md` for details on that setting.

## idle_prompt Firing Conditions (line 593589)

All of the following must be true for `idle_prompt` to fire:

| Variable     | Meaning                                    | Condition       |
|--------------|--------------------------------------------|-----------------|
| `Jq`         | Claude is loading/streaming                | must be `false` |
| `SK`         | Turn counter (increments on user submit)   | must be `> 0`   |
| `Z5`         | Timestamp when last response ended         | must be `> 0`   |
| `sb() > Z5`  | User active after last response            | must be `false` |
| `O7`         | Active local JSX UI (slash command dialog) | must be falsy   |
| `Z_.current` | Internal ref (pending operation)           | must be `void 0`|
| elapsed      | `Date.now() - Z5`                          | must be `>= messageIdleNotifThresholdMs` |

### Key State Variables (identified via minified code)

| Minified | State declaration (line) | Meaning                                    |
|----------|--------------------------|--------------------------------------------|
| `Z5`     | `useState(0)` — line 592531, setter `N_` | Timestamp of last response end |
| `SK`     | `useState(0)` — line 592499, setter `mq` | User submission counter        |
| `Zq`     | `useState(T98())` — line 592451, setter `Lj` | Current prompt input text  |

### Timing Analysis

`N_(Date.now())` — the `Z5` setter — is called at line 593175 inside the
`finally` block of `pD()` (the query handler), i.e. when streaming **ends**.

`LA6(true)` — which sets `lastInteractionTime = Date.now()` — is called by
`useEffect([Zq, SK])` at line 593578. This fires when:
- `SK` increments (user **submits** a message, via `mq()` in `GW` at line 593332)
- `Zq` changes (user types or input is cleared)

The expected timeline for a normal exchange:

```
T1  user submits  →  SK++, Zq cleared  →  lastInteractionTime = T1
T2  response ends →  N_(T2)            →  Z5 = T2   (T2 > T1)

After timeout fires:
  sb() = T1  <  T2 = Z5  →  sb() > Z5 is False  →  notification fires
```

### Unresolved: onRender() activity bump

`rh1()` is called on every Ink render (line 150648). It calls `ss8()`
(which updates `lastInteractionTime`) only if `nh1 === true`. `nh1` is set
to `true` by `LA6(false)`. If `LA6(false)` is called during response
streaming, `nh1` becomes `true` and the next render after T2 would set
`lastInteractionTime = T2 + ε > Z5`, making `sb() > Z5` true and
suppressing the notification. Whether `LA6(false)` is called during
streaming was not determined.

## Built-in Terminal Notification Path

`H0Y()` at line 348337 dispatches on `preferredNotifChannel`:

```javascript
[source fragment removed]
```

In "auto" mode, `j0Y()` at line 348360 reads `s8.terminal` to pick the handler:

```javascript
[source fragment removed]
```

### OSC Escape Sequences

Terminal-specific handlers write escape sequences to stdout via `sW()`:

| Handler          | OSC code | Sequence pattern                                 |
|------------------|----------|--------------------------------------------------|
| `notifyITerm2`   | 9        | `ESC ] 9 ; <message> BEL`                       |
| `notifyKitty`    | 99       | Three-part sequence with title, body, focus      |
| `notifyGhostty`  | 777      | `ESC ] 777 ; notify ; <title> ; <message> BEL`  |
| `notifyBell`     | —        | `BEL` (0x07)                                     |

All sequences are written via `stdout.write()`.

### Ghostty OSC 777: Observed Behaviour on macOS

Claude Code's responsibility ends at the `stdout.write()` call. What follows is
handled by Ghostty and macOS.

Ghostty intentionally suppresses visual notification delivery (banner + sound)
when its window is focused, via:

```
!window.isKeyWindow || !surface.focused
```

When focused: the notification is silently stored in Notification Centre only —
no banner, no sound. When unfocused: the full banner and sound appear as
configured in System Settings. This is the standard macOS convention for
well-behaved notification senders.

Consequence for Claude Code idle notifications: if the user is actively looking
at the Ghostty window, the `idle_prompt` notification fires and OSC 777 is
written, but nothing visible occurs. The notification only appears (with sound)
when Ghostty loses focus — which is also when it is actually useful.

The apparent 3–5 second delay is because the notification was already delivered
to Notification Centre; the banner appears when the user switches away from
Ghostty, not at the moment of delivery.

Setting System Settings → Notifications → Ghostty to "Alerts" (sticky) rather
than "Banners" (auto-dismiss) ensures the banner persists until dismissed.

See https://github.com/ghostty-org/ghostty/discussions/10151 for details.

The `preferredNotifChannel` setting takes effect immediately without restarting
Claude Code — changing it via `/config` is picked up on the next notification
because `k1()` (the config reader) re-reads `~/.claude.json` from disk on each
call.

Sound intermittently stops playing even though the banner still appears. This
appears to be a Ghostty or macOS bug, not a Claude Code issue.

TODO: Investigate Ghostty's `UNNotificationContent` construction — specifically
whether sound, badge, and interruptionLevel are set correctly, and whether the
focus-suppression logic could be made configurable.

## Notification Hook Path

`Mg()` fires the user-configured `Notification` hook event (if one is set up in
`settings.json`). It receives a JSON payload on stdin including `hook_event_name`,
`message`, `title`, `notification_type`, and session context.

Hooks cannot block or suppress notifications — they are for side effects only
(playing sounds, sending external messages, etc.). A hook works regardless of
which terminal is in use, making it the only reliable approach when running
inside a multiplexer like tmux.

## Bug: "ghostty" Channel Value is Non-functional

The settings UI presents "ghostty" as a valid `preferredNotifChannel` option
(line 461448), but `H0Y()`'s switch statement has no `case "ghostty"`. It falls
through to `default: return "none"` — no notification is sent.

The `notifyGhostty()` function (OSC 777) is only reachable via the `"auto"` path
through `j0Y()`. The same applies to "ghostty" in the UI options list at line
461442–461449: the enum includes "ghostty" but the dispatcher does not.

Consequence: setting `preferredNotifChannel: "ghostty"` silently disables
built-in notifications. Use `"auto"` instead.

Similarly, there is no `case "ghostty"` for the forced path — if auto-detection
misidentifies the terminal (common inside tmux), there is no way to force Ghostty
OSC 777 via the channel setting.

### Fix

Add a single case to `H0Y()` at line 348348, after the `"kitty"` case:

```javascript
[source fragment removed]
```

`notifyGhostty()` already exists and is called correctly via the `"auto"` path.
The fix is a one-line missing case.

## preferredNotifChannel Values

Defined in the settings UI at line 461442:

| Value                    | Effect                                             |
|--------------------------|----------------------------------------------------|
| `"auto"` (default)       | Auto-detect terminal; use its native protocol      |
| `"iterm2"`               | Force iTerm2 OSC 9                                 |
| `"iterm2_with_bell"`     | iTerm2 OSC 9 + BEL                                 |
| `"kitty"`                | Force Kitty OSC 99                                  |
| `"terminal_bell"`        | BEL only                                           |
| `"ghostty"`              | BUG: falls to default, nothing sent                |
| `"notifications_disabled"` | Suppress built-in notifications entirely         |

## Terminal Detection (vNK(), line 53917)

`s8.terminal` is set once at startup by `vNK()`. The detection priority is:

1. `CURSOR_TRACE_ID` / `VSCODE_GIT_ASKPASS_MAIN` → IDE variants
2. `__CFBundleIdentifier` → JetBrains and other IDE bundles
3. `TERM === "xterm-ghostty"` → `"ghostty"`
4. `TERM` includes `"kitty"` → `"kitty"`
5. `TERM_PROGRAM` → returned verbatim (e.g. `"iTerm.app"`)
6. `TMUX` → `"tmux"`
7. Various other env vars (`KONSOLE_VERSION`, `ALACRITTY_LOG`, etc.)
8. `!process.stdout.isTTY` → `"non-interactive"`

Ghostty sets `TERM=xterm-ghostty`, which matches check 3. However, if Claude
Code is running inside tmux within Ghostty, tmux overrides `TERM` to
`screen-256color` or `tmux-256color`, causing check 6 to match instead —
`s8.terminal` becomes `"tmux"` and `j0Y()` returns `"no_method_available"`.

## macOS Notification Permissions

When `notifyGhostty()` writes OSC 777 to stdout, Ghostty intercepts it and
calls the macOS notification API. This requires Ghostty to have notification
permission in System Settings → Notifications → Ghostty. If permission is
absent or denied, macOS silently drops the notification — no error, no
fallback.

This is a common failure mode: the code path works correctly end-to-end but
macOS suppresses the final delivery.

## Confirmed Bug: "ghostty" Channel Value

The bug in `H0Y()` (no `case "ghostty":`) was confirmed by the following
sequence of observations:

1. With `preferredNotifChannel: "ghostty"` set → no notifications
2. Switched to `"auto"` → still no notifications (separate macOS permissions issue)
3. macOS permissions resolved → `"auto"` works; `"ghostty"` still does not

The two problems coexisted independently. Switching to `"auto"` fixed the
missing-case bug, but the macOS permission issue masked that fix until
permissions were granted. The bug is real: `"ghostty"` hits `default: return
"none"` regardless of whether permissions are in order.

This is tracked in https://github.com/anthropics/claude-code/issues/19979.
The reporter observed the same symptom (no notifications with `"ghostty"`) and
found that switching to `"iterm2"` works as a workaround — consistent with
`"iterm2"` having an explicit `case` in `H0Y()` while `"ghostty"` does not.

## tmux Considerations

When running inside tmux (or other multiplexers), OSC escape codes are typically
swallowed by the multiplexer. `s8.terminal` will likely not be detected as
"ghostty" or "kitty" either. In this environment:

- Built-in terminal notifications will not reach the outer terminal
- A Notification hook (running a subprocess like `osascript`) is the only
  reliable path for desktop notifications

The proper fix would be to detect `$TMUX` and wrap OSC sequences in DCS
passthrough format, which tmux forwards to the outer terminal:

```
# plain (current):    ESC ] 9 ; message BEL
# tmux DCS-wrapped:   ESC P tmux ; ESC ESC ] 9 ; message BEL ESC \
```

This requires tmux 3.3+ with `allow-passthrough on` (or `all`) in
`~/.tmux.conf`. This is a known feature request:
https://github.com/anthropics/claude-code/issues/19976

As a workaround until the fix lands, a Notification hook can write the
DCS-wrapped sequence directly to `/dev/tty` (hook stdout is captured by
Claude Code, so `/dev/tty` must be used explicitly):

```bash
#!/bin/bash
[ -z "$TMUX" ] && exit 0
read -r input
message=$(echo "$input" | jq -r '.message // "Claude Code"')
printf '\033Ptmux;\033\033]9;%s\007\033\\' "$message" > /dev/tty
```
