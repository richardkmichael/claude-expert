# The `/cd` command (move a session to a new directory)

Verified against: cli.prettier.js 2.1.198 (2026-07-03)

`/cd <path>` moves the running session to a new working directory. It changes the process cwd,
relocates the session transcript into the target directory's project folder, re-loads `CLAUDE.md`
for the new tree, and refreshes the git/branch state. It does not move, copy, or merge the
project's auto-memory: memory stays anchored to the directory the session launched in.

The command is a `local-jsx` slash command, described in the picker as
`Move this session to a new working directory` with `argumentHint: "<path>"`. It is not hidden.


## Relocating the doc

Landmark strings (stable across releases; the minified identifiers below churn every release):

- Registration / picker: `Move this session to a new working directory`, `argumentHint: "<path>"`.
- Command body messages: `Usage: /cd <path>`, `is not a directory. Did you mean`,
  `Couldn't find a directory at`, `Already in `, `Yes, move here`, `No, stay put`.
- chdir routine telemetry + stale-env notice: `tengu_cd_command`, and
  `The session's working directory has changed to ${...} (via /cd). The environment block at the
  start of this conversation still names the ` (the env block injected at session start now points
  at the old dir, so this meta-message tells the model paths resolve from the new dir).
- Permission gate (tool name `Cd`): `/cd is turned off by the`,
  `/cd is limited to directories matching`, `Cd rule in /permissions`.
- Transcript relocation: the `relocated` transcript record type (fields `sessionId`,
  `relocatedCwd`), and log strings `relocateSessionTranscript: old file missing`,
  `/cd transcript move failed and rollback chdir failed`.

Relocation recipe: `rg -n -F 'Move this session to a new working directory' <bundle>` lands on the
registration; the chdir routine is a few hundred lines above, reachable from the `tengu_cd_command`
and `via /cd` strings. The transcript mover is a separate function found via
`relocateSessionTranscript: old file missing`. In 2.1.198 the pieces are the command module near
601588–601940 (chdir routine, `M2m`, ~601781; arg validation, `F2m`, ~601830), the transcript mover
(`sze`) near 716128, and the memory-dir resolver (`Af`/`gjd`/`hjd`) near 178822.


## What it changes

Pre-flight (arg validation + gate): resolve and `stat` the path (must be a directory), `realpath`
it, no-op if already there (`Already in …`). Then the `Cd` permission gate runs — a deny rule
blocks the move; if any allow rules exist the target must match one. If the target has never been
trusted (`~/.claude.json` `projects[<dir>].hasTrustDialogAccepted`, checked walking up parents), a
trust prompt appears; confirming writes `hasTrustDialogAccepted: true` into the target's
`~/.claude.json` project entry.

On a confirmed move:

- Working directory: `process.chdir(<dir>)`, then the session `cwd` and `originalCwd` state fields
  are set to the new (realpath'd) directory. On any failure the chdir and both fields roll back.
- Session transcript: moved, not copied. Target project dir is
  `~/.claude/projects/<encode(originalCwd)>` (the encoder replaces every non-alphanumeric char with
  `-`). The `<sessionId>.jsonl` file is renamed there (with copy-then-delete fallback across
  devices), the per-session `<sessionId>/` sibling dir (subagent/task output) moves with it and its
  symlinks are repointed, and a `{type:"relocated"}` record is appended. Edge cases: if history is
  disabled or there is no session file, nothing moves; if the target maps to the same project dir
  (`current === target`), no move happens but the `relocated` marker is still appended.
- `CLAUDE.md`: re-loaded for the new tree. The loader walks root→dir gathering `CLAUDE.md` files
  (unless `CLAUDE_CODE_DISABLE_CLAUDE_MDS`); the result plus the stale-env notice is injected as a
  message on the next reply rather than rebuilt into the system prompt. Injecting it as a message
  keeps the conversation's prompt cache intact (the docs call this out explicitly).
- Git / config state: git branch watcher re-anchored and its cache cleared, `refreshGitBranch()`
  runs, and the global config is re-read into memory (`refreshConfig()`).
- The internal session→project-dir pointer is repointed to the new project dir (this is what makes
  later transcript writes land in the new folder). The `sessionId` itself is unchanged.

Not touched by the handler: the permission allowlist (the `Cd` rule only gates whether `/cd` may
run — it is not the session's allowed-tools set), `.mcp.json` / MCP servers (no re-init on the cd
path), todos, shell snapshots, and input history (these are keyed by `sessionId` or live in global
`~/.claude` subdirectories, not by project dir).


## Auto-memory is not moved, merged, or switched

This is the load-bearing finding. `/cd` leaves the per-project auto-memory
(`~/.claude/projects/<slug>/memory/`, `MEMORY.md` + files) entirely alone. The old project's
memories are neither carried into the target nor swapped for the target's own memory dir — memory
stays pinned to the directory the session was launched in.

Why, from the two keys the code uses:

- The transcript's project dir keys off `originalCwd` (the `ar()` getter). `/cd` updates
  `originalCwd`, so the transcript follows the move.
- The auto-memory dir keys off `projectRoot` (the memory resolver `Af()` → `gjd()` →
  `tl()` → `projectRoot`; `projectRoot` is the git root or, failing that, the working dir captured
  at session start — see `AUTO_MEMORY.md`). `/cd` never updates `projectRoot`, so memory resolution
  is unchanged.

Proof that `/cd` cannot move memory, three ways:

1. The entire `/cd` command module contains zero references to memory, `autoMemoryDirectory`,
   `MEMORY.md`, or the memory resolver.
2. `projectRoot` has exactly one writer in the bundle — the `Ege` setter (`Ut.projectRoot = …`).
   Its call sites are the worktree-enter, worktree-exit, deeplink-cwd-change, and session-claim
   paths; none is `/cd`. Every one of those cwd-changing paths pairs the `originalCwd` setter with
   the `projectRoot` setter. `/cd` is the sole cwd-changing path that sets `originalCwd` alone.
3. `tengu_memdir_loaded` does not fire on `/cd`.

Consequence for users: `/cd` is a transcript-and-cwd move, not a project migration. Move a session
into another project and it writes future turns to that project's transcript folder, but it keeps
reading and writing the memory of wherever it started. Manually copying `MEMORY.md` and the memory
files between the two `~/.claude/projects/<slug>/memory/` dirs is the only way to carry memory
across.


## Telemetry

- `tengu_cd_command` (empty payload) on a successful move.
- `tengu_shell_set_cwd` `{ success: true }` from the cwd change.
- `tengu_memdir_loaded` is notably absent.


## Official docs and drift

`/cd` is documented. The commands reference (`code.claude.com/docs/en/commands`) describes it as
moving the session to a new working directory, preserving the prompt cache by appending the new
`CLAUDE.md` as a message instead of rebuilding the system prompt, relocating the session to the new
directory's project storage so `--resume` / `--continue` find it there, prompting for trust on an
unfamiliar directory, and being restrictable via `Cd` permission rules. The `Cd` rule syntax (bare
`Cd` deny disables it, `Cd(<pattern>)` scopes targets, allow rules switch to allowlist mode) is
documented in the permissions reference. The docs also state `/cd` requires v2.1.169 or later;
earlier versions report `Unknown command: /cd`.

All of that matches the source. The one drift is memory: the docs say "the session is relocated to
the new directory's project storage" but never state what happens to auto-memory, and that phrasing
can read as though the whole session — memory included — moves. It does not. Auto-memory stays
anchored to the launch directory's `projectRoot` (see above). The memory doc, which explains memory
is keyed on the git repo / working dir, likewise never mentions `/cd`. So the gap is an omission on
both sides rather than an incorrect statement — but it is the surprising case, and worth flagging if
the docs are ever revised.


## Version fragility

The `originalCwd`-updated-but-`projectRoot`-untouched asymmetry is the easy-to-miss, load-bearing
detail. A refactor that "tidied" the cd path by adding the `projectRoot` setter alongside the
`originalCwd` setter would silently start moving auto-memory with the session. Re-verify on each
release that the cd chdir routine sets `originalCwd` without setting `projectRoot`, and that the cd
module still has no memory references. Everything else keyed on minified identifiers should be
relocated via the landmark strings above.
