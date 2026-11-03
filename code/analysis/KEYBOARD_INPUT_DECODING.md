# Keyboard Input Decoding

Verified against: cli.prettier.js 2.1.317 (2026-11-03)

How raw terminal bytes on stdin become key events, what escape-sequence dialects Claude Code
negotiates, and where the CSI-u (Kitty keyboard protocol) support stops. Also covers how keystroke
patterns in `keybindings.json` are matched against decoded events, and how `voice:pushToTalk` infers
a held key from auto-repeat rather than from key-release events.

## Summary

- The decoder is hand-rolled Claude Code code, not a runtime facility and not a live dependency. Its
  skeleton is a fork of the `parse-keypress` lineage (the shape ink vendors, itself descended from
  Node's `readline` keypress internals), extended in-tree with bracketed paste, SGR/X10 mouse, UTF-8
  continuation reassembly, CSI-u, and xterm `modifyOtherKeys`. See Provenance below; the
  bun-compiled distribution does not change this.
- Claude Code pushes Kitty progressive-enhancement flags `5` (`1` disambiguate escape codes, `4`
  report alternate keys) plus xterm `modifyOtherKeys` mode 2. It never requests `2` (report event
  types), `8` (report all keys as escape codes), or `16` (report associated text). Flags `1` alone
  are pushed only in a legacy compatibility case.
- The push happens at once for a terminal on an env-derived allowlist. Any other terminal gets it
  only if it answers a `CSI ? u` query sent just after raw-mode entry. A terminal that does not
  answer stays on legacy encodings.
- Modifier-only key events (Kitty codes 57441–57454, e.g. right Option = 57449) would be received
  and tokenized correctly, but decode to a key event with no name and an empty `key`, so they are
  dropped inertly: no text inserted, no binding matched.
- The CSI-u regex accepts alternate-key sub-parameters on the code (`<code>:<shifted>:<base>`) but
  not event types on the modifier (`;<mods>:<event>`). An event-typed sequence fails the regex and
  falls through to an inert empty-name event.
- The decoder is not gated on negotiation. A CSI-u or `modifyOtherKeys` sequence decodes the same
  whether or not Claude Code asked for it, so a terminal key binding can send one unprompted.

## Locating the decoder

Grep anchors, in the order that gets you there fastest:

- `CLAUDE_CODE_BS_AS_CTRL_BACKSPACE` and `CLAUDE_CODE_ALTGR_AS_TEXT`: these two env vars are read
  inside the keypress module, and are the cheapest proof that the module is app code rather than a
  vendored library.
- `rg -n 'type: "kittyKeyboard"'`: a single hit, in the terminal-response classifier.
- `pendingByteEvents`: appears in the parse-state object, the decode entrypoint, and the key reader
  the stdin handler drives; the fastest way to jump between them.
- `INTELLIJ_TERMINAL_COMMAND_BLOCKS` and `emitJediTermScrollBug`: the JetBrains wheel/trackpad
  workaround. It lives in a separate, nearby module; the stdin handler feeds it.

Expected shape of the module:

- A tokenizer factory (call it `makeTokenizer`) returning `{ feed, flush, reset, buffer }` over a
  VT500-style state machine with states `ground`, `escape`, `escapeIntermediate`, `csi`, `ss3`,
  `osc`, `dcs`, `apc`, `pm`, `sos`. Locate it via the CSI byte-range constants
  `PARAM_START: 48, PARAM_END: 63, INTERMEDIATE_START: 32, INTERMEDIATE_END: 47, FINAL_START: 64,
  FINAL_END: 126`.
- A decode entrypoint taking `(parseState, chunkOrNull)` and returning `[events, nextState]`. It
  owns bracketed-paste mode (`IN_PASTE`), the UTF-8 continuation-byte buffer, the Windows
  high-surrogate carry, and mouse-token re-synthesis.
- A single-sequence classifier (call it `decodeKey`) that turns one tokenized sequence into a key
  event object.
- The stdin side lives in Claude Code's ink fork, in the same module as the decoder: grep
  `rawModeEnabledCount`, `handleReadable`, `flushIncomplete`, `incompleteEscapeTimer`,
  `byteRunDeadlineAt`. The key reader flushes an incomplete escape sequence or a pending byte run
  after 50 ms of quiet, and an unterminated paste after 2000 ms.

## The key event object

Every decoded key event has this shape (field names are stable; they are read by name all over the
app):

```
{ kind: "key", name, fn, ctrl, meta, shift, option, super, sequence, raw, code, col, row }
```

The decoder also emits `kind: "mouse"`, `"response"`, `"paste"` (`{ kind: "paste", text }`, one per
bracketed paste) and `"focus"`. A key event read late gains `readLate: true`. The `super` field only
ever gets set from CSI-u / `modifyOtherKeys` / xterm-modifier bitmasks; plain legacy encodings
cannot express it.

Before reaching React, this is wrapped into a `keydown` event class with fields `key`, `name`,
`sequence`, `ctrl`, `shift`, `meta`, `superKey`, `fn`, `soloKeypress`, `readLate`. Note the renames:
`super` on the decoded event becomes `superKey` on the dispatched event, `meta` on the dispatched
event is `decoded.meta || decoded.option`, and a missing `name` becomes `""`. Relocate the boundary
with `rg -n 'this\.superKey = \w+\.super'`.

The `key` field is computed by a small normalizer. Its fallthrough order matters for the
modifier-only case:

1. name `"space"` → `" "`.
2. `ctrl` set → the name.
3. single-char sequence with code ≥ 32 and ≠ 127 → that char.
4. non-empty name → the name. When `shift` is set and the name is one character, it first tries the
   CSI-u shifted alternate, then the upper-cased name.
5. sequence starting with ESC (code 27) → `""`.
6. an SGR-mouse-shaped sequence → `""`.
7. otherwise the raw sequence.

Step 5 is what makes an unrecognized CSI sequence inert rather than garbage-inserting.

## Provenance: forked `parse-keypress`, not the runtime's readline

Worth being precise about, because the bundle is bun-compiled and it is tempting to assume the
runtime supplies this. It does not. The parser is inlined app code, and nothing in the TUI input
path reaches for the runtime's keypress machinery:

- `emitKeypressEvents`, readline's keypress entrypoint in both Node and Bun, appears nowhere in the
  bundle.
- `from "readline"` imports do appear (`rg -n 'from "readline"'`), but all are `createInterface` or
  namespace imports in other modules; none is in the module that holds the decoder and the ink stdin
  handler. The TUI path instead attaches its own `handleReadable` to the stdin `readable` event
  (`rg -n 'addListener\("readable", this\.handleReadable\)'`) and feeds the decode entrypoint.

So Bun vs Node is not the axis here. What the code actually descends from is the `parse-keypress`
package shape (what ink vendors as its own `parse-keypress`), which in turn descends from Node's
`readline` keypress internals. The markers that distinguish those two ancestors:

| Marker                                            | Node `readline` | `parse-keypress` |
| ------------------------------------------------- | --------------- | ---------------- |
| `fn` and `option` fields on the key object        | absent          | present          |
| `raw` field alongside `sequence`                  | absent          | present          |
| Field order `name, fn, ctrl, meta, shift, option` | different       | exact match      |
| Shift/ctrl-implying codes as array helpers        | inline switch   | exact match      |

The two array helpers are the cleanest fingerprint; the bundle carries both lists verbatim (relocate
with `rg -n '"\[2\$",'`):

```
shift: ["[a","[b","[c","[d","[e","[2$","[3$","[5$","[6$","[7$","[8$","[Z"]
ctrl:  ["Oa","Ob","Oc","Od","Oe","[2^","[3^","[5^","[6^","[7^","[8^"]
```

Shared with both ancestors, so not discriminating on their own but useful for relocation: the
function-key regex in the table below, the `"[[A": "f1"` … `"[Z": "tab"` lookup table, the code
assembly `[p1,p2,p4,p6].filter(Boolean).join("")`, and the modifier extraction
`(p3 || p5 || 1) - 1`.

One tell that this is a fork rather than a reimplementation: `fn` is initialized to `false` on every
construction path and never assigned `true` anywhere in the bundle. It is a dead field carried along
from upstream. `option`, by contrast, is live: set for double-ESC-prefixed sequences.

## Dialects the decoder accepts

Relocate these by grepping the regex bodies; they are literal and stable (dialect, then the regex
verbatim from the source):

```
CSI-u / Kitty:
  /^\x1b\[(\d+)(?::(\d*)(?::(\d+))?)?(?:;(\d+))?u/
xterm modifyOtherKeys format 2:
  /^\x1b\[27;(\d+);(\d+)~/
ESC-prefixed meta:
  /^(?:\x1b)([a-zA-Z0-9])$/
Function/cursor keys:
  /^(?:\x1b+)(O|N|\[|\[\[)(?:(\d+)(?:;(\d+))?([~^$])|(?:1;)?(\d+)?([a-zA-Z]))/
SGR mouse:
  /^\x1b\[<(\d+);(-?\d+);(-?\d+)([Mm])$/
X10 mouse:
  /^\x1b\[M[\x20-\x7f][\x20-\uffff]{2}$/
```

Modifier bitmask decode is the standard `param - 1` bitfield: `1 = shift`, `2 = meta`, `4 = ctrl`,
`8 = super`. Hyper and meta (Kitty bits `16` and `32`) are not broken out. SGR and X10 wheel buttons
decode to key events named `wheelup` / `wheeldown`.

Special cases inside the CSI-u and `modifyOtherKeys` paths:

- Ctrl alone with code `[` → `escape`, `m`/`M` → `return`, `i`/`I` → `tab`, `h`/`H` → `backspace`,
  each with `ctrl` cleared.
- Ctrl with a code above 127 and a base-layout alternate present → the base-layout key is used, so
  Ctrl plus a letter on a non-Latin layout decodes as the Latin letter.
- Ctrl+Meta (no Super) with a printable code → the literal character, as AltGr text. Controlled by
  `CLAUDE_CODE_ALTGR_AS_TEXT`: truthy forces it for every printable code, falsy turns it off, and
  unset means auto (non-alphanumeric codes only) inside Windows Terminal (`WT_SESSION`) and off
  elsewhere.

Legacy `0x08` decodes to `backspace`, with `ctrl` added when `CLAUDE_CODE_BS_AS_CTRL_BACKSPACE` is
truthy. Unset, the default depends on a platform check that is `win32` outside mintty and Cygwin;
the call site passes a fixed platform string, and in this macOS build that string is `darwin`, so
the default is off.

Two terminal key dialects are recognised from `TERM` (or, for an attaching client, from its
`keyDialect` capability): `st` (`st`/`stterm`) decodes an unmodified `CSI P` as `delete` rather than
`f1`, and `rxvt` builds the tokenizer with `escPrefixedKeyIsAlt`.

Also parsed, as `kind: "response"` rather than key events: DECRPM (`CSI ? <mode> ; <status> $y`),
DA1, DA2, the Kitty keyboard flags reply (`CSI ? <flags> u`), cursor position
(`CSI ? <row> ; <col> R`), theme notify (`CSI ? 997 ; <1|2> n`), cell size (`CSI 6 ; <h> ; <w> t`),
OSC, XTVERSION (`DCS > | <name> ST`), and Kitty graphics replies (`APC G … ST`).

## What gets pushed to the terminal, and when

Five constants, all built through the same CSI helper. Grep for the literal payloads
(`rg -n '\(">5u"\)'` and its neighbours):

| Payload      | Meaning                                                         |
| ------------ | --------------------------------------------------------------- |
| `CSI < u`    | Kitty progressive enhancement: pop                              |
| `CSI > 5 u`  | Kitty progressive enhancement: push flags=5 (disambiguate, alt) |
| `CSI > 1 u`  | Kitty progressive enhancement: push flags=1 (legacy case only)  |
| `CSI > 4;2m` | `modifyOtherKeys` = 2                                           |
| `CSI > 4 m`  | `modifyOtherKeys` reset                                         |

The enable string is `pop + push(5) + modifyOtherKeys(2)`, and it is empty unless the `extendedKeys`
terminal capability reads true. The `push(1)` variant is chosen only when a `legacyKitty` option is
set, which happens on the attach path (the one that prints `Attaching…`) when the version compared
there differs from the running build's own `VERSION`.

### The capability store

Terminal capabilities live in one store; relocate it with
`rg -n 'kittyKeyboard: \w+\(\w+\.terminal'`. Each capability starts either settled or pending, and a
pending one reads as a fixed default until it settles (`extendedKeys` false, `kittyKeyboard` true).
The two keyboard entries start as:

- `extendedKeys`: settled false for a background worker; settled true when the terminal is on the
  allowlist; settled false for `st` and for a VTE-based terminal older than 0.53 (`VTE_VERSION` \<
  5300, which prints unknown sequences as text); otherwise pending with `likely: false`.
- `kittyKeyboard`: settled true for a background worker; settled false for `st` and for VTE before
  0.53; otherwise pending with `likely: true`.

The allowlist (`rg -n -B9 '= \["windows-terminal"\];'`, the array just above that one-entry list):

```
["iTerm.app", "kitty", "WezTerm", "ghostty", "tmux", "windows-terminal", "WarpTerminal"]
```

The terminal name is env-derived. IDE detection runs first (Cursor, VS Code forks, JetBrains IDEs by
bundle identifier, `VisualStudioVersion`, `TERMINAL_EMULATOR=JetBrains-JediTerm` → `pycharm`). Then,
in order: `TERM=xterm-ghostty` → `ghostty`, `TERM` containing `kitty` → `kitty`, then `TERM_PROGRAM`
verbatim, then a chain of env checks (`TMUX`, `STY`, …, `VTE_VERSION` → `vte-based`, …,
`KITTY_WINDOW_ID`, `ALACRITTY_LOG` → `alacritty`, `WT_SESSION`, …), and finally `TERM` (`alacritty`,
`rxvt` or `termite` when `TERM` contains them, else `TERM` itself). Alacritty with
`TERM=xterm-256color`, no `TERM_PROGRAM` and no `ALACRITTY_LOG` is therefore named `xterm-256color`.
No name outside the allowlist enables the keys up front, `alacritty` included.

### The probe

On raw-mode entry the extended-keys mode is set (an empty string while `extendedKeys` is still
false), and if `extendedKeys` is pending a listener is armed to write the enable string when it
settles true. On the next tick the querier runs (grep `CSI ? u not asked` for it), except under
`CLAUDE_BG_BACKEND=daemon`. It sends XTVERSION (skipped for VTE before 0.53), plus `CSI ? u`
whenever `extendedKeys` or `kittyKeyboard` is pending, under a 2000 ms timer. A `CSI ? <flags> u`
reply of any value settles both `extendedKeys` and `kittyKeyboard` true, which fires the listener
and pushes the protocol mid-session; the flags value itself is only logged. If the querier's flush
completes with no such reply, `kittyKeyboard` settles false at once. Whatever is still pending when
the querier finishes (or its timer fires) settles to its `likely` value, so `extendedKeys` ends
false.

The querier then probes DECRQM 2026 (unless XTVERSION went unanswered or the terminal is
`Apple_Terminal`) and, where pending, the graphics and pixel-mouse capabilities. It logs one debug
line naming each capability's result and source: grep the debug log for `Terminal capabilities:` and
`XTVERSION:` to see what a session decided.

There is no `CLAUDE_CODE_*` env var or setting that forces `extendedKeys` or `kittyKeyboard`.
`CLAUDE_CODE_FORCE_SYNC_OUTPUT` and `CLAUDE_CODE_FORCE_TERMINAL_IMAGES` exist for the neighbouring
capabilities only. The one lever is the terminal name: a `TERM_PROGRAM` on the allowlist settles
`extendedKeys` true before the probe, unless IDE detection names the terminal first, and at the cost
of every other check that reads `TERM_PROGRAM`.

The keyboard modes are entries in the ink fork's terminal-mode stack. Entering the alt screen pushes
a second keyboard entry that re-emits the enable string there, and leaving it pops that entry;
`reassertKeys` re-sends whichever entry is current. The matching disable (`modifyOtherKeys reset` +
`pop`) is written on raw-mode exit (grep `rawModeEnabledCount`) and on the synchronous process-exit
path. The `pop` is sent whenever `extendedKeys` or `kittyKeyboard` reads true, and `kittyKeyboard`
reads true while still pending. Both the `pop` and the `modifyOtherKeys` reset are suppressed for a
terminal that prints unknown sequences (`hasUnknownSequencePrintingBug`, VTE before 0.53, or an
attaching client's `printsUnknownSequences` capability).

Two consumers ask whether extended keys can be trusted (`rg -n 'chat:sendNowHintPress'`): outside
tmux and screen, with `extendedKeys` reading true, and, in Windows Terminal, only once
`kittyKeyboard` is confirmed. When they cannot be trusted, the hint for `chat:sendNow` prefers a
binding that needs neither Super nor Ctrl/Shift+Enter, and the `canDispatchAndOpen` action is off.

## Where Kitty-protocol support stops

The CSI-u regex is `/^\x1b\[(\d+)(?::(\d*)(?::(\d+))?)?(?:;(\d+))?u/`: a numeric code with optional
`:shifted:base` alternates, one optional numeric modifier mask, then `u`. The modifier takes no
sub-parameter. Behavior against that regex:

| Sequence       | Kitty flag needed    | Matches? |
| -------------- | -------------------- | -------- |
| `CSI 13;5u`    | 1 (disambiguate)     | yes      |
| `CSI 57449;3u` | 8 (report all keys)  | yes      |
| `CSI 97;1:3u`  | 2 (event types)      | no       |
| `CSI 97:65;2u` | 4 (alternate keys)   | yes      |
| `CSI 97;1;97u` | 16 (associated text) | no       |

Both alternates are used: the key normalizer returns the shifted one for a shifted single-character
name, and the decoder uses the base-layout one for Ctrl with a non-ASCII code. Event types and
associated text still fail the match. The tokenizer is not the limitation: `:` is 0x3A, inside the
`PARAM_START: 48 … PARAM_END: 63` range, so `CSI 97;1:3u` arrives as one clean sequence token. It is
the key-decode regex that rejects it. A non-matching CSI sequence falls through the whole classifier
chain to a key event with `name: ""`, and then `key: ""` via step 5 of the normalizer: silently
dropped, not mis-inserted.

The functional-key code table handles Kitty codes 57399–57426 explicitly (keypad `0`–`9`, `.`, `/`,
`*`, `-`, `+`, keypad Enter, `=`, `,`, and keypad arrows/nav). Everything else falls to
`code >= 32 && code <= 126` or `code >= 160 && code < 55296`. Note the upper bound: 55296 is 0xD800,
the surrogate range start, so the whole Private Use Area is excluded. Consequences:

- Modifier keys (57441 left shift … 57454 ISO level5 shift; right Option/Alt = 57449) → name
  `undefined`.
- Caps/scroll/num lock, Print Screen, Pause, Menu (57358–57363) → name `undefined`.
- F13–F35 (57376–57398) → name `undefined`.
- Media keys (57428–57440) → name `undefined`.

So even with `flags = 8` pushed, standalone modifier presses would arrive, tokenize correctly,
decode to a nameless event (dispatched with `name: ""` and `key: ""`), and be discarded before
reaching any binding matcher.

## Shift+Backspace

Legacy encodings cannot carry Shift on Backspace: a terminal sends `0x7f` (or `0x08`) either way,
and both decode to a bare `backspace` (`0x08` gains `ctrl` only under
`CLAUDE_CODE_BS_AS_CTRL_BACKSPACE`). Opt+Backspace survives as `ESC 0x7f`, the ESC-prefixed form,
which decodes with `meta: true`.

Four sequences decode to `{ name: "backspace", shift: true }`, because the code-to-name table maps
both `8` and `127` to `backspace` and the modifier mask `2` is Shift:

| Sequence               | Dialect                                      |
| ---------------------- | -------------------------------------------- |
| `ESC [ 127 ; 2 u`      | CSI-u (what a Kitty-protocol terminal sends) |
| `ESC [ 8 ; 2 u`        | CSI-u                                        |
| `ESC [ 27 ; 2 ; 127 ~` | `modifyOtherKeys`                            |
| `ESC [ 27 ; 2 ; 8 ~`   | `modifyOtherKeys`                            |

The dispatched keydown has `key: "backspace"` and `shift: true`. The composer's base input treats it
as a plain Backspace: its `backspace` case branches only on `superKey` (delete to line start) and
`meta`/`ctrl` (delete word), so Shift deletes one character. The edit recorded for `prompt.edit`
carries `key: { key: "backspace", shift: true }`. Vim NORMAL mode treats it like a bare Backspace:
the `<BS>` motion, one character left, crossing to the previous line where `h` would stop.

No default keybinding names `shift+backspace`, and the binding matcher compares `shift` exactly, so
`backspace` bindings (e.g. `attachments:remove` in the `Attachments` context) do not fire on it.

A terminal that does not negotiate the protocol can still send one of these from a key binding,
since the decoder is not gated on negotiation. For Alacritty:

```toml
[[keyboard.bindings]]
key = "Back"
mods = "Shift"
chars = "\u001b[127;2u"
```

That binding applies to every program in the terminal, and a shell without a CSI-u binding of its
own receives the raw sequence.

□ Tripwire: the code-to-name table still maps `127` and `8` to `backspace`; the base input's
`backspace` case still ignores `shift`; no default binding names `shift+backspace`.

## Keybinding matching

Two functions meet in the middle; both must agree for a binding to fire.

Pattern side: a keystroke pattern is split on whitespace into chords (a pattern of exactly `" "` is
`space`), each chord split on `+` into parts. Recognized modifier words are `ctrl`/`control`,
`alt`/`opt`/`option`, `shift`, `meta`, and `cmd`/`command`/`super`/`win` (which sets `super`, not
`meta`). Recognized key aliases: `esc`, `return` → `enter`, `del` → `delete`, `space` → `" "`, and
the four arrow glyphs. Anything else becomes the key verbatim, lower-cased; the last such part wins.
The result is `{ key, ctrl, alt, shift, meta, super }`.

Note what this means for a bare modifier: `"alt"` parses successfully to
`{ key: "", alt: true, … }`. Nothing rejects it. Pattern validation has three parse errors
(`rg -n 'Empty key part in'`): an empty part (a stray `+`), a space next to `+` that leaves a press
with no key, and a non-final part that is not a modifier
(`"a" is not a modifier, so "a+b" … applies to "b" instead`). A pattern of modifiers only trips none
of them.

Event side: the dispatched keydown is normalized to the same chord shape via a lookup table of
`escape`, `return` → `enter`, `tab`, `backspace`, `delete`, `up`, `down`, `left`, `right`, `pageup`,
`pagedown`, `wheelup`, `wheeldown`, `home`, `end` (`rg -n 'wheeldown: "wheeldown"'`), falling back
to the `key` field when it is exactly one character long, lower-cased. A line-feed `enter` event
uses `"\n"` as its key. If neither yields a key, the normalizer returns null and the chord resolver
reports `"none"` (or `"chord_cancelled"` mid-chord): no binding fires. Two more event-side rules: on
macOS an unmodified `†` (Option+T) becomes `t` with Alt, and `shift` is inferred from an upper-case
single-character key but dropped when Shift produced a non-letter symbol.

That is the hard stop for bare-modifier bindings. A modifier-only event has `name: ""` and
`key: ""`, not in the table and not length 1, so the normalizer returns null before any pattern
comparison happens. An `"alt": "voice:pushToTalk"` entry in `keybindings.json` would load, validate,
and never fire.

Comparison itself is exact equality on `key`, `ctrl`, `shift`, `super`, with `alt` and `meta`
collapsed into one slot (`(a.alt || a.meta) === (b.alt || b.meta)`); the event side sets both from
the event's `meta`. Relocate the matcher with `rg -n '\(\w+\.alt \|\| \w+\.meta\) === '`.

## Push-to-talk: hold inferred from auto-repeat

Because no release events exist, `voice:pushToTalk` reconstructs a held key from keyboard
auto-repeat. Grep `voice:pushToTalk` for the default (`space` in `Chat`), the resolution, and the
validation warning; grep `awaitingVoiceSubmitDoubleTap` to land in the keybinding handler.

This section covers only how the keybinding handler reads the key. What the recording then does (its
release timer, tap mode's keystroke-free termination, the auto-submit gate, and the speech-to-text
stream) is in `VOICE_MODE.md`.

The handler resolves the binding from the last single-chord `Chat` binding for `voice:pushToTalk`; a
later single-chord `Chat` binding on the same keys cancels it. A binding is "printable" when it is
one character with no modifiers, like the default `space`; a printable binding is ignored while the
composer is not taking typed keys. Constants, adjacent in the source
(`rg -U -n '= 120,\n\s+\w+ = 2000,\n\s+\w+ = 5,\n\s+\w+ = 2,\n\s+\w+ = 300;'`):

| Value  | Role                                                                            |
| ------ | ------------------------------------------------------------------------------- |
| `120`  | ms of quiet that resets the warmup counters; also tap repeat window, send delay |
| `2000` | first-press fallback passed to the recorder for a binding that is not printable |
| `5`    | presses of a printable bound key before recording starts (the hold threshold)   |
| `2`    | presses that reach the input; the second also starts the warmup indicator       |
| `300`  | double-tap window for sending a held-mode transcript                            |

Hold mode, printable binding: each matching event counts its characters (one stdin chunk can carry
the char repeated N times). The first two presses reach the input as ordinary text, and the second
also sets the warmup state (the footer shows `keep holding…`); later echoes are swallowed. At 5
presses the handler anchors and strips the echoed characters and tells the recorder to start. A
non-matching key, or 120 ms with no matching key, resets the counters and clears the warmup state;
that timer ends a warmup, not a recording. The 120 ms value also sets the tap-mode repeat window and
the double-tap send delay below.

Hold mode, non-printable binding: the first matching event starts recording at once and passes the
2000 ms first-press fallback to the recorder in place of its 600 ms default.

Once recording, every further auto-repeat is forwarded to the recorder (and, for a printable
binding, its echo stripped). The recorder, not this handler, ends a hold-mode recording: it arms a
200 ms release timer on each repeat and finishes when it fires (`VOICE_MODE.md`; the recorder logs
`[voice] No auto-repeat seen, arming release timer via fallback` when the first-press fallback fires
instead).

Tap mode: repeats within 120 ms of the previous press are swallowed, so one physical tap toggles
once; a tap on a non-empty input is not consumed.

Double-tap to send (hold mode, printable binding only): while `awaitingVoiceSubmitDoubleTap` is set,
two presses within 300 ms with the cursor at the end of the input and voice idle submit the input
120 ms later, with the echoed character stripped. Any other key, a press away from the end, or a
too-slow second press clears the flag.

This is why the validation layer warns when `voice:pushToTalk` is bound to a bare letter
(`rg -n 'prints into the input during warmup'`). The warning reads: Binding "<key>" to
voice:pushToTalk prints into the input during warmup; use space or a modifier combo like meta+k.

The warmup presses are real keystrokes and land in the input buffer before the threshold is crossed;
the handler then anchors and strips them. Real key-release events would remove the need for both the
threshold and the strip-back.

## What a "bind a bare modifier to push-to-talk" feature would touch

Derived from the above; listed as scope, not as a recommendation:

1. Push `flags = 1 | 2 | 8` instead of the hardcoded `CSI > 5 u`, and use the flags value of the
   `kittyKeyboard` reply, which today is only logged.
2. Widen the CSI-u regex to accept a `:` sub-parameter on the modifier parameter, and surface event
   type (press/repeat/release) on the key event object.
3. Extend the functional-key code table past 57426 to cover 57441–57454, and lift the
   `code < 55296` fallback bound that currently excludes the whole PUA.
4. Give the event object an `eventType` field and route release events through dispatch (today every
   dispatched key event is a `keydown`).
5. Let the chord normalizer produce a chord for a nameless modifier-only event, and let the chord
   comparator match a pattern whose `key` is `""`; currently the null-chord early return and exact
   `key` equality both block it.
6. Gate the whole path on the terminal allowlist plus the negotiated flags, with the auto-repeat
   heuristic as the fallback for terminals that decline.
