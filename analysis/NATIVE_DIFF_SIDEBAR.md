# The Native `/diff` Sidebar, End to End

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)
Verified: 2.1.277

A reference extraction of the engine's own diff sidebar: the `/diff` command, the component tree,
the drag-to-attach path, and focus handling. It exists to be compared against what a function-hooks
plugin can reach through the `$` API, so the last section maps each native capability onto the
plugin surface and says whether a plugin can do it.

Line numbers in this document are for 2.1.277 only. Every section leads with a grep recipe; relocate
with that, not with the numbers. Minified identifiers are given in parentheses as a reading aid, not
as anchors — they churn every release.

Companion doc: `PLUGIN_PANES_AND_COMPOSER.md` covers the pane/dock chrome geometry, the `$` noun
table, and the `diff` built-in plugin that can displace this sidebar.


## Terminology correction: two different flags

The sidebar described here is the engine's native Ink component. It is not the `diff` built-in
plugin, and the two are gated by different flags.

| Surface                      | Gate                                                    | Default |
| ---------------------------- | ------------------------------------------------------- | ------- |
| Native diff sidebar          | `!flag("tengu_jazzy_ripple", false)` — a kill switch    | on      |
| `diff` built-in plugin (mod) | `functionHooksOn && flag("tengu_quiet_dolphin", false)` | off     |

Relocate with `rg -nF 'tengu_jazzy_ripple'` (1 hit, inside the sidebar's enable predicate) and
`rg -nF 'tengu_quiet_dolphin'` (1 hit, inside the mod's `isAvailable`). The mod's module also
declares `isOnByDefault = false` and the description
`The diff panel as a plugin pane: /diff, the changed files and their hunks beside the transcript,
refreshed as Claude edits`.

Everything below — the `paddingY: 1` header, `setIdeSelection({ source: "diff" })`, the
`selected_lines_in_diff` attachment — belongs to the native sidebar. The mod has none of it; its
own attach is a whole-file append through the `prompt.submit` hook.

```js
// cli.prettier.js:451065
function XCe() {
  return !P("tengu_jazzy_ripple", !1);
}
// cli.prettier.js:1410306
var Rr = () => "tengu_quiet_dolphin";
var bt = !1;
var At = () => aX() && ql(Rr(), bt);
```


## 1. The `/diff` command and its gating

### Registration

`rg -nF '"Toggle the diff panel showing uncommitted changes"'` — 2 hits: the command descriptor and
the mod's copy of the same string.

```js
// cli.prettier.js:451072  — the built-in command descriptor
var g3e = {
  type: "local-jsx",
  name: "diff",
  isEnabled: () => !wyn(),
  get description() {
    return kWt($a() ? "fullscreen" : "inline") === "fullscreen"
      ? "Toggle the diff panel showing uncommitted changes"
      : "View uncommitted changes and per-turn diffs";
  },
  immediate: (e, n) => kWt(n) === "fullscreen",
  thinClientDispatch: "control-request",
};
```

`wyn()` (`rg -nF 'isOwnedByPlugin'`) is true when the `diff` mod owns the surface; the built-in
command then disables itself. `kWt(presentation, dispatchedAsImmediate)` picks the surface:

```js
// cli.prettier.js:451068
function kWt(e, n = !1) {
  if (Nt() || e !== "fullscreen") return "inline";
  return XCe() || n ? "fullscreen" : "inline";
}
```

Fullscreen resolves to the docked sidebar; inline falls back to a modal `DiffDialog`. The command
body picks between them (`cli.prettier.js:1590739`):

```js
var s = async (a, l) => (
  a(l.toggleDiffPanel ? await l.toggleDiffPanel() : PLn, { display: "system" }),
  null
);
var r = async (a, l) => {
  let { DiffDialog: o } = await import("…");
  return e(o, { messages: l.messages, onDone: a });
};
var C = (a, l, o, m) =>
  kWt(l.presentation, l.dispatchedAsImmediate) === "fullscreen" ? s(…) : r(…);
```

`toggleDiffPanel` is supplied by the REPL host (`rg -nF 'toggleDiffPanel'` — 2 hits, the provider
and the command). It calls the toggle helper, waits up to 2000 ms for the first diff to settle, and
returns the status text (`cli.prettier.js:1265620`).

### The toggle helper and its four outcomes

`rg -nF '"Diff panel shown"'` — 2 hits: the constant and the mod's copy. The helper lives beside it
(`cli.prettier.js:1126838`):

```js
function FPt({ host: t, getReplTab: r, setAppState: o, columns: s, trackSequence: i, storageV5: a }) {
  if (r() === "diff") return (oe(t, o, "diff", a), { status: "hidden" });
  if (!XCe()) return { status: "refused", reason: "unavailable", text: PLn };
  if (!NPt()) return { status: "refused", reason: "no-git", text: De };
  if (s < zZ)
    return {
      status: "refused",
      reason: "too-narrow",
      text: `Resize your terminal to at least ${zZ} columns to show the diff panel`,
    };
  return { status: "shown", settled: Se(t, r, o, i, a).catch(d) };
}
```

| Outcome                                                                                                   | Text                                                                                 |
| --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| shown                                                                                                     | `Diff panel shown`                                                                   |
| hidden                                                                                                    | `Diff panel hidden`                                                                  |
| refused / `unavailable`| `The diff panel isn't available right now — run /diff again to see your changes` |                                                                                      |
| refused / `no-git`                                                                                        | `The diff panel shows git changes — the current directory isn't in a git repository` |
| refused / `too-narrow`                                                                                    | `Resize your terminal to at least 110 columns to show the diff panel`                |

A refusal is also surfaced as a 3000 ms immediate notification keyed `diff-sidebar-<reason>` when
the toggle arrives by keybinding rather than by command (`app:toggleReplTab`, sidebar host).

### Width rule

`rg -nF 'var zZ = 110'` — the two constants sit together:

```js
// cli.prettier.js:325768
var zZ = 110,
  P9e = 144;
```

`110` is the floor to show the panel at all; `144` is the auto-open floor unless the user has
already opened it once (`diffSidebarOpen === true`), in which case `110` applies:

```js
// cli.prettier.js:1126804
function HLn(t) {
  let r = ae().diffSidebarOpen;
  if (r === !1) return !1;
  return t >= (r === !0 ? zZ : P9e) && NPt();
}
```

The same two numbers gate plugin pane placement, and the telemetry buckets are
`under_110` / `110_to_143` / `144_to_199` / `200_plus` (`rg -nF 'under_110'`).

The full mount predicate (`cli.prettier.js:1126794`):

```js
function JQt({ enabled: t, fullscreen: r, columns: o, isThinClient: s, isMainFocused: i, hasGitRepo: a }) {
  return t && r && !s && i && o >= zZ && a;
}
```

### Telemetry

`tengu_repl_diff_panel_shown` with `trigger: "auto_open" | "manual"` and
`terminal_width_bucket`, logged once per session id (`cli.prettier.js:1279652`). Tab switches log
`repl_tab_switch`; base cycling logs `repl_diff_base_switch`.


## 2. The sidebar component tree

Relocate the panel body with `rg -n 'context: "DiffPanel"'` — 2 hits, the default keybinding table
and the component that registers the base-cycling binding.

| Role                    | Symbol | Lines (2.1.277) |
| ----------------------- | ------ | --------------- |
| auto-open baseline hook | `Vge`  | 1279748–1279784 |
| sidebar host            | `Kge`  | 1279785–1279951 |
| panel body              | `c8e`  | 1279952–1280535 |
| base-mode label         | `HQt`  | 1280538–1280552 |
| pre-session block       | `$9`   | 1280553–1280680 |
| close button            | `u8e`  | 1280681–1280714 |
| noise-filter toggle     | `m8e`  | 1280715–1280766 |
| file-list row           | `p8e`  | 1280767–1280866 |
| per-file diff block     | `Bbe`  | 1279323–1279632 |
| drag-attach hook        | `e4e`  | 1279275–1279306 |
| row → path resolver     | `b4e`  | 1279670–1279684 |

### Host

The host does the gating and nothing else — no wrapper Box, so the panel body is the sidebar
(`cli.prettier.js:1279944`):

```js
H4o = e(c8e, { width: Mge, minCol: O2t, onAskAboutSelection: A2t });
```

`minCol` is `terminalColumns − sidebarWidth`, the left edge used by the attach hook.
`onAskAboutSelection` is `undefined` whenever a modal slot is active (`cli.prettier.js:1282973`):

```js
onAskAboutSelection: cz ? void 0 : Tu.setIdeSelection,
```

The layout places the result in its `sidebar` slot, which adds width and a background and no
padding (`rg -n 'backgroundColor: "composerSidebarBackground"'`).

### Root and header

```js
// cli.prettier.js:1280520 — panel root
r(sQt, { ref: K2t, flexDirection: K4i, width: C4e, height: z4i,
         onWheel: L4e, selectionScope: Q4i, children: [$4e, W4e] })
// sQt = Box, K4i = "column", z4i = "100%", Q4i = true

// cli.prettier.js:1280392 — header block
$4e = r(s, {
  flexDirection: "column",
  paddingX: 1,
  paddingY: 1,
  flexShrink: 0,
  children: [U4e, H4e, j4e, mQt],
})
```

`paddingY: 1` is the sidebar's leading blank row. `selectionScope: true` confines a mouse drag to
the panel's own columns.

Header children, in order:

| Child | Content                                                                          |
| ----- | -------------------------------------------------------------------------------- |
| `U4e` | row: `<N> files changed` + net `+a −b`, spacer, close button `✕`                 |
| `H4e` | dim base-mode line                                                               |
| `j4e` | todo progress bar, `marginTop: 1, gap: 1`, drawn only when the session has todos |
| `mQt` | the file list, `marginTop: 1`                                                    |

The count row (`cli.prettier.js:1280257`):

```js
F4e = !mH && fR === null &&
  r(n, {
    children: [
      r(n, { bold: !0, children: [BN, " ", I(BN, "file")] }),
      " ", "changed",
      (E4e > 0 || I4e > 0) && " ",
      e(my, { added: E4e, removed: I4e }),
    ],
  })
```

The base-mode line (`cli.prettier.js:1280538`):

```js
function HQt(h, E, O) {
  let Q;
  switch (h) {
    case "session":     Q = "this session"; break;
    case "uncommitted": Q = "uncommitted (vs HEAD)"; break;
    case "branch":
      if (E.kind === "branch") Q = `branch vs ${E.baseBranch}`;
      else Q = O ? "branch diff" : "vs HEAD (no base branch)";
      break;
  }
  return O ? `${Q}…` : Q;
}
```

A trailing `…` marks a pending recompute after a base switch. When the repo has no commits the line
is replaced by `no commits yet — showing staged and new files`.

### File list

A windowed list, 8 rows (`Hge = 8`), with `↑ N more above` / `↓ N more below (alt+down to scroll)`
affordances and suffixes for `N read-denied` and `N not shown`. Each row is `p8e`: a middle-elided
path (`width − 12`, floor 8), a spacer, and the `+a −b` counter; hovering underlines it and clicking
scrolls the matching diff block into view via `scrollToElement`.

Below the rows sit two toggles:

- `m8e` — `<N> tests/generated (show|hide)`, bound to `app:toggleDiffNoiseFilter`.
- `$9` — `+<N> files edited before this session (show|hide)`, bound to `app:toggleDiffPreSession`.
  Expanded it draws its own file rows plus their diffs, capped at 20 files
  (`qge = 20`, then `diffs hidden above 20 files`).

### Empty and loading states

`mH` (loading) shows `Loading diff…` after a 300 ms delay (`UQt = 300`). Otherwise one of:

| Headline                                 | Hint                                                                     |
| ---------------------------------------- | ------------------------------------------------------------------------ |
| `Diff unavailable`                       | `Couldn't read the git diff — it will retry on the next change`          |
| `No commits yet`                         | `Nothing to diff against until the repo's first commit`                  |
| `No uncommitted changes`                 | —                                                                        |
| `No changes vs <base>`                   | —                                                                        |
| `No changes vs HEAD`                     | `No base branch to compare against — showing changes vs HEAD`            |
| `No changes this session`                | —                                                                        |
| `Too many changed files to show diff`    | `Per-file diff is skipped above 500 files`                               |
| `Only hidden files changed`              | `Read-denied, test, and generated files are hidden in this panel`        |
| `Only read-denied files changed`         | `Read-denied files are hidden in this panel`                             |
| `Only tests and generated files changed` | `Tests and generated files are hidden · click "show" above to view them` |

### Per-file diff rendering

`Bbe` draws one file. Its short-circuit branches, in order: read-denied
(`Content restricted by read-permission rules`), untracked (`New file not yet staged.` plus
``Run `git add :/<path>` to see line counts.``), binary, large. The normal path is a bold path, a
rule, then one hunk block per hunk (`cli.prettier.js:1279575`):

```js
AN = t4e.length === 0
  ? e(hr, { children: "No diff content" })
  : t4e.map((w3i, v3i) =>
      e(MB, { patch: w3i, filePath: Zd, firstLine: _2t, fileContent: x2t, dim: !1, width: hh }, v3i),
    )
```

with `… diff truncated (exceeded 400 line limit)` when the hunks were cut.

`MB` is the shared hunk renderer, the same one the Edit tool result uses
(`rg -nF 'skipHighlighting'`). It builds a structured diff and falls back to a plain patch renderer
when highlighting is off (`syntaxHighlightingDisabled`, or `skipHighlighting`). Colour keys come
from the theme table (`rg -nF 'diffAddedWord'`):

| Key                 | Dark                             | ANSI themes      |
| ------------------- | -------------------------------- | ---------------- |
| `diffAdded`         | green                            | `ansi:green`     |
| `diffRemoved`       | red/pink                         | `ansi:red`       |
| `diffAddedDimmed`   | muted green                      | `ansi:green`     |
| `diffRemovedDimmed` | muted red                        | `ansi:red`       |
| `diffAddedWord`     | strong green| `ansi:greenBright` |                  |
| `diffRemovedWord`   | strong red                       | `ansi:redBright` |

`filePath` reaches the highlighter only as a language hint; it registers no node and takes no part
in the row → path lookup below.

### Keyboard

`rg -nF 'app:cycleDiffBase'` finds both the binding table and the handler.

| Action                      | Default chord            | Context     | Effect                                      |
| --------------------------- | ------------------------ | ----------- | ------------------------------------------- |
| `app:toggleReplTab`         | none in the table        | `Global`    | open/close the panel (same path as `/diff`) |
| `app:cycleDiffBase`         | `ctrl+x b`               | `DiffPanel` | session → uncommitted → branch → session    |
| `app:diffFileListUp`        | `ctrl+up`, `meta+up`     | `Global`    | scroll the file-list window up              |
| `app:diffFileListDown`      | `ctrl+down`, `meta+down` | `Global`    | scroll the file-list window down            |
| `app:toggleDiffNoiseFilter` | none in the table        | `Global`    | show/hide tests and generated files         |
| `app:toggleDiffPreSession`  | none in the table        | `Global`    | show/hide pre-session changes               |

The `DiffPanel` context is described as `When the diff sidebar panel is open`
(`rg -nF '"When the diff sidebar panel is open"'`). Note what is absent: the sidebar registers no
`escape` binding and never enters the focus ring. It is not a focusable surface. Escape in the
sidebar reaches whatever else claims it; closing is the `✕` button, `/diff` again, or
`app:toggleReplTab`.

All six actions are on the engine's plugin-addressable keybinding-action allowlist — see the
correspondence section.

### Scrolling

The body is the engine's scroll box with `stickyScroll: false` and `paddingX: 1`
(`cli.prettier.js:1280446`). Three inputs drive it:

- `onWheel` on the panel root: `scrollBy(deltaY * 3)`, then `preventDefault` + `stopPropagation`.
- Clicking a file-list row: `scrollToElement(node)` against a `Map<path, inkNode>` that each file
  block populates through a `ref` callback.
- Drag autoscroll: the selection-store hook subscribed with `{ requireScope: true }`, which nudges
  the scroll handle while a drag is held past an edge.

The file list has its own independent window offset, clamped to `files.length − 8`, with its own
`onWheel`.


## 3. Drag-to-attach, end to end

### The terminal selection store

One accessor wraps the terminal's own mouse-selection state (`rg -nF 'subscribeToSelectionChange'`,
`cli.prettier.js:705144`):

```js
{
  copySelection, copySelectionNoClear, getSelectedText, clearSelection,
  hasSelection, getState, subscribe, moveFocus, setSelectionBgColor
}
```

`getSelectedText` has exactly 3 hits in the bundle: the store method, this wrapper, and one
consumer — the diff attach hook. Nothing else in the application reads selected text.

### The attach hook

```js
// cli.prettier.js:1279275
function e4e(h, E, O, Q) {
  let ee = ZC(), be = T("");
  let ke = Nr(() => {
    if (!O) return;
    let we = ee.getState();
    if (we?.isDragging || !ee.hasSelection()) { be.current = ""; return; }
    if (!we?.anchor || !we.focus || we.anchorSpan?.kind === "line") return;
    let Pe = we.virtualAnchorCol ?? we.anchor.col,
        Me = we.virtualFocusCol ?? we.focus.col;
    if (Pe < h || Me < h) return;
    let Ne = E();
    if (Ne === null || we.anchor.row > Ne || we.focus.row > Ne) return;
    let We = ee.getSelectedText();
    if (!We.trim() || We === be.current) return;
    be.current = We;
    let He = sn(We.trimEnd(), "\n") + 1,
        Qe = Q?.(Math.min(we.anchor.row, we.focus.row));
    (O({ source: "diff", text: We, lineCount: He, filePath: Qe }),
      _("diff_selection_attach"));
  });
  C(() => ee.subscribe(() => ke()), [ee]);
}
```

Arguments: `h` = `minCol`, `E` = `getMaxRow`, `O` = the attach callback, `Q` = row → path.

Exclusions, in order: no callback (a modal is open), mid-drag, no selection, missing anchor/focus,
`anchorSpan.kind === "line"` (triple-click line selections never attach; character and word drags
do), either column left of `minCol`, either row below the panel's last row, blank or unchanged text.

`getMaxRow` walks `getComputedTop()` up the parent chain and adds the panel's computed height minus
one — the panel's own last row (`cli.prettier.js:1280049`).

### Row → path

```js
// cli.prettier.js:1279670
function b4e(h, E, O) {
  let Q = 0;
  for (let ee = E ?? void 0; ee; ee = ee.parentNode) Q += ee.yogaNode?.getComputedTop() ?? 0;
  if (h < Q) return;
  for (let [ee, be] of O) {
    let ke = 0;
    for (let Pe = be; Pe; Pe = Pe.parentNode)
      if (((ke += Pe.yogaNode?.getComputedTop() ?? 0), Pe.scrollTop)) ke -= HJ(Pe);
    let we = be.yogaNode?.getComputedHeight() ?? 0;
    if (h >= ke && h < ke + we) return ee;
  }
  return;
}
```

`O` is the `Map<repoRelativePath, inkNode>` the file blocks fill through their `ref`. The answer is
the key whose vertical band contains the selection's topmost row. A selection above the scroll
region returns `undefined`, and the attachment then carries no path.

### Copy-on-select runs alongside, not instead

Copy-on-select is a separate global subscriber to the same store, mounted once at the app root
(`rg -nF 'copyOnSelect'`). It fires at drag end, reads `copySelectionNoClear()`, and writes through
the native clipboard, a tmux buffer, or OSC 52. The attach path never calls `copySelection`, so
attaching does not suppress copying and copying does not suppress attaching. Default on; the
`/config` row is labelled `Copy on select`.

### State: `setIdeSelection({ source: "diff" })`

```js
// cli.prettier.js:1269963
setIdeSelection = (h) => {
  if (((this.#c = null), Object.is(h, this.#r.ideSelection))) return;
  this.#s({ ...this.#r, ideSelection: h });
};
offerIdeSelection = (h) => {
  if (this.#r.ideSelection?.source === "diff" && !h.text) return;
  if (pVt(h) === this.#c) return;
  this.setIdeSelection(h);
};
dismissIdeSelection = () => {
  let h = this.#r.ideSelection;
  if (!h) return;
  (this.setIdeSelection(void 0), (this.#c = pVt(h)));
};
```

Two writers only. `setIdeSelection` is the sidebar's `onAskAboutSelection`; `offerIdeSelection` is
the IDE MCP path, which yields `source`-less selections and defers to a live diff selection.
`dismissIdeSelection` remembers the dismissed selection so the IDE cannot immediately re-offer it.

### The composer pill

The pill is a prefix rendered ahead of the draft, not text in the draft. It is built in two steps
(`rg -nF 'from diff'`, `cli.prettier.js:1233443`):

```js
function HBe(h, E) {
  if (!E) return null;
  let O = E.source === "diff";
  if (!O && h !== "connected") return null;
  if (E.text && E.lineCount > 0) {
    let Q = E.lineCount,
      ee = O && E.filePath ? `from ${C_t(E.filePath)}` : O ? "from diff" : "selected";
    return `⧉ ${Q} ${Q === 1 ? "line" : "lines"} ${ee}`;
  }
  if (!O && E.filePath) return `⧉ In ${C_t(E.filePath)}`;
  return null;
}
var eRo = 32;
function jBe(h) {
  let E = h.replace(/]/g, ")").replace(/[\r\n]/g, " ");
  return `[${Om(E, eRo, "truncate-middle")}] `.normalize("NFC");
}
```

`C_t` is basename. So a diff selection renders `[⧉ 3 lines from README.md] `, middle-truncated at 32
characters, with `]` inside the label rewritten to `)` so the brackets stay balanced. The glyph `⧉`
is a hoisted constant, which is why grepping for the whole rendered string finds nothing.

The pill object is `{ text, onDelete }` with `onDelete = dismissIdeSelection`
(`cli.prettier.js:1235701`).

Its colour is a highlight range, not a prop on a Text node (`cli.prettier.js:709286`):

```js
q = f.leadingPill?.text ?? "",
pe = q
  ? [
      { start: 0, end: q.length - 1, color: "ide", priority: 30 },
      ...(_t ?? []).map((ze) => ({ ...ze, start: ze.start + q.length, end: ze.end + q.length })),
    ]
  : _t,
```

and in the masked/ghost branch, `q ? e(n, { color: "ide", children: q }) : null`.

The theme key is `ide`:

| Theme family     | `ide`             |
| ---------------- | ----------------- |
| light / dark / … | `rgb(71,130,200)` |
| ANSI dark        | `ansi:blueBright` |
| ANSI light       | `ansi:blue`       |

Every offset the composer receives from a caller is shifted by `pillText.length`, and the cursor is
clamped so it cannot enter the pill. Backspacing past offset 0 clears the prefix and fires
`onDelete`. `$.prompt.read` returns the draft without the pill.

### The attachment

Creation (`cli.prettier.js:506281` is the renderer; creation is at `cli.prettier.js:476666`):

```js
async function BUo(e, n) {
  if (e?.source === "diff" && e.text)
    return [{ type: "selected_lines_in_diff", lineCount: e.lineCount, content: e.text, filePath: e.filePath }];
  …  // otherwise the IDE variant, selected_lines_in_ide
}
```

Rendering to the model:

```js
selected_lines_in_diff: (e) =>
  fi([
    Te({
      content: `The user selected the following ${e.lineCount} ${e.lineCount === 1 ? "line" : "lines"} from the diff view${e.filePath ? ` (in ${yu(e.filePath)})` : ""}:
${aDn(e.content)}

This may or may not be related to the current task.`,
      isMeta: !0,
    }),
  ]),
```

marked as a meta message. The transcript row reads `⧉ Selected <N> lines from diff view`.

Clearing: the attachment fires exactly once. On submit
(`cli.prettier.js:1270222`):

```js
if ((Qe.setMode("prompt"), Fo?.source !== "diff" || (!Ho && Eo !== "bash")))
  ft.setIdeSelection(void 0);
```

so the selection survives only when the submitted text is a slash command or a bash-mode line;
otherwise it is cleared as the turn starts. It is also cleared by backspacing the pill away, and by
`setIdeSelection(undefined)` from the modal-slot path.


## 4. Focus

### The sidebar never holds the keyboard

The panel registers exactly one context, `DiffPanel`, for one binding. It has no focusables, no
focus ring, no entry in the pane store, and no `escape` handler of its own. Attaching a selection
changes `ideSelection` state and nothing else — there is no focus call anywhere on the attach path.

So the answer to "does the native sidebar move focus to the composer when it attaches?" is that it
never had the focus to move. The composer's text input is focused whenever no modal overlay and no
history search are up (`focus = !hidden && !isSearchingHistory && !isModalOverlayActive`); plugin
panes take the keyboard by intercepting keys through their contexts, not by unfocusing the composer.

### Three separate focus stores

| Store                          | Setter                              | Holder                        |
| ------------------------------ | ----------------------------------- | ----------------------------- |
| pane store                     | `focusPane(id)`                     | a plugin pane, by `focusedId` |
| above-prompt band              | local state                         | the band's focus index        |
| Client region store| `FHt(id)` | a `Client` region that accepts keys |                               |

The pane setter (`rg -nF 'focusPane'`, `cli.prettier.js:325756`):

```js
var W4 = (e) =>
  Lc().setState((n) => {
    let r = e === null || n.open.some((y) => y.id === e),
      s = r ? e : n.focusedId,
      g = r && e !== null ? e : n.shownId;
    return n.focusedId === s && n.shownId === g && n.focusRequest === null
      ? n
      : { ...n, focusedId: s, shownId: g, focusRequest: null };
  });
```

Region store and setter (`cli.prettier.js:782051`):

```js
var dEe = vn(Bs({ focusedId: null }), …);
var FHt = (r) => dEe.setState((a) => (a.focusedId === r ? a : { focusedId: r }));
```

### `ctrl+x tab` cycling

Binding `"ctrl+x tab"` → `abovePrompt:focus`, context `Chat`, described as
`focus plugin buttons, inputs and selects`. Sibling `"ctrl+x ctrl+a"` → `abovePrompt:toggle`
(`hide/show plugin panel`). The handler walks composer → pane 1 → pane 2 → … → composer, because the
"next pane" helper returns `open[indexOf(focusedId) + 1] ?? null`. Once a pane holds the keyboard
the active contexts are `Pane`, or `PaneField` when the focused element is an `Input` or `Select`.

### The engine releases plugin focus when the draft changes

This is the mechanism behind the measured difference between the Button path and the region path.
The hook is named for what it does (`rg -nF 'useReleaseOnEdit'`):

```js
// cli.prettier.js:1213931
var NRe = (h, E, O) =>
  C(() => {
    if (E === null) return;
    let Q = h.getState().value;
    return h.subscribe(() => {
      if (h.getState().value !== Q) O();
    });
  }, [E, h, O]);
```

One call site, in the always-mounted above-prompt band (`cli.prettier.js:1214242`):

```js
let Ei = oe(() => { (Pe(null), W4(null)); }, []);
(NRe(yr, we ?? Or, Ei), …)
// yr = the draft store, we = band focus, Or = panesStore.focusedId, Ei = release both
```

`E` is `bandFocus ?? paneFocusedId`. While either is non-null the hook subscribes to the draft store
and, on the first change to `value`, clears the band index and calls `focusPane(null)`.

`$.prompt.fill` changes `value`. Its implementation does no focus work of its own
(`cli.prettier.js:1270509`):

```js
fillDraft = (h, E) => {
  let { draft: O, dialogStore: Q } = this.#e;
  if (Q.getState().open.length > 0) return { isFilled: !1 };
  switch (E) {
    case "replace": (O.setMode("prompt"), O.replaceValue(h)); break;
    case "append":  O.replaceValue(O.value + h); break;
    case "insert":  O.insertText(h, "outside"); break;
  }
  if (E !== "insert" && O.cursorOffset !== O.value.length) O.setCursorOffset(O.value.length);
  return { isFilled: !0 };
};
```

So the sequence for the Button path is: the pane holds the keyboard (`focusedId === paneId`) because
a Button is only pressable once the pane is focused → the handler calls `$.prompt.fill` → the draft
store emits → release-on-edit fires → `focusPane(null)` → the keyboard is back at the composer.

A later `$.ui.focus` is then denied, because the site check reads the same store
(`rg -nF 'that site does not hold the keyboard'`, `cli.prettier.js:326211`):

```js
function kV(e) {
  let n = eSt(e);
  if (!n) return { deny: "no such site" };
  if (H_t(n, e)) return { deny: "not this plugin's site" };
  if (!n.isHeldNow()) return { deny: "that site does not hold the keyboard" };
  if (toe(n, e.origin)) return { deny: "another plugin's element holds the keyboard" };
  let r = n.commit(e);
  return r === void 0 ? {} : { deny: r };
}
```

The Pane site's `isHeldNow` is `() => panesStore.getState().focusedId === paneId`, which
release-on-edit has just set to `null`.

### Why a `Client` region keeps focus

Two reasons, both structural.

First, a `Client` is not a focusable. The focusable collector takes only three element types
(`cli.prettier.js:1213670`):

```js
if (h.type === "Button" || h.type === "Input" || h.type === "Select") { … }
```

Second, a region that accepts keys holds the keyboard in its own store and explicitly drops the pane
focus when it takes it (`cli.prettier.js:1017722`):

```js
function D(R) {
  if (R.type === "down" && c.acceptsKeys()) (W4(null), FHt(c.id));
  ((E.current = { x: R.localCol, y: R.localRow }), c.pointer({ … }));
}
```

Pointer-down on a key-accepting region sets `focusPane(null)` and `FHt(regionId)`. From then on
`panesStore.focusedId` is already `null`, so release-on-edit's `E` argument is `null`, the
subscription never mounts, and a `$.prompt.fill` from the region's `ui.message` handler changes the
draft without touching region focus. The region's key routing is a separate interceptor keyed on
`dEe.getState().focusedId === regionId` (`cli.prettier.js:1017683`), and the only things that
release it are `escape` / `ctrl+c` / `ctrl+d`, a click elsewhere, or the pane taking focus back.

### Moving focus back

There is no way. `$.ui.focus({ requestId, key })` moves focus within a site the plugin already
holds; it cannot acquire focus. Its five denials are `no such site`, `not this plugin's site`,
`that site does not hold the keyboard`, `another plugin's element holds the keyboard`, and
`no element of its own is drawn under that key`.

The one adjacent affordance is `$.ui.open({ focus: true })`, which records a `focusRequest` the chat
component honours only when the composer draft is empty, no dialog is open, no footer or agent-view
selection is active, and at least one pane is placed. Filling the composer therefore blocks it.

Three engine-side releases exist and none of them is plugin-callable:

| Hook                                                                    | Trigger                                             |
| ----------------------------------------------------------------------- | --------------------------------------------------- |
| `useReleaseOnEdit`                                                      | draft `value` changes while a pane or band holds it |
| `useReleaseOnClickElsewhere`| a click lands outside the focused element |                                                     |
| `useReleaseGoneHold`                                                    | the focused index outruns the focusable list        |


## 5. Correspondence: native sidebar vs the plugin API

The complete plugin op and hook-event inventory is two adjacent arrays; relocate with
`rg -nF '"prompt.attachment"'` and read the enclosing arrays. Nothing in either names a selection, a
pill, or an attachment constructor.

### Capability map

| Native capability                            | Plugin equivalent                                                            | Verdict              |
| -------------------------------------------- | ---------------------------------------------------------------------------- | -------------------- |
| Dock a panel beside the transcript           | `$.ui.open({ id, title, rows, columns })` + `ui.render`                      | yes                  |
| Draw a diff with syntax colouring            | `Code` element (`source`, `language`, `path`, `startLine`, `format`, `wrap`) | yes, engine-rendered |
| Own header, file list, toggles               | any `Box`/`Text`/`Button` tree                                               | yes                  |
| Scroll the panel body                        | engine chrome scrolls it; `$.ui.scroll` moves it                             | yes                  |
| Click a row to scroll to a block             | `Button` + `$.ui.scroll({ to: { key } })`                                    | yes                  |
| Bind `ctrl+x b`-style chords                 | no; `Button action` reuses engine actions only (below)                       | partial              |
| Confine a mouse drag to the panel            | automatic — the pane chrome sets `selectionScope: true`                      | yes                  |
| Read the dragged text                        | nothing reaches the selection store                                          | no                   |
| Write `ideSelection`                         | no writer is exposed                                                         | no                   |
| Show a coloured composer pill                | no; `$.prompt.fill` inserts plain draft text                                 | no                   |
| Create a `selected_lines_in_diff` attachment | no constructor; `prompt.attachment` only rewrites                            | no                   |
| Clear the selection on submit                | n/a without a selection                                                      | no                   |
| Keep the keyboard after filling the draft    | only from a `Client` region, not from a `Button`                             | partial              |
| Move focus from the composer into a pane     | no op does this                                                              | no                   |

### Keybinding actions a plugin can reuse

A plugin `Button` may carry an `action` naming one of the engine's keybinding actions — including
all six diff-panel actions. The validator (`rg -nF 'is not one of the engine'`,
`cli.prettier.js:431158`):

```js
if (w !== void 0 && (typeof w !== "string" || !kzr(w))) {
  let Ie = typeof w === "string" ? JSON.stringify(w) : LU(w);
  return `Button "${g}" action ${Ie} is not one of the engine's keybinding actions (app:cycleDiffBase, app:diffFileListDown)`;
}
if (typeof w === "string" && Rzr(w))
  return `Button "${g}" action "${w}" is the engine's alone: its key cannot be rebound (ctrl+c, ctrl+d)`;
```

So a plugin can surface a button that dispatches `app:cycleDiffBase`, and the user can rebind that
action's chord. What a plugin cannot do is declare a chord of its own in a context it owns.

### (a) Composer pill styling

Confirmed: no `$` op creates a `leadingPill`, and none creates an attachment.

- The pill prop is engine-internal. `rg -nF 'leadingPill'` returns 6 hits, all inside the composer:
  the prop forwarded through the text-input hook, the highlight computation, two memo comparisons,
  and the construction site. It is never reachable from plugin code.
- The highlight is `{ start: 0, end: pillText.length - 1, color: "ide", priority: 30 }`. The theme
  key is `ide`, resolving to `rgb(71,130,200)` in the graphical themes and `ansi:blue` /
  `ansi:blueBright` in the ANSI themes.
- The composer's highlight list is assembled inside the chat component from engine-owned sources
  only: bash-mode prefix, `@`-mentions, slash commands, the ultrathink/auto-accept shimmer, and
  ghost text. There is no hook or prop through which a plugin contributes a range.
- `$.prompt.fill` is the only way a plugin puts text in the composer, and it writes plain draft text
  with no styling and no atomicity. The engine's own paste placeholders (`[Pasted text #N]`,
  `[Image #N]`) are literal draft text drawn in the `suggestion` colour and expanded at submit;
  the selection pill is neither in the draft nor the same colour.
- `prompt.attachment` is a rewrite hook. The engine renders an attachment it already created and
  matches handlers by `{ type }` (e.g. `selected_lines_in_diff`); a handler may change the text or
  drop it. It cannot construct one, and it never touches the composer.

### (b) Selection in the main window

Confirmed: no hook and no `$` op observes the terminal selection store.

- `getSelectedText` has 3 hits: the store method, the accessor wrapper, and the diff attach hook.
  There is no fourth consumer, and none of the three is reachable from plugin code.
- The full hook-event list contains no selection event. The pointer-shaped events that do exist are
  `ui.press`, `ui.input`, `ui.select` and `ui.message`, all keyed to a specific element the plugin
  drew.
- What a plugin's pane does get is confinement and autoscroll, not observation. The pane chrome sets
  `selectionScope: true`, so a drag started inside the pane is clamped to the pane's columns, and
  the shared autoscroll hook nudges the scroll handle at the edges. Neither yields text.
- A plugin's own `Client` region does receive pointer events for drags inside itself, through
  `onPointer`. The region component forwards `type`, `x`/`y` in region-local cells, optional `fine`
  sub-cell coordinates, `button`, and the `shift` / `alt` / `ctrl` modifiers, plus `enter` and
  `leave`. That is region-local input, not the terminal's text selection: the region sees
  coordinates, never the selected characters, and sees nothing at all about drags in the transcript,
  in the native sidebar, or in another plugin's pane.

### (c) Focus after `$.prompt.fill`

Confirmed, and the live measurement matches the code.

| Path                           | What holds the keyboard before    | After `$.prompt.fill`                |
| ------------------------------ | --------------------------------- | ------------------------------------ |
| pane `Button` → `ui.press`     | the pane (`focusedId === paneId`) | released to the composer             |
| `Client` region → `ui.message` | the region (`dEe.focusedId`)      | unchanged, focus stays in the region |

Code responsible:

- Release: `useReleaseOnEdit` (`rg -nF 'useReleaseOnEdit'`), mounted once in the above-prompt band.
  Its gate is `bandFocus ?? panesStore.focusedId` and its effect is
  `() => { clearBandFocus(); focusPane(null); }`. Any change to the draft's `value` while a pane
  holds the keyboard releases it.
- Denial: `$.ui.focus`'s site check requires `isHeldNow()`, which for a Pane site reads
  `panesStore.focusedId === paneId`. Once released, the call returns
  `{ deny: "that site does not hold the keyboard" }`.
- Region immunity: `Client` is not in the focusable set, and a key-accepting region's pointer-down
  handler runs `focusPane(null); FHt(regionId)`. Pane focus is therefore already `null` when the
  fill happens, so release-on-edit's subscription is not mounted and the region's own focus store is
  untouched.

There is no `$` op that moves focus from the composer back into a pane. `$.ui.focus` can only move
focus within a site that already holds it, and `$.ui.open({ focus: true })` is honoured only while
the composer draft is empty — which a preceding `$.prompt.fill` guarantees it is not.

□ Tripwire: `rg -nF 'useReleaseOnEdit'` has 2 hits (the export and the definition) and exactly one
  call site. If a second call site appears, or if the gate stops including the pane store, the
  Button-path behaviour changes.


## Version notes

- 2.1.277: the native sidebar is gated by `tengu_jazzy_ripple` (a kill switch, on by default);
  `tengu_quiet_dolphin` gates the separate `diff` built-in plugin, which is off by default and
  requires function hooks. The sidebar holds no keyboard focus and registers only the `DiffPanel`
  context for `ctrl+x b`. Drag-to-attach is engine-only: the selection store has one consumer, and
  no hook event or `$` op reaches it. `$.prompt.fill` releases pane focus through
  `useReleaseOnEdit`, but not `Client` region focus, which lives in its own store.
