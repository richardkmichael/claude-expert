---
verified: 2.1.316
verified_on: 2026-11-02
section: Memory
style: landmark
scope: 'Per-project auto memory: dir resolution, load, `/memory`'
landmarks:
  - '"MEMORY.md"'
  - autoMemoryDirectory
  - Edit CLAUDE.md files and memory settings
---
# Auto Memory (MEMORY.md)

The user-facing, cross-session memory the main session builds up over time: a per-project directory
holding a `MEMORY.md` index plus per-topic memory files, written by the model as it works and loaded
back at the start of future sessions.

This is a leaf of the memory system; read `MEMORY_SYSTEM.md` first for the shared machinery (the
index pattern, memory types, save protocol, the master gate, truncation caps). This doc covers what
is specific to auto memory: where the directory lives, how the index loads, and the related slash
commands.

Public docs: `code.claude.com/docs/en/memory`.


## Where it lives

The directory resolver is a memoized function. Relocate it via the override inputs it consults —
`CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` and `autoMemoryDirectory` — and the `projects` path segment it
joins. The default path is:

```
<memory-base>/projects/<project-slug>/memory/
```

- memory-base: `CLAUDE_CODE_REMOTE_MEMORY_DIR` if set, else the config dir (`CLAUDE_CONFIG_DIR` or
  `~/.claude`). Grep `process.env.CLAUDE_CODE_REMOTE_MEMORY_DIR`.
- project-slug: the canonical root of the project (see below) with every non-alphanumeric character
  replaced by `-`. Slugs longer than 200 chars are truncated and given a hash suffix.
- When memory-base is the config dir and either `CLAUDE_CONFIG_DIR` is set or the process is
  diskless, `CLAUDE_CODE_PROJECT_DIR_NAME` replaces the slug. Its value must be 1 to 64 characters
  from `[A-Za-z0-9_-]` and not a Windows reserved device name; otherwise it is ignored.
- The leaf is always `memory` (the constant sits next to `"MEMORY.md"`).

So the typical path is `~/.claude/projects/-Users-you-src-myproject/memory/`, with the index at
`MEMORY.md` inside it (grep the quoted literal `"MEMORY.md"`).

The canonical root is the first of these that resolves:

1. A working-copy root registered for the project directory (the `"working_copy"` key source).
2. The canonical git root (the `"git"` key source). For an ordinary checkout this is its top-level
   directory. For a linked worktree it is the main repository: Claude Code reads the worktree's
   `.git` file (`gitdir: ...`), follows that directory's `commondir`, and takes

   - the common dir's parent when the common dir is named `.git` (a worktree of a normal checkout),
   - the common dir itself otherwise (a worktree of a bare repository, such as `project.git`).

   Every link is cross-checked: the worktree directory must sit under `<common>/worktrees/`, and its
   `gitdir` file must point back at the worktree's `.git`. Any mismatch falls back to the worktree's
   own root.
3. The project directory itself (the `"project_root"` key source).

All linked worktrees of one repository therefore share one memory directory. For a bare repository
at `~/src/project/project.git` with a worktree at `~/src/project/development`, memory lives in
`~/.claude/projects/-Users-you-src-project-project-git/memory/`, while that worktree's transcripts
stay under `-Users-you-src-project-development`, which is keyed by the working directory. Relocate
the resolver via the `"commondir"` and `"gitdir:"` literals; the function returns the canonical
root.

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
dropped content is replaced by a warning — grep `Keep index entries to one line`. A PostToolUse
nudge fires when an edited `MEMORY.md` nears the cap — grep `tengu_memdir_entrypoint_near_cap`.

One override short-circuits the whole thing: when `CLAUDE_COWORK_MEMORY_GUIDELINES` is set and
memory is on, the dispatcher returns that text verbatim under a literal `# auto memory` heading
instead of the built-in memory prompt. Grep `# auto memory`.


## Gate

Auto memory is on by default and gated by the master gate (see `MEMORY_SYSTEM.md`). It is off under
safe mode (`CLAUDE_CODE_SAFE_MODE` or `--safe-mode`), when `CLAUDE_CODE_DISABLE_AUTO_MEMORY` is
truthy, under `CLAUDE_CODE_SIMPLE`, and in a remote session that has neither
`CLAUDE_CODE_REMOTE_MEMORY_DIR` nor `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE`. An explicitly falsy
`CLAUDE_CODE_DISABLE_AUTO_MEMORY` forces it on; otherwise the `autoMemoryEnabled` setting decides,
defaulting to on. Grep `process.env.CLAUDE_CODE_DISABLE_AUTO_MEMORY`. When off, the dispatcher emits
`tengu_memdir_disabled` and returns no memory section.


## Two things called "memory"

The bundle has two distinct memory concepts, and the slash commands attach to the older one. Keep
them separate:

- Auto memory (this doc): the `MEMORY.md` index plus topic files, written by the model, loaded
  automatically, telemetry taxonomy `auto`/`team`/`agent`.
- CLAUDE.md memory: the project/user/local `CLAUDE.md` instruction files, authored by hand, with the
  capitalized `User`/`Project`/`Local`/`Managed` taxonomy.

The `/memory` slash command (grep `Edit CLAUDE.md files and memory settings`) opens a dialog for
editing CLAUDE.md files. It does not edit the `MEMORY.md` index, but the dialog has rows that open
the auto-memory, team-memory and agent-memory folders (grep `Open auto-memory folder`). The
onboarding card presents it as the way to edit CLAUDE.md (grep `Teach Claude your rules`). The
public "Memory" doc page covers both concepts under one heading; the source keeps them as separate
code paths.

`/pause-memory` (aliases `memory-pause` and `toggle-memory`; grep
`Pause automemory for this session`) is the runtime switch that turns auto memory off for the
current session, firing `tengu_memory_toggled`. In this build its `isEnabled` is hardwired false, so
the command is inert: the session switch exists in code but is not exposed.


## Memory types and the memory-types skill

Auto memory uses the shared four-type taxonomy (`user`/`feedback`/`project`/`reference`) documented
in `MEMORY_SYSTEM.md`. When `tengu_ochre_finch` is on, the inline taxonomy is replaced by a pointer
to the `memory-types` skill (grep `Full reference for the memory type taxonomy`), a
non-user-invocable skill enabled only when memory is on and that flag is set.


## Relocating in a new bundle

All anchors are version-stable strings, not minified symbol names.

| Concept             | Grep anchor                                            |
| ------------------- | ------------------------------------------------------ |
| Directory resolver  | `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` + `projects` join |
| Memory base         | `process.env.CLAUDE_CODE_REMOTE_MEMORY_DIR`            |
| Slug override       | `CLAUDE_CODE_PROJECT_DIR_NAME`                         |
| Canonical git root  | `"commondir"`, `"gitdir:"`                             |
| Index filename      | `"MEMORY.md"`                                          |
| Directory override  | `autoMemoryDirectory`                                  |
| Session dispatcher  | `tengu_memdir_loaded` (emitted on load)                |
| Load telemetry      | `tengu_memdir_loaded`                                  |
| Truncation warning  | `Keep index entries to one line`                       |
| Near-cap nudge      | `tengu_memdir_entrypoint_near_cap`                     |
| Guidelines override | `# auto memory`                                        |
| `/memory` command   | `Edit CLAUDE.md files and memory settings`             |
| `/pause-memory`     | `Pause automemory for this session`                    |


## Tripwires

- `□` Default path is `<memory-base>/projects/<slug>/memory/` with the index at `MEMORY.md`.
- `□` Slug = canonical root with non-alphanumerics → `-`, capped 200 chars + hash.
- `□` A linked worktree's canonical root is its main repository: the common dir's parent, or the
  common dir itself for a bare repository.
- `□` Load caps: 200 lines / 25,000 chars, then a truncation warning replaces the overflow.
- `□` `CLAUDE_COWORK_MEMORY_GUIDELINES` overrides the built-in prompt with `# auto memory`.
- `□` `/memory` edits CLAUDE.md, not the auto-memory `MEMORY.md` index.
- `□` `/pause-memory` exists but `isEnabled` is false in this build (inert).
