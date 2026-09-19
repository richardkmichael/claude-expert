# Plugin Panes, the Prompt Composer, and Drag-Select Attachment

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)
Verified: 2.1.277

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


## Version notes

- 2.1.277: `diff` is a built-in plugin, off by default, requiring function hooks. When it owns the
  sidebar the native diff panel is unreachable, because `panelFileView` has no setter. Drag-select
  attachment therefore only reaches a user running the native sidebar (the mod off, or function
  hooks off).
