---
verified: 2.1.316
verified_on: 2026-10-31
section: Observability
style: landmark
scope: >-
  Notification triggers, channels, idle and dialog timers, terminal write path, hook
  `terminalSequence`
landmarks:
  - idle_prompt
  - preferredNotifChannel
  - tengu_idle_return_action
  - CLAUDE_CODE_DISABLE_PERMISSION_PROMPT_NOTIFY_HOOKS
  - TerminalWriteProvider
---
# Notification System

Two independent notification paths fire on every notification event:

1. Notification hook, a user-configured shell command.
2. Built-in terminal notification, OSC escape codes written to stdout.

The hook fires first, then the built-in. Neither depends on or replaces the other. The dispatch
awaits the Notification hooks to completion before it resolves and writes the channel, so a slow
hook delays the built-in OSC by its own runtime. The hook call is unconditional:
`notifications_disabled` suppresses only the built-in channel, and Notification hooks still run.

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

Tripwire: re-read the enum on a new version rather than trusting this table.

## The idle notifier

The idle logic is a class, constructed with a named options object. The option names are the
landmarks; grep `hasArmedQuotaAutoResume` or `hasSeededRemotePrompt` to land on the construction
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
fires, rather than re-arming it. The notifier sends at most once per completed query.

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

## Dialog notifications and the 6-second timer

Permission prompts, elicitations and other dialogs notify through a different timer from the idle
notifier, and the idle notifier never fires while a dialog is on screen (its `isDialogOnScreen`
gate).

In the interactive TUI, each dialog kind maps to a notification spec in a per-kind table. Grep
`Claude needs your permission"` for the shared default, and `Teammate setup needs your input` or
`A sandboxed command needs network access` for neighbouring entries. The tool-permission kind
(`kind: "permission_prompt"`) uses the default, so its Notification hook receives the generic
message `Claude needs your permission` with `notification_type: "permission_prompt"`, and no tool
name. A spec without an explicit `type` defaults to `permission_prompt`.

The dialog host mounts a notifier component per notifying dialog. That component runs a repeating
6000 ms interval. The constant is shared with the SDK timer below: grep
`CLAUDE_CODE_DISABLE_PERMISSION_PROMPT_NOTIFY_HOOKS`, follow the `setTimeout` delay to its
declaration in the hook-timeout block (beside `"SessionStart", "Setup"`), then follow that name's
other importer to the notifier. On each tick it sends only if both of these are true:

    □ at least 6000 ms since the dialog mounted
    □ at least 6000 ms since the last user interaction (keypress, paste, prompt edit)

It sends once, then stops the interval. The send is the ordinary dispatch, so the Notification hook
and the OSC channel fire together, hook first. Terminal focus is not consulted. The focus-tracking
state (DECSET 1004, recorded as `terminalFocus` on the user-presence store) gates other features,
not this one. The ticks are not reset by interaction, so a keypress during the first 6 s pushes the
send to the 12 s tick, and so on in 6 s steps. The observed delay is between 6 and 12 s after the
prompt appears, or later while the user is typing.

A dialog queued behind the visible one notifies on its first reveal instead (grep
`buried-idle-cue`).

### SDK hosts

When permission requests go to an SDK host (`can_use_tool` over structured IO, as in Claude Desktop,
the VS Code extension and `-p` with an SDK client), a separate one-shot `setTimeout` of the same
6000 ms constant fires the Notification hook only, with message
`Claude needs your permission to use <tool display name>` and type `permission_prompt`. It is
cleared when the host answers. No OSC is written on this path. Grep
`CLAUDE_CODE_DISABLE_PERMISSION_PROMPT_NOTIFY_HOOKS`, which turns that timer off entirely.

### PermissionRequest as the earlier signal

The `PermissionRequest` hook fires with no timer. In the interactive flow it starts when the dialog
is queued and races it, or runs to completion before the dialog appears when
`awaitAutomatedChecksBeforeDialog` is set. Its input carries `tool_name`, `tool_input`,
`permission_suggestions` and optional `mcp_server`, so it is a better notification source than the
dialog's Notification hook. It does not fire for person-only asks, remote-execution calls, or calls
a PreToolUse hook or rule already settled. A hook that wants only a side effect must exit without a
decision, or it resolves the prompt. See `HOOKS.md` § Permission-request timing.

## Terminal write path

All built-in notification sequences and hook `terminalSequence` values go through one writer
registered by the mounted Ink app (`TerminalWriteProvider`, whose value is Ink's `writeRaw`, a
`stdout.write`). Grep `useTerminalNotification must be used within TerminalWriteProvider`.

Every OSC is wrapped for the multiplexer before writing. The wrapper reads the attacher's mux first,
then `TMUX`, `STY` and `ZELLIJ`. Under tmux the sequence is wrapped as
`ESC P tmux; <seq with ESC doubled> ESC \`. Under GNU screen the same form is used without the
`tmux;` prefix. Zellij is passed through unwrapped. Grep `\x1BPtmux;` to relocate.

The writer stack holds only the mounted app. In `-p`, the SDK, or any process without the TUI on
screen, the write is a silent no-op.

## Notification catalogue

Only plugin notifications carry a title. Every other emitter passes `{ message, notificationType }`
with no `title`, so the Notification hook input has no `title`, and the built-in channels fall back
(see Ghostty payload). Two dispatch shapes exist:

- Full dispatch (hook, then terminal channel): the notification function whose callers pass
  `{ message, notificationType }` as the first argument.
- Hook only, no terminal write: callers of the bare Notification-hook runner (grep
  `confirmed elicitation`, `Elicitation response for server`, and the SDK permission timer).

| notification_type                    | Message                                                                                                                                   | Path      |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | --------- |
| `permission_prompt` (TUI dialogs)    | per dialog kind, table below                                                                                                              | full      |
| `permission_prompt` (SDK host timer) | `Claude needs your permission to use <display name>`                                                                                      | hook only |
| `idle_prompt`                        | `Claude is waiting for your input`                                                                                                        | full      |
| `auth_success`                       | `Claude Code login successful`                                                                                                            | full      |
| `auth_storage_failure`               | `Claude Code login needs attention: credentials may not have been saved` (transient) or `... could not be saved`                          | full      |
| `elicitation_dialog`                 | `Claude Code needs your input`                                                                                                            | full      |
| `elicitation_url_dialog`             | `Claude Code needs your input` (URL mode) or `An MCP server needs your input`                                                             | full      |
| `elicitation_complete`               | `MCP server "<server>" confirmed elicitation <id> complete`                                                                               | hook only |
| `elicitation_response`               | `Elicitation response for server "<server>": <action>` (`decline` after a blocking hook error)                                            | hook only |
| `agent_needs_input` (agent view)     | `<label> needs your input` plus `: <needs>` (needs cut at 120 characters with an ellipsis)                                                | full      |
| `agent_needs_input` (dialogs)        | `Teammate setup needs your input`; `Auto mode has a classifier billing notice to acknowledge`                                             | full      |
| `agent_completed`                    | `<label> finished` or `<label> failed`                                                                                                    | full      |
| `worker_permission_prompt`           | `<worker name or "A subagent"> needs permission for <tool name or "(unnamed tool)">`; or `... needs network access to <host or "a host">` | full      |
| `push_notification`                  | the PushNotification tool's `message` input, verbatim                                                                                     | full      |
| `computer_use_enter`                 | `Claude is using your computer · press Esc to stop` (Ctrl+C variant)                                                                      | full      |
| `computer_use_exit`                  | `Claude is done using your computer`                                                                                                      | full      |
| `quota_auto_resume_fired`            | `Usage limit reset — Claude is continuing your task`; `Usage limit available — Claude is continuing your task`                            | full      |
| `quota_auto_resume_stale`            | `Usage limit reset — press enter to continue`                                                                                             | full      |
| `quota_auto_resume_disabled`         | `Automatic continue ...` variants (turned off, 24 h horizon, continuation dropped, cap exhausted)                                         | full      |
| `plugin_notification`                | the mod's text; title is the mod's `title` or its plugin name                                                                             | full      |

`model_refusal_fallback` is a settings-enum member with no emitter found at 2.1.316. No emitter
passes a session name or project directory. `<label>` is the agent-view row label: the session's
name if set, else its intent cut to 3 words and 25 columns with an ellipsis, else a placeholder
(`current session`, `new session`, `untitled session`) or the template name.

`<tool name>` and `<host>` in the worker messages are sanitised and cut at 48 characters.

Dialog kinds each carry a notification spec (grep `Claude needs your permission"` for the table).
The default text `Claude needs your permission` applies to the tool-permission kinds
(`permission_prompt`, `permission_bash`, `permission_file`, `permission_webfetch`,
`permission_skill`, `permission_powershell`, `permission_monitor`, `permission_browser`,
`permission_ask_user_question`, `computer_use_approval`) and carries type `permission_prompt`. Kinds
with their own text, all type `permission_prompt` unless stated:

| Dialog kind                    | Message                                                                                                               |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| `permission_enter_plan_mode`   | `Claude Code wants to enter plan mode`                                                                                |
| `permission_exit_plan_mode_v2` | `Claude Code needs your approval for the plan`                                                                        |
| `permission_publish_plugin`    | `Claude Code is waiting for your answer before it publishes a plugin`                                                 |
| `goal_proposal`                | `Claude proposed a session goal`                                                                                      |
| `refusal_fallback_prompt`      | `Session paused`                                                                                                      |
| `fable_overage_consent_prompt` | `Session paused`                                                                                                      |
| `peer_inbound_approval`        | `A message from another session needs your approval`                                                                  |
| `chrome_install_upsell`        | `Claude wants to use your browser`                                                                                    |
| `chrome_install_setup`         | `Setting up Claude in Chrome`                                                                                         |
| `sandbox_network_access`       | `A sandboxed command needs network access`                                                                            |
| `managed_settings_security`    | `Managed settings need your review before they apply`                                                                 |
| `auto_mode_setup_review`       | `Auto-mode setup proposal is ready for review`                                                                        |
| `auto_mode_flagged_allow`      | `Auto-mode setup flagged some permission rules for review`                                                            |
| `mcp_elicitation`              | `Claude Code needs your input`; type `elicitation_dialog`, or `elicitation_url_dialog` when the request mode is `url` |
| `mcp_elicitation_waiting`      | `Claude Code needs your input`; type `elicitation_url_dialog`                                                         |
| `mcp_url_elicitation`          | `An MCP server needs your input`; type `elicitation_url_dialog`                                                       |

The dialog text never includes the tool name, the MCP server name or the project directory.

## Ghostty payload

The `ghostty` channel (forced, or chosen by `auto` on `TERM=xterm-ghostty`) calls the Ghostty writer
with `{ ...notification, title: notification.title || "Claude Code" }`. It writes one sequence:

    ESC ] 777 ; notify ; <title> ; <message> BEL

Title field: the notification's `title`, else the literal `Claude Code`. Only plugin notifications
carry a title, so every other notification shows `Claude Code`. Body field: the `message`.

Both fields pass through one sanitiser that replaces every character below U+0020, U+007F and U+0080
to U+009F with a space. That removes ESC, BEL, newlines and tabs, so a multi-line message becomes
one line. There is no length limit and no escaping of `;`. A `;` in the title or message is written
as-is and splits the OSC 777 payload at the terminal. The terminator is BEL, because the ST
terminator is used only when the detected terminal is `kitty`. The result is wrapped for tmux or
screen as described under Terminal write path.

For comparison, `iterm2` writes `ESC ] 9 ; <title>: <message> BEL` (just the message when there is
no title), and `kitty` writes three OSC 99 sequences (title, body, focus) with a random id.

## Hook terminalSequence

Any hook event's JSON output may carry `terminalSequence`. It is parsed in the shared hook output
processor, so no event is excluded, and is written by both the in-REPL hook runner and the
outside-REPL runner that Notification uses. Relocate with
`returned a terminalSequence that was rejected by the allowlist`.

Validation, all-or-nothing:

- Total length at most 4096 UTF-8 bytes.
- The string is a run of bare BEL and OSC sequences only. Each OSC is `ESC ]`, a numeric `Ps`,
  optional `;payload`, ended by BEL or ST (`ESC \`).
- `Ps` in {0, 1, 2, 9, 99, 777}.
- Payload control characters (C0, DEL, C1) are stripped.
- An OSC 9 body may not start with a digit unless it is the `4;<state>[;<pct>]` progress form.

A valid sequence is rebuilt (the terminator is BEL, or ST under kitty) and passed through the mux
wrapper above, so under tmux it is DCS-wrapped. A rejected one is dropped whole with a debug log.
The published hooks page says this works inside tmux. That holds only with tmux 3.3+ and
`allow-passthrough on`.

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

Detection reports `tmux` rather than the outer terminal (tmux sets `TERM_PROGRAM=tmux`), so the
`auto` channel returns `no_method_available` and nothing is written. An explicit channel such as
`iterm2` or `ghostty` is written DCS-wrapped (see Terminal write path) and reaches the outer
terminal when tmux 3.3+ has `allow-passthrough on`.

From a hook, return the sequence in `terminalSequence` rather than writing `/dev/tty`. Claude Code
wraps it for tmux itself.
