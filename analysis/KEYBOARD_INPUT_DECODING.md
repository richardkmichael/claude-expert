# Keyboard Input Decoding

Verified against `work/2.1.226/package/cli.prettier.js`.

How raw terminal bytes on stdin become key events, what escape-sequence dialects Claude Code
negotiates, and where the CSI-u (Kitty keyboard protocol) support stops. Also covers how keystroke
patterns in `keybindings.json` are matched against decoded events, and why `voice:pushToTalk` infers
"hold" from auto-repeat rather than from key-release events.

## Summary

- The decoder is hand-rolled Claude Code code, not a runtime facility and not a live dependency. Its
  skeleton is a fork of the `parse-keypress` lineage (the shape ink vendors, itself descended from
  Node's `readline` keypress internals), extended in-tree with bracketed paste, SGR/X10 mouse, UTF-8
  continuation reassembly, CSI-u, and xterm `modifyOtherKeys`. See Provenance below — the bun-compiled
  distribution does not change this.
- Claude Code does push the Kitty progressive-enhancement flags on raw-mode entry, but only
  `flags = 1` (disambiguate escape codes). It never requests `2` (report event types), `4` (report
  alternate keys), `8` (report all keys as escape codes), or `16` (report associated text).
- The push is gated on an env-derived terminal allowlist; outside it, Claude Code stays on legacy
  encodings entirely.
- There is no negotiation round-trip. A `CSI ? <flags> u` reply is parsed into a
  `{ type: "kittyKeyboard", flags }` response object, but nothing consumes it — the terminal is never
  queried for its flags, so the push is blind.
- Modifier-only key events (Kitty codes 57441–57454, e.g. right Option = 57449) would be received and
  tokenized correctly, but decode to a key event with an empty name and empty `key`, so they are
  dropped inertly — no text inserted, no binding matched.
- Any CSI-u sequence carrying a `:` sub-parameter — which is how both event types (`;<mods>:<event>`)
  and alternate keys (`<code>:<shifted>:<base>`) are encoded — fails the CSI-u regex entirely and
  falls through to the same inert empty-name event.

## Locating the decoder

Grep anchors, in the order that gets you there fastest:

- `CLAUDE_CODE_BS_AS_CTRL_BACKSPACE` and `CLAUDE_CODE_ALTGR_AS_TEXT` — these two env vars sit inside
  the keypress module, and are the cheapest proof that the module is app code rather than a vendored
  library.
- `"kittyKeyboard"` — a single hit; the terminal-response classifier.
- `INTELLIJ_TERMINAL_COMMAND_BLOCKS_REWORKED` / `jediTerm` — the JetBrains wheel-event workaround at
  the top of the same module.
- `pendingByteEvents` — appears in the parse-state object, the decode entrypoint, and the stdin
  handler; the fastest way to jump between them.

Expected shape of the module:

- A tokenizer factory (call it `makeTokenizer`) returning `{ feed, flush, reset, buffer }` over a
  VT500-style state machine with states `ground`, `escape`, `escapeIntermediate`, `csi`, `ss3`,
  `osc`, `dcs`, `apc`, `pm`, `sos`. Locate it via the CSI byte-range constants
  `PARAM_START: 48, PARAM_END: 63, INTERMEDIATE_START: 32, INTERMEDIATE_END: 47, FINAL_START: 64,
  FINAL_END: 126`.
- A decode entrypoint taking `(parseState, chunkOrNull)` and returning `[events, nextState]`. It owns
  bracketed-paste mode (`IN_PASTE`), the UTF-8 continuation-byte buffer, and mouse-token
  re-synthesis.
- A single-sequence classifier (call it `decodeKey`) that turns one tokenized sequence into a key
  event object.
- The stdin side lives in Claude Code's ink fork: grep `rawModeEnabledCount`, `handleReadable`,
  `flushIncomplete`, `NORMAL_TIMEOUT`, `PASTE_TIMEOUT`.

## The key event object

Every decoded key event has this shape (field names are stable; they are read by name all over the
app):

```
{ kind: "key", name, fn, ctrl, meta, shift, option, super, sequence, raw, isPasted, code, col, row }
```

`kind` is one of `"key"`, `"mouse"`, `"response"`. The `super` field only ever gets set from CSI-u /
`modifyOtherKeys` modifier bitmasks — legacy encodings cannot express it.

Before reaching React, this is wrapped into a `keydown` event class with fields `key`, `name`,
`sequence`, `ctrl`, `shift`, `meta`, `superKey`, `fn`, `soloKeypress`. Note the rename: `super` on the
decoded event becomes `superKey` on the dispatched event, and `meta` on the dispatched event is
`decoded.meta || decoded.option`. Grep `superKey` to find the boundary.

The `key` field is computed by a small normalizer. Its fallthrough order matters for the
modifier-only case:

1. name `"space"` → `" "`.
2. `ctrl` set → the name.
3. single-char sequence with code ≥ 32 and ≠ 127 → that char.
4. non-empty name → the name (upper-cased when `shift` and length 1).
5. sequence starting with ESC (code 27) → `""`.
6. an SGR-mouse-shaped sequence → `""`.
7. otherwise the raw sequence.

Step 5 is what makes an unrecognized CSI sequence inert rather than garbage-inserting.

## Provenance: forked `parse-keypress`, not the runtime's readline

Worth being precise about, because from 2.1.117 the bundle is bun-compiled and it is tempting to
assume the runtime supplies this. It does not. The parser is inlined app code, and nothing in the TUI
input path reaches for the runtime's keypress machinery:

- `emitKeypressEvents` — readline's keypress entrypoint in both Node and Bun — appears nowhere in the
  bundle.
- `require("readline")` does appear, many times, but every hit is bundled third-party library code.
  The TUI path instead wires `stdin.on("readable")` to its own decode entrypoint; grep
  `handleReadable` and `pendingByteEvents` to confirm the two never meet.

So Bun vs Node is not the axis here. What the code actually descends from is the `parse-keypress`
package shape (what ink vendors as its own `parse-keypress`), which in turn descends from Node's
`readline` keypress internals. The markers that distinguish those two ancestors:

| Marker                                                                | Node `readline` | `parse-keypress` lineage |
| --------------------------------------------------------------------- | --------------- | ------------------------ |
| `fn` and `option` fields on the key object                            | absent          | present                  |
| `raw` field alongside `sequence`                                      | absent          | present                  |
| Field order `name, fn, ctrl, meta, shift, option`                     | different       | exact match              |
| Shift/ctrl-implying codes as array-membership helpers                 | inline switch   | exact match              |

The two array helpers are the cleanest fingerprint — the bundle carries both lists verbatim:

```
shift: ["[a","[b","[c","[d","[e","[2$","[3$","[5$","[6$","[7$","[8$","[Z"]
ctrl:  ["Oa","Ob","Oc","Od","Oe","[2^","[3^","[5^","[6^","[7^","[8^"]
```

Shared with both ancestors, so not discriminating on their own but useful for relocation: the two
regexes in the table below, the `"[[A": "f1" … "[Z": "tab"` lookup table, the code assembly
`[p1,p2,p4,p6].filter(Boolean).join("")`, and the modifier extraction `(p3 || p5 || 1) - 1`.

One tell that this is a fork rather than a reimplementation: `fn` is initialized to `false` on every
construction path and never assigned `true` anywhere in the bundle. It is a dead field carried along
from upstream. `option`, by contrast, is live — set for double-ESC-prefixed sequences.

## Dialects the decoder accepts

Relocate these by grepping the regex bodies — they are literal and stable:

| Dialect                       | Regex (verbatim in source)                                                    |
| ----------------------------- | ----------------------------------------------------------------------------- |
| CSI-u / Kitty                 | `/^\x1b\[(\d+)(?:;(\d+))?u/`                                                  |
| xterm `modifyOtherKeys` fmt 2 | `/^\x1b\[27;(\d+);(\d+)~/`                                                    |
| ESC-prefixed meta             | `/^(?:\x1b)([a-zA-Z0-9])$/`                                                   |
| Function/cursor keys          | `/^(?:\x1b+)(O\|N\|\[\|\[\[)(?:(\d+)(?:;(\d+))?([~^$])\|(?:1;)?(\d+)?([a-zA-Z]))/` |
| SGR mouse                     | `/^\x1b\[<(\d+);(\d+);(\d+)([Mm])$/`                                          |
| X10 mouse                     | `/^\x1b\[M[\x20-\x7f][\x20-￿]{2}$/`                                      |

Modifier bitmask decode is the standard `param - 1` bitfield: `1 = shift`, `2 = meta`, `4 = ctrl`,
`8 = super`. Hyper and meta (Kitty bits `16` and `32`) are not broken out.

Also parsed, as `kind: "response"` rather than key events: DECRPM (`CSI ? <mode> ; <status> $y`), DA1,
DA2, cursor position (`CSI ? <row> ; <col> R`), the Kitty keyboard flags reply (`CSI ? <flags> u`),
theme notify (`CSI ? 997 ; <1|2> n`), OSC, and XTVERSION (`DCS > | <name> ST`).

## What gets pushed to the terminal, and when

Four constants, all built through the same CSI helper. Grep for the literal payloads:

| Payload      | Meaning                                     |
| ------------ | ------------------------------------------- |
| `CSI < u`    | Kitty progressive enhancement: pop          |
| `CSI > 1 u`  | Kitty progressive enhancement: push flags=1 |
| `CSI > 4;2m` | `modifyOtherKeys` = 2                       |
| `CSI > 4 m`  | `modifyOtherKeys` reset                     |

The enable function emits `pop + push(1) + modifyOtherKeys(2)` — and only if the detected terminal is
in this allowlist:

```
["iTerm.app", "kitty", "WezTerm", "ghostty", "tmux", "windows-terminal", "WarpTerminal"]
```

Terminal detection is env-var-based (`TERM=xterm-ghostty` → `ghostty`, `TERM` containing `kitty` or
`KITTY_WINDOW_ID` → `kitty`, else `TERM_PROGRAM`, then `TMUX`, `WT_SESSION`, …), later refined by the
XTVERSION reply. There is no `CLAUDE_CODE_*` env var to force or suppress the push. On every other
terminal Claude Code is legacy-encoding-only: no CSI-u is requested, so none arrives except from a
terminal configured to send it unprompted.

The enable string is written on raw-mode entry and re-emitted after alt-screen transitions; the
matching disable (`modifyOtherKeys reset` + `pop`) is written on raw-mode exit and on the synchronous
process-exit path. Grep `rawModeEnabledCount` for both sites.

Immediately after the push, the terminal querier is scheduled. It sends exactly two probes —
XTVERSION and `DECRQM(2026)` (synchronized update) — and nothing else. It never queries the Kitty
flags, so the `kittyKeyboard` response branch is dead: parsed, handed to the querier, ignored.

## Where Kitty-protocol support stops

The CSI-u regex is `/^\x1b\[(\d+)(?:;(\d+))?u/` — one numeric code, one optional numeric modifier
mask, then `u`. It has no sub-parameter (`:`) support at all. Verified behavior:

| Sequence            | Kitty flag needed          | Matches? |
| ------------------- | -------------------------- | -------- |
| `CSI 13;5u`         | 1 (disambiguate)           | yes      |
| `CSI 57449;3u`      | 8 (report all keys)        | yes      |
| `CSI 97;1:3u`       | 2 (event types)            | no       |
| `CSI 97:65;2u`      | 4 (alternate keys)         | no       |
| `CSI 97;1;97u`      | 16 (associated text)       | no       |

A `:` therefore kills the match, which rules out event types and alternate keys wholesale. The
tokenizer is not the limitation — `:` is 0x3A, inside the `PARAM_START: 48 … PARAM_END: 63` range, so
`CSI 97;1:3u` arrives as one clean sequence token. It is the key-decode regex that rejects it. A
non-matching CSI sequence falls through the whole classifier chain to a key event with `name: ""`,
and then `key: ""` via step 5 of the normalizer — silently dropped, not mis-inserted.

The functional-key code table handles Kitty codes 57399–57426 explicitly (keypad `0`–`9`, `.`, `/`,
`*`, `-`, `+`, keypad Enter, `=`, `,`, and keypad arrows/nav). Everything else falls to
`code >= 32 && code <= 126` or `code >= 160 && code < 55296`. Note the upper bound: 55296 is 0xD800,
the surrogate range start, so the whole Private Use Area is excluded. Consequences:

- Modifier keys (57441 left shift … 57454 ISO level5 shift; right Option/Alt = 57449) → name
  `undefined`.
- Caps/scroll/num lock, Print Screen, Pause, Menu (57358–57363) → name `undefined`.
- F13–F35 (57376–57398) → name `undefined`.
- Media keys (57428–57440) → name `undefined`.

So even with `flags = 8` pushed, standalone modifier presses would arrive, tokenize correctly, decode
to a nameless event, and be discarded before reaching any binding matcher.

## Keybinding matching

Two functions meet in the middle; both must agree for a binding to fire.

Pattern side: a keystroke pattern is split on whitespace into chords, each chord split on `+` into
parts. Recognized modifier words are `ctrl`/`control`, `alt`/`opt`/`option`, `shift`, `meta`, and
`cmd`/`command`/`super`/`win` (which sets `super`, not `meta`). Recognized key aliases: `esc`,
`return` → `enter`, `del` → `delete`, `space` → `" "`, and the four arrow glyphs. Anything else
becomes the key verbatim, lower-cased. The result is
`{ key, ctrl, alt, shift, meta, super }`.

Note what this means for a bare modifier: `"alt"` parses successfully to
`{ key: "", alt: true, … }`. Nothing rejects it — the only pattern validation is an empty-part check
that rejects stray `+` characters.

Event side: the dispatched keydown is normalized to the same chord shape via a lookup table of
`escape, return→enter, tab, backspace, delete, up, down, left, right, pageup, pagedown, wheelup,
wheeldown, home, end`, falling back to the `key` field when it is exactly one character long:

```
let chordKey = NAME_TABLE[event.name] ?? (key.length === 1 ? key.toLowerCase() : null);
if (!chordKey) return null;   // → { type: "none" }, no binding fires
```

That is the hard stop for bare-modifier bindings. A modifier-only event has `name: ""` and
`key: ""` — not in the table, not length 1 — so the normalizer returns null and the chord machine
reports `"none"` before any pattern comparison happens. A `"alt": "voice:pushToTalk"` entry in
`keybindings.json` would load, validate, and never fire.

Comparison itself is exact-equality on `key`, `ctrl`, `shift`, `super`, with `alt` and `meta`
collapsed into one slot (`(a.alt || a.meta) === (b.alt || b.meta)`). Grep for that `||`-collapsed
comparison to relocate the matcher.

## Push-to-talk: hold inferred from auto-repeat

Because no release events exist, `voice:pushToTalk` reconstructs hold-and-release from keyboard
auto-repeat. Grep `voice:pushToTalk` for the resolution, the validation warning, and the handler.

The handler keeps repeat counters and one timer. Constants, adjacent in the source:

| Value | Role                                                                             |
| ----- | -------------------------------------------------------------------------------- |
| `120` | ms with no further keypress → treated as release                                 |
| `5`   | repeats of a printable bound key before recording starts (the hold threshold)    |
| `2`   | repeats before the echoed characters start being floored/anchored in the input   |

For a printable single-char binding the handler counts repeats of that char (including the case where
one stdin chunk contains the char repeated N times) and only commits to "held" at 5. For a
non-printable binding each event counts as 1. The 120 ms timer is rearmed on every keypress; when it
fires, that is the release.

This is why the validation layer warns when `voice:pushToTalk` is bound to a bare letter:

```
Binding "<key>" to voice:pushToTalk prints into the input during warmup; use space or a modifier combo like meta+k
```

The warmup repeats are real keystrokes and land in the input buffer before the threshold is crossed;
the handler then anchors and strips them. Real key-release events would remove the need for both the
threshold and the strip-back.

## What a "bind a bare modifier to push-to-talk" feature would touch

Derived from the above; listed as scope, not as a recommendation:

1. Push `flags = 1 | 2 | 8` (or query first, then push the intersection) instead of the hardcoded
   `CSI > 1 u`, and consume the `kittyKeyboard` response that is already parsed.
2. Widen the CSI-u regex to accept `:` sub-parameters on both the code and modifier parameters, and
   surface event type (press/repeat/release) on the key event object.
3. Extend the functional-key code table past 57426 to cover 57441–57454, and lift the
   `code < 55296` fallback bound that currently excludes the whole PUA.
4. Give the event object an `eventType` field and route release events through dispatch (today every
   dispatched event is a `keydown`).
5. Let the chord normalizer produce a chord for a nameless modifier-only event, and let the chord
   comparator match a pattern whose `key` is `""` — currently `!chordKey → null` and exact `key`
   equality both block it.
6. Gate the whole path on the terminal allowlist plus the negotiated flags, with the auto-repeat
   heuristic as the fallback for terminals that decline.
