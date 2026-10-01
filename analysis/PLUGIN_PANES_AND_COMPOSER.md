# Plugin Panes, the Prompt Composer, and Drag-Select Attachment

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)
Verified: 2.1.286 (pane keyboard and `prompt.edit` sections); other sections last checked at
2.1.277

Three surfaces meet at the bottom of a fullscreen terminal session, and they are commonly confused
with one another:

- Panes drawn by a function-hooks plugin through the `Pane` render site. Entirely plugin-authored
  content; the engine supplies chrome, scrolling, focus and keybindings.
- The engine's own diff sidebar, a native Ink component that predates the `diff` mod and still
  ships. It is the only surface wired to drag-select-to-attach.
- The prompt composer, which draws a leading "pill" for an IDE/diff line selection. The pill is not
  composer text and has no plugin-facing API.

The practical consequence: a third-party plugin drawing its own `Pane` cannot get the
`[⧉ N lines from FILE]` behaviour. Nothing in the plugin API reaches it.

`NATIVE_DIFF_SIDEBAR.md` is the full extraction of the second surface: the `/diff` command and its
gating, the sidebar's component tree, the drag-to-attach path end to end, focus handling, and a
capability-by-capability correspondence with the `$` API.


## The `diff` mod is a built-in plugin, and it displaces the native sidebar

Grep `kBe("diff"` — or more stably, the built-in-plugin registration function, found by
`rg -n 'builtinPluginsInitialized'` and reading the initializer it guards. That initializer registers
a fixed list of built-in plugins by name: `sec-default`, `agents-md`, `plugin-authoring`, `tips`,
`mermaid`, `diff`, `claude-test`. Each is a separate bun module required lazily.

`diff` and `claude-test` are skipped when `CLAUDE_CODE_ENTRYPOINT` is `local-agent` or starts with
`remote`. The `diff` mod's `isOnByDefault` is `false`; it also requires function hooks to be on
(`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS`, see `rg -n 'CLAUDE_CODE_ENABLE_FUNCTION_HOOKS'`).

Ownership handoff: find the predicate with
`rg -n 'isOwnedByPlugin'` (3 hits — a factory, a comparison, and the gate). The factory reads two
things: whether the sidebar feature is on at all, and whether the `diff` plugin owns it. The
ownership check requires the plugin to be available, function hooks on, the plugin in the enabled
set, and its storage id live.

The two surfaces answer to different flags: the native sidebar is on unless the kill switch
`tengu_jazzy_ripple` is set, while `tengu_quiet_dolphin` gates the mod (off by default). Do not read
`tengu_quiet_dolphin` as the `/diff` gate.

Two consequences follow, both greppable:

- The built-in `/diff` slash command is defined with `isEnabled: () => !<ownedByPlugin>()`. Locate it
  with `rg -n '"Toggle the diff panel showing uncommitted changes"'` and read the surrounding command
  object.
- The native sidebar renders only when `isSidebarOn && (panelFileView !== null || !isOwnedByPlugin)`.
  In 2.1.277 `panelFileView` has exactly 13 occurrences (`rg -c 'panelFileView'`) and **none of them
  assign a non-null value** — it is initialized to `null`, read by two selectors, and cleared by
  three reducers. So when the mod owns the diff, the native sidebar never mounts.

□ Tripwire: `rg -c 'panelFileView'` = 13, and `rg -n 'panelFileView:' | rg -v 'null'` is empty.
  If a setter appears, the native sidebar can coexist with the mod and this section needs revisiting.


## Drag-select to attach: engine-only, native diff sidebar only

### What the feature is

Dragging a text selection inside the native diff sidebar puts `{ source: "diff", text, lineCount,
filePath }` into the session's `ideSelection` state. The composer then shows a leading pill, and the
selected lines travel with the next prompt as a `selected_lines_in_diff` attachment.

### Locating it

Grep the telemetry event: `rg -n 'diff_selection_attach'`. Expect 3 hits — the event-name allowlist,
the call site, and a re-declaration inside the `diff` mod's own telemetry key table (the mod reuses
the same event name for its *file-level* attach, which is a different feature; see below).

The call site is a React hook of the shape:

```
hook(minCol, getMaxRow, onAskAboutSelection, rowToPath)
  subscribe to the terminal selection store
  bail if: no attach callback | isDragging | no selection
  bail if: no anchor/focus, or anchorSpan.kind === "line"
  bail if: anchor or focus column < minCol
  bail if: anchor or focus row > getMaxRow()
  text = store.getSelectedText(); bail if blank or unchanged
  lineCount = newline count of text.trimEnd() + 1
  filePath = rowToPath(min(anchor.row, focus.row))
  onAskAboutSelection({ source: "diff", text, lineCount, filePath })
```

The terminal selection store itself is the engine's mouse-selection accessor, reachable from
`rg -n 'subscribeToSelectionChange'` — it exposes `getSelectedText`, `copySelection`,
`copySelectionNoClear`, `hasTextSelection`, `clearTextSelection`, `moveSelectionFocus`,
`setSelectionBgColor` and the raw `selection` state.

□ Tripwire: `rg -n 'getSelectedText'` has exactly one *consumer* outside the selection store's own
  class and the null-object stub. If a second consumer appears, the feature has been generalized.

### What it applies to

Not "any Ink text", not `Code` elements, and not plugin panes.

- The only producer of `ideSelection` with `source: "diff"` is the native diff sidebar's
  `onAskAboutSelection` prop. Grep `rg -n 'onAskAboutSelection'` — 4 hits, all in the native sidebar
  chain: the host passes `Tu.setIdeSelection` down, or `undefined` when a modal slot is active.
- The only other writer of `ideSelection` is the IDE MCP connection path
  (`rg -n 'offerIdeSelection'`), which produces `source`-less selections that render as
  `selected_lines_in_ide`.
- A mod-drawn `Pane` gets drag *autoscroll* (the same selection store is subscribed with
  `requireScope: true`) and gets its selection *clamped* to its own column band, but no attach. Grep
  `rg -n 'selectionScope'` — the flag is set by the engine's scrollable-box component, so every
  scroll container (including a Pane body) confines a drag to its own columns.

### Where the filename comes from

Not from a `Code` element's `path` prop, not from a heading. The sidebar keeps a `Map<path, inkNode>`
populated by a per-file `ref` callback on each rendered file block, keyed on the file's repo-relative
path. A helper walks that map, computes each node's absolute top (summing `getComputedTop()` up the
parent chain, subtracting `scrollTop` where a parent scrolls), and returns the key whose vertical
band contains the selection's topmost row. Relocate it by grepping for the ref that does
`map.set(<file>.path, node)` inside the file-list render, then finding the row→path helper that reads
the same ref.

The mod's `Code` elements do pass `path`, but the engine's `Code` renderer uses it only as the
`filePath` for syntax highlighting and diff rendering. Confirm with `rg -n 'Code prop "'` to find the
`Code` prop validator (`source`, `language`, `path`, `startLine`, `format`, `wrap`), then follow the
terminal renderer — it forwards `path` into the highlighter and registers no node anywhere.

### Gating

Placement and width, but through the sidebar's own gates rather than a pane `placement` prop:

| Gate | Where |
| ---- | ----- |
| Fullscreen only | the sidebar enable predicate requires `fullscreen` |
| `columns >= 110` | same predicate; auto-open needs `>= 144` unless `diffSidebarOpen === true` |
| A git repo, main session focused, not a thin client | same predicate |
| `replTab === "diff"` | the sidebar host returns `null` otherwise |
| Left-edge column | the attach hook's `minCol` is `terminalColumns − sidebarWidth`, so a drag that starts or ends left of the sidebar is ignored |
| Bottom row | the attach hook's `getMaxRow` is the sidebar's last row |
| No overlay open | the attach callback is withheld while any overlay other than the autocomplete is active, or while the autocomplete popup / a dialog is showing |
| Not a line selection | `anchorSpan.kind === "line"` (triple-click) is excluded; character and word drags attach |

`110` and `144` are the same two constants the pane placement gate uses (see Panes below) and the
same buckets the diff telemetry reports (`under_110`, `110_to_143`, `144_to_199`, `200_plus`).

### Clipboard

Attach does not suppress copy. Copy-on-select is a separate, global subscriber to the same selection
store, gated on the `copyOnSelect` setting (default on, toggle labelled "Copy on select" in
`/config`). It fires on drag end and writes through the native clipboard, a tmux buffer, or OSC 52,
reporting `copied N chars to clipboard` / `sent N chars via OSC 52`. If a drag in the diff sidebar
does not reach the clipboard, `copyOnSelect` is off — the attach path never calls `copySelection`.

### What the model receives

`rg -n 'from the diff view'` finds the attachment's prompt rendering:

```
The user selected the following <N> line(s) from the diff view (in <path>):
<content>

This may or may not be related to the current task.
```

marked as a meta message. The IDE variant is `The user selected the lines <a> to <b> from <file>:`.
Both attachment types appear in the attachment-type list alongside `selected_lines_in_ide`; grep
`rg -n 'selected_lines_in_diff'` for all five sites (creation, prompt rendering, type list, transcript
row, and the type union).

The selection is cleared on submit, so it attaches exactly once.

### The mod's own attach is a different thing

The `diff` mod attaches a *whole file's* diff, not a mouse selection, and it does it through the
`prompt.submit` hook by appending a context block. Grep
`rg -n 'from the diff pane to this prompt'` — the text is
`The user attached the diff of <path> from the diff pane to this prompt:` followed by hunk lines,
truncated with `(The rest of this diff was cut: it did not fit in the prompt.)`. This produces no
composer pill. It reuses the `diff_selection_attach` telemetry name, which is why that event name
appears both in engine and mod code.


## The composer pill is a `leadingPill`, not text

Grep `rg -n 'leadingPill'`. Expect ~7 hits: the prop in the text-input hook's destructuring, the
render site, the highlight computation, two memo-cache comparisons, and the construction site.

The pill object is `{ text, onDelete }`. Its label is built in two steps:

1. A label builder producing `⧉ <N> line|lines from <basename(filePath)>` for a diff-sourced
   selection, `⧉ <N> lines from diff` when there is no path, `⧉ <N> lines selected` for an IDE
   selection, or `⧉ In <basename>` for a cursor-position-only IDE selection. Relocate with
   `rg -n '\\u29C9 \$\{'` or by grepping the `from diff` / `selected` literals; note the glyph is a
   hoisted constant, so searching for the rendered string `[⧉ 3 lines from README.md]` finds nothing.
2. A wrapper that replaces `]` with `)`, collapses newlines to spaces, truncates the label to 32
   characters middle-out, wraps it in `[...]`, appends a trailing space, and NFC-normalizes.

Behaviour that follows from it being a prefix rather than buffer content:

- The composer's cursor model is built from `pillText + value`, and every offset the caller supplies
  is shifted by `pillText.length`. The cursor is clamped so it cannot move inside the pill.
- The pill is highlighted as range `[0, pillText.length - 1]` with theme colour `ide` at priority 30.
  `ide` resolves to `rgb(71,130,200)` in the graphical themes and `ansi:blue` / `ansi:blueBright` in
  the ANSI themes — the light blue the question describes.
- Backspacing past offset 0 clears the prefix and fires `onDelete`, which dismisses the selection.
- `$.prompt.read` returns the draft `{ text, cursor }` without the pill.

This is *not* how pasted-text and image placeholders work. Those are literal text in the draft
buffer: `[Pasted text #N]`, `[Pasted text #N +M lines]`, `[Image #N]`, `[Audio #N]`,
`[...Truncated text #N +M lines]`. Grep the shared atomic-token regex with
`rg -n 'Pasted text\|Image\|Audio'` — the same alternation also matches `\[⧉ [^\]\n]+\]`, so the
composer treats a pasted pill and the selection pill alike for word-motion and atomic delete, but
only the paste placeholders are in the buffer and expanded at submit. They are drawn with the
`suggestion` colour, not `ide`.

### No plugin API reaches it

The composer's highlight list is computed entirely inside the chat component from engine-owned
sources (bash-mode prefix, `@`-mentions, slash commands, ultrathink/auto-accept shimmer, ghost text).
There is no hook, prop, or `$` noun that contributes a range.

The plugin-facing `$` surface is built by one factory; relocate it with
`rg -n 'blit: \(' -A 2` or by grepping `\$\.ui\.resolve` and reading the enclosing object. As of
2.1.277 it is:

| Noun | Methods |
| ---- | ------- |
| `ui` | `notice`, `invalidate`, `blit`, `resolve`, `log`, `status`, `ask`, `toast`, `open`, `close`, `panes`, `scroll`, `focus` |
| `prompt` | `submit`, `read`, `fill`, `suggest` |
| `session` | `messages`, `cwd`, `root`, `model`, `turns`, `id`, `repo`, `surface`, `surfaces`, `authorize`, `usage`, `compact` |
| `model` | `complete`, `fork`, `classify` |
| `settings` | `read` |
| others | `audio`, `mcp`, `turn`, `tool`, `command`, `config`, `agent`, `store`, `fs`, `clock`, `http`, `process`, `env` |

`prompt.attachment`, `prompt.edit`, `prompt.section` and `prompt.context` exist only as hook *events*
a plugin registers a handler for — they are not callable methods. `prompt.attachment` in particular
is a rewrite hook: the engine renders an attachment it already created, matched by
`{ type }` (e.g. `selected_lines_in_diff`), and a handler may rewrite the text or leave it out. It
cannot create an attachment, and it never touches the composer.

So a plugin can put literal text in the composer with `$.prompt.fill`, and that is all. There is no
way to colour it and no way to make it atomic.

□ Tripwire: the full hook-event list is one array; find it with `rg -n '"prompt.attachment"'` and
  read the enclosing array. If a text-selection event or a composer-attachment method appears, this
  section is stale.


## `$.prompt.fill` and keyboard focus

Grep `rg -n 'fillDraft'` — 3 hits: the bridge (`composer.write`), the implementation, and one
re-export. The implementation:

- Refuses (`{ isFilled: false }`) when a modal dialog is open. The pane store is a *different* store,
  so a focused pane does not block a fill.
- `replace`: sets input mode back to `prompt`, replaces the value.
- `append`: concatenates onto the current value. Does **not** reset input mode.
- `insert`: inserts at the cursor.
- For `replace` and `append`, moves the cursor to end of value.

It performs no focus manipulation at all. **After `$.prompt.fill`, focus stays wherever it was.** If
the plugin's pane held the keyboard, it still holds it. Nothing in the dispatch chain above
`fillDraft` moves focus either.

The one focus interaction with the draft runs the other way: a pane opened with
`$.ui.open({ focus: true })` records a `focusRequest`, and the chat component only honours it when
the composer draft is empty (plus no dialog, no footer selection, no agent-view selection, and at
least one pane placed). So filling the composer *prevents* a later pane from taking focus, rather
than surrendering focus to the composer.

### `$.ui.focus` cannot grab focus

`$.ui.focus({ requestId, key })` moves focus **within** a site the plugin already holds. Grep
`rg -n 'that site does not hold the keyboard'` for the core implementation; it denies with one of:

- `no such site`
- `not this plugin's site`
- `that site does not hold the keyboard`
- `another plugin's element holds the keyboard`
- `no element of its own is drawn under that key`

There is no plugin-callable way to move focus from the composer into a pane.


## Moving focus into a pane: `ctrl+x tab`

Confirmed from the default keybinding table. Grep `rg -n 'abovePrompt:focus'`:

- Binding: `"ctrl+x tab"` → `abovePrompt:focus`, in the **`Chat`** context (the composer's context;
  the engine calls these *contexts*, not bands).
- Description string: `focus plugin buttons, inputs and selects`.
- Sibling: `"ctrl+x ctrl+a"` → `abovePrompt:toggle` (`hide/show plugin panel`).

The handler cycles, in this order:

1. If a pane is already focused, move to the **next open pane**. The "next" helper returns
   `open[indexOf(focusedId) + 1] ?? null` — so after the last pane it yields `null`, which returns
   focus to the composer. Repeated `ctrl+x tab` therefore walks composer → pane 1 → pane 2 → … →
   composer.
2. Otherwise, if an above-prompt element is focusable, focus that.
3. Otherwise, if any pane is open, focus the first one (same helper, with no current focus).
4. Otherwise the binding is unhandled.

Once a pane holds the keyboard, the relevant contexts are `Pane` (and `PaneField` when the focused
element is an `Input` or `Select`):

| Context | Bindings |
| ------- | -------- |
| `Pane` | `tab` / `shift+tab` navigate, `enter` press, `escape` leave, `up`/`down`/`pageup`/`pagedown`/`home`/`end` scroll, `ctrl+x left`/`up` grow, `ctrl+x right`/`down` shrink, `ctrl+x x` close |
| `PaneField` | `ctrl+x x` close |
| `AbovePrompt` | as `Pane`, plus `right`/`left` navigate and `space` press |

`pane:next` / `pane:previous` (`show next/previous plugin pane`) are separate actions that change
which pane is *shown*, and carry no default chord in the table.

### Keys a focused pane does not consume

A focused pane never takes focus away from the composer's text input. It intercepts keys in two
layers, and any key neither layer consumes reaches the composer as ordinary typing. The pane loses
the keyboard as a side effect of that typing. No key rule releases it, and the key is not replayed:
it was never consumed.

Layer 1 is Button hotkeys, a pre-dispatch interceptor that runs before keybinding resolution.
Relocate it from the module's exports, `rg -nF 'hotkeysOf: () =>'` and
`rg -nF 'hotkeyPresses: () =>'`, then read the two definitions and the interceptor that calls the
second. Shape:

- `hotkeysOf` walks the drawn tree and maps each Button's `hotkey` to its press. It does not
  descend into `engine` nodes.
- A key qualifies only with no ctrl, meta, super, escape, tab or return flag, and only if its text
  matches `/^[^\p{C}\p{Z}]+$/u`. Space is a separator (`\p{Z}`), so Space is never a hotkey.
- Each character is NFKC-normalized and lowercased before lookup. Shift+A, or A under caps lock,
  presses the `a` hotkey. The shift flag is not checked.
- Every character of the input chunk must map to a hotkey. A multi-character chunk (a paste, or
  keys the terminal delivered together) presses all of them, or none and falls through whole.
- The interceptor is active only while the `Pane` context is, i.e. the focused element is not an
  `Input` or `Select`.
- The Button validator accepts only `/^[0-9a-z]$/` (`rg -nF 'hotkey must be one digit'`).

Layer 2 is the `Pane` context table above. Every action in it has a handler in every pane state, so
each of these keys is consumed even when it has nothing to do:

| Key                                    | Effect                                                                      |
| -------------------------------------- | --------------------------------------------------------------------------- |
| `tab` / `shift+tab`                    | walk the ring: plugin focusables, then a stop per other open pane, then `✕` |
| `enter`                                | press the focused Button or submit the focused Input; else nothing          |
| `escape`                               | leave the pane, or close it when opened with `closeOnEscape`                |
| `up` / `down`, content overflows       | scroll one row (`ui.scroll`)                                                |
| `up` / `down`, nothing to scroll       | previous / next plugin focusable, wrapping; nothing when there are none     |
| `pageup` / `pagedown` / `home` / `end` | scroll by a page / to an end; nothing when the content fits                 |
| `ctrl+x` chords                        | grow, shrink, close                                                         |

The `up`/`down` split comes from how the handler map is merged: the ring handlers define
`pane:scrollUp`/`pane:scrollDown` as focus moves, and the scroll handlers replace them only when
the pane's `maxOffset > 0`. Relocate with `rg -n '"pane:scrollUp": \(\) =>'`.

Every other key reaches the composer: Space, printable characters with no matching hotkey (including
uppercase letters, punctuation, and digits or letters no Button claims), Backspace, Delete,
left/right, and ctrl or meta editing chords. Chat and Global bindings the `Pane` context does not
bind still resolve; `ctrl+x tab` is one.

The release is `useReleaseOnEdit` (see `NATIVE_DIFF_SIDEBAR.md`). While a pane or the band holds the
keys, it subscribes to the draft store and, on the first change to `value`, clears the band focus
and calls `focusPane(null)`. It compares `value` only, which splits the fall-through keys:

- A key that changes the draft text releases the pane, and the edit stays in the draft.
- A key that reaches the composer but leaves the text unchanged does not release. Left/right,
  ctrl+a/ctrl+e, Backspace at cursor 0 or on an empty draft, and Delete at the end move the
  composer's cursor or do nothing, and the pane keeps the keyboard.

#### What a plugin can do about it

No pane option, Button prop or hook event intercepts an unconsumed key. `$.ui.open` options are
`title`, `focus`, `closeOnEscape`, `holdToasts`, `rows` and `columns`. `ui.focus` is raised for
moves within a site; release-on-edit calls `focusPane(null)` directly and raises nothing.

`prompt.edit` cannot prevent the release, because it runs too late. The composer's key handler
writes the new value to the draft store first and records the edit for the hook chain second, and
the relay batches records onto a microtask (`rg -nF "the editor's edit stands"`). By the time a
handler runs, the pane has already lost the keyboard. A handler can still undo the text: answering
the before state `{ text: e.text, cursor: e.cursor }` is committed if the draft has not changed
since. The input carries:

- `origin`: always `{ kind: "composer" }` for composer typing. Nothing marks a key that fell through
  from a pane. A plugin's only signal is the last `isFocused` its `ui.render` received, and the
  re-render with `isFocused: false` can land before or after the `prompt.edit` call.
- `key`: present only when the batch holds exactly one edit. It is `{ key, ctrl?, shift?, meta? }`,
  where `key` is the single character typed, `"space"` for Space, or the key name for a named key.

Taking the keyboard back is narrower still. `$.ui.focus` is denied (`that site does not hold the
keyboard`). `$.ui.open({ id, focus: true })` on a pane that is already open records a
`focusRequest`. The settle step (`rg -nF 'settleFocusRequest'`) re-evaluates the request whenever
it or the draft text changes, honours it only when the draft is `""`, no dialog, footer or
agent-view selection is active, no pane is focused and a pane is placed, and otherwise clears it. So
re-focusing works only when the draft was empty before the key, and only if the open runs after the
undo has committed; an open issued from inside the `prompt.edit` handler sees the unreverted draft
and is dropped. The pane's focus index resets to none when it loses the keyboard, so a plugin that
regains it must call `$.ui.focus({ requestId, key })` to put the ring back on its Button.

□ Tripwire: the hotkey test still excludes `\p{Z}` and still lowercases; the `Pane` table has no
  `space`, `backspace` or `left`/`right` binding; `useReleaseOnEdit` still compares only `value`;
  the composer still applies the edit before it records it for `prompt.edit`. If any of these
  changes, this section is stale.


## What `prompt.edit` receives: edit shape, Vim mode and undo

Only two composer paths record an edit for the `prompt.edit` relay. Relocate them with
`rg -n 'we\.record\(\{|nv\.record\(\{'` (symbol names churn; the shape is `<relay>.record({ before,
after, key? })`):

- The base text input's key handler, after it has applied a key: `before`/`after` are
  `{ text, cursor }` with the leading pill stripped, and `key` is the key event. It records only
  when the text or the cursor changed.
- The composer's insert-text path for typed insertions, without a `key`.

Everything else changes the draft without raising `prompt.edit`: Vim NORMAL and VISUAL commands,
undo, `$.prompt.fill`, and the hook's own commits.

### Field derivation

The relay batches records onto a microtask (`rg -nF "the editor's edit stands"`). A batch is
`{ before: first.before, after: last.after }`, and `key` is kept only when the batch holds exactly
one record. The hook input is then:

- `text`, `cursor`: the batch's `before`. `cursor` is the cursor before the edit.
- `start`, `end`, `inputText`: a prefix/suffix diff of `before` against `after`. Relocate the diff
  with `rg -n 'return \{ start: n\.cursor, end: n\.cursor, inputText: "" \}'`. When the text is
  unchanged it returns `start = end = after.cursor` and `inputText: ""`. Otherwise the common
  prefix is capped at `min(before.cursor, after.cursor)`.
- `origin`: `{ kind: "composer" }`.
- `key`: `{ key, ctrl?, shift?, meta? }`. `key` is the single character, `"space"`, or the key name.

| Edit, cursor `c`                  | `start` | `end` | `inputText` | `cursor` | `key`                     |
| --------------------------------- | ------- | ----- | ----------- | -------- | ------------------------- |
| Backspace (default or Vim INSERT) | `c-1`   | `c`   | `""`        | `c`      | `{ key: "backspace" }`    |
| Left arrow                        | `c-1`   | `c-1` | `""`        | `c`      | `{ key: "left" }`         |
| Typed `x`                         | `c`     | `c`   | `"x"`       | `c`      | `{ key: "x" }`            |

A deletion always has `end > start`, so `start === end && inputText === ""` identifies a pure
cursor move. The one exception is a batch whose edits cancel out, such as a deletion and a retype
merged while the chain was busy.

### Vim mode

The Vim key handler sits in front of the base input. Relocate it with
`rg -n 'else if \(ye && S\.name === "backspace"\) Ce = "h"'` (symbols churn; the shape is "map
arrow/backspace/delete to `h`/`l`/`k`/`j`/`x`, then run the command table").

- INSERT: every key that is not a remap is forwarded to the base handler, so Backspace deletes and
  is recorded as in the table above. Esc's one-column step left is not recorded.
- NORMAL: Backspace becomes the `h` motion, Delete becomes `x`, and left/right become `h`/`l`.
  Motions and edits (`h`, `w`, `b`, `x`, `dd`, `p`, ...) run in the Vim layer, which sets the
  cursor and text directly. None of them raises `prompt.edit`. The keys forwarded to the base
  handler, and therefore recorded, are ctrl and meta chords, Return, `up`/`down` while no command
  is pending, and `left` on an empty draft.
- VISUAL: never forwarded, never recorded.

A `prompt.edit` hook that snaps the cursor out of a token therefore does nothing in NORMAL mode.
Backspace walks the cursor left through the token one column at a time, and `x`/`d` edits can cut
it without the hook seeing them.

The current Vim mode lives in the draft store's `vimMode`. Hook inputs, `$.prompt.read` (only
`{ text, cursor }`), and `ui.render` props do not expose it. The status-line command's
`vim.mode` field is the only outside reader. Whether Vim is on is the global-config key
`editorMode` (`"vim"`).

### Undo

`chat:undo` (`ctrl+_`, `ctrl+-`, `ctrl+shift+-`, `ctrl+shift+_`) and Vim `u` call the same undo
function. It pops a snapshot and sets the value and cursor directly, so undo raises no
`prompt.edit`. A hook cannot see or re-shape an undo, and nothing marks a later edit as following
one.

The snapshots come from the composer's change handler. Relocate it with
`rg -n 'maxBufferSize: 50, debounceMs: 1000'`. Each draft change pushes the text before the
change, and that includes a hook's commit, which goes through the same handler. Pushes are
debounced at 1000 ms: a push within 1 s of the last real push cancels any pending one and
reschedules itself. The exceptions are Vim NORMAL mode, where every push is immediate, and the
first push after each Vim mode change. Undo cancels a pending push.

For a keystroke the hook rewrites, the keystroke pushes the original text and the hook's commit
pushes the intermediate text (keystroke applied, before the rewrite):

- Undo within 1 s of an idle start restores the original in one step.
- Undo after 1 s restores the intermediate text first, then the original.
- When the keystroke came within 1 s of earlier typing, the original's push is replaced by the
  intermediate's, so undo reaches the intermediate text and never the original.

□ Tripwire: `rg -n '\.record\(\{'` inside the composer still finds exactly the two relay sites;
  the Vim NORMAL path still maps Backspace to `h`; the undo handler still sets the value without
  recording. If any changes, this section is stale.


## Pane placement and width

Panes are placed only when the terminal is wide enough. The predicate compares
`Nme.get()?.columns` against `110` if the user has already been asked about this pane
(the pane store's `asked` list), or `144` otherwise. Same constants as the diff sidebar. Relocate by
grepping for the pane store's shape: `rg -n 'focusedId'` and read the reducer file that also defines
`shownId`, `unplaced`, `asked`, `placements`, `closing`.

The `Pane` render site passes these props to the plugin's `ui.render` handler:

```
{ title, isFocused, bodyColumns, placement: "dock" | "inline", scroll: { offset, bodyRows }, view }
```

`placement` is `"dock"` when the pane fills, `"inline"` otherwise. The engine components a plugin can
draw are fixed; grep the component→site map with `rg -n 'AskUserQuestionPermissionDialog'` — it maps
`AskUserQuestion`, `UserMessage`, `AssistantMessage`, `ToolUse`, `ToolResult`, `ToolGroup`,
`ToolProgress`, `CommandOutput`, `Spinner`, `TurnDuration`, `InfoNotice`, `SessionMode`,
`PromptHint`, `AbovePrompt`, `Pane`. The elements available per surface are a separate table
(`rg -n '"Raster"'`); the `terminal` surface allows `Box`, `Text`, `Button`, `Input`, `Select`,
`Link`, `Code`, `Markdown`, `Client`, `Raster`, `Image`.


## Vertical chrome: which surface owns the blank rows

No shared container inserts a blank row. The fullscreen layout's side slots, the pane dock, and the
pane host all add zero vertical padding, so every blank row above a panel's first line of content is
drawn by that panel's own tree.

### The layout's two side slots add width and a background, nothing else

Grep `rg -n 'sidebarWidth'` — 2 hits, the prop and its single consumer, the fullscreen layout
component. That component takes `sidebar` / `sidebarWidth` and `dock` / `dockWidth`, and wraps
each in the same Box:

```
{ width, flexShrink: 0, flexDirection: "column", overflow: "hidden",
  backgroundColor: "composerSidebarBackground" }
```

(the dock slot additionally sets `display: "flex" | "none"`). Relocate both by grepping
`rg -n 'backgroundColor: "composerSidebarBackground"'` — 3 hits in the layout module: the sidebar
slot, the dock slot, and the absolutely-positioned dock tail below the pane. None of the three sets
`padding*`, `margin*` or `gap`.

The transcript column is the one slot that insets itself. Its scroll box carries
`paddingTop: <1, or 0 while a sticky prompt is showing>`. That row belongs to the transcript; the
side slots never receive it.

### The diff sidebar's blank top row is a `paddingY: 1` on its own header block

The native diff panel body is the component that registers the base-cycling binding; find it with
`rg -n 'context: "DiffPanel"'` (2 hits: the default keybinding table and the component). Its root
is

```
Box { flexDirection: "column", width, height: "100%", onWheel, selectionScope: true }
```

with no padding, no margin and no gap, and exactly two children:

| Child         | Props                                                              |
| ------------- | ------------------------------------------------------------------ |
| header block  | `flexDirection: "column", paddingX: 1, paddingY: 1, flexShrink: 0`  |
| scroll region | `flexGrow: 1, flexDirection: "column", overflow: "hidden"`          |

The `paddingY: 1` on the header block is the inset. It puts one blank row above the header's first
line, the `<N> files changed` row built as
`[Text{bold}[count, " ", plural("file")], " ", "changed", <+/- counts>]`, and one blank row below
the block's last child. The base-mode line (`uncommitted (vs HEAD)`, `branch vs <base>`,
`vs HEAD (no base branch)`, or `no commits yet — showing staged and new files`) is the header
block's second child and sits directly under the count row with nothing between them.

Relocate the header block from the base-mode label: `rg -nF 'uncommitted (vs HEAD)'` (1 hit) finds
the label helper, whose sole caller is the header block's second child. Read up from that call to
the enclosing Box carrying `paddingX: 1, paddingY: 1`.

Below the header, the scroll region adds `paddingX: 1` only; the scrollable Box spreads its rest
props straight into `style` and contributes no padding of its own. The empty-state branch
(`Loading diff…`, `No uncommitted changes`, …) likewise sets `paddingX: 1` with no vertical
padding.

□ Tripwire: `rg -n 'paddingY' <bundle>` in the diff panel's component; if the header block loses
  `paddingY: 1` in favour of `paddingTop`/`paddingBottom`, the top and bottom insets can diverge.

### A plugin pane's tree starts on the first body row

The dock chain is three components, all exported from one module's `Cs(...)` map — grep
`rg -n 'PaneSite: \(\) =>'` and read the enclosing export list for `PaneDock`, `PaneHost`,
`PaneSite`, `PaneTabs`, `chromeRows`, `DOCK_GRIP_COLUMNS`.

`PaneDock` is a row Box, `flexGrow: 1`, holding the drag grip (`DOCK_GRIP_COLUMNS = 1`) and a plain
`flexDirection: "column"` Box around `PaneHost`. `PaneHost` resolves the shown pane and renders
`PaneSite` inside an error boundary. Neither adds padding.

`PaneSite` is the chrome. Its outer Box:

```
Box {
  flexDirection: "column", flexShrink: 0, width, height: <fill ? rows : undefined>,
  borderStyle: <inline ? "round" : undefined>, borderDimColor: !isFocused,
  borderTopDimColor: !isFocused && !lit, borderTopColor: <lit ? "suggestion" : undefined>,
  paddingX: <inline ? 1 : 0>, onClick, onWheel, selectionScope: true,
}
```

`inline` is `!fill`, and `fill` is what the `placement` prop reports: `placement: fill ? "dock" :
"inline"`. So a docked pane gets `paddingX: 0` and no border at all. There is no `paddingY`,
`paddingTop`, `marginTop` or `gap` on this Box in either placement.

Its children, in order:

| Child        | Condition         | Shape                                                        |
| ------------ | ----------------- | ------------------------------------------------------------ |
| `PaneTabs`   | 2+ panes open     | row Box, `height: 1`, `gap: 1`, `overflow: "hidden"`          |
| viewport     | always            | `flexShrink: 0, maxHeight, overflowY: "hidden"`               |
| close button | always            | `position: "absolute", top: 0, right: <inline ? 1 : 0>`       |

The viewport wraps one inner Box, `marginTop: -<scroll offset>, flexDirection: "column",
flexShrink: 0`, whose children are the plugin's rendered tree. That negative `marginTop` is the
viewport's only vertical offset, and it is `0` at scroll offset 0. The close button is absolutely
positioned and consumes no row. So the plugin's first row lands on the pane's first body row, with
the single-row tab strip above it only when a second pane is open.

The row budget agrees: `chromeRows = (hasTabs ? 1 : 0) + (inline ? 2 : 0)`, so a docked single pane
reserves nothing. The column budget is `bodyColumns = columns - (inline ? 4 : 0)`: 4 for the round
border plus `paddingX: 1` on both sides.

To match the diff sidebar's look from a plugin pane, draw the blank row yourself: wrap the pane's
header in a `Box` with `paddingY: 1` (and `paddingX: 1`, which a docked pane also does not get).

□ Tripwire: `PaneSite`'s outer Box carries `paddingX` and no other spacing prop. If a `paddingY`
  or `gap` appears there, docked plugin panes gain an inset and this section is stale.

## Version notes

- 2.1.286: keys a focused pane does not bind reach the composer, and a resulting draft change
  releases the pane through `useReleaseOnEdit`. Hotkeys lowercase their input and never match
  Space. `prompt.edit` runs after the release and reports `origin: { kind: "composer" }`.
- 2.1.286: Vim NORMAL/VISUAL commands and undo (`chat:undo`, Vim `u`) raise no `prompt.edit`;
  NORMAL-mode Backspace is the `h` motion. Undo snapshots include a hook's commits.

- 2.1.277: the pane dock adds no vertical padding; a plugin pane's tree starts on the first body
  row. The diff sidebar's leading blank row is a `paddingY: 1` on its own header block.
- 2.1.277: `diff` is a built-in plugin, off by default, requiring function hooks. When it owns the
  sidebar the native diff panel is unreachable, because `panelFileView` has no setter. Drag-select
  attachment therefore only reaches a user running the native sidebar (the mod off, or function
  hooks off).
