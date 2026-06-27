# Auto Memory (MEMORY.md)

Verified against: cli.prettier.js 2.1.186 (2026-06-26)

The user-facing, cross-session memory the main session builds up over time: a per-project directory
holding a `MEMORY.md` index plus per-topic memory files, written by the model as it works and loaded
back at the start of future sessions.

This is a leaf of the memory system; read `MEMORY_SYSTEM.md` first for the shared machinery (the
index pattern, memory types, save protocol, the `Gc()` gate, truncation caps). This doc covers what
is specific to auto memory: where the directory lives, how the index loads, and the related slash
commands.

Public docs: `code.claude.com/docs/en/memory`.


## Where it lives

The directory resolver is a memoized function. Relocate it via the override inputs it consults —
`CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` and `autoMemoryDirectory` — and the `projects` path segment it
joins. The default path is:

```
<config-dir>/projects/<project-slug>/<leaf>/
```

- config-dir: `CLAUDE_CODE_REMOTE_MEMORY_DIR` if set, else `CLAUDE_CONFIG_DIR` or `~/.claude` (grep
  `process.env.CLAUDE_CONFIG_DIR ??`).
- project-slug: the project's git root (or, failing that, its working directory) with every
  non-alphanumeric character replaced by `-`. Slugs longer than 200 chars are truncated and given a
  hash suffix.
- leaf: normally `memory`; under the `tengu_billiard_aviary` flag it is `tiny_memory` (grep the
  quoted literal `"tiny_memory"`).

So the typical path is `~/.claude/projects/-Users-you-src-myproject/memory/`, with the index at
`MEMORY.md` inside it (grep the quoted literal `"MEMORY.md"`).

Two overrides are checked before the default:

- `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` — explicit directory.
- the `autoMemoryDirectory` setting — precedence policy → flag → (local → project when the project
  is trusted) → user. Grep `autoMemoryDirectory`.

The team-memory subdirectory is a sibling under the same root: `<auto-memory-dir>/team/`. See
`TEAM_MEMORY.md`.


## Loading at session start

The session dispatcher (relocate via the `tengu_memdir_loaded` event it emits) reads `MEMORY.md`,
runs it through the shared truncation helper, and emits it as a `## MEMORY.md` system-prompt section
(or "currently empty" text when the file is absent). It fires `tengu_memdir_loaded` with
`memory_type: "auto"` and ensures the directory exists first (grep
`ensureMemoryDirExists failed for`).

Truncation caps are the shared ones: first 200 lines and ~25,000 characters. Over the cap, the
dropped content is replaced by a warning — grep `Only part of it was loaded. Keep index entries`. A
PostToolUse nudge fires when an edited `MEMORY.md` nears the cap — grep
`tengu_memdir_entrypoint_near_cap`.

One override short-circuits the whole thing: when `CLAUDE_COWORK_MEMORY_GUIDELINES` is set and
memory is on, the dispatcher returns that text verbatim under a literal `# auto memory` heading
instead of the built-in memory prompt. Grep `# auto memory`.


## Gate

Auto memory is on by default and gated by the master gate (see `MEMORY_SYSTEM.md`): off under safe
mode, remote-without-remote-dir, `CLAUDE_CODE_DISABLE_AUTO_MEMORY` truthy, `CLAUDE_CODE_SIMPLE`, a
flag kill-switch, or `autoMemoryEnabled: false`. When off, the dispatcher emits
`tengu_memdir_disabled` and returns no memory section.


## Two things called "memory"

The bundle has two distinct memory concepts, and the slash commands attach to the older one. Keep
them separate:

- Auto memory (this doc): the `MEMORY.md` index plus topic files, written by the model, loaded
  automatically, telemetry taxonomy `auto`/`team`/`agent`.
- CLAUDE.md memory: the project/user/local `CLAUDE.md` instruction files, authored by hand, with the
  capitalized `User`/`Project`/`Local`/`Managed` taxonomy.

The `/memory` slash command (grep `Open a memory file in your editor`) edits CLAUDE.md files, not
the auto-memory `MEMORY.md` index — it opens a chosen file in `$VISUAL`/`$EDITOR` (grep
`Opened memory file at`), and the onboarding card describes it as the way to edit CLAUDE.md inline
(grep `Teach Claude your rules`). The public "Memory" doc page covers both under one heading; the
source keeps them as separate code paths.

`/toggle-memory` (grep `Toggle automemory off/on for this session`) is the runtime kill-switch the
`Gc()` gate reads, printing `Automemory disabled for this session` / re-enabled messages and firing
`tengu_memory_toggled`. In this build its `isEnabled` is hardwired false, so the command is
effectively inert — the runtime toggle exists in code but is not exposed.


## Memory types and the memory-types skill

Auto memory uses the shared four-type taxonomy (`user`/`feedback`/`project`/`reference`) documented
in `MEMORY_SYSTEM.md`. When `tengu_ochre_finch` is on, the inline taxonomy is replaced by a pointer
to the `memory-types` skill (grep `Full reference for the memory type taxonomy`), a
non-user-invocable skill enabled only when memory is on and that flag is set.


## Relocating in a new bundle

All anchors are version-stable strings, not minified symbol names.

| Concept                  | Grep anchor                                          |
| ------------------------ | ---------------------------------------------------- |
| Directory resolver       | `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` + `projects` join |
| Config dir               | `process.env.CLAUDE_CONFIG_DIR ??`                   |
| Leaf dir name            | `"tiny_memory"`                                      |
| Index filename           | `"MEMORY.md"`                                        |
| Directory override       | `autoMemoryDirectory`                                |
| Session dispatcher       | `tengu_memdir_loaded` (emitted on load)             |
| Load telemetry           | `tengu_memdir_loaded`                                |
| Truncation warning       | `Only part of it was loaded. Keep index entries`     |
| Near-cap nudge           | `tengu_memdir_entrypoint_near_cap`                   |
| Guidelines override      | `# auto memory`                                      |
| `/memory` command        | `Open a memory file in your editor`                  |
| `/toggle-memory`         | `Toggle automemory off/on for this session`         |


## Tripwires

- `□` Default path is `<config-dir>/projects/<slug>/memory/` with the index at `MEMORY.md`.
- `□` Slug = git-root-or-cwd with non-alphanumerics → `-`, capped 200 chars + hash.
- `□` Load caps: 200 lines / 25,000 chars, then a truncation warning replaces the overflow.
- `□` `CLAUDE_COWORK_MEMORY_GUIDELINES` overrides the built-in prompt with `# auto memory`.
- `□` `/memory` edits CLAUDE.md, not the auto-memory `MEMORY.md` index.
- `□` `/toggle-memory` exists but `isEnabled` is false in this build (inert).
