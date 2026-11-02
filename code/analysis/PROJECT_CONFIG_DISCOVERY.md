# Project Config Discovery from a Subdirectory

Verified against: cli.prettier.js 2.1.316 (2026-11-01)

Which project files a session reads when it starts in a subdirectory of a repository, and which it
picks up later. This matters for any layout where sessions start below the git root, such as an MCP
server that runs `claude -p` with its working directory set to one subtree of a monorepo.

See also: [File Inclusion](FILE_INCLUSION.md) (the same ancestor walk feeds `@` completion),
[Auto Memory](AUTO_MEMORY.md) (memory is keyed on the git root), [Settings](SETTINGS.md),
[MCP](MCP.md).

## Summary

| Item                                    | Read from                                                        | Loaded                                                                  |
| --------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `CLAUDE.md`                             | Start directory and every ancestor                               | At start                                                                |
| `CLAUDE.md` in a subdirectory           | A subdirectory of the start directory                            | On first file read there                                                |
| `CLAUDE.md` in an `--add-dir` directory | Each additional directory                                        | At start, when `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` is truthy |
| Skills, agents, commands, output styles | Every `.claude/<subdir>` from start directory up to the git root | At start                                                                |
| Skills in a subdirectory                | `.claude/skills` below the start directory                       | On first file read there                                                |
| `.mcp.json`                             | Start directory and every ancestor                               | At start                                                                |
| `.claude/settings.json`                 | Start directory only                                             | At start                                                                |
| Auto memory                             | One directory per git root                                       | At start                                                                |
| Session transcripts                     | One directory per start directory                                | n/a                                                                     |

Headless (`claude -p`) sessions behave the same as interactive ones for every row tested below.

## Ancestor walk for `.claude/` subdirectories

Skills, agents, commands, output styles, workflows and routines come from every `.claude/<subdir>`
on the chain from the start directory up to the git root, stopping early at the home directory. The
git root's own `.claude/<subdir>` is added when the walk does not reach it.

Relocate: `rg -n 'getProjectDirsUpToHome: stat'` lands in the stat loop that keeps only the
`.claude/<subdir>` paths that exist. The walk that builds its input runs just above it: it pushes
`<dir>/.claude/<subdir>` for each directory and breaks when it reaches the home directory or the git
root.

Consequence: in a monorepo, skills defined once in the root `.claude/skills` are available to a
session started in any subtree, including a `claude -p` child.

## Subdirectory skills and `CLAUDE.md` load on first read

A `.claude/skills` directory below the start directory is not loaded at start. It is added once the
session reads a file in that subtree. A subdirectory's `CLAUDE.md` follows the same rule.

Relocate: `rg -n 'dynamicSkillStates|dynamicSkillsLoaded'` finds the per-session state that holds
skills discovered after startup.

The trigger is a file under the start directory. A file in a sibling directory, outside the start
directory, does not load that directory's `CLAUDE.md`, even when the read succeeds and both
directories share a git root.

## `--add-dir` and `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD`

With the env var truthy, the `CLAUDE.md` of each `--add-dir` directory is loaded at start, before
any read. Without it, an additional directory grants file access only. The var is commonly set
through the `env` block of user `settings.json`, in which case a `claude -p` child spawned by
anything the user runs inherits it.

Relocate: `rg -n 'CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD'`. Expect the env var registry entry,
a gate that reads the var through a truthy helper (with a setting checked first), a spawn site that
sets it to `"1"` for a child, and a check that refuses `add_directory` in a container where it is
unset.

To give a session started in one subtree the instructions of a sibling subtree deterministically,
pass `--add-dir <sibling>` and set the var in the child's environment. Do not rely on the read
trigger.

## `.mcp.json` and settings

`.mcp.json` files are read from the start directory and every directory above it. Relocate with
`rg -n 'from .mcp.json files in this folder or above it'` (the project trust warning).

`.claude/settings.json` (`projectSettings`) is read from the start directory only. The same warning
screen tells the model to "read this folder's .claude/settings.json and .claude/settings.local.json,
and the .mcp.json files here or above"; relocate with
`rg -n "read this folder's .claude/settings.json"`. `localSettings` resolution compares the start
directory with the canonical git root and can select either one. Which it selects for a plain
subdirectory start is not yet resolved.

## Transcripts versus memory

Session transcripts are stored under `~/.claude/projects/<slug>/`, where the slug is derived from
the start directory. A session started in a subtree therefore has its own transcript directory, and
`--resume <id>` only finds sessions recorded under the same start directory. Auto memory is keyed on
the git root (see `AUTO_MEMORY.md`), so every subtree of one repository shares a single memory
directory.

## Tripwires

Run from a scratch git repo with a root `CLAUDE.md`, a root `.claude/skills/root-skill`, a
`sub/.claude/skills/nested-skill`, and `code/` and `desktop/` subdirectories each with a
`CLAUDE.md`:

- [ ] Session started at root lists only `root-skill` before any read
- [ ] Same session lists `nested-skill` after reading `sub/<file>`
- [ ] Session started in `sub/` lists both skills
- [ ] Session started in `desktop/` loads root and desktop `CLAUDE.md`, not code's
- [ ] Same session, after reading `../code/<file>`, still does not load code's `CLAUDE.md`
- [ ] Same session with `--add-dir ../code` and the env var set loads code's `CLAUDE.md` before any
  read
