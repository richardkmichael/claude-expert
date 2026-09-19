# Notification System

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)
Verified against: cli.prettier.js 2.1.277 (2026-09-19)

Two independent notification paths fire on every notification event:

1. Notification hook, a user-configured shell command.
2. Built-in terminal notification, OSC escape codes written to stdout.

The hook fires first, then the built-in. Neither depends on or replaces the other.

## Locating the dispatch

Grep `tengu_notification_method_used`. The single hit is in the outer notification function, which
reads the `preferredNotifChannel` setting, fires the hook, resolves a channel, emits the OSC
sequence, and records the event. Three helpers sit immediately below it:

| Role             | What it does                                                            |
| ---------------- | ----------------------------------------------------------------------- |
| Channel resolver | Maps the configured channel to an effective one, or delegates to `auto` |
| Auto-detector    | Maps the detected terminal to a channel                                 |
| Emitter          | Switches on the effective channel and writes the escape sequence        |

Splitting resolution from emission is what makes `auto` work: the auto-detector returns a channel
name, which is then emitted by the same switch that handles an explicitly configured one.

## Channel values

Grep the `preferredNotifChannel` settings enum to relocate the list.

| Value                      | Effect                                              |
| -------------------------- | --------------------------------------------------- |
| `auto` (default)           | Detect the terminal, then use its native protocol   |
| `iterm2`                   | iTerm2 OSC 9                                        |
| `iterm2_with_bell`         | iTerm2 OSC 9 plus BEL                               |
| `kitty`                    | Kitty OSC 99                                        |
| `ghostty`                  | Ghostty OSC 777                                     |
| `terminal_bell`            | BEL only                                            |
| `notifications_disabled`   | Suppress built-in notifications entirely            |

An unrecognized value resolves to `none`, and nothing is sent.

The setting takes effect without restarting. The config reader re-reads the global config file on
each call, so a change made through `/config` is picked up on the next notification.

## OSC escape sequences

Terminal-specific handlers write to stdout.

| Handler          | OSC code | Sequence pattern                                |
| ---------------- | -------- | ----------------------------------------------- |
| `notifyITerm2`   | 9        | `ESC ] 9 ; <message> BEL`                       |
| `notifyKitty`    | 99       | Three-part sequence with title, body, and focus |
| `notifyGhostty`  | 777      | `ESC ] 777 ; notify ; <title> ; <message> BEL`  |
| `notifyBell`     | none     | `BEL` (0x07)                                    |

Kitty and Ghostty both default the title to `Claude Code` when the notification carries none. Kitty
additionally receives a random numeric id per notification.

## Terminal detection

Detection runs once at startup and is recorded on the app's terminal state. Priority order:

1. `CURSOR_TRACE_ID` / `VSCODE_GIT_ASKPASS_MAIN`, giving IDE variants
2. `__CFBundleIdentifier`, giving JetBrains and other IDE bundles
3. `TERM` equal to `xterm-ghostty`, giving `ghostty`
4. `TERM` containing `kitty`, giving `kitty`
5. `TERM_PROGRAM`, returned verbatim, for example `iTerm.app`
6. `TMUX`, giving `tmux`
7. Other terminal-specific env vars such as `KONSOLE_VERSION` and `ALACRITTY_LOG`
8. `process.stdout.isTTY` false, giving `non-interactive`

The auto-detector recognizes only `Apple_Terminal`, `iTerm.app`, `kitty` and `ghostty`. Everything
else, `tmux` included, yields `no_method_available`.

Detection consults an attacher terminal before the local one, so a session attached from elsewhere
is notified according to the attaching terminal. The telemetry event carries both as `term` and
`attacher_term`.

Apple Terminal is the one detected terminal with a conditional result: it resolves to
`terminal_bell` only when the front window's settings have the bell enabled, read through
`osascript` and a `defaults export` of `com.apple.Terminal`. Otherwise it reports
`no_method_available`.

## Notification types

Grep the notification-type enum; it sits near the `preferredNotifChannel` enum in the same settings
block.

| Type                                               | Trigger                                          |
| -------------------------------------------------- | ------------------------------------------------ |
| `idle_prompt`                                      | Claude waiting for user input                    |
| `permission_prompt`                                | Tool use requires permission                     |
| `worker_permission_prompt`                         | Permission required in a worker session          |
| `auth_success`                                     | Authentication completed                         |
| `elicitation_dialog`                               | Elicitation dialog shown                         |
| `elicitation_url_dialog`                           | URL elicitation dialog shown                     |
| `agent_needs_input`                                | A background agent is blocked on input           |
| `agent_completed`                                  | A background agent finished                      |
| `push_notification`                                | Mobile push delivery                             |
| `computer_use_enter` / `_exit`                     | Computer-use session boundaries                  |
| `quota_auto_resume_fired` / `_stale` / `_disabled` | Quota auto-resume state changes                  |
| `model_refusal_fallback`                           | Model refusal triggered a fallback               |

`elicitation_complete` and `elicitation_response` appear at call sites without being members of the
enum, so treat the enum as the settings-facing list rather than the complete set.

Tripwire: the enum held 5 members at 2.1.76 and 15 at 2.1.277. Re-read it rather than trusting this
table.

## The idle notifier

At 2.1.277 the idle logic is a class, constructed with a named options object. The option names are
the landmarks; grep `hasArmedQuotaAutoResume` or `hasSeededRemotePrompt` to land on the construction
site, and `setLocalOverlayShowing` for the class body.

It subscribes to a turn snapshot exposing `isLoading`, `submitCount` and `lastQueryCompletionTime`,
and re-arms whenever any of those change.

A timer is armed only when the turn is not loading, `lastQueryCompletionTime` is non-zero, and
either `submitCount` is above zero or a remote prompt was seeded. Its delay is the idle threshold,
clamped to the 32-bit timeout ceiling.

When the timer fires, the notification is sent only if all of these hold:

    □ last interaction time is not newer than lastQueryCompletionTime
    □ turn still not loading
    □ no local overlay showing
    □ no dialog on screen
    □ no pending loop wakeup
    □ no armed quota auto-resume
    □ elapsed since lastQueryCompletionTime >= idle threshold

The threshold is the `messageIdleNotifThresholdMs` setting, default 60000. The message is
`Claude is waiting for your input`.

The last-interaction check is the interesting one: the timer is armed from the moment the response
ends, and any user activity after that point cancels the notification when the timer eventually
fires, rather than re-arming it.

## The idle return hint

A second, separate mechanism on the same class adds an in-app contextual notification rather than a
terminal notification. Grep `idle-return-hint` or `tengu_idle_return_action`.

It arms when the context is large enough, then fires after a longer idle period, showing
`new task? /clear to save <n> tokens`. Both bounds are env-configurable:

| Env var                              | Default | Meaning                                   |
| ------------------------------------ | ------- | ----------------------------------------- |
| `CLAUDE_CODE_IDLE_TOKEN_THRESHOLD`   | `1e5`   | Minimum context tokens before it arms     |
| `CLAUDE_CODE_IDLE_THRESHOLD_MINUTES` | `75`    | Idle minutes before the hint appears      |

`tengu_idle_return_action` records `hint_shown` when it appears and `hint_converted` when the user
subsequently submits a `/clear`, each with `idleMinutes`, `messageCount` and `contextTokens`.

## Notification hook path

The `Notification` hook event fires if one is configured in `settings.json`. It receives a JSON
payload on stdin including `hook_event_name`, `message`, `title`, `notification_type`, and session
context.

Hooks cannot block or suppress notifications; they are for side effects only, such as playing a
sound or sending an external message. A hook works regardless of terminal, which makes it the only
reliable approach inside a multiplexer.

## Ghostty OSC 777 on macOS

Claude Code's responsibility ends at the stdout write. What follows is Ghostty and macOS.

Ghostty suppresses visual delivery, meaning banner and sound, while its window is focused and the
surface is key. Focused, the notification is stored in Notification Centre silently. Unfocused, the
banner and sound appear as configured in System Settings. This is the standard macOS convention for
a well-behaved notification sender.

The consequence for idle notifications: if the user is looking at the Ghostty window, OSC 777 is
written and nothing visible happens. The notification surfaces when Ghostty loses focus, which is
also when it is useful. An apparent delay of a few seconds is the banner appearing on focus change,
not delivery being slow.

Setting System Settings → Notifications → Ghostty to Alerts rather than Banners keeps the banner up
until dismissed. See https://github.com/ghostty-org/ghostty/discussions/10151.

macOS silently drops the notification if Ghostty lacks notification permission. No error, no
fallback, and the code path is working correctly end to end. This is a common failure mode and it
masks unrelated configuration problems while it lasts.

Sound intermittently stops playing while the banner still appears. That is a Ghostty or macOS
issue, not a Claude Code one.

## tmux

A multiplexer swallows OSC escape codes, and detection reports `tmux` rather than the outer
terminal, so the auto-detector returns `no_method_available`. Built-in notifications do not reach
the outer terminal at all.

A Notification hook running a subprocess is the reliable path. A hook can also write the
DCS-wrapped sequence directly to `/dev/tty`, since hook stdout is captured:

```bash
#!/bin/bash
[ -z "$TMUX" ] && exit 0
read -r input
message=$(echo "$input" | jq -r '.message // "Claude Code"')
printf '\033Ptmux;\033\033]9;%s\007\033\\' "$message" > /dev/tty
```

This requires tmux 3.3+ with `allow-passthrough on` in `~/.tmux.conf`. Wrapping OSC sequences in DCS
passthrough when `$TMUX` is set is a standing feature request:
https://github.com/anthropics/claude-code/issues/19976

## Version history

- 2.1.76: `ghostty` is offered in the settings enum but absent from the channel switch, so
  configuring it silently sends nothing and OSC 777 is reachable only through `auto`. Reported as
  https://github.com/anthropics/claude-code/issues/19979. Forcing `iterm2` was the workaround.
- 2.1.277: fixed. The dispatch is split into resolver, auto-detector and emitter, and `ghostty` is
  accepted on both the forced and auto paths. Idle logic extracted into a class with named
  dependencies. Notification type enum grown to 15 members. Attacher-terminal detection and the
  `attacher_term` telemetry field added. Idle return hint added.
