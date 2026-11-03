# Plugin Panes, the Prompt Composer, and Drag-Select Attachment

Verified against: cli.prettier.js 2.1.317 (2026-11-03)

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)

Three surfaces meet at the bottom of a fullscreen terminal session, and they are commonly confused
with one another:

- Panes drawn by a function-hooks plugin through the `Pane` render site. Entirely plugin-authored
  content; the engine supplies chrome, scrolling, focus and keybindings.
- The engine's own diff sidebar, a native Ink component that still ships beside the `diff` mod. It
  is the only surface wired to drag-select-to-attach.
- The prompt composer, which draws a leading "pill" for an IDE/diff line selection. The pill is not
  composer text and has no plugin-facing API.

The practical consequence: a third-party plugin drawing its own `Pane` cannot get the
`[⧉ N lines from FILE]` pill or the `selected_lines_in_diff` attachment. It can read the terminal
selection (`$.ui.selection`), put text in the composer and colour it (`$.prompt.fill`,
`$.prompt.paint`), and add context at submit, but not reach the pill itself.

`NATIVE_DIFF_SIDEBAR.md` is the full extraction of the second surface: the `/diff` command and its
gating, the sidebar's component tree, the drag-to-attach path end to end, focus handling, and a
capability-by-capability correspondence with the `$` API.


## The `diff` mod is a built-in plugin, on by default, and it displaces the native sidebar

Relocate the built-in-plugin registration with `rg -n 'builtinPluginsInitialized'` and read the
initializer it guards. It registers built-in plugins by internal name (`cc-plugin-<name>`), each a
separate bun module required lazily: `sec-default`, `agents-md`, `telemetry`, `privacy`, then
(unless `CLAUDE_CODE_ENTRYPOINT` is `local-agent`) `plugin-authoring`, `mods-guide`, `tips`,
`mermaid`, `you-should-know`, and the entrypoint-gated `responsive-mode`, `diff`, `easel`,
`claude-platform`, `claude-test`. `diff`, `claude-platform` and `claude-test` are skipped when the
entrypoint is `local-agent` or starts with `remote`.

The `diff` mod's module exports `isOnByDefault` (true), `availabilityFlag` (`tengu_quiet_dolphin`),
`isAvailable`, `isOfferedNow`, `isPaneDrawable` and `carryPanelPreference`; relocate them with
`rg -n 'The diff panel as a plugin pane'` (its plugin description, 1 hit) and read the exports below
it. `isAvailable` requires a drawable pane (an interactive session, or the Claude Desktop entrypoint
with a pane surface) and `tengu_quiet_dolphin`, read with default true and pinned for the session.
Built-in plugins load regardless of the hooks-module rollout gates for installed plugins
(`rg -n 'built-in plugins load regardless'`), so `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` does not gate
the mod. When the mod is offered, `carryPanelPreference` copies the native sidebar's saved
`diffSidebarOpen` into the mod's store once (`diff: carried the built-in panel's saved preference`).

Ownership handoff: `rg -n 'isOwnedByPlugin'` (3 hits: a factory, a comparison, and the gate). The
factory reads whether the native sidebar is on at all and whether the mod owns it. Ownership
requires: not a thin client (remote mode), the `cc-plugin-diff` plugin registered and
`isAvailable()`, the plugin in the enabled set, and its storage id live.

The two surfaces answer to different flags: the native sidebar is on unless the kill switch
`tengu_jazzy_ripple` is set, while `tengu_quiet_dolphin` gates the mod (default on).

Two consequences follow, both greppable:

- The built-in `/diff` slash command is enabled only while the mod does not own the diff. Locate it
  with `rg -n '"Toggle the diff panel showing uncommitted changes"'` (2 hits: the built-in command,
  and the mod's own `COMMAND_DESCRIPTION`).
- The native sidebar renders only when
  `isSidebarOn && (panelFileView !== null || !isOwnedByPlugin)`. `panelFileView` has 13 occurrences
  and none assigns a non-null value: it is initialized to `null`, read by selectors, and cleared by
  reducers. So when the mod owns the diff, the native sidebar never mounts, and by default it does.

□ Tripwire: `rg -c 'panelFileView'` = 13, and `rg -n 'panelFileView:' | rg -v 'null'` is empty. If a
setter appears, the native sidebar can coexist with the mod; revisit this section.


## Drag-select to attach: engine-only, native diff sidebar only

### What the feature is

Dragging a text selection inside the native diff sidebar puts
`{ source: "diff", text, lineCount, filePath }` into the session's `ideSelection` state. The
composer then shows a leading pill, and the selected lines travel with the next prompt as a
`selected_lines_in_diff` attachment. It reaches only a user whose native sidebar mounts: the `diff`
plugin disabled, or `tengu_quiet_dolphin` served off.

### Locating it

Grep the telemetry event: `rg -n 'diff_selection_attach'`. Expect 3 hits: the event-name allowlist,
the call site, and the `diff` mod's telemetry key table (the mod reuses the name for its file-level
attach, a different feature; see below).

The call site is a React hook of the shape:

```
hook(minCol, getMaxRow, onAskAboutSelection, rowToPath)
  subscribe to the terminal selection store
  bail if: no attach callback | isDragging | no selection
  bail if: no anchor/focus, or anchorSpan.kind === "line"
  bail if: anchor or focus column (virtual column when set) < minCol
  bail if: anchor or focus row > getMaxRow()
  text = store.getSelectedText(); bail if blank or unchanged
  lineCount = newline count of text.trimEnd() + 1
  filePath = rowToPath(min(anchor.row, focus.row))
  onAskAboutSelection({ source: "diff", text, lineCount, filePath })
```

The terminal selection store is the engine's mouse-selection accessor, reachable from
`rg -n 'subscribeToSelectionChange'`. It exposes `getSelectedText`, `copySelection`,
`copySelectionNoClear`, `hasTextSelection`, `clearTextSelection`, `moveSelectionFocus`,
`setSelectionBgColor` and the raw `selection` state.

□ Tripwire: outside the selection store's own class and its null-object stub, `getSelectedText` has
three consumers: the attach hook, the `$.ui.selection` reader, and the reset of the selection kept
for that reader. A fourth consumer means the feature has been generalized.

### What it applies to

Not "any Ink text", not `Code` elements, and not plugin panes.

- The only producer of `ideSelection` with `source: "diff"` is the native diff sidebar's
  `onAskAboutSelection` prop. `rg -n 'onAskAboutSelection'`: 4 hits, all in the native sidebar
  chain. The REPL host passes the session's `setIdeSelection` down, or `undefined` while a blocking
  dialog is visible.
- The only other writer of `ideSelection` is the IDE MCP connection path
  (`rg -n 'offerIdeSelection'`), which produces `source`-less selections that render as
  `selected_lines_in_ide`.
- A mod-drawn `Pane` has its drag clamped to its own column band but gets no attach and no drag
  autoscroll. The renderer clamps a drag to the nearest ancestor Box with `selectionScope` (inside
  its border and padding), and both `PaneSite` Boxes set it. Drag autoscroll runs only in the
  transcript and in the native diff panel, which subscribes with `requireScope: true`
  (`rg -n 'requireScope: !0'`, 1 hit, in the diff panel).

### Plugins: `$.ui.selection`

`$.ui.selection()` answers the terminal's current mouse selection as `{ text, requestId? }`, or
nothing. It reads only while the alternate screen is active (fullscreen). `requestId` is set when
the selection lies wholly within one transcript row the engine can attribute. A selection that was
taken down (for example by the click that pressed a Button) is kept and answered until a newer
selection or the next hook run. Telemetry: `plugin_function_hooks_selection_read`. It does not touch
`ideSelection`, so it produces neither the pill nor the attachment.

### Where the filename comes from

Not from a `Code` element's `path` prop, not from a heading. The sidebar keeps a
`Map<path, inkNode>` populated by a per-file `ref` callback on each rendered file block, keyed on
the repo-relative path. A helper walks that map, computes each node's absolute top (summing
`getComputedTop()` up the parent chain, subtracting `scrollTop` where a parent scrolls), and returns
the key whose vertical band contains the selection's topmost row.

The mod's `Code` elements do pass `path`, but the terminal `Code` renderer uses it only as the
`filePath` for syntax highlighting and diff rendering. `rg -n 'Code prop "'` finds the `Code` prop
validator (`source`, `language`, `path`, `startLine`, `format`, `wrap`).

### Gating

| Gate                       | Where                                                        |
| -------------------------- | ------------------------------------------------------------ |
| Fullscreen only            | the sidebar enable predicate requires `fullscreen`           |
| `columns >= 110`           | same; auto-open needs `>= 144` unless `diffSidebarOpen` true |
| Git repo, main, not remote | same predicate                                               |
| `replTab === "diff"`       | the sidebar host returns `null` otherwise                    |
| Left-edge column           | `minCol` is terminal columns minus sidebar width             |
| Bottom row                 | `getMaxRow` is the sidebar's last row                        |
| No blocking dialog         | the host withholds the attach callback while one is visible  |
| Not a line selection       | `anchorSpan.kind === "line"` (triple-click) is excluded      |

`110` and `144` are the constants the pane placement gate uses (see Panes below) and the buckets the
diff telemetry reports (`under_110`, `110_to_143`, `144_to_199`, `200_plus`). The refusal text is
`Resize your terminal to at least 110 columns to show the diff panel`.

### Clipboard

Attach does not suppress copy. Copy-on-select is a separate, global subscriber to the same selection
store, gated on the `copyOnSelect` setting (default on, toggle labelled "Copy on select" in
`/config`). It fires on drag end and writes through the native clipboard, a tmux buffer, or OSC 52,
reporting `copied N chars to clipboard` / `sent N chars via OSC 52`. If a drag in the diff sidebar
does not reach the clipboard, `copyOnSelect` is off: the attach path never copies.

### What the model receives

`rg -n 'from the diff view'` finds the attachment's prompt rendering:

```
The user selected the following <N> line(s) from the diff view (in <path>):
<content>

This may or may not be related to the current task.
```

marked as a meta message. The IDE variant is `The user selected the lines <a> to <b> from <file>:`.
`rg -n 'selected_lines_in_diff'` finds five sites: creation, prompt rendering, two attachment-type
sets, and the transcript row. The selection is cleared on submit, so it attaches exactly once.

### The mod's own attach is a different thing

The `diff` mod attaches a whole file's diff, not a mouse selection, through its `prompt.submit` hook
by appending a context block. `rg -n 'from the diff pane to this prompt'`: the text is
`The user attached the diff of <path> from the diff pane to this prompt:` followed by hunk lines,
truncated with `(The rest of this diff was cut: it did not fit in the prompt.)`. This produces no
composer pill.


## The composer pill is a `leadingPill`, not text

`rg -n 'leadingPill'`: 7 hits: the prop in the text-input hook's destructuring, the input's cursor
model, two renderer reads, a memo comparison, and the construction site.

The pill object is `{ text, onDelete }`. Its label is built in two steps:

1. A label builder producing `⧉ <N> line|lines from <basename(filePath)>` for a diff-sourced
   selection, `⧉ <N> lines from diff` when there is no path, `⧉ <N> lines selected` for an IDE
   selection (only while the IDE is connected), or `⧉ In <basename>` for a cursor-only IDE
   selection. The glyph is a hoisted constant: relocate with `rg -n 'In \$\{'` near `"from diff"`,
   never the rendered `[⧉ 3 lines from README.md]`.
2. A wrapper that replaces `]` with `)`, collapses newlines to spaces, truncates to 32 columns
   middle-out, wraps it in `[...]`, appends a trailing space, and NFC-normalizes.

Behaviour that follows from it being a prefix rather than buffer content:

- The cursor model is built from `pillText + value`, and every offset is shifted by
  `pillText.length`. The cursor is clamped so it cannot move inside the pill.
- The pill is highlighted as `[0, pillText.length - 1]` with theme colour `ide` at priority 30.
  `ide` is `rgb(71,130,200)` in the graphical themes and `ansi:blue` / `ansi:blueBright` in the ANSI
  themes.
- Backspace at offset 0 clears the prefix and fires `onDelete`, which dismisses the selection.
- `$.prompt.read` returns the draft `{ text, cursor }` without the pill.

Pasted-text placeholders are literal text in the buffer: `[Pasted text #N]`,
`[Pasted text #N +M lines]`, `[Image #N]`, `[...Truncated text #N +M lines...]`,
`[✦ Team setup guide #N]`. The shared atomic-token pattern (`rg -nF 'Pasted text|Image|'`) also
matches `\[⧉ [^\]\n]+\]`, so word motion and atomic delete treat the pill like a placeholder, but
only placeholders are in the buffer and expanded at submit.

### What a plugin can and cannot do in the composer

The engine's highlight list (bash prefix, `@`-mentions, slash commands, shimmer, ghost text) is
computed inside the chat component. Plugin decorations are a separate layer merged over it:

- `$.prompt.paint({ text, decorations })` sets the calling plugin's layer of runs over the draft. It
  paints only when the composer reads exactly `text`; `decorations: []` clears the layer. Layers
  paint in first-paint order, a later one winning per style key, and follow later edits.
- `$.prompt.fill({ text, mode, decorations?, cursor? })` places text (`replace`, `append`, `insert`)
  and can paint runs over the placed text and set the caret.
- A `prompt.edit` answer may carry `decorations`, painted when the draft reads its text.

A run is `{ start, end }` in UTF-16 offsets plus `color`, `backgroundColor`, `dimColor`, `bold`,
`italic`, `underline`, `strikethrough`, and `virtualText`: a zero-width run whose text is drawn at
`start` without entering the draft. No run key makes a range atomic, and nothing reaches
`leadingPill` or `ideSelection`.

The plugin-facing `$` surface is built by one factory; relocate it with `rg -n 'blit: \('` and read
the enclosing object and its caller, which lists the nouns:

- `ui`: `notice`, `invalidate`, `blit`, `resolve`, `log`, `status`, `ask`, `toast`, `notify`,
  `open`, `close`, `panes`, `place`, `backdrop`, `selection`, `scroll`, `focus`, `copy`, `view`
- `prompt`: `submit`, `read`, `media`, `fill`, `paint`, `suggest`, `compose`
- `session`: `messages`, `cwd`, `root`, `model`, `turns`, `id`, `repo`, `surface`, `surfaces`,
  `authorize`, `identity`, `usage`, `version`, `send`, `append`, `compact`
- `model`: `complete`, `fork`, `classify`; `settings`: `read`
- others: `audio`, `mcp`, `turn`, `tool`, `command`, `config`, `telemetry`, `agent`, `fs`, `store`,
  `state`, `clock`, `http`, `process`, `env`, `flag`

`prompt.attachment`, `prompt.edit`, `prompt.change`, `prompt.section`, `prompt.context`,
`prompt.autocomplete` and `prompt.mention` exist only as hook events. `prompt.attachment` rewrites
an attachment the engine already created, matched by `{ type }` (e.g. `selected_lines_in_diff`); it
cannot create one and never touches the composer.

□ Tripwire: the full hook-event list is one array; find it with `rg -n '"prompt.attachment"'` (the
first hit) and read the enclosing array. If a pill-related event, a composer-attachment method or an
atomic decoration key appears, this section is stale.


## `$.prompt.fill` and keyboard focus

The implementation: `rg -nF 'fillDraft = '` (1 hit); the bridge is the session scope's `composer`
object (`write`, `paint`, `read`).

- Refuses with `{ isFilled: false, refusal: "dialog" }` while a dialog is open. The pane store is a
  different store, so a focused pane does not block a fill.
- `replace`: sets input mode back to `prompt`, replaces the value. `append`: concatenates, without
  resetting the mode. `insert`: inserts at the cursor, outside any placeholder.
- `cursor` places the caret (snapped out of placeholders and to a grapheme boundary); without it,
  `replace` and `append` move the caret to the end.

It performs no focus manipulation. After `$.prompt.fill`, focus stays wherever it was.

The one focus interaction runs the other way: a pane opened with `$.ui.open({ focus: true })`
records a `focusRequest`, honoured only while the draft is empty (and no dialog, footer selection or
agent-view selection is active, no pane is focused, and a pane is placed). So filling the composer
prevents a later pane from taking focus.

### `$.ui.focus` cannot grab focus

`$.ui.focus({ requestId, key })` moves focus within a site the plugin already holds. Grep
`rg -n 'that site does not hold the keyboard'` for the core; it denies with one of:

- `no such site`
- `not this plugin's site`
- `that site does not hold the keyboard`
- `another plugin's element holds the keyboard`
- `no element of its own is drawn under that key`


## Moving focus into a pane: `ctrl+x tab`

Default keybinding table, `rg -n 'abovePrompt:focus'`:

- `"ctrl+x tab"` → `abovePrompt:focus`, in the `Chat` context, described
  `focus plugin buttons, inputs and selects`.
- `"ctrl+x ctrl+a"` → `abovePrompt:toggle` (`hide/show plugin panel`).

The handler, in order:

1. A pane is focused: move to the next open pane (`open[indexOf(focused) + 1] ?? null`); past the
   last it yields `null`, returning focus to the composer.
2. The above-prompt band has a focusable: focus it.
3. Any pane is open: focus the first.
4. Otherwise the binding is unhandled.

Once a pane holds the keyboard, its contexts are `Pane`, or `PaneField` plus `AbovePromptInput` /
`AbovePromptSelect` when the focused element is an `Input` / `Select`:

| Context             | Bindings                                                                |
| ------------------- | ----------------------------------------------------------------------- |
| `Pane`              | `tab`/`shift+tab` navigate, `enter` press, `escape` leave, `up`/`down`/ |
|                     | `pageup`/`pagedown`/`home`/`end` scroll, `ctrl+x left`/`up` grow,       |
|                     | `ctrl+x right`/`down` shrink, `ctrl+x x` close                          |
| `PaneField`         | `ctrl+x x` close                                                        |
| `AbovePromptInput`  | `tab`/`shift+tab` navigate, `enter` submit, `escape` leave              |
| `AbovePromptSelect` | as `AbovePromptInput`, plus `up`/`down` move the highlight              |
| `AbovePrompt`       | as `Pane` without the `ctrl+x` chords, plus `right`/`left` navigate and |
|                     | `space` press                                                           |

`pane:next` / `pane:previous` (`show next/previous plugin pane`) are bound in `Global` while two or
more panes are open, with no default chord. With the composer focused, `escape` closes the shown
pane when it was opened with `closeOnEscape` and the draft is empty.

### Keys a focused pane does not consume

A focused pane intercepts keys in two layers; any key neither consumes reaches the composer as
ordinary typing, and the pane loses the keyboard as a side effect. The key is not replayed.

Layer 1 is Button hotkeys, a pre-dispatch interceptor. Relocate it from the module's exports,
`rg -nF 'hotkeysOf: () =>'` and `rg -nF 'hotkeyPresses: () =>'`:

- `hotkeysOf` maps each drawn Button's `hotkey` to its press, not descending into `engine` nodes.
- A key qualifies only with no ctrl, meta, super, escape, tab or return flag, and only if its text
  matches `/^[^\p{C}\p{Z}]+$/u`. Space is `\p{Z}`, so Space is never a hotkey.
- Each character is NFKC-normalized and lowercased; Shift+A presses the `a` hotkey.
- Every character of the chunk must map to a hotkey, or none is pressed.
- The interceptor is active only while the `Pane` context is.
- The Button validator accepts only one digit or lowercase letter
  (`rg -nF 'hotkey must be one digit'`).

Layer 2 is the `Pane` table. Every action has a handler in every pane state:

| Key                              | Effect                                                       |
| -------------------------------- | ------------------------------------------------------------ |
| `tab` / `shift+tab`              | walk the ring: focusables, a stop per other open pane, `✕`   |
| `enter`                          | press the Button, submit the Input, pick the tab, or close   |
| `escape`                         | leave the pane, or close it when opened with `closeOnEscape` |
| `up` / `down`, content overflow  | scroll one row                                               |
| `up` / `down`, nothing to scroll | previous / next plugin focusable, wrapping; else nothing     |
| `pageup` `pagedown` `home` `end` | scroll by a page / to an end                                 |
| `ctrl+x` chords                  | grow, shrink, close                                          |

The `up`/`down` split: the ring handlers define `pane:scrollUp`/`pane:scrollDown` as focus moves,
and the scroll handlers replace them only when `maxOffset > 0`. `rg -n '"pane:scrollUp": \(\) =>'`
finds both (2 hits).

Every other key reaches the composer: Space, printable characters no hotkey claims, Backspace,
Delete, left/right, ctrl or meta editing chords. `Chat` and `Global` bindings the `Pane` context
does not bind still resolve; `ctrl+x tab` is one.

The release is `useReleaseOnEdit` (`rg -nF 'useReleaseOnEdit: () =>'`). While a pane or the band
holds the keys, it watches the draft and, on the first change to `value`, clears the band focus and
calls `focusPane(null)`. It compares `value` only: a key that changes the text releases the pane and
the edit stays; a key that leaves the text unchanged (left/right, Backspace at offset 0 or on an
empty draft, Delete at the end) does not release.

#### What a plugin can do about it

No pane option, Button prop or hook event intercepts an unconsumed key. `$.ui.open` options are
`id`, `title`, `focus`, `closeOnEscape`, `holdToasts`, `backgroundColor`, `rows` and `columns`.

`prompt.edit` cannot prevent the release: the composer writes the new value first and records the
edit second, and the relay batches onto a microtask (`rg -nF "the editor's edit stands"`). A handler
can still undo the text by answering the before state `{ text: e.text, cursor: e.cursor }`. The
input's `origin` is always `{ kind: "composer" }`; nothing marks a key that fell through from a
pane. `key` is present only when the batch holds one edit.

Taking the keyboard back: `$.ui.focus` is denied (`that site does not hold the keyboard`).
`$.ui.open({ id, focus: true })` records a `focusRequest`; the settle step
(`rg -nF 'settleFocusRequest'`) re-evaluates it when it or the draft changes and honours it only
under the empty-draft conditions above. So re-focusing works only when the draft was empty before
the key and the undo has committed. The pane's focus index resets when it loses the keyboard, so a
plugin must call `$.ui.focus({ requestId, key })` to put the ring back on its Button.

□ Tripwire: the hotkey test still excludes `\p{Z}` and lowercases; the `Pane` table has no `space`,
`backspace` or `left`/`right`; `useReleaseOnEdit` compares only `value`; the composer applies the
edit before recording it. If any changes, this section is stale.


## What `prompt.edit` receives: edit shape, Vim mode and undo

The relay records only while some plugin hooks `prompt.edit` (`rg -n 'prompt.edit: hooked'`). Two
composer paths record (`rg -n '\.record\(\{'`, 2 hits):

- The base text input's key handler, after it applied a key: `before`/`after` are `{ text, cursor }`
  with the pill stripped, and `key` is the key event. It records only when text or cursor changed.
- The composer's insert-text path, without a `key`.

Everything else changes the draft without raising `prompt.edit`: Vim NORMAL and VISUAL commands, Vim
INSERT remaps (`vimInsertModeRemaps`), undo, `$.prompt.fill`, and the hook's own commits.

### Field derivation

A batch is `{ before: first.before, after: last.after }`, with `key` only for a single record. The
hook input (budget 50 ms):

- `text`, `cursor`: the batch's `before`.
- `start`, `end`, `inputText`: a prefix/suffix diff of `before` against `after`, found in the same
  block as the relay. Unchanged text gives `start = end = after.cursor` and `inputText: ""`;
  otherwise the common prefix is capped at `min(before.cursor, after.cursor)`.
- `origin`: `{ kind: "composer" }`.
- `key`: `{ key, ctrl?, shift?, meta? }`; `key` is the single character, `"space"`, or the key name.

| Edit at cursor `c` | `start` | `end` | `inputText` | `cursor` | `key`                  |
| ------------------ | ------- | ----- | ----------- | -------- | ---------------------- |
| Backspace          | `c-1`   | `c`   | `""`        | `c`      | `{ key: "backspace" }` |
| Left arrow         | `c-1`   | `c-1` | `""`        | `c`      | `{ key: "left" }`      |
| Typed `x`          | `c`     | `c`   | `"x"`       | `c`      | `{ key: "x" }`         |

Backspace has this shape in the default editor and in Vim INSERT.

`start === end && inputText === ""` identifies a pure cursor move, except for a batch whose edits
cancel out.

The answer `{ text, cursor, decorations? }` commits when the draft still reads the editor's `after`.
If typing moved on meanwhile, the answer's change is rebased over it when the two do not overlap;
otherwise it is dropped with `a rewrite no longer fits the draft (it moved meanwhile)`.

### Vim mode

The Vim key handler sits in front of the base input; relocate it with `rg -n 'vim_insert_remap'`
(the telemetry calls inside it).

- INSERT: every key that is not a remap is forwarded to the base handler, so Backspace is recorded
  as above. Esc's step left is not recorded.
- NORMAL: Backspace is Vim's backspace motion (left, crossing line starts), Delete is `x`, arrows
  are `h`/`j`/`k`/`l`. Motions and edits run in the Vim layer and raise no `prompt.edit`. Forwarded
  and recorded: ctrl and meta chords, Return, `up`/`down` while idle, `left` on an empty draft.
- VISUAL: never forwarded, never recorded.

The current mode is the draft store's `vimMode`; hook inputs, `$.prompt.read` and `ui.render` props
do not expose it. The status-line command's `vim.mode` field is the only outside reader. Vim is on
when the `editorMode` setting is `"vim"`.

### Undo

`chat:undo` (`ctrl+_`, `ctrl+-`, `ctrl+shift+-`, `ctrl+shift+_`) and Vim `u` pop a snapshot and set
the value directly, so undo raises no `prompt.edit`. It does raise `prompt.change` with
`origin: { kind: "undo" }`, an observer event for draft changes that are not composer typing; its
answer is not applied, so a hook can see an undo but not re-shape it.

Snapshots come from the composer's change handler (`rg -n 'maxBufferSize: 50, debounceMs: 1000'`).
Each change pushes the text before it, including a hook's commit. Pushes are debounced at 1000 ms: a
push within 1 s of the last cancels any pending one and reschedules itself. With Vim on, pushes
outside INSERT and the first push after a mode change are immediate. Undo cancels a pending push.

For a keystroke the hook rewrites, the keystroke pushes the original and the commit pushes the
intermediate text:

- Undo within 1 s of an idle start restores the original in one step.
- Undo after 1 s restores the intermediate text first, then the original.
- When the keystroke came within 1 s of earlier typing, undo reaches the intermediate text and never
  the original.

□ Tripwire: `rg -n '\.record\(\{'` still finds exactly two relay sites; NORMAL Backspace is still a
motion; undo still sets the value without recording. If any changes, this section is stale.


## Pane placement and size

A pane opens placed only when the terminal is wide enough: `110` columns if the person opened that
id before (the pane store's persisted `asked` list), else `144`; a person-initiated open bypasses
the gate. Otherwise it waits in `unplaced` with a reason starting `unasked below <N> columns`
(`rg -n 'unasked below'`), placed when the person opens it or the terminal is widened.

A placed pane docks or sits inline:

- Docked (`placement: "dock"`): fullscreen, the native diff sidebar not showing, and `>= 110`
  columns. Default width `min(floor(0.45 × columns), 90, columns − 70)`; a chosen or requested width
  is clamped to `[24, min(floor(0.45 × columns), columns − 60)]`.
- Inline (`placement: "inline"`): above the prompt, full width. Default height a third of the rows,
  at least 5.

Sizes chosen with the grips or `ctrl+x` chords persist in global config `pluginPanes`
(`dockColumns`, `inlineRows`). Relocate with `rg -nF 'DOCK_GRIP_COLUMNS: () =>'`, whose export map
also lists `chromeRows`, `dockColumns`, `inlineRows`, `PaneDock`, `PaneHost`, `PaneSite`,
`PaneTabs`, `DockTail` and `InlinePanes`.

The `Pane` render site passes the plugin's `ui.render` handler:

```
{ title, isFocused, bodyColumns, placement: "dock" | "inline", scroll: { offset, bodyRows }, view }
```

The components a plugin can draw are a fixed map (`rg -n 'AskUserQuestionPermissionDialog'`):
`AskUserQuestion`, `UserMessage`, `AssistantMessage`, `ToolUse`, `ToolResult`, `ToolGroup`,
`ToolProgress`, `CommandOutput`, `Spinner`, `TurnDuration`, `InfoNotice`, `SessionMode`,
`PromptHint`, `AbovePrompt`, `Pane`, `Placed`, and `Backdrop` (drawn only by a remote surface). The
`terminal` surface allows `Box`, `Text`, `Button`, `Input`, `Select`, `Link`, `Code`, `Markdown`,
`Client`, `Raster`, `Image` (`rg -n 'mobile: \["Box"'` finds the per-surface table).


## Vertical chrome: which surface owns the blank rows

### The layout's side slots add width, nothing vertical

`rg -n 'sidebarWidth'` (2 hits: the fullscreen layout's prop and its caller). The layout wraps the
sidebar, when its width is positive, in a column Box with `width`, `flexShrink: 0`,
`overflow: "hidden"` and `backgroundColor: "composerSidebarBackground"`, and the dock in the same
Box with `display: "flex" | "none"` and no background. Neither sets `padding*`, `margin*` or `gap`.
The dock's fill comes from `PaneDock` and `DockTail`: `composerSidebarBackground`, or none when the
shown pane was opened with `backgroundColor: "transparent"`.

The transcript scroll box carries `paddingTop: 1`, or `0` while a sticky prompt shows; that row
belongs to the transcript.

### The diff sidebar's blank top row is a `paddingY: 1` on its own header block

`rg -n 'context: "DiffPanel"'` (2 hits: the keybinding table and the panel). Its root is
`Box { flexDirection: "column", width, height: "100%", onWheel, selectionScope: true }` with two
children:

| Child         | Props                                                              |
| ------------- | ------------------------------------------------------------------ |
| header block  | `flexDirection: "column", paddingX: 1, paddingY: 1, flexShrink: 0` |
| scroll region | `flexGrow: 1, flexDirection: "column", overflow: "hidden"`         |

The `paddingY: 1` puts one blank row above the header's first line and one below its last child. The
first line is a row: `<N> files changed` with `+/-` counts, a spacer, and a close button. Under it,
the base-mode line (`this session`, `uncommitted (vs HEAD)`, `branch vs <base>`,
`vs HEAD (no base branch)`, or `no commits yet — showing staged and new files`), shown unless the
base is `session`; then a progress bar and the file list, each with `marginTop: 1`. Relocate the
block from `rg -nF 'uncommitted (vs HEAD)'` (1 hit, the label helper).

Below the header the scroll region adds `paddingX: 1` only. The empty state centres its headline
with `paddingX: 1`, plus a `paddingBottom: 1` row for files edited before the session.

□ Tripwire: if the header block loses `paddingY: 1` for `paddingTop`/`paddingBottom`, the insets can
diverge.

### A docked plugin pane reserves one top row

`PaneDock` is a row Box (`flexGrow: 1`, the dock fill) holding the drag grip
(`DOCK_GRIP_COLUMNS = 1`) and a column Box around `PaneHost`, which renders `PaneSite` in an error
boundary. Neither adds padding.

`PaneSite` is an outer column Box (`width`, `onClick`, `onWheel`, `selectionScope: true`) holding
the chrome Box and the close mark:

```
Box {
  flexDirection: "column", flexShrink: 0, height: <dock ? rows : undefined>, selectionScope: true,
  borderStyle: <inline ? "round" : undefined>, borderDimColor: !isFocused,
  borderTopDimColor: !isFocused && !lit, borderTopColor: <lit ? "suggestion" : undefined>,
  paddingX: <inline ? 1 : 0>,
}
```

| Child     | Condition           | Shape                                                          |
| --------- | ------------------- | -------------------------------------------------------------- |
| tab strip | 2+ panes open       | `PaneTabs`: row Box, `height: 1`, `gap: 1`, `overflow: hidden` |
| blank row | docked, single pane | `Box { flexShrink: 0, height: 1 }`                             |
| viewport  | always              | `backgroundColor`, `maxHeight`, `overflowY: "hidden"`          |

The close mark is absolutely positioned at `top: 0`, `right: 2` inline or `right: 1` docked, so it
sits on the border or the reserved top row. The viewport holds one Box with
`marginTop: -<scroll offset>`, `0` at offset 0, around the plugin's tree.

So a docked pane's first plugin row is the pane's second row: the first is the blank row (with `✕`)
or the tab strip. Inline, it is the first row inside the border, under the tabs when shown.
`chromeRows = (hasTabs || docked ? 1 : 0) + (inline ? 2 : 0)`, and
`bodyColumns = columns − (inline ? 4 : 0)`.

To match the diff sidebar from a docked pane, the reserved row already gives one blank row above;
add `paddingX: 1` yourself, which a docked pane does not get.

□ Tripwire: a docked single pane still renders the `height: 1` spacer; if it goes, plugin trees
start on the pane's first row and this section is stale.


## The rows under the prompt: `$.ui.status`, the `statusLine` command, and `PromptHint`

Outside screen-reader mode, the prompt column stacks:

| Order | Row                         | Drawn by                     | Plugin access               |
| ----- | --------------------------- | ---------------------------- | --------------------------- |
| 1     | prompt input box            | composer                     | `prompt.*` ops and hooks    |
| 2     | pinned notices, one per row | pinned list                  | `$.ui.status` adds one row  |
| 3     | `statusLine` command output | footer left column 1st child | none                        |
| 4     | footer hint line            | `FooterHintLine`             | `ui.render` on `PromptHint` |

The footer's right column (MCP status, IDE selection, mode labels, toasts) sits beside rows 3-4, or
below them when the footer wraps. With a screen reader on, the input box moves below the footer.

Relocate the column with `rg -n 'Waiting for permission\\u2026'` (2 hits). The hit inside a
`flexDirection: "column"` Box lists the permission-wait line, the input box, the pinned-notice list,
the footer, and a second input box for screen-reader mode.

### `$.ui.status` is a pinned notification

The REPL host's `status(plugin, text)` removes the notification `plugin-status-<plugin>` and, unless
`text` is `undefined`, adds one with `kind: "event"`, `priority: "low"`, `pinned: true` and text
`<plugin display name>: <text>`. `rg -n 'plugin-status-'` (1 hit); `toast` and `notify` sit above.

The pinned-notice list (`rg -n 'notifications\.pinned'`, 3 hits) sorts by priority and draws one
`Text` per notice in a `paddingX: 2` column, prefixed `⚠`, coloured `warning` unless set, truncated
unless the notice asks to wrap. A plugin status sets neither, so it is a single yellow
`⚠ plugin: text` row. Among `low` notices the most recently updated status is drawn last.

In a headless session the call logs `no status row in a headless session`.

### The `statusLine` command row

The footer mounts the status-line component when in `prompt` mode, no exit message shows, the user
is not pasting, and a `statusLine` is configured. Relocate with `rg -n 'tengu_status_line_mount'`
and `rg -n 'Skipping StatusLine command execution'`. The runner keeps the last stdout (`lastText`);
the component draws dim truncated `Text` lines in a Box with `paddingX` from `statusLine.padding`.
Nothing else reads that text.

### What a plugin can and cannot do to the `statusLine` row

- No render site exists for it; the component map has no status-line entry.
- No op or hook input exposes its text. A mod can read `statusLine` with `$.settings.read`, run it
  with `$.process.run`, and show the result in `$.ui.status`, `AbovePrompt` or `PromptHint`.
- `ui.status` calls pass through the hook chain, so a `ui.status` hook sees and can rewrite other
  plugins' `$.ui.status` calls. It never sees the `statusLine` command.

### `PromptHint` is the row below the `statusLine` row

The footer's left column holds the status-line component, then `FooterHintLine`. A configured
`statusLine` sets `suppressHint`, which hides only the `? for shortcuts` fallback;
`suppressHintExceptStatusline` (2 hits) omits that term for the compact footer.

`FooterHintLine` wraps its hint in `PromptHintPart`. With `ui.render` hooks for `PromptHint`, it
reads the drawn hint text, strips the mode label, and passes `{ isDraft, isWorking, hint }` to
`PromptHintSite` (`rg -n 'useRenderInput\("PromptHint"'`, 1 hit), never the status-line text.

□ Tripwire: `rg -c 'plugin-status-'` = 1 and its notice sets `pinned`; the component map has no
status-line entry; the footer's left column lists the status line before `FooterHintLine`.
