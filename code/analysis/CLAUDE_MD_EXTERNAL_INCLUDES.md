---
verified: 2.1.317
verified_on: 2026-11-03
section: Config, settings, and frontmatter
style: landmark
scope: External CLAUDE.md `@import` and symlinked `.claude/rules` approval dialog and flags
landmarks:
  - hasClaudeMdExternalIncludesApproved
  - showExternalIncludesDialog
---
# External CLAUDE.md include approval

A loaded `CLAUDE.md` / `CLAUDE.local.md` can pull in other files with `@path` imports, and a
`.claude/rules` directory can be a symlink to rule files kept elsewhere. When either reaches outside
the start directory, Claude Code gates it behind a one-time approval dialog before the external
content is loaded into context. It is a security boundary: a cloned repo's `CLAUDE.md` could
otherwise `@import` arbitrary local files into the model's context.

What counts as external. Two kinds of file, both judged by their resolved path against the start
directory (see `PROJECT_FILES_AND_STATE.md`, "`@` imports"):

- An `@` import, at any nesting depth, whose resolved path lies outside the start directory. A
  parent directory's `CLAUDE.md` importing a file beside itself is therefore external.
- A rule file reached through a symlinked `.claude/rules` directory, or a symlinked directory inside
  it, whose target lies outside the start directory; for project rules, also through a `.claude`
  directory that is itself such a symlink.

Managed, project and local files are gated. The user-level `CLAUDE.md` and user rules directory load
with external includes allowed regardless of the dialog, and never count toward it.

The dialog. Title `Allow external CLAUDE.md file imports?`; body, one line in the source:

    This project's CLAUDE.md or .claude/rules imports files outside the current working directory.
    Never allow this for third-party repositories.

The external files' paths are listed under `External imports:`. Up to 8 are listed; past that the
first 6 are followed by `… +N imports not shown.` and
`Yes covers those too, plus any this project adds later.` A footer reads
`Important: Only use Claude Code with files you trust.` with a link to the security docs. Two
choices, with the decline listed first and focused:

- `No, disable external imports` → declines; the external files stay blocked.
- `Yes, allow external imports` → approves; the external files load. Approval is blanket: it covers
  external includes the project adds later, which then load without asking.

Esc declines. The dialog's cancel handler answers "no", and its input guide renders the `confirm:no`
action with `fallback: "Esc"` and `description: "cancel"`, so the key labeled "cancel" is a decline,
not a defer. Keystrokes arriving in the first moments after the dialog opens are refused by the
shared dialog input guard, so typing ahead does not answer it.

State. Two per-project booleans live in the `projects` entry of `~/.claude.json`:

- `hasClaudeMdExternalIncludesApproved`: the answer (`true` allows, `false` blocks)
- `hasClaudeMdExternalIncludesWarningShown`: set `true` once an answer is recorded, whatever it is

The entry is keyed by the canonical root, so every subdirectory and every linked worktree of a
repository shares one answer: approving in one worktree approves them all. What counts as external
is still judged per session against its own start directory. Key resolution and the full contents of
the entry: `PROJECT_FILES_AND_STATE.md`, "The `projects` entry in `~/.claude.json`".

One function records every decision, exported as `recordExternalIncludesDecision`: it writes the
answer to `…Approved`, sets `…WarningShown: true`, and emits the accepted or declined event with a
`source` of `dialog` or `config_toggle`. Accept writes `true`/`true`; decline writes `false`/`true`.

The gate. The startup dialog is shown only when neither flag is set and a forced scan of the
instruction files finds at least one external include. So once it has been answered, even declined
with Esc, `…WarningShown: true` suppresses it permanently: a declined project silently never loads
its external includes and is never asked again at startup. The gate returns "don't show" when
`approved || warningShown`.

Loading reads only `…Approved`: the instruction-file loader includes external files when the call
forces it (the scans behind the gate and the `/config` row) or when `…Approved` is `true`. The same
flag governs instruction files loaded later from directories below the start directory and the
managed instruction files.

Startup placement. The dialog is a step of the interactive startup routine, immediately after the
`.mcp.json` server approval step. It is skipped when `CLAUBBIT` is set; when `IS_DEMO` is set, by
the early return that skips every interactive startup gate (see `IS_DEMO.md`); and in a background
session (`CLAUDE_CODE_SESSION_KIND=bg`) or a bridge reattach (`CLAUDE_BRIDGE_REATTACH_SESSION`),
whose shorter step list has no such step. In all of these the flags keep their stored value, so
external includes stay blocked unless already approved.

Re-enabling after a decline, or revoking. Two routes:

- `~/.claude.json`: set `hasClaudeMdExternalIncludesApproved` to `true` in the canonical root's
  `projects` entry to approve outright, or clear both flags (`false`/removed) to make the startup
  dialog fire again on next launch.
- `/config` → the row with setting id `showExternalIncludesDialog`, labeled
  `External CLAUDE.md includes`, or `External CLAUDE.md files` when the `tengu_maple_sundial`
  grouped layout is on (it sits in the Connections section there). Its value shows the current
  approval. Selecting it opens the same dialog inline, whose footer labels Esc
  `disable external includes`. In the grouped layout, selecting it while approved revokes at once
  without the dialog (`source: config_toggle`). The row renders only when a forced scan finds an
  external include (`shouldShowExternalIncludesToggle`), so it appears even after a decline, but
  only in a session started where such an include exists. `/config showExternalIncludesDialog=…` is
  refused with `can't be set with key=value — use /config (External CLAUDE.md row).`

No CLI reset. Unlike MCP servers (`claude mcp reset-project-choices`), there is no external-includes
reset subcommand or flag. `claude purge [path]` (the old `claude project purge` still works as a
hidden alias that prints a rename notice) deletes the project's `projects` entry along with its
other state, so it clears these flags only as a side effect. Because the entry is keyed by the
canonical root, purging any one worktree resets the answer for all of them. What purge removes and
keeps: `PROJECT_FILES_AND_STATE.md`, "Other per-project and per-session state".

Telemetry: `tengu_claude_md_includes_dialog_shown` (on render, no properties),
`tengu_claude_md_external_includes_dialog_accepted`,
`tengu_claude_md_external_includes_dialog_declined` (both with `source`).

Relocation, with expected `rg -cF` counts in 2.1.317:

- `hasClaudeMdExternalIncludesApproved` (9): the project-entry defaults, the gate, the recorder, the
  instruction-file loaders (top-level walk, rules directories, files below the start directory,
  managed files), and two in the `/config` view.
- `hasClaudeMdExternalIncludesWarningShown` (4): the defaults, the gate, the recorder, and the set
  of volatile project keys whose changes alone are ignored when comparing configs.
- `recordExternalIncludesDecision` (1) and `ClaudeMdExternalIncludesDialog` (2): the export aliases
  of the recorder and the dialog component; the second hit is the startup step's dynamic import.
- `Allow external CLAUDE.md file imports?` (1),
  `Yes covers those too, plus any this project adds later.` (1): the dialog.
- `shouldShowExternalIncludesToggle` (3), `/config (External CLAUDE.md row)` (1), `"config_toggle"`
  (1): the `/config` row, its key=value refusal, and the grouped-layout revoke.
- `` `claude project purge` is now `claude purge` `` (1): the purge command and its hidden alias.

Tripwire for a new version: □ title `Allow external CLAUDE.md file imports?` and body naming
`.claude/rules` □ decline listed first and focused □ both flags in the canonical-root `projects`
entry □ decline/Esc still sets `…WarningShown: true` (sticky no) □ gate suppresses on
`approved || warningShown` □ user-level `CLAUDE.md` imports not gated □ step still follows the
`.mcp.json` approval step and is skipped under `IS_DEMO` / `CLAUBBIT` □ `/config`
`showExternalIncludesDialog` row present only with an external include □ still no reset subcommand.
