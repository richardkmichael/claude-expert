# Project Files and State

Verified against: cli.prettier.js 2.1.317 (2026-11-03)

Two different mechanisms decide what "the project" is, and they use different roots:

1. Files a session reads. Claude Code finds instruction files, `.claude/` content, settings and
   `.mcp.json` by walking directories from the start directory. Each kind of file has its own walk:
   some stop at the start directory, some at the git top-level, some go all the way to the
   filesystem root, and some are picked up later, when a tool touches a file below the start
   directory.
2. State Claude Code keeps per project. Transcripts, memory, the `projects` entry in
   `~/.claude.json`, trust and the rest are stored under a key. Some keys are the start directory;
   others are the canonical root, which makes every linked worktree of a repository share one entry.

A session started in a subdirectory, or in a linked worktree, is where the two diverge: it reads
files relative to where it started, but shares state with the whole repository.

See also: [Auto Memory](AUTO_MEMORY.md) (memory directory and the canonical-root resolver),
[Settings](SETTINGS.md), [MCP](MCP.md), [Skills](SKILLS.md), [Subagents](SUBAGENTS.md),
[File Inclusion](FILE_INCLUSION.md) (the same `.claude/` walk feeds `@` completion),
[External CLAUDE.md includes](CLAUDE_MD_EXTERNAL_INCLUDES.md),
[Session Transcript](SESSION_TRANSCRIPT.md), [Agent Memory](AGENT_MEMORY.md),
[Team Memory](TEAM_MEMORY.md), [githubRepoPaths](GITHUB_REPO_PATHS.md),
[Command History](COMMAND_HISTORY.md), [Worktrees](WORKTREES.md) (`--worktree` and the worktree
hooks).

## Terms

- Start directory: the directory the session was launched in. A `--worktree` session starts in the
  worktree it creates. A `cd` in the Bash tool does not move it; the current directory (cwd) does
  move, and a few lookups below use it instead.
- Git top-level: the nearest ancestor of the start directory that holds a `.git` entry (directory or
  file). In a linked worktree it is the worktree's own root.
- Canonical root: the git top-level, except in a linked worktree, where it is the main repository:
  the common dir's parent when the common dir is named `.git`, or the common dir itself for a bare
  repository (`project/project.git`). Outside a repository it is the start directory. The resolver
  and its cross-checks are documented in `AUTO_MEMORY.md`; relocate it via `"commondir"` and
  `"gitdir:"`.
- Config dir: `CLAUDE_CONFIG_DIR`, else `~/.claude`. "`~/.claude`" below means the config dir.
- Slug: a path with every non-alphanumeric character replaced by `-`, truncated at 200 characters
  plus a hash. `CLAUDE_CODE_PROJECT_DIR_NAME` replaces it when `CLAUDE_CONFIG_DIR` is set or the
  session is diskless.

## 1. Files a session reads

| Item                             | Looked for in                         | Loads           |
| -------------------------------- | ------------------------------------- | --------------- |
| `CLAUDE.md`, `.claude/CLAUDE.md` | Start directory and every ancestor    | At start        |
| `CLAUDE.local.md`                | Start directory and every ancestor    | At start        |
| Rules without `paths:`           | Start directory and every ancestor    | At start        |
| Rules with `paths:`              | Same, plus user and managed rules     | On a match      |
| `AGENTS.md`, `.claude/AGENTS.md` | Start directory and every ancestor    | If no CLAUDE.md |
| `CLAUDE.md` family, below start  | Each directory down to a touched file | On first touch  |
| `@` imports                      | Relative to the importing file        | With that file  |
| `CLAUDE.md` family, `--add-dir`  | Each additional directory             | At start, gated |
| `.claude/<subdir>`               | Start directory up to git top-level   | At start        |
| `.claude/skills`, below start    | From a touched file up to the start   | On first touch  |
| Skills and agents, `--add-dir`   | Each additional directory             | At start        |
| `.claude/settings.json`          | Start directory only                  | At start        |
| `.claude/settings.local.json`    | Canonical root, then start directory  | At start        |
| `.mcp.json`                      | Start directory and every ancestor    | At start        |
| User files                       | `~/.claude/`                          | At start        |
| Managed files                    | Managed directory                     | At start        |

- "Every ancestor" means up to the filesystem root, past the git top-level and the home directory.
- "The `CLAUDE.md` family" is `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` and the rules
  under `.claude/rules/`.
- `<subdir>` is `skills`, `agents`, `commands` or `output-styles`.
- User files: `CLAUDE.md`, `rules/`, each `<subdir>/` and `settings.json` under `~/.claude/`, and
  user-scope MCP servers in `~/.claude.json`.
- Managed files: `CLAUDE.md`, `.claude/rules/`, `.claude/<subdir>/` and `managed-settings.json` in
  the OS-fixed managed directory (`/Library/Application Support/ClaudeCode` on macOS,
  `/etc/claude-code` on Linux).

Headless (`claude -p`) sessions load the same set.

### The instruction-file walk: every ancestor

At start, the loader lists the start directory and every ancestor up to the filesystem root, and
visits them outermost first. In each directory it reads `CLAUDE.md`, `.claude/CLAUDE.md`, the rules
under `.claude/rules/` (subfolders included) that have no `paths:` frontmatter, and
`CLAUDE.local.md`. The walk is not bounded by the git top-level or the home directory: a `CLAUDE.md`
or `CLAUDE.local.md` in a directory that contains the repository is loaded.

So in a bare-repository layout, a session started in `project/development` loads `project/CLAUDE.md`
and `project/CLAUDE.local.md` as well as the worktree's own files.

User files (`~/.claude/CLAUDE.md`, `~/.claude/rules/`) and managed files (`<managed>/CLAUDE.md`,
`<managed>/.claude/rules/`, and a `claudeMd` string in managed settings) are added alongside. The
project files need the `projectSettings` setting source; `CLAUDE.local.md` needs `localSettings`.

One exception: when the git top-level is a linked worktree nested inside its main repository (for
example `.claude/worktrees/<name>`), the directories from the main repository's root down to, but
not including, the worktree's root contribute only their `CLAUDE.local.md`. Their `CLAUDE.md`,
`.claude/CLAUDE.md` and rules are skipped, because the worktree has its own checked-out copies.
Sibling worktrees outside the main repository's directory are unaffected.

`AGENTS.md` and `.claude/AGENTS.md` are read by a built-in plugin from the same ancestors, by
default only when the walk finds no `CLAUDE.md`. Grep `AGENTS.md as project instructions` for the
plugin's option text and `no CLAUDE.md found; AGENTS.md loaded: ` for its debug line.

Relocate: `rg -n 'memory_files_started'` lands at the top of the start-time loader. Below it, a loop
builds the ancestor list up to the filesystem root, then maps each directory to its project files,
its `.claude/rules` directory and its `CLAUDE.local.md`. The nested-worktree exception is the helper
returning `{ worktreeRoot, mainRepoRoot }` (grep `mainRepoRoot`).

### Files below the start directory: on first touch

A directory below the start directory contributes nothing at start. When the Read, Edit or Write
tool touches a file, or a prompt `@`-mentions one, every directory from just below the start
directory down to the file's directory contributes its `CLAUDE.md` family, once. The file must be
under the start directory: a file in a sibling directory loads no `CLAUDE.md`, even when the read
succeeds and both share a git top-level.

The same touch also loads rules with `paths:` frontmatter whose globs match the file. Globs are
evaluated relative to the directory holding the rule's `.claude/`, for the directories above, the
start directory and its ancestors, and the user and managed rules. A rule in an ancestor's
`.claude/rules/` can therefore match a file outside the start directory, as long as the file is
under that ancestor.

The `InstructionsLoaded` hook reports each file with a `load_reason`: `session_start`,
`nested_traversal` (below the start directory), `path_glob_match` (a `paths:` rule), `include` (an
`@` import) or `compact`.

Relocate: `rg -n 'nestedMemoryAttachmentTriggers'` finds the trigger list the file tools push to;
the reason literals `nested_traversal` and `path_glob_match` sit in the attachment builder that
consumes it.

### `@` imports

An `@path` in a loaded instruction file is resolved relative to that file and loaded with it;
imports nest at most four levels below the file that started the chain. An import that resolves
outside the start directory is skipped until the external-includes dialog is accepted, which is
recorded in the `projects` entry (part 2). Imports from the user `CLAUDE.md` are followed regardless
of that dialog. A parent directory's `CLAUDE.md` importing a file beside itself is therefore
importing from outside the start directory. Details: `CLAUDE_MD_EXTERNAL_INCLUDES.md`.

### `--add-dir` directories

An additional directory grants file access. Its `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/`
and `CLAUDE.local.md` are loaded at start only when a host option enables it or
`CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` is truthy. The variable is commonly set in the `env`
block of user `settings.json`, so a `claude -p` child spawned from a session inherits it.

Its `.claude/skills` and `.claude/agents` are loaded at start without the variable. Agents from an
additional directory rank below the project's own (`SUBAGENTS.md`). The settings cascade has no
`--add-dir` source, and `.mcp.json` is not read from additional directories.

Relocate: `rg -n 'CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD'`. The gate reads the host option
(`claudeMdAdditionalDirectoriesAsked`) first and falls back to the variable through a truthy helper.

To give a session started in one subtree the instructions of a sibling subtree deterministically,
pass `--add-dir <sibling>` with the variable set. Do not rely on the touch trigger, which ignores
files outside the start directory.

### Skills, agents, commands and output styles: up to the git top-level

At start, each of `skills`, `agents`, `commands` and `output-styles` is collected from every
`<dir>/.claude/<subdir>` from the start directory upward. The walk stops before the home directory
(the user's `~/.claude/<subdir>` is a separate source) and stops after the git top-level, so a
`.claude/skills` in a directory that contains the repository is not read. Outside a repository the
walk runs up to the home directory or the filesystem root. If the current directory is inside a
repository nested in the start directory's repository, the walk continues to the outer repository's
top-level.

Linked worktrees: when the git top-level has no `.claude/<subdir>` of its own, the canonical root's
`<root>/.claude/<subdir>` is added. For a worktree of an ordinary checkout that is the main
checkout's `.claude/<subdir>`; for a worktree of a bare repository it is
`project/project.git/.claude/<subdir>`, inside the bare repository directory. A worktree that has
the subdirectory, for example because it is checked in, gets no fallback. `.claude/workflows`
follows the same walk without the fallback.

A host-supplied `--project-config-root <dir>` starts this walk, the `.mcp.json` walk and the project
settings at `<dir>` instead of the start directory.

Relocate: `rg -n 'getProjectDirsUpToHome: stat'` lands in the existence check after the walk. The
walk is just above it: it pushes `<dir>/.claude/<subdir>`, breaks at the home directory, and breaks
after the git top-level. The worktree fallback follows it: it compares the git top-level with the
canonical root and appends `<canonical>/.claude/<subdir>` when the top-level's own is missing. The
skills loader logs its result, grep `Loading skills from: managed=`.

### Skills below the start directory: on first touch

A `.claude/skills` below the start directory is loaded when the Read, Edit or Write tool first
touches a file under it: each directory from the file's directory up to, but not including, the
start directory is checked. (If the cwd has moved into a different repository, the cwd takes the
start directory's place.) A gitignored skills directory is skipped. The same touch activates a skill
whose `paths:` frontmatter matches the file.

Relocate: `rg -n 'dynamicSkillStates'` finds the per-session state for skills discovered after
start; `[skills] Skipped gitignored skills dir` and `Activated conditional skill` are the debug
lines.

### Settings

- `.claude/settings.json` (`projectSettings`) is read from the start directory only. There is no
  ancestor walk and no worktree fallback.
- `.claude/settings.local.json` (`localSettings`) is read from the canonical root when all hold: the
  canonical root differs from the start directory, it is not the home directory, and the canonical
  root, its `.git` entry and its `.claude` entry (if any) are owned by the current user. Otherwise
  it is read from the start directory. The start directory's file is still read when it differs,
  below the canonical one, so its keys apply where the canonical file does not set them. Writes
  (permission "always allow", `.mcp.json` approvals, `/config` local changes) go to the selected
  file.

So a session started in a subdirectory of an ordinary repository, or in a linked worktree of an
ordinary checkout, reads and writes the repository top-level's (or main checkout's)
`.claude/settings.local.json`. A worktree of a bare repository keeps its own: the bare directory has
no `.git` entry, so ownership cannot be verified, and the debug log records a
`localSettings: not canonicalizing the consent store to` warning naming the bare directory.

Relocate: `rg -n 'localSettings: not canonicalizing the consent store to'` (three warnings: no uid
semantics, ownership mismatch, ownership unverifiable). The start-directory read is reported through
`onLegacyLocalSettingsRead`. A debug run lists every settings file it watches: grep
`Watching for changes in setting files`.

### `.mcp.json`

Project-scope servers come from `.mcp.json` in the start directory and every ancestor up to the
filesystem root; a nearer file's server overrides a farther one of the same name. The trust screen
says the same: grep `from .mcp.json files in this folder or above it`. Approval state is a settings
matter (`MCP.md`); `claude mcp add -s project` writes `.mcp.json` in the current directory.

## 2. State Claude Code keeps, and its key

Paths are relative to the config dir unless they start with `<dir>` or `.claude/`.

| State                              | Location                                 | Key                           |
| ---------------------------------- | ---------------------------------------- | ----------------------------- |
| Session transcripts                | `projects/<slug>/<session>.jsonl`        | Start directory               |
| `--continue` lookup                | The start directory's transcripts        | Start directory               |
| `--resume <id>` lookup             | Start dir, worktrees, every project dir  | Session id                    |
| `/resume` picker                   | Start dir and every worktree of the repo | The repository's worktrees    |
| Prompt history (up arrow)          | `history.jsonl`, `project` field         | Start directory               |
| Auto memory                        | `projects/<slug>/memory/`                | Canonical root                |
| Team memory                        | `<auto memory dir>/team/`                | Canonical root                |
| Agent memory, `project`, `local`   | `<dir>/.claude/agent-memory[-local]/`    | Current directory             |
| Agent memory, `user`               | `agent-memory/<agent>/`                  | None (global)                 |
| `projects` entry, `~/.claude.json` | `projects["<path>"]`                     | Canonical root                |
| Workspace trust                    | `hasTrustDialogAccepted` in that entry   | Canonical root, see below     |
| Local settings                     | `.claude/settings.local.json`            | Canonical root, see Settings  |
| `githubRepoPaths`                  | `~/.claude.json`, `owner/repo` to paths  | Start dir's git top-level     |
| File history (checkpoints)         | `file-history/<session>/`                | Session id                    |
| Task lists                         | `tasks/<list id>/`                       | Session id by default         |
| Plans                              | `plans/`                                 | None, unless `plansDirectory` |
| Debug logs                         | `debug/<session>.txt`                    | Session id                    |
| Shell snapshots                    | `shell-snapshots/`                       | None (not project-scoped)     |

### Transcripts and resume

Transcripts live in `~/.claude/projects/<slug of the start directory>/`, so every start directory,
including each subdirectory and each worktree, has its own transcript directory.

Finding a session works at three widths:

- `--continue` looks only in the start directory's transcript directory (and the aliases recorded
  there). From a sibling worktree it finds nothing and starts a new session. Grep
  `No conversation found to continue`.
- `--resume <id>` tries the start directory's transcript directory, then the transcript directory of
  every worktree that `git worktree list` reports (telemetry `tengu_resume_worktree_fallback`), then
  scans every directory under `~/.claude/projects/` for `<id>.jsonl`, accepting it only when exactly
  one matches (`tengu_transcript_id_scan_fallback`). The resumed session keeps appending to the
  transcript where it was found, not to the new start directory's transcript directory.
- The `/resume` picker lists sessions from the start directory and every worktree of its repository,
  including directories whose slug extends a worktree's slug (sessions started in its
  subdirectories) and Claude-managed worktrees under `.claude/worktrees/`. Ctrl+A widens it to all
  projects. Grep `/resume: loading sessions for cwd=` (debug line) and `loadSameRepoMessageLogs`.

Relocate the by-id fallbacks with the two telemetry names; the per-directory lookup is exported as
`resolveSessionFilePath`.

### Memory

Auto memory and team memory are keyed by the canonical root, so every subdirectory and every linked
worktree of a repository shares one directory. For a bare repository at `~/src/project/project.git`
it is `~/.claude/projects/-Users-you-src-project-project-git/memory/`, next to (not inside) the
transcript directories of `-Users-you-src-project-development` and
`-Users-you-src-project-feature-x`. Full resolution, overrides and the `"working_copy"` key source:
`AUTO_MEMORY.md`.

Agent memory is not keyed through a slug. Its `project` scope is
`<current directory>/.claude/agent-memory/<agent>/` and its `local` scope
`<current directory>/.claude/agent-memory-local/<agent>/` (under `CLAUDE_CODE_REMOTE_MEMORY_DIR`,
`local` moves to `<remote>/projects/<slug of the canonical root>/agent-memory-local/<agent>/`). Each
worktree therefore has its own. Grep `"agent-memory-local"`; details in `AGENT_MEMORY.md`.

### The `projects` entry in `~/.claude.json`

One resolver, exported as `getProjectPathForConfig`, picks the key for every read and write of the
current project's entry: the canonical root of the start directory, or the start directory's real
path outside a repository. It is cached per process and cleared when the start directory changes. A
session in `project/development` or `project/feature-x` reads and writes
`projects["/…/project/project.git"]`; one in `repo/sub` or in a linked worktree of `repo` reads and
writes `projects["/…/repo"]`.

That entry holds, among others: local-scope MCP servers (`mcpServers`, from
`claude mcp add -s local`), the external-includes flags (`hasClaudeMdExternalIncludesApproved`,
`hasClaudeMdExternalIncludesWarningShown`), `exampleFiles` and `exampleFilesGeneratedAt`, the
project onboarding counters, the last-session statistics (`lastSessionId`, `lastCost`,
`lastModelUsage` and the other `last*` fields), `lastGracefulShutdown`, `lastVersionBase`, and the
legacy `allowedTools` and MCP-approval keys. All of these are shared by a repository's worktrees.

Workspace trust is written under a key computed the same way: grep
`canonical git root when inside a repository`, the SDK schema text that states it. Reading is wider:
a session is trusted when the entry under the config key has `hasTrustDialogAccepted`, or when any
directory from the start directory up to its git top-level has an entry with it (outside a
repository, up to the filesystem root). The upward check stops at the git top-level, so trusting a
directory that contains a repository does not trust a session started inside the repository.

An entry under a linked worktree's own path is not written by any path found in 2.1.317. A probe
with `claude mcp add -s local` from a bare-repository worktree wrote only the bare-repository key.
Where both a worktree-path entry and a canonical entry exist, the worktree-path entry still counts
for trust through the upward check, and `claude purge <path>` matches entries under both the path it
is given and that path's canonical root.

Relocate: `rg -n 'getProjectPathForConfig'` (the export alias of the resolver),
`rg -n 'hasTrustDialogAccepted'` (the reader with its upward check, and the writer).

### Other per-project and per-session state

- `githubRepoPaths` maps a lowercase `owner/repo` to checkout paths. The path recorded is the real
  path of the start directory's git top-level, so each worktree is listed separately under the same
  key. Grep `Not in a GitHub repository, skipping path mapping update`; see `GITHUB_REPO_PATHS.md`.
- Prompt history is one file; the up-arrow reader filters on the `project` field, which is the start
  directory. Grep `readTimestamped`; see `COMMAND_HISTORY.md`.
- File history, task lists and debug logs are keyed by session id (task lists by
  `CLAUDE_CODE_TASK_LIST_ID` or a team name when set). Plans are global unless the `plansDirectory`
  setting names a directory, which must lie inside the current directory (grep
  `plansDirectory must be within project root`). Shell snapshots are not project-scoped.
- `claude purge [path]` enumerates a project's state: its transcript directories (including
  subdirectory ones it can confirm), the sessions' task lists, debug logs and file history, its
  `projects` entries, and its prompt-history lines. Grep `Delete a project's Claude Code data` and
  `file edit history for session`. Purging one worktree deletes the shared canonical `projects`
  entry but not the shared memory directory.

## 3. Worktrees: shared and separate

Worked example, a bare repository with peer worktrees:

```
project/
  CLAUDE.md, CLAUDE.local.md, .mcp.json   # above every worktree
  project.git/                            # bare repository (the canonical root)
  development/                            # linked worktree
  feature-x/                              # linked worktree
```

| Item                                 | Shared by the worktrees              | Separate per worktree           |
| ------------------------------------ | ------------------------------------ | ------------------------------- |
| `project/` instruction files         | Yes, through the ancestor walk       |                                 |
| Instruction files in a worktree      |                                      | Yes                             |
| `.claude/<subdir>`                   | Only `project.git/.claude/` fallback | Yes; `project/.claude/` unread  |
| `.claude/settings.json`              |                                      | Yes                             |
| `.claude/settings.local.json`        |                                      | Yes; a bare root is never used  |
| `.mcp.json`                          | `project/.mcp.json`, ancestor walk   | The worktree's own              |
| `projects` entry in `~/.claude.json` | Yes, keyed `project/project.git`     |                                 |
| Local MCP servers, include approval  | Yes, in the `projects` entry         |                                 |
| Workspace trust                      | Yes, canonical key                   | A worktree-path entry counts    |
| Auto memory and team memory          | Yes, slug of `project/project.git`   |                                 |
| Agent memory, `project` and `local`  |                                      | Yes, in the worktree `.claude/` |
| Session transcripts                  | `/resume`, `--resume <id>` see all   | Stored here; `--continue`       |
| Prompt history                       |                                      | Yes                             |
| `githubRepoPaths`                    | One `owner/repo` key                 | One path per worktree           |
| File history, tasks, plans           | Not project-scoped                   | Not project-scoped              |

`project/` instruction files are `project/CLAUDE.md`, `project/CLAUDE.local.md` and
`project/.claude/rules/`. Instruction files in a worktree are its checked-out `CLAUDE.md` and its
untracked `CLAUDE.local.md`.

With an ordinary checkout as the main repository (`repo/` plus a linked worktree `repo-wt/` beside
it), two rows change: `repo-wt` reads and writes `repo/.claude/settings.local.json` (with its own
file read underneath), and its `.claude/<subdir>` fallback is `repo/.claude/<subdir>`. `repo/` is
not an ancestor of `repo-wt`, so `repo/CLAUDE.md` and `repo/CLAUDE.local.md` are not loaded there. A
worktree nested inside `repo/` (such as `repo/.claude/worktrees/<name>`) does have `repo/` as an
ancestor: it loads `repo/CLAUDE.local.md` but skips `repo/CLAUDE.md` in favor of its own copy.

## Tripwires

Run from a scratch layout: `project/project.git` (bare, with `.claude/agents/bare-agent.md`),
worktrees `project/development` and `project/feature-x` that check in `.claude/skills/tracked-skill`
but no `.claude/agents`, `project/CLAUDE.md`, `project/CLAUDE.local.md`,
`project/.claude/rules/r.md`, `project/.claude/skills/parent-skill`, an untracked
`development/.claude/skills/dev-skill` and `development/sub/.claude/skills/nested-skill`; plus an
ordinary `repo/` with `.claude/settings.local.json` setting `outputStyle` and a linked worktree
`repo-wt/`. Use a fresh `CLAUDE_CONFIG_DIR`; `claude -p --output-format stream-json --verbose`
prints skills, agents and `memory_paths` in its init message even without credentials, and an
`InstructionsLoaded` hook passed with `--settings` reports each instruction file.

- [ ] In `development`, `InstructionsLoaded` reports `project/CLAUDE.md`, `project/CLAUDE.local.md`
  and `project/.claude/rules/r.md` (ancestor walk past the git top-level)
- [ ] In `development`, skills include `dev-skill` and `tracked-skill` but not `parent-skill` or
  `nested-skill`; agents include `bare-agent` (main-repository fallback)
- [ ] In `development`, `memory_paths.auto` ends in `-project-project-git/memory/`; the transcript
  is under `-project-development`
- [ ] In `development`, the debug log has `localSettings: not canonicalizing the consent store to`
  naming `project.git`
- [ ] In `repo-wt` and in `repo/sub`, the init message's `output_style` comes from
  `repo/.claude/settings.local.json`
- [ ] `claude mcp add -s local x -- /bin/echo` from `development` writes
  `projects["…/project/project.git"]`; from `repo/sub`, `projects["…/repo"]`
- [ ] From `feature-x`, `--resume <development session id>` resumes and appends to the
  `-project-development` transcript; `--continue` starts a new session
- [ ] `rg -cF` each relocation anchor in this doc against the new bundle returns at least 1
