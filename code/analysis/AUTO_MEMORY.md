---
verified: 2.1.317
verified_on: 2026-11-03
section: Memory
style: landmark
scope: 'Per-project auto memory: dir resolution, index load and backfill, `/memory`'
landmarks:
  - '"MEMORY.md"'
  - autoMemoryDirectory
  - "user's auto-memory, persists across conversations"
  - tengu_memdir_index_backfilled
  - Edit CLAUDE.md files and memory settings
---
# Auto Memory (MEMORY.md)

The user-facing, cross-session memory the main session builds up over time: a per-project directory
holding a `MEMORY.md` index plus per-topic memory files, written by the model as it works and loaded
back at the start of future sessions.

This is a leaf of the memory system; read `MEMORY_SYSTEM.md` first for the shared machinery (the
index pattern, memory types, save protocol, the master gate, the session dispatcher, truncation
caps). This doc covers what is specific to auto memory: where the directory lives, how its index
reaches the model, the index backfill, and the related slash commands.

Public docs: `code.claude.com/docs/en/memory`.


## Where it lives

The directory resolver is a memoized method of a per-host resolver class. Relocate it via the
override inputs it consults (`CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` and `autoMemoryDirectory`) and the
`"projects"` path segment it joins. The default path is:

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
- With no project directory the resolver returns no directory. In a diskless process a null resolver
  is used, but memory is already off there (the master gate).

So the typical path is `~/.claude/projects/-Users-you-src-myproject/memory/`, with the index at
`MEMORY.md` inside it (grep the quoted literal `"MEMORY.md"`).

The canonical root is the first of these that resolves:

1. A working-copy root registered for the project directory (the `"working_copy"` key source). The
   resolver has a slot for it, but in this build nothing fills it: `warmCanonicalWcRoot()` resolves
   immediately and only the reset path writes the slot. This step never applies.
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
the canonical-root function via the `"commondir"` and `"gitdir:"` literals (many hits; the one that
also compares against `"worktrees"` and returns the common dir or its parent).

Two overrides are checked before the default, in this order:

- `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE`: explicit directory, taken literally (no `~` expansion).
- the `autoMemoryDirectory` setting: the first enabled settings source that sets it wins, in the
  order policy → flag → (local → project, only when the workspace is trusted or the session is
  non-interactive) → user. A leading `~/` expands to the home directory; a value that climbs out of
  it with `..` is rejected. Grep `autoMemoryDirectory`.

Both must normalize to an absolute path of at least 3 characters that is not a bare drive letter and
holds no NUL byte, or they are ignored. An invalid `autoMemoryDirectory` falls through to the
default path, not to a lower-precedence settings source.

The team-memory subdirectory is a sibling under the same root: `<auto-memory-dir>/team/`. See
`TEAM_MEMORY.md`.


## How it reaches the model

Two separate pieces carry auto memory into a session.

The instructions are the memory prompt built by the session dispatcher (`MEMORY_SYSTEM.md`, "The
session dispatcher"). In the plain auto-memory branch it calls the instruction builder with the
display name `auto memory`, which emits `# auto memory` and
`You have a persistent, file-based memory system at <dir>`. The prompt does not carry the index.
Before returning, the dispatcher creates the directory (a failure is logged at debug level, grep
`ensureMemoryDirExists failed for`) and fires `tengu_memdir_loaded` with `memory_type: "auto"` plus
the directory's file and subdirectory counts.

The index is loaded with the CLAUDE.md files, not into the memory prompt. The CLAUDE.md loader
appends `MEMORY.md` after the other instruction files as a context file of type `AutoMem`, and it
renders inside the CLAUDE.md block as

```
Contents of <dir>/MEMORY.md (user's auto-memory, persists across conversations):
```

followed by the index content (grep `user's auto-memory, persists across conversations`). The
loader:

- Runs only when the master gate is on and the read fence is down (`MEMORY_SYSTEM.md`, "The master
  gate").
- Skips the index in recall mode, where the save instructions are the one-step form.
- Strips YAML frontmatter and block-level HTML comments, does not expand `@` includes, then applies
  the shared truncation: first 200 lines and 25,000 characters, cut at a line boundary. Over the cap
  a `> WARNING:` line replaces the dropped content (grep `Keep index entries to one line`).
- Uses `CLAUDE_COWORK_MEMORY_INDEX_CONTENT` in place of the file when it is set; an empty value
  suppresses the index.
- While `blockReadsOutsideWorkingDirectories` is in force, loads the index only when its path
  resolves inside the memory directory.
- Emits nothing when the file is absent. There is no "currently empty" text for auto memory.

Although the index is a CLAUDE.md-list entry, the `/memory` dialog filters it out of its file list
(see below).

A PostToolUse check runs after a write to `MEMORY.md` and measures the index the way loading sees
it. At 80% of either cap it adds a reminder to compact the index to under 70% (140 lines or 17,500
characters); past a cap the reminder becomes
`Error: this write left the memory index at MEMORY.md at ...`. Both fire
`tengu_memdir_entrypoint_near_cap`.

One override short-circuits the memory prompt: when `CLAUDE_COWORK_MEMORY_GUIDELINES` is set and
memory is on, the dispatcher returns that text verbatim under a literal `# auto memory` heading
instead of the built-in memory prompt. Grep `# auto memory`.


## Index backfill

When the index is absent at load time, the loader can write one from the topic files and then read
it. It tries this only when `CLAUDE_COWORK_MEMORY_INDEX_CONTENT` is unset, recall mode is off,
`CLAUDE_CODE_REMOTE` is unset and the read-fence path check passes. The outcome is cached per memory
directory for the process, except that a directory with nothing to index, or one whose check failed,
is checked again on the next load. Relocate it with `rg -nF 'memory index backfill'` (the debug-log
prefix of most exits) or `tengu_memdir_index_backfilled`.

- It does nothing when `MEMORY.md` already exists, or when the directory has no `.md` file and no
  subdirectory other than dot-entries and the reserved `team`, `logs`, `sessions` and `proposals`
  directories. Links and special files do not count.
- It scans the memory files the same way recall does: every `.md` file except `MEMORY.md`, skipping
  dot-prefixed path segments and the reserved directories.
- Each file becomes one line, `- [<basename>](<relative path>) — <description>`, with the
  description from the file's frontmatter, the whole line capped at 150 characters. Files whose path
  holds brackets, parentheses, line breaks or control characters are skipped and counted.
- It stops adding lines at 70% of the index caps (140 lines or 17,500 characters).
- It writes to a temporary `.MEMORY.md.backfill-<pid>-<hex>.tmp` and links it into place, so it
  never overwrites an index that appeared in the meantime. If that fails it creates `MEMORY.md`
  exclusively in place. A read-only directory ends the attempt.
- On a successful write it fires `tengu_memdir_index_backfilled` with `file_count` and
  `skipped_count`.


## Gate

Auto memory is on by default and governed by the master gate; `MEMORY_SYSTEM.md` ("The master gate")
has the full order. In brief: safe mode, a restricted session, a diskless process or a truthy
`CLAUDE_CODE_DISABLE_AUTO_MEMORY` turns it off; an explicitly falsy value forces it on past
`CLAUDE_CODE_SIMPLE`, the remote-session check, the model kill switch and the `autoMemoryEnabled`
setting, which otherwise decides (default on). When it is off the dispatcher emits
`tengu_memdir_disabled` and returns no memory prompt, and the loader skips the index.


## Two things called "memory"

The bundle has two distinct memory concepts, and the slash commands attach to the older one. Keep
them separate:

- Auto memory (this doc): the `MEMORY.md` index plus topic files, written by the model, loaded
  automatically, telemetry taxonomy `auto`/`team`/`agent`.
- CLAUDE.md memory: the project/user/local `CLAUDE.md` instruction files, authored by hand, with the
  capitalized `User`/`Project`/`Local`/`Managed` taxonomy. The auto-memory index rides in the same
  file list as a fifth type, `AutoMem`, but it is still the auto-memory index.

The `/memory` slash command (grep `Edit CLAUDE.md files and memory settings`) opens a dialog for
editing CLAUDE.md files. It drops the `AutoMem` entry from its file list, so it does not edit the
`MEMORY.md` index, but it has rows that open memory folders: `Open auto-memory folder`,
`Open team memory folder` (only when team memory is active), and `Open <agent> agent memory` for
each agent with a `memory:` scope. Its `Auto-memory` and `Auto-dream` rows are covered in
`MEMORY_SYSTEM.md`. The onboarding card presents `/memory` as the way to edit CLAUDE.md (grep
`Teach Claude your rules`). The public "Memory" doc page covers both concepts under one heading; the
source keeps them as separate code paths.

`/pause-memory` (aliases `memory-pause` and `toggle-memory`) is the runtime switch that turns memory
off for the current session, firing `tengu_memory_toggled`. Its description is either
`Pause automemory for this session` or
`Pause account memory and local auto-memory for this session (run again to turn both back on)` (grep
either). Its `isEnabled` is hardwired false, so the command is inert: the session switch exists in
code but is not exposed.


## Memory types and the memory-types skill

Auto memory uses the shared four-type taxonomy (`user`/`feedback`/`project`/`reference`) documented
in `MEMORY_SYSTEM.md`. When `tengu_ochre_finch` is on, the inline taxonomy is replaced by a pointer
to the `memory-types` skill (grep `Full reference for the memory type taxonomy`), a
non-user-invocable skill enabled only when memory is on and that flag is set.


## Relocating in a new bundle

All anchors are version-stable strings, not minified symbol names.

| Concept              | Grep anchor                                                  |
| -------------------- | ------------------------------------------------------------ |
| Directory resolver   | `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` + `"projects"` join     |
| Memory base          | `process.env.CLAUDE_CODE_REMOTE_MEMORY_DIR`                  |
| Slug override        | `CLAUDE_CODE_PROJECT_DIR_NAME`                               |
| Key sources          | `via: "working_copy"` / `via: "git"` / `via: "project_root"` |
| Canonical git root   | `"commondir"`, `"gitdir:"`                                   |
| Index filename       | `"MEMORY.md"`                                                |
| Directory override   | `autoMemoryDirectory`                                        |
| Load telemetry       | `tengu_memdir_loaded`                                        |
| Index delivery       | `user's auto-memory, persists across conversations`          |
| Index content swap   | `CLAUDE_COWORK_MEMORY_INDEX_CONTENT`                         |
| Truncation warning   | `Keep index entries to one line`                             |
| Near-cap nudge       | `tengu_memdir_entrypoint_near_cap`                           |
| Index backfill       | `memory index backfill` / `tengu_memdir_index_backfilled`    |
| Guidelines override  | `# auto memory`                                              |
| `/memory` command    | `Edit CLAUDE.md files and memory settings`                   |
| `/memory` folder row | `Open auto-memory folder`                                    |
| `/pause-memory`      | `Pause automemory for this session`                          |


## Tripwires

- `□` Default path is `<memory-base>/projects/<slug>/memory/` with the index at `MEMORY.md`.
- `□` Slug = canonical root with non-alphanumerics → `-`, capped 200 chars + hash.
- `□` A linked worktree's canonical root is its main repository: the common dir's parent, or the
  common dir itself for a bare repository.
- `□` `warmCanonicalWcRoot()` is a no-op, so the `"working_copy"` key source never applies.
- `□` The index is an `AutoMem` file in the CLAUDE.md block, rendered with
  `(user's auto-memory, persists across conversations)`; the memory prompt does not carry it.
- `□` Load caps: 200 lines / 25,000 chars, then a truncation warning replaces the overflow.
- `□` A missing index is backfilled from topic files, at most 70% of the caps, never overwriting.
- `□` `CLAUDE_COWORK_MEMORY_GUIDELINES` overrides the built-in prompt with `# auto memory`.
- `□` `/memory` edits CLAUDE.md and filters out the `AutoMem` entry.
- `□` `/pause-memory` exists but `isEnabled` is false in this build (inert).
