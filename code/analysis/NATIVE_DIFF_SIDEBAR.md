# The Native `/diff` Sidebar, End to End

Verified against: cli.prettier.js 2.1.317 (2026-11-03)

A reference extraction of the engine's own diff sidebar: who owns `/diff`, the command, the
component tree, the drag-to-attach path, focus handling and the close mark. It exists to be compared
against what a function-hooks plugin can reach through the `$` API, so the last section maps each
native capability onto the plugin surface and says whether a plugin can do it.

Every section leads with an `rg` recipe over `work/2.1.317/package/cli.prettier.js`; relocate with
those. Companion doc: `PLUGIN_PANES_AND_COMPOSER.md` covers the pane/dock chrome geometry, the `$`
noun table, and the `diff` built-in plugin that displaces this sidebar.


## Which surface owns `/diff`

The sidebar described here is the engine's native Ink component. It is not the `diff` built-in
plugin (a mod, registered as `cc-plugin-diff`, short name `diff`), and the two are gated by
different flags.

| Surface                      | Gate                                | Code default |
| ---------------------------- | ----------------------------------- | ------------ |
| Native diff sidebar          | `tengu_jazzy_ripple`, a kill switch | on           |
| `diff` built-in plugin (mod) | `tengu_quiet_dolphin`, pinned       | on           |

Relocate with `rg -nF 'tengu_jazzy_ripple'` (1 hit, the sidebar's enable predicate) and
`rg -nF 'tengu_quiet_dolphin'` (1 hit, the mod's availability flag). The mod's module exports
`isOnByDefault` true, `isAvailable` = "the pane is drawable and the pinned flag is on", and the
description
`The diff panel as a plugin pane: /diff, the changed files and their hunks …`
(`rg -nF 'The diff panel as a plugin pane'`). "Drawable" means an interactive session, or one Claude
Desktop hosts. Built-in plugins are enabled unless `enabledPlugins` turns them off, so with the code
defaults an interactive session gets the mod.

The mod owns the surface (`rg -nF 'isOwnedByPlugin'`, 3 hits: the snapshot, its comparison, the
predicate) when all of these hold: the session is not a thin client or remote, the `cc-plugin-diff`
built-in reports available, it is enabled, and its hooks module (or a `--plugin-dir` copy of the
same name) is live. While it owns the surface:

- the native `/diff` command reports itself disabled, and the mod registers its own `/diff`;
- the native sidebar is not drawn (the predicate is "kill switch off and not owned by the mod").

The native sidebar is therefore the fallback: it draws when the mod is turned off in
`enabledPlugins`, when the flag is off for the session, when the hooks module failed to load, or in
a context the mod does not draw in.

Name collisions go through the hooks loader's one same-name rule. Plugins are ranked by tier
(`prepend`, `user`, `append`, `builtin`, `core`); the first plugin of a name to rank wins, and a
built-in's name set includes its short name. A later one gets
`hooks module <id> not loaded: another plugin of that name loads first (…)`
(`rg -nF 'another plugin of that name loads first'`). A `--plugin-dir` plugin named `diff` sits in
the `user` tier, ahead of `builtin`, so it wins over the built-in. It loses only to a managed plugin
of that name, or when hooks modules are held for installed plugins (rollout switch, `--bare`,
managed-only or `disableAllHooks`); every such reason ends `built-in plugins load regardless`. The
one hard name refusal is `claude plugin test` in the `builtin` tier:
`<name> cannot load in the builtin tier: this Claude Code bundles a plugin of that name, …`
(`rg -nF 'cannot load in the builtin tier'`).

Everything below — the `paddingY: 1` header, `setIdeSelection({ source: "diff" })`, the
`selected_lines_in_diff` attachment — belongs to the native sidebar. The mod has none of it. Its
attach is per file: arming a file shows `<file> rides your next prompt (press asked ✓ to drop it)`
(`rg -nF 'rides your next prompt'`), and its `prompt.submit` handler then appends that file's diff
to the prompt's `context` list.


## 1. The `/diff` command and its gating

### Registration

`rg -nF '"Toggle the diff panel showing uncommitted changes"'` — 2 hits: the built-in command
descriptor and the mod's copy of the string. The descriptor is `type: "local-jsx"`, `name: "diff"`,
`thinClientDispatch: "control-request"`, enabled only while the mod does not own the surface. Its
description depends on the surface it would pick:
`Toggle the diff panel showing uncommitted changes` for fullscreen,
`View uncommitted changes and per-turn diffs` otherwise. It runs as an immediate command exactly
when it picks fullscreen.

The surface picker returns `inline` for a thin client or remote session, or when the presentation is
not fullscreen; otherwise `fullscreen` if the sidebar's kill switch is off or the command was
dispatched as immediate, else `inline`. Fullscreen resolves to the docked sidebar; inline falls back
to the modal `DiffDialog` (`rg -nF '{ DiffDialog: '`, the command body's lazy import).

In fullscreen the command calls the REPL host's `toggleDiffPanel` (`rg -nF 'toggleDiffPanel'` — 2
hits, the provider and the command). The provider runs the toggle helper, waits up to 2000 ms for
the first diff to settle when the panel is shown, and returns the status text, which the command
prints as a system message.

### The toggle helper and its four outcomes

`rg -nF '"Diff panel shown"'` — 2 hits: the constant beside the helper, and the mod's copy. The
helper hides the panel if it is the current tab; otherwise it refuses, in order, when the kill
switch is set, when there is no git repository, and when the terminal is under 110 columns; else it
shows the panel and starts the first diff.

- shown: `Diff panel shown`
- hidden: `Diff panel hidden`
- refused `unavailable`:
  `The diff panel isn't available right now — run /diff again to see your changes`
- refused `no-git`:
  `The diff panel shows git changes — the current directory isn't in a git repository`
- refused `too-narrow`: `Resize your terminal to at least 110 columns to show the diff panel`

The bundle stores the dash and apostrophe as escapes, so search
`rg -nF 'run /diff again to see your changes'` and `rg -nF 'columns to show the diff panel'`.

Showing or hiding writes `diffSidebarOpen` to the user's config and logs `repl_tab_switch`. When the
toggle arrives by keybinding (`app:toggleReplTab`, registered by the sidebar host and active only in
fullscreen outside a thin client), a refusal is also surfaced as a 3000 ms immediate notification
keyed `diff-sidebar-<reason>` (`rg -nF 'diff-sidebar-'`, 1 hit).

### Width rule

`rg -n -B2 '= "cc-plugin-diff";'` shows the two width constants declared just above the plugin name:
`110` and `144`. `110` is the floor to show the panel at all. `144` is the auto-open floor; once the
person has opened the panel (`diffSidebarOpen === true`) auto-open uses `110` instead, and after
they have closed it (`diffSidebarOpen === false`) the panel never auto-opens.

Auto-open fires from the sidebar host when the conversation tab is showing, the session's tracked
file count is non-zero and has changed since the baseline, the layout is fullscreen and not a thin
client, and the width rule passes; it waits 150 ms, computes the diff, then opens the panel.

The full mount predicate is: the sidebar enabled, fullscreen, not a thin client, the main agent view
focused, at least 110 columns, and a git repository. The docked width is
`min(floor(0.45 × columns), 90, columns − 70)` (`rg -nF 'Math.floor(h * 0.45), 90, h - 70'`).

### Telemetry

`tengu_repl_diff_panel_shown` with `trigger: "auto_open" | "manual"` and `terminal_width_bucket`,
logged once per session id (`rg -nF 'tengu_repl_diff_panel_shown'`, 2 hits: the native logger and
the mod's copy). The buckets are `under_110` / `110_to_143` / `144_to_199` / `200_plus`
(`rg -nF 'under_110'`). Tab switches log `repl_tab_switch`, base cycling logs
`repl_diff_base_switch` with `mode`, and a failed git read logs `repl_diff_read` /
`git_diff_failed`.


## 2. The sidebar component tree

Relocate the panel body with `rg -n 'context: "DiffPanel"'` — 2 hits: the default keybinding table
and the component that registers the base-cycling binding. The panel lives in one module with the
rest of the REPL screen; these strings land on each part.

| Role                    | Landmark                                         |
| ----------------------- | ------------------------------------------------ |
| sidebar host            | `rg -nF 'diff-sidebar-'` (refusal toast)         |
| panel body              | `rg -nF 'context: "DiffPanel" }'`                |
| base-mode label         | `rg -nF 'uncommitted (vs HEAD)'` (1 hit)         |
| empty and hidden states | `rg -nF 'Only hidden files changed'` (1 hit)     |
| per-file diff block     | `rg -nF 'Content restricted by read-permission'` |
| pre-session block       | `rg -nF ' edited before this session ('`         |
| noise-filter toggle     | `rg -nF '"/generated ("'` (1 hit)                |
| drag-attach hook        | `rg -nF 'g("diff_selection_attach")'` (1 hit)    |
| row → path resolver     | the function after the attach hook               |

### Host

The host does the gating and nothing else; it renders the panel body directly, with
`minCol = terminalColumns − sidebarWidth` (the left edge used by the attach hook) and the attach
callback `onAskAboutSelection`. The REPL layout passes `setIdeSelection` as that callback, or
`undefined` while a modal slot is visible (`rg -nF '.setIdeSelection,'`, 1 hit).

The layout places the host in its `sidebar` slot, which adds width and a background and no padding
(`rg -n 'backgroundColor: "composerSidebarBackground"'`).

### Root and header

The panel root is a column `Box` at the sidebar's width and `100%` height with an `onWheel` handler
and `selectionScope: true`, which confines a mouse drag to the panel's own columns. Its two children
are the header block and the scroll body.

The header block is `flexDirection: "column", paddingX: 1, paddingY: 1, flexShrink: 0`.
`paddingY: 1` is the sidebar's leading blank row. Its children, in order:

| Child         | Content                                                                         |
| ------------- | ------------------------------------------------------------------------------- |
| count row     | `<N> files changed` (count bold) + net `+a −b`, a `flexGrow: 1` spacer, `✕`     |
| base line     | dim base-mode label; drawn only off the `session` base or while a switch is due |
| todo progress | ratio bar (`min(20, width − 12)` wide) and `done/total`, only when todos exist  |
| file list     | the windowed list, `marginTop: 1`                                               |

The count row is hidden while loading or while an empty-state headline applies. The base-mode label
reads `this session`, `uncommitted (vs HEAD)`, `branch vs <base>`, or, without a base branch,
`vs HEAD (no base branch)` (`branch diff` while pending). A trailing `…` marks a pending recompute
after a base switch. When the repo has no commits the line is replaced by
`no commits yet — showing staged and new files`. The base persists per user as
`diffSidebarBaseMode`.

### File list

A windowed list of 8 rows with a `↑ N more above` line and a footer joining, with `·`,
`N more below (<key> to scroll)`, `N read-denied` and `N not shown`. `<key>` is the shortcut bound
to `app:diffFileListDown`, falling back to `alt+down`. Each row is a middle-elided path
(`width − 12`, floor 8), a spacer, and the `+a −b` counter; hovering underlines it and clicking
scrolls the matching diff block into view via `scrollToElement`. The list has its own window offset,
clamped to `files.length − 8`, and its own `onWheel` while it overflows.

Two toggles, each clickable and underlined on hover:

- `<N> test/generated (show|hide)` (pluralised `tests/generated`), at the end of the file list,
  bound to `app:toggleDiffNoiseFilter`.
- `+<N> files edited before this session (show|hide)`, bound to `app:toggleDiffPreSession`.
  Expanded, it draws its own file rows plus their diffs, capped at 20 files, then
  `diffs hidden above 20 files`.

### Empty and loading states

While loading, `Loading diff…` appears after a 300 ms delay. Otherwise one of:

- `Diff unavailable`, hint `Couldn't read the git diff — it will retry on the next change`
- `No commits yet`, hint `Nothing to diff against until the repo's first commit`
- `No uncommitted changes`
- `No changes vs <base>`
- `No changes vs HEAD`, hint `No base branch to compare against — showing changes vs HEAD`
- `No changes this session`
- `Too many changed files to show diff`, hint `Per-file diff is skipped above 500 files`
- `Only hidden files changed`, hint
  `Read-denied, test, and generated files are hidden in this panel`
- `Only read-denied files changed`, hint `Read-denied files are hidden in this panel`
- `Only tests and generated files changed`, hint
  `Tests and generated files are hidden · click "show" above to view them`

### Per-file diff rendering

One component draws each file: a bold path, a rule, then the body. Its short-circuit branches, in
order:

- restricted: `Content restricted by read-permission rules`
- untracked: path suffixed `(untracked)`; `New file not yet staged.` and
  `` Run `git add :/<path>` to see line counts. ``
- binary: `Binary file - cannot display diff`
- large: `Large file - diff exceeds 1 MB limit` (`Diff too large to display.` remote)

The normal path suffixes `(truncated)` to the path when the hunks were cut, then draws one hunk
block per hunk (`No diff content` when there are none) and
`… diff truncated (exceeded 400 line limit)` at the end. The file's content (up to 1 MB) is read
only to seed highlighting.

The hunk block is the shared renderer the Edit tool result also uses (`rg -nF 'skipHighlighting'`, 1
hit, its destructured props: `patch`, `dim`, `filePath`, `firstLine`, `fileContent`, `width`,
`skipHighlighting`). It builds a structured diff, unified or split, and falls back to a plain patch
renderer when highlighting is off (`syntaxHighlightingDisabled`, or `skipHighlighting`). `filePath`
reaches the highlighter only as a language hint; it takes no part in the row → path lookup below.
Colour keys come from the theme tables (`rg -nF 'diffAddedWord'`):

| Key                 | Graphical themes | ANSI themes        |
| ------------------- | ---------------- | ------------------ |
| `diffAdded`         | green            | `ansi:green`       |
| `diffRemoved`       | red/pink         | `ansi:red`         |
| `diffAddedDimmed`   | muted green      | `ansi:green`       |
| `diffRemovedDimmed` | muted red        | `ansi:red`         |
| `diffAddedWord`     | strong green     | `ansi:greenBright` |
| `diffRemovedWord`   | strong red       | `ansi:redBright`   |

### Keyboard

`rg -nF 'app:cycleDiffBase'` finds the binding table, the plugin-action allowlist, the action
descriptions and the handler.

| Action                      | Default chord            | Context     | Active while       |
| --------------------------- | ------------------------ | ----------- | ------------------ |
| `app:toggleReplTab`         | none in the table        | `Global`    | fullscreen         |
| `app:cycleDiffBase`         | `ctrl+x b`               | `DiffPanel` | the panel is drawn |
| `app:diffFileListUp`        | `ctrl+up`, `meta+up`     | `Global`    | the list overflows |
| `app:diffFileListDown`      | `ctrl+down`, `meta+down` | `Global`    | the list overflows |
| `app:toggleDiffNoiseFilter` | none in the table        | `Global`    | noise files exist  |
| `app:toggleDiffPreSession`  | none in the table        | `Global`    | pre-session files  |

`app:toggleReplTab` opens and closes the panel through the same helper as `/diff`.
`app:cycleDiffBase` steps session → uncommitted → branch → session.

The `DiffPanel` context is described as `When the diff sidebar panel is open`
(`rg -nF '"When the diff sidebar panel is open"'`). Note what is absent: the sidebar registers no
`escape` binding and never enters a focus ring. It is not a focusable surface. Escape in the sidebar
reaches whatever else claims it; closing is the `✕` button, `/diff` again, or `app:toggleReplTab`.

All six actions are on the engine's plugin-addressable keybinding-action allowlist — see the
correspondence section.

### Scrolling

The body is the engine's scroll box with `stickyScroll: false` and `paddingX: 1`. Three inputs drive
it:

- `onWheel` on the panel root: `scrollBy(deltaY * 3)`, then `preventDefault` and `stopPropagation`.
- Clicking a file-list row: `scrollToElement(node)` against a `Map<path, inkNode>` that each file
  block populates through a `ref` callback.
- Drag autoscroll: the selection-store hook subscribed with `{ requireScope: true }`
  (`rg -nF 'requireScope: !0'`, 1 hit), which nudges the scroll handle while a drag is held past an
  edge.


## 3. Drag-to-attach, end to end

### The terminal selection store

One accessor wraps the terminal's own mouse-selection state (`rg -nF 'subscribeToSelectionChange'`).
It exposes `copySelection`, `copySelectionNoClear`, `getSelectedText`, `clearSelection`,
`hasSelection`, `getState`, `subscribe`, `moveFocus` and `setSelectionBgColor`, with a null-object
stub when there is no terminal.

`rg -nF 'getSelectedText'` has 7 hits: the store method and its own internal call, the accessor's
stub and live wrapper, the diff attach hook, and two in the transcript selection keeper that serves
`$.ui.selection` (section 6).

### The attach hook

The hook takes the panel's left column (`minCol`), a `getMaxRow` callback, the attach callback, and
the row → path resolver. It subscribes to the selection store; on each change it attaches unless one
of these holds, checked in order:

1. there is no attach callback (a modal slot is visible);
2. a drag is in progress, or nothing is selected (both reset the "last attached" memo);
3. anchor or focus is missing, or `anchorSpan.kind === "line"` (triple-click line selections never
   attach; character and word drags do);
4. either end's column (virtual column when present) is left of `minCol`;
5. either end's row is below the panel's last row;
6. the selected text is blank, or equal to the text last attached.

Otherwise it calls the callback with `{ source: "diff", text, lineCount, filePath }`, where
`lineCount` counts newlines in the right-trimmed text plus one and `filePath` is the resolver's
answer for the selection's topmost row, and logs `diff_selection_attach`.

`getMaxRow` walks `getComputedTop()` up the parent chain and adds the panel's computed height minus
one — the panel's own last row.

### Row → path

The resolver sums `getComputedTop()` up from the scroll region to find its top; a row above that
returns `undefined`. Otherwise it walks the `Map<repoRelativePath, inkNode>` the file blocks fill,
computing each block's top (subtracting any ancestor's scroll offset) and height, and returns the
key whose vertical band contains the row. A selection with no matching band carries no path.

### Copy-on-select runs alongside, not instead

Copy-on-select is a separate global subscriber to the same store, mounted once at the app root
(`rg -nF 'copyOnSelect'`). It fires when a drag ends with a non-blank selection, reads
`copySelectionNoClear()`, logs `clipboard_write`, and writes through the native clipboard, a tmux
buffer, or OSC 52. The attach path never calls `copySelection`, so attaching does not suppress
copying and copying does not suppress attaching. Default on; the `/config` row is labelled
`Copy on select`.

### State: `setIdeSelection({ source: "diff" })`

The selection lives in the REPL session store as `ideSelection` (`rg -nF 'consumeIdeSelection = '`,
1 hit, among its methods):

- `setIdeSelection`: replaces it; forgets the dismissed and the consumed records
- `offerIdeSelection`: IDE path; ignored if a diff selection is live and the offer has no text, or
  if it is the one just dismissed
- `dismissIdeSelection`: clears it and remembers it as dismissed, so the IDE cannot re-offer it
- `consumeIdeSelection`: clears it and records `{ selection, promptUuid }`
- `recordIdeSelectionConsumedBy`: records a selection against a prompt uuid directly
- `restoreIdeSelectionConsumedBy`: returns a selection recorded against that uuid
- `returnIdeSelection`: sets it back only if no selection with text and no diff selection is live

Two writers set a fresh selection: `setIdeSelection`, which is the sidebar's attach callback, and
`offerIdeSelection`, the IDE MCP path, whose selections carry no `source`.

### The composer pill

The pill is a prefix rendered ahead of the draft, not text in the draft. The label is built from a
hoisted glyph constant (`rg -n '= "\\u29C9 ";'`, 1 hit), which is why grepping for the whole
rendered string finds nothing; the builder sits right after it. For a diff selection with text the
label is `⧉ <N> line(s) from <basename>`, or `from diff` without a path; an IDE selection reads
`selected` or `In <basename>`, and only while the IDE is connected.

The label is then wrapped as `[<label>] `, middle-truncated at 32 characters, with `]` inside the
label rewritten to `)` and newlines to spaces
(`rg -nF 'truncate-middle")}] `'`, 1 hit). So a diff selection renders `[⧉ 3 lines from README.md]
`. The composer receives it as `leadingPill: { text, onDelete: dismissIdeSelection }\`.

Its colour is a highlight range, not a prop on a Text node: the composer prepends
`{ start: 0, end: pillText.length - 1, color: "ide", priority: 30 }` to its highlights and shifts
every other range by the pill's length (`rg -nF 'color: "ide", priority: 30'`, 1 hit). The plain
branch draws the pill as a Text with `color: "ide"`. The theme key is `ide`:

| Theme family     | `ide`             |
| ---------------- | ----------------- |
| light / dark / … | `rgb(71,130,200)` |
| ANSI dark        | `ansi:blueBright` |
| ANSI light       | `ansi:blue`       |

Every offset the composer receives from a caller is shifted by the pill length, and the cursor is
clamped so it cannot enter the pill. Backspacing past offset 0 clears the prefix and fires
`onDelete`. `$.prompt.read` returns the draft without the pill.

### The attachment

Creation: `rg -nF 'type: "selected_lines_in_diff"'` (1 hit). A selection with `source: "diff"` and
text becomes `{ type: "selected_lines_in_diff", lineCount, content, filePath }`; anything else falls
through to the IDE variant, `selected_lines_in_ide`.

Rendering to the model (`rg -nF 'from the diff view'`, 1 hit), as a meta message:

```
The user selected the following <N> line(s) from the diff view (in <path>):
<content>

This may or may not be related to the current task.
```

The ` (in <path>)` part appears only with a path. The transcript row reads
`⧉ Selected <N> line(s) from diff view` (`rg -nF '" from diff view"'`).

### Clearing and returning

A submit consumes the selection: `consumeIdeSelection(promptUuid)` clears it and records it against
the prompt's uuid. Two exceptions leave it in place:

- a diff selection survives a slash command or a bash-mode line;
- engine-initiated submits pass `leavesIdeSelection` (`rg -nF 'leavesIdeSelection: !0'`, 4 hits: the
  idle `/clear` keybinding, `/btw`, `/web-setup`, and a keybinding submit).

A queued prompt takes the selection with it when it is queued (`takeIdeSelectionForQueue`).

The selection comes back, pill and all, when its prompt returns to the composer: the prompt is
handed back instead of run, a draft is restored from it (`restoreDraftFrom`), or a queued prompt is
pulled back for editing (`popQueuedIntoDraft`, and the typed-hand-back path). A return never
overwrites a live selection: if the person has made a new diff selection, or any selection with
text, the old one is dropped.

It is cleared outright only by backspacing the pill away (`dismissIdeSelection`) or by the next
attach replacing it. Any `setIdeSelection` call also forgets the consumed record.


## 4. Focus

### The sidebar never holds the keyboard

The panel registers exactly one context, `DiffPanel`, for one binding. It has no focusables, no
focus ring, no entry in the pane store, and no `escape` handler of its own. Attaching a selection
changes `ideSelection` and nothing else — there is no focus call anywhere on the attach path.

So the answer to "does the native sidebar move focus to the composer when it attaches?" is that it
never had the focus to move. The composer's text input holds focus whenever nothing takes its place:
no dialog or overlay content, no history search, no modal overlay. Plugin panes take the keyboard by
intercepting keys through their contexts, not by unfocusing the composer.

### Three separate focus stores

| Store               | Setter                        | Holder                              |
| ------------------- | ----------------------------- | ----------------------------------- |
| pane store          | `focusPane(id)`               | a plugin pane, by `focusedId`       |
| above-prompt band   | local state                   | the band's focus index              |
| Client region store | the region store's own setter | a `Client` region that accepts keys |

`focusPane(id)` (`rg -nF 'focusPane: () =>'`) sets
`focusedId` (and `shownId`) only if `id` is `null` or an open pane, and always
clears `focusRequest`.

### `ctrl+x tab`

Binding `"ctrl+x tab"` → `abovePrompt:focus`, context `Chat`, described as
`focus plugin buttons, inputs and selects`. Sibling `"ctrl+x ctrl+a"` → `abovePrompt:toggle`
(`hide/show plugin panel`). When a pane holds the keyboard it moves to the next open pane (the
helper returns `open[indexOf(focusedId) + 1] ?? null`, so past the last pane it returns to the
composer); otherwise it takes the band when the band has focusables, else the first pane. Once a
pane holds the keyboard the active contexts are `Pane`, or `PaneField` when the focused element is
an `Input` or `Select`.

### The engine releases plugin focus when the draft changes

This is the mechanism behind the measured difference between the Button path and the region path.
The hook is exported as `useReleaseOnEdit` (`rg -nF 'useReleaseOnEdit'`). It takes the draft store,
a holder value and a release callback; while the holder is non-null it records the draft `value`
and, on the first change to it, calls the release.

Its one call site is in the always-mounted above-prompt band, with holder
`bandFocus ?? panesStore.focusedId` and release "clear the band index, then `focusPane(null)`".

`$.prompt.fill` changes `value`. Its implementation (`rg -nF 'fillDraft = '`) does no focus work of
its own: it refuses with `{ isFilled: false, refusal: "dialog" }` while a dialog is open, otherwise
writes the text by mode (`replace`, `append`, `insert`), sets the cursor (the given `cursor`, else
the end for non-insert modes), and paints any `decorations` onto the filled text.

So the sequence for the Button path is: the pane holds the keyboard (`focusedId === paneId`),
because a Button is only pressable once the pane is focused → the handler calls `$.prompt.fill` →
the draft store emits → release-on-edit fires → `focusPane(null)` → the keyboard is back at the
composer.

The `$.ui.focus` op first waits, for up to 3000 ms, for the site to settle: while its own pane has a
pending `focusRequest`, or while the site holds the keyboard but the named element is not drawn yet.
`rg -nF 'focusSiteDraws'` (2 hits) finds the store it re-checks on. The wait exists for
`$.ui.open({ focus: true })` followed at once by `$.ui.focus`. It returns at once when the site does
not hold the keyboard, so it does not change the outcome after a fill.

A later `$.ui.focus` is then denied, because the site check reads the same store
(`rg -nF 'that site does not hold the keyboard'`, 2 hits: the op's check and the `ui.focus` core).
The checks, in order: the site exists, it is this plugin's, it holds the keyboard, no other plugin's
element holds it, and the plugin drew an element under that key. A Pane site holds the keyboard
while `panesStore.focusedId === paneId`, which release-on-edit has just set to `null`.

### Why a `Client` region keeps focus

Two reasons, both structural.

First, a `Client` is not a focusable. The focusable collector takes only `Button`, `Input` and
`Select` (`rg -nF 'type === "Button" || e.type === "Input" || e.type === "Select") {'`).

Second, a region that accepts keys holds the keyboard in its own store and explicitly drops the pane
focus when it takes it: pointer-down on a key-accepting region calls `focusPane(null)` and then the
region store's setter with the region id (`rg -nF 'p.acceptsKeys()) ('`, 1 hit). From then on
`panesStore.focusedId` is already `null`, so release-on-edit's holder is `null`, the subscription
never mounts, and a `$.prompt.fill` from the region's `ui.message` handler changes the draft without
touching region focus. The region's key routing is a separate interceptor keyed on the region store,
and the only things that release it are `escape` / `ctrl+c` / `ctrl+d`, a click elsewhere
(`useReleaseOnClickElsewhere`), or a pane taking focus back.

### Moving focus back

There is no way. `$.ui.focus({ requestId, key })` moves focus within a site the plugin already
holds; it cannot acquire focus. Its argument check requires both strings non-empty
(`rg -nF 'takes { requestId, key } (which of its sites'`), and its denials are `no such site`,
`not this plugin's site`, `that site does not hold the keyboard`,
`another plugin's element holds the keyboard`, and `no element of its own is drawn under that key`.

The one adjacent affordance is `$.ui.open({ focus: true })`, which records a `focusRequest` that the
band honours only when the composer draft is empty, no engine dialog or feedback survey is up, no
band element or pane already holds the keyboard, and at least one pane is placed. Filling the
composer therefore blocks it.

`$.ui.open` resolves to `{ isPlaced, reason? }` (`rg -nF 'waits unplaced ('`). An asked open (one a
person started) is placed at any width; an unasked open is placed only at 110 columns if the person
has opened that id before, else 144. With no terminal measured, a session whose attached surfaces
place no panes leaves it unplaced with that reason. A `focus: true` request is recorded only if the
pane is placed at open; an unplaced pane's request is dropped, and placing it later carries only the
store's then-current request.

Three engine-side releases exist and none of them is plugin-callable:

| Hook                         | Trigger                                             |
| ---------------------------- | --------------------------------------------------- |
| `useReleaseOnEdit`           | draft `value` changes while a pane or band holds it |
| `useReleaseOnClickElsewhere` | a click lands outside the focused element           |
| `useReleaseGoneHold`         | the focused index outruns the focusable list        |


## 5. The close mark

Both surfaces draw a `✕` at their top-right, from the same hoisted glyph constant. The bundle stores
it escaped, so relocate it with `rg -n 'u2715"'` (1 hit, the declaration) rather than by searching
for the rendered character. They are different components with different hover styling, and only the
pane's is reachable from the keyboard.

### The plugin pane's close mark

Drawn by the pane host, not by the plugin. The pane site renders it as the last child of its outer
box, after the bordered column that holds the tab strip and the viewport. It is the engine's
`CloseMark` (`rg -nF 'CloseMark: () =>'`, 2 hits): an absolutely positioned box at `top: 0`,
`right: <inset>`, whose `onClick` stops immediate propagation, wrapping a `DimButton` labelled with
the glyph. The inset is `BORDER_MARK_INSET` (2) for an inline pane and `MARK_EDGE_COLUMNS` (1) for a
docked one, and `CLOSE_MARK_COLUMNS` (2) are taken out of a docked pane's tab-strip width.

Row 0 of the site is chrome, not body: the round border's top edge for an inline pane, and the tab
strip (or a reserved blank row when only one pane is open) for a docked pane. So the mark sits on
chrome and does not cover the plugin's first body row.

`DimButton` (`rg -nF 'DimButton: () =>'`) is a `Box` whose `onClick` releases Ink focus
(`releaseInkFocus`, the same blur helper the plugin `Button` element uses), wrapping the engine's
`Button` primitive with `tabIndex: -1` (out of Ink's own tab order). Its render function is one
expression: `dimColor` when neither hovered nor held, `inverse` when either. That inverse under the
pointer is the highlight you see.

### It is a stop in the pane's focus ring

`isHeld` is true when the ring's engine-stop index equals the tab count (the number of other open
panes), and the engine names that stop `"mark"` (`rg -nF '? "mark" :'`, the pane site's hit). The
ring counts it: its length is `focusables + tabCount + 1`, the `+ 1` being the close mark, and
pressing at that index closes the pane rather than picking a tab.

In the `Pane` context `tab` / `shift+tab` are `abovePrompt:next` / `abovePrompt:previous` and
`enter` is `abovePrompt:press`, so tabbing past the plugin's own `Button`/`Input`/`Select` elements
lands on each other pane's tab and then on the close mark, which renders inverse while held.
Pressing it closes the pane — the same path as `ctrl+x x` (`pane:close`).

The hook-event schema calls this an engine stop rather than a plugin element. A `ui.focus` event
carries `element: undefined` when the move names one, and a rewriting handler may not convert
between the two: `an element where the move named none (one of the engine's stops)` and
`no element where the move named one (a rewrite names another)`
(`rg -nF 'one of the engine'"'"'s stops'`).

`$.ui.focus` cannot address it either: the argument check requires a non-empty `key`, and the site
check then requires the plugin to have drawn an element under that key — the close mark is the
engine's, so no key reaches it.

### No plugin control over it

Neither the open arguments nor the render props mention it.

- `$.ui.open` arguments: `id`, `title`, `focus`, `closeOnEscape`, `holdToasts`, `backgroundColor`,
  `rows`, `columns`
- `ui.render` Pane props: `title`, `isFocused`, `bodyColumns`, `placement`, `scroll`, `view`

`closeOnEscape` changes what `escape` does — close the pane rather than release focus — but does not
hide or restyle the mark. There is no way to suppress it, relabel it, move it, or change its hover
treatment.

### The native sidebar's close mark

A local component in the sidebar's own module, drawn as the last child of the header's count row,
after a `flexGrow: 1` spacer. It is a `Box` with `onClick` (close the panel), `onMouseEnter` and
`onMouseLeave` driving local hover state, around a Text that is `bold` when hovered and `dimColor`
otherwise.

It does track hover, contrary to a plain reading of the rendered output: the glyph goes from
`dimColor` to `bold`. What it does not do is invert. Dim-to-bold on a single `✕` is a far weaker cue
than the pane's reversed cell, which is why the two read as "one highlights, one does not".

| Aspect            | Plugin pane (`DimButton`)          | Native sidebar                        |
| ----------------- | ---------------------------------- | ------------------------------------- |
| Hover styling     | `inverse`, undimmed                | `bold`, undimmed                      |
| Held styling      | same inverse, driven by `isHeld`   | none — it is never held               |
| Focusable         | `Button` primitive, `tabIndex: -1` | none                                  |
| In the focus ring | yes, as the engine stop `"mark"`   | no                                    |
| Reachable by key  | `tab` to it, `enter` to press      | no                                    |
| Positioning       | `position: "absolute", top: 0`     | in flow, after a `flexGrow: 1` spacer |

The sidebar has no focus ring at all — it registers only the `DiffPanel` context for one binding
and owns no focusables — so there is nothing for its close mark to be a stop in, and no held state
for it to render.


## 6. Correspondence: native sidebar vs the plugin API

The complete plugin op and hook-event inventory is one array of names, ending with the op list;
relocate with `rg -nF '"prompt.attachment",'` and read the enclosing arrays (the op list starts at
`"model.complete"`). The plugin-side builders for `$.ui` and `$.prompt` are found with
`rg -nF 'selection: () => o("ui.selection", {})'` and `rg -nF 'paint: (r) =>'`.

### Capability map

- Dock a panel beside the transcript: `$.ui.open({ id, title, rows, columns })` + `ui.render`.
  Verdict: yes.
- Draw a diff with syntax colouring: `Code` element (`source`, `language`, `path`, `startLine`,
  `format`, `wrap`). Verdict: yes, engine-rendered.
- Own header, file list, toggles: any `Box`/`Text`/`Button` tree. Verdict: yes.
- Scroll the panel body: engine chrome scrolls it; `$.ui.scroll` moves it. Verdict: yes.
- Click a row to scroll to a block: `Button` + `$.ui.scroll({ to: { key } })`. Verdict: yes.
- Bind `ctrl+x b`-style chords: no; `Button action` reuses engine actions, `hotkey` is one
  digit/letter. Verdict: partial.
- Confine a mouse drag to the panel: automatic — the pane chrome sets `selectionScope: true`.
  Verdict: yes.
- Read the dragged text: `$.ui.selection()`, pull-only; no change event. Verdict: yes, by asking.
- Write `ideSelection`: no writer is exposed. Verdict: no.
- Show a coloured composer pill: `$.prompt.paint` runs with `color` and `virtualText`. Verdict:
  partial.
- Create a `selected_lines_in_diff` attachment: no constructor; `prompt.submit` can add `context`
  text. Verdict: no (context: yes).
- Clear the selection on submit: n/a without `ideSelection`; a plugin clears its own paint. Verdict:
  n/a.
- Keep the keyboard after filling the draft: only from a `Client` region, not from a `Button`.
  Verdict: partial.
- Move focus from the composer into a pane: no op does this. Verdict: no.
- Close mark hover styling: the host draws it and inverts it under the pointer; no prop restyles it.
  Verdict: n/a, engine-owned.
- Hide or relabel the close mark: no; not in `$.ui.open` args nor in the Pane render props. Verdict:
  no.
- Copy text to the clipboard: `$.ui.copy({ text, surface? })`, write-only. Verdict: yes.
- Log first-party telemetry: `$.telemetry.log` / `.mark` refuse non-built-in callers. Verdict: no.

### Keybinding actions a plugin can reuse

A plugin `Button` may carry an `action` naming one of the engine's keybinding actions — including
all six diff-panel actions. The validator (`rg -nF 'is not one of the engine'`) refuses anything off
the allowlist with
`… is not one of the engine's keybinding actions (app:cycleDiffBase, app:diffFileListDown)`,
and refuses the engine-only actions with
`… is the engine's alone: its key cannot be rebound (ctrl+c, ctrl+d)`.

So a plugin can surface a button that dispatches `app:cycleDiffBase`, and the user can rebind that
action's chord. A `Button` may also carry a `hotkey` of one digit or lowercase letter. What a plugin
cannot do is declare a chord of its own in a context it owns.

### Plugin ops that touch this surface

| Op                       | What it does                                                          |
| ------------------------ | --------------------------------------------------------------------- |
| `$.ui.selection()`       | reads what the person has selected: `{ text, requestId? }` or nothing |
| `$.prompt.paint`         | paints styled runs, and virtual text, over the current draft          |
| `$.prompt.fill`          | writes draft text; may carry `decorations` and `cursor`               |
| `$.ui.copy`              | writes plugin-supplied text to a surface's clipboard                  |
| `$.telemetry.log`/`mark` | first-party telemetry, served only to built-in plugins                |

`$.ui.selection()` in the terminal (`rg -nF 'selection: { read: () =>'`) answers only while the
alternate screen is active, that is, in fullscreen. It returns the current selection's text, as a
copy would produce it, with a `requestId` when the selection lies within one plugin-drawn transcript
entry. With no live selection it returns one the person's click or keypress took down, kept until
their next prompt or command has run; otherwise nothing. In a headless session it asks every
attached client that answers `ui_read_selection` and takes the first non-empty answer
(`rg -nF 'ui.selection` reached its core in a headless session'\`).

`$.prompt.paint({ text, decorations })`
(`rg -nF 'decorations must be an array of { start, end } runs'`) takes runs keyed `start`, `end`
(UTF-16 offsets), `color`, `backgroundColor`, `dimColor`, `bold`, `italic`, `underline`,
`strikethrough` and `virtualText`. `text` names the draft the runs were computed for; if the draft
has changed since, nothing is painted. It resolves to `{ isPainted, text, cursor }`. Each plugin
paints its own layer, and the engine carries layers through later edits.

`$.ui.copy({ text, surface? })` resolves to `{ isCopied: true }` or
`{ isCopied: false, reason: "no-surface" | "no-clipboard" }` (`rg -nF '$.ui.copy ('`). On the
`terminal` surface it writes through the same clipboard helper copy-on-select uses — native, a tmux
buffer, or OSC 52, bounded at 1 MiB for the OSC write. On another surface it goes to an attached
client that answers `ui_copy`. Its input is the `text` argument alone; it reads no selection.

`$.telemetry.log` / `$.telemetry.mark` are not engine ops but hook events served by the `telemetry`
built-in plugin, which refuses callers outside the `builtin` and `core` tiers with
`$.telemetry serves the plugins built into Claude Code alone`
(`rg -nF 'serves the plugins built into Claude Code alone'`). The check is in the providing plugin,
not the engine's op table.

### (a) Composer pill styling

No `$` op creates a `leadingPill`, and none creates an attachment. A plugin can paint a look-alike.

- The pill prop is engine-internal. `rg -nF 'leadingPill'` returns 7 hits, all inside the composer:
  the prop forwarded through the text-input hook, the highlight computation, two memo comparisons,
  the forwarding into the input, and the construction site. It is never reachable from plugin code.
- The engine's highlight is `{ start: 0, end: pillText.length - 1, color: "ide", priority: 30 }`.
  The theme key is `ide`, resolving to `rgb(71,130,200)` in the graphical themes and `ansi:blue` /
  `ansi:blueBright` in the ANSI themes.
- A plugin contributes ranges through `$.prompt.paint` (or `decorations` on `$.prompt.fill`). A run
  with `start: 0, end: 0, virtualText: "[⧉ 3 lines from x] ", color: "ide"` draws a pill-like label
  ahead of the draft without putting it in the draft. What it does not get is the pill's behaviour:
  backspacing past it fires nothing, the paint is keyed to the draft text it was computed for, and
  nothing is attached at submit.
- `$.prompt.fill` without decorations writes plain draft text. The engine's own paste placeholders
  (`[Pasted text #N]`, `[Image #N]`) are literal draft text expanded at submit; the selection pill
  is neither in the draft nor produced by paint.
- `prompt.attachment` is a rewrite hook. The engine renders an attachment it already created and
  matches handlers by `{ type }` (e.g. `selected_lines_in_diff`); a handler may change the text or
  drop it. It cannot construct one. A `prompt.submit` handler cannot change the prompt's attachments
  either, but it can append strings to the prompt's `context`, which is how the `diff` mod sends a
  file's diff along.

### (b) Selection in the main window

A plugin can read the terminal selection, but only by asking: no hook event observes it.

- `$.ui.selection()` reads the same terminal selection store the attach hook reads, through the
  REPL's selection keeper. It answers in fullscreen only, covers a selection anywhere on screen
  (transcript, the native sidebar, another plugin's pane), and names a `requestId` only for a
  selection inside one plugin-drawn transcript entry.
- The full hook-event list contains no selection event, so a plugin learns of a new selection only
  by calling `$.ui.selection()` again (on a timer, or from one of its own events). The
  pointer-shaped events that exist are `ui.press`, `ui.input`, `ui.select` and `ui.message`, all
  keyed to a specific element the plugin drew.
- A pane gets confinement: the pane chrome sets `selectionScope: true`, so a drag started inside the
  pane is clamped to the pane's columns.
- A plugin's own `Client` region receives pointer events for drags inside itself, through
  `onPointer`. The region component forwards `type`, `x`/`y` in region-local cells, optional `fine`
  sub-cell coordinates, `button`, and the `shift` / `alt` / `ctrl` modifiers, plus `enter` and
  `leave`. That is region-local input, not text: the region sees coordinates, never the selected
  characters.

### (c) Focus after `$.prompt.fill`

| Path                           | Holds the keyboard before | After `$.prompt.fill`    |
| ------------------------------ | ------------------------- | ------------------------ |
| pane `Button` → `ui.press`     | the pane                  | released to the composer |
| `Client` region → `ui.message` | the region's own store    | unchanged, stays there   |

Code responsible:

- Release: `useReleaseOnEdit`, mounted once in the above-prompt band. Its holder is
  `bandFocus ?? panesStore.focusedId` and its release clears the band index and calls
  `focusPane(null)`. Any change to the draft's `value` while a pane holds the keyboard releases it.
- Denial: `$.ui.focus`'s site check requires the site to hold the keyboard, which for a Pane site
  reads `panesStore.focusedId === paneId`. Once released, the call returns
  `{ deny: "that site does not hold the keyboard" }`.
- Region immunity: `Client` is not in the focusable set, and a key-accepting region's pointer-down
  handler runs `focusPane(null)` before taking region focus. Pane focus is therefore already `null`
  when the fill happens, so release-on-edit's subscription is not mounted and the region's own focus
  store is untouched.

There is no `$` op that moves focus from the composer back into a pane. `$.ui.focus` can only move
focus within a site that already holds it, and `$.ui.open({ focus: true })` is honoured only while
the composer draft is empty — which a preceding `$.prompt.fill` guarantees it is not.

### Tripwires

- □ `rg -nF 'tengu_jazzy_ripple'` and `rg -nF 'tengu_quiet_dolphin'` have 1 hit each; the mod's
  `isOnByDefault` is true.
- □ `rg -nF 'isOwnedByPlugin'` has 3 hits; the sidebar is drawn only when not owned by the mod.
- □ `rg -nF 'useReleaseOnEdit'` has 1 hit, the export; the hook has one call site, in the band, and
  its holder includes the pane store. A second call site, or a holder without the pane store,
  changes the Button-path behaviour.
- □ `rg -nF 'getSelectedText'` has 7 hits; a new consumer means a new reader of the selection.
- □ `rg -nF 'leadingPill'` has 7 hits, all in the composer.
- □ `rg -nF '"ui.selection"'` is in the op list and not among the hook events.
