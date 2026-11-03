# Worktree hooks: WorktreeCreate / WorktreeRemove lifecycle

Verified against: cli.prettier.js 2.1.317 (2026-11-03)

How Claude Code builds the WorktreeCreate and WorktreeRemove hook payloads, which entry points fire
them, what `cwd` the hook receives, how `worktree.baseRef` interacts with a hook, and when a
hook-created worktree is (and is not) removed. `HOOKS.md` holds the event inventory, the common
input fields and the restricted-personal-hooks rules. `PROJECT_FILES_AND_STATE.md` defines the
canonical root and covers what worktrees share. This doc covers the worktree lifecycle around the
two events.

## Re-location recipes

Every anchor is a literal; search it with `rg -nF '<anchor>' cli.prettier.js`.

| Target                         | Anchor                                                         |
| ------------------------------ | -------------------------------------------------------------- |
| WorktreeCreate payload         | `hook_event_name: "WorktreeCreate"` (one hit)                  |
| WorktreeRemove payload         | `hook_event_name: "WorktreeRemove"` (one hit)                  |
| WorktreeCreate input schema    | `("WorktreeCreate"), name:`                                    |
| WorktreeRemove input schema    | `("WorktreeRemove"), worktree_path:`                           |
| Common input fields            | `scratchpad_dir:` beside `transcript_path:`                    |
| Hook configured but not run    | `hook is configured but did not run (workspace not trusted or` |
| Hook output contract           | `hookSpecificOutput.worktreePath`                              |
| Personal-config refusal        | `doesn't let your own hooks choose the worktree folder`        |
| Returned-path screen           | `hook emitted a path with dot segments`                        |
| Returned-path directory check  | `returned a path that is not a directory`                      |
| Hook working-dir fallback      | `Hooks: working directory`                                     |
| Remove executor outcomes       | `treating it as removed`, `left the tree in place (workspace`  |
| Worktree name validator        | `is a reserved git directory name`                             |
| Session worktree creator       | `Created hook-based worktree at:`                              |
| Agent worktree creator         | `Created hook-based agent worktree at:`                        |
| `--worktree` chdir             | `worktree_resolved_to_main_repo`                               |
| `--worktree` pre-check         | `Can only use --worktree in a git repository`                  |
| `--worktree` plugin hooks      | `plugin worktree hooks not registered before creating the`     |
| `--worktree --tmux` name       | `"swift", "bright", "calm", "keen", "bold"`                    |
| EnterWorktree create branch    | `Already in a worktree session`, then the chdir                |
| Subagent cleanup closure       | `Hook-based agent worktree kept at:`                           |
| Session worktree remover       | `No WorktreeRemove hook configured; falling back`              |
| Agent/job remover              | `removeAgentWorktree: kept hook-based worktree`                |
| Remove-only config message     | `the repo defines only WorktreeCreate`                         |
| Forced job delete              | `job_delete_force_remove`, `--force-remove-worktree`           |
| Interactive exit dialog        | `Worktree removed (no changes)`, `WorktreeExitDialog`          |
| Exit-dialog status command     | `"--ignore-submodules=dirty",` in a frozen `status` array      |
| Exit-dialog submodule scan     | `submodule inspection deadline`                                |
| User-set vs AI session title   | `currentSessionTitle` vs `currentSessionAiTitle`               |
| Git post-creation setup        | `Configured worktree to use hooks from main`                   |
| Git branch name                | `` `worktree-${ `` (`/` in the name becomes `+`)               |
| `worktree.baseRef` schema      | `Which ref new worktrees branch from.`                         |
| Fresh-base fallback            | `basing worktree on local HEAD`                                |
| Git worktree lock reason       | `(pid ${process.pid}`                                          |
| SubagentStop, interrupted run  | `SubagentStop on interrupted query failed`                     |
| Turn-end reactions only        | `Turn-end reaction hook block discarded`                       |
| Agent id generator             | `.replace(/[^\w-]/g, "").slice(0, 63)`                         |
| Agent id validator             | `` `^a(?:${ `` (a `RegExp` built from a template literal)      |
| Reserved worktree names        | `/^agent-a[0-9a-f]{16}$/`                                      |
| Resume with a missing worktree | `This agent cannot be resumed: its worktree`                   |
| Agent tool result text         | `worktreePath: ${`                                             |
| Task-notification tags         | `= "worktreePath",`, between the other two tag names           |

## WorktreeCreate payload

There is exactly one builder: the common fields plus `hook_event_name: "WorktreeCreate"` and `name`.

The common-fields builder is called with only the session and the current cwd, so
`permission_mode`, `agent_id` and `effort` are always absent. What a command hook receives:
`session_id`, `transcript_path`, `cwd`, `hook_event_name`, `name`, plus `prompt_id`,
`scratchpad_dir` and `agent_type` when they have a value.

No other worktree field exists. The Zod input schema declares only `name` beside `hook_event_name`.
`worktree_name`, `base_path`, `base_ref` and `repo_root` do not occur as identifiers anywhere in the
bundle, and `pr_number` appears only in unrelated GitHub and PR-subscription payloads. Neither
worktree payload carries a branch field. The hook process env adds no worktree-specific variable
either (see `HOOKS.md`, Hook process environment).

### Hook output

A command hook prints the worktree path to stdout, and the last line is used. An http or callback
hook returns `hookSpecificOutput.worktreePath`. The run fails with an error when:

- the hook is configured but nothing ran
  (`hook is configured but did not run (workspace not trusted or matcher mismatch)`)
- every hook succeeded but none returned a path
- any hook failed (`WorktreeCreate hook failed: <command>: <output>`)
- the only answer came from the person's own hook while `CLAUDE_CODE_RESTRICT_PERSONAL_CONFIG` is
  set: the folder is not used (`doesn't let your own hooks choose the worktree folder`; see
  `HOOKS.md`, Restricted personal hooks)

An absolute path is used as is. A relative path resolves against the hook's `cwd` (in a session with
a remote attached, against the session's original cwd instead). If that directory no longer exists,
hooks run from the original cwd or the project root instead
(`Hooks: working directory … no longer exists; running hooks from …`), and the relative path
resolves against that.

### `name` per entry point

| Entry point                      | `name` value                                          |
| -------------------------------- | ----------------------------------------------------- |
| `claude --worktree <name>`       | `<name>` as given                                     |
| `claude --worktree` (no name)    | the session's plan slug                               |
| `claude --worktree <PR#/URL>`    | `pr-<N>`                                              |
| `--worktree --tmux` (no name)    | `<adjective>-<noun>-<4 base36>`, e.g. `bold-oak-a3f2` |
| EnterWorktree tool               | its `name` argument, else the plan slug               |
| Subagent `isolation: "worktree"` | `agent-<agentId>`, e.g. `agent-a321c56d3b6ffa445`     |
| Remote Control bridge            | `bridge-<id>`                                         |
| Background session               | via EnterWorktree (see below)                         |

A background session isolates through EnterWorktree: before the first code change by default, as its
first action when configured with `isolation: worktree` (`CLAUDE_BG_ISOLATION=worktree`), and not at
all when configured to work in place.

Every name passes the slug validator first (`Invalid worktree name`): at most 64 characters,
`/`-separated segments of letters, digits, `.`, `_` and `-`, no `.` or `..` segment, and no segment
that is `.git` ignoring case and trailing dots.

### Hook `cwd`

`cwd` is the process cwd at the moment the hook fires. The entry points differ in whether they
chdir before calling it:

- `--worktree`: chdirs only when the launch directory is in a git repository and its git root
  differs from its canonical root, which means the launch directory is inside a linked worktree. The
  CLI then logs `worktree_resolved_to_main_repo` and chdirs to the canonical root. From a
  subdirectory of a normal clone the two roots are equal, so there is no chdir and `cwd` is the
  subdirectory. With no git repository (hook-only VCS), there is no chdir either.
- EnterWorktree without `path` (and so background sessions): chdirs to the canonical root whenever
  it differs from the current cwd, and restores the cwd if creation fails. Unlike `--worktree`,
  this includes a subdirectory of a normal clone, so `cwd` is the clone root there. Outside a git
  repository there is no chdir. EnterWorktree with `path` enters an existing worktree and fires no
  WorktreeCreate.
- Subagent isolation and the bridge: no chdir. `cwd` is the calling context's current cwd, which
  can be a subdirectory, a linked worktree, or the worktree of an enclosing isolated subagent.
- `--worktree --tmux`: no chdir. `cwd` is the launch directory.

| Launch directory                     | `--worktree`  | EnterWorktree | Subagent isolation |
|--------------------------------------|---------------|---------------|--------------------|
| Normal clone root                    | clone root    | clone root    | clone root         |
| Subdirectory of a normal clone       | subdirectory  | clone root    | subdirectory       |
| Linked worktree of a normal clone    | main checkout | main checkout | linked worktree    |
| Linked worktree of a bare repository | bare repo dir | bare repo dir | linked worktree    |

The canonical root is defined in `PROJECT_FILES_AND_STATE.md`, Terms. For a linked worktree of a
bare repository it is the bare repository directory itself, so for `project/project.git`,
`--worktree` and EnterWorktree hand the hook `cwd: "…/project/project.git"`, while a subagent hands
it the launching worktree.

## What the hook replaces

When any WorktreeCreate hook is configured, it replaces git worktree creation entirely. The git
path (`.claude/worktrees/<name>`, branch `worktree-<name>`, `worktree.baseRef`, `.worktreeinclude`,
`sparsePaths`, `symlinkDirectories`, PR fetch) runs only when no hook is configured.

"Configured" means a settings WorktreeCreate hook is in the hooks snapshot, or a loaded
function-hook module subscribes to `classic.WorktreeCreate` (the subscription test builds the name
as `` `classic.${…}` ``). All four creators (`--worktree`, `--worktree --tmux`, EnterWorktree, agent
isolation) test that same predicate. The `--worktree` "not a git repository" pre-check
(`Can only use --worktree in a git repository`) reads only the settings hooks. `--worktree` also
registers plugin worktree hooks before creating the worktree, and logs
`plugin worktree hooks not registered before creating the worktree` when it cannot.

The git creators share one post-creation setup step, run only for a newly created worktree and
never on the hook path. It copies `settings.local.json`, rewrites a relative `core.hooksPath` from
the main repository as an absolute path in the worktree (`Configured worktree to use hooks from
main repository`), creates the `symlinkDirectories` links, and copies `.worktreeinclude` files.

- Branch name: the git path names the branch `worktree-<name>` with `/` replaced by `+`, and puts
  the directory at `.claude/worktrees/<name>` with the same replacement. Neither value is computed
  or passed on the hook path. A hook that wants the same convention must derive it from `name`.
- `worktree.baseRef` is read only inside the git creator. Nothing resolves a base ref on the hook
  path, and no field or env var carries it to the hook. A hook that wants to honor it must read
  settings itself.
- `--worktree <PR#>` on the hook path sends only `name: "pr-<N>"`. No fetch happens.

After the hook returns, the path is screened before use. It is rejected if it has `.` or `..`
segments (`hook emitted a path with dot segments`), or if a component below the repository root is a
symlink or cannot be verified. The agent creator also requires an existing directory
(`returned a path that is not a directory`). For `--worktree`, a path that does not exist fails when
the CLI tries to enter it, with an error telling the hook to print the directory it created as the
last line of its stdout.

## `worktree.baseRef`

Schema: an optional `"fresh"` / `"head"` enum, described as "Which ref new worktrees branch from.
'fresh' (default) branches from origin/<default-branch> … 'head' branches from your current local
HEAD … Applies to --worktree, EnterWorktree, and agent isolation." `/config` exposes it as
`Worktree base ref` (`worktreeBaseRef`), defaulting to `fresh`.

The git creator branches from local HEAD when the caller passes `fromHead`, or when there is no PR
and `baseRef` is `head`. Otherwise it fetches and uses `origin/<default branch>` (`origin/HEAD` when
no default branch is known). If that fetch fails, it logs `basing worktree on local HEAD` and
branches from local HEAD.

## WorktreeRemove payload

One builder: the common fields plus `hook_event_name: "WorktreeRemove"` and `worktree_path`, where
`worktree_path` is the path WorktreeCreate returned. It runs only for hook-created worktrees.
Git-created worktrees are removed with git, and the hook never fires for them.

The gate is the `hookBased` flag on the worktree record, not whether a WorktreeRemove hook is
configured. Only the hook branches of the creators set `hookBased: true`, and the record carries it
through to background jobs as `worktreeHookBased`. The executor has two callers, the session remover
and the agent/job remover, and each reaches it only inside an `if (hookBased)` branch. The
stale-worktree cleanup (`stale_cleanup`), the job retention sweep (`job_retention_sweep`) and the
workflow tool (`workflow_tool`) call the agent/job remover with `hookBased` false, so they never
fire it.

So a configuration with only a WorktreeRemove hook never fires it: every worktree is git-created,
and every removal path (exit dialog, ExitWorktree `action: "remove"`, subagent cleanup, background
session delete) uses git. The reverse case, a hook-created worktree with no WorktreeRemove hook,
falls back to `git worktree remove` for session worktrees and keeps agent and job worktrees, with
the log reason `no WorktreeRemove hook is enabled here (hooks are disabled, or the repo defines
only WorktreeCreate)`.

Executor outcomes:

| Situation                                          | Outcome          |
| -------------------------------------------------- | ---------------- |
| No settings or function WorktreeRemove hook        | `not_configured` |
| Configured, but no hook ran (untrusted, no match)  | `failed`         |
| All hooks succeeded                                | `removed`        |
| All succeeded, workspace untrusted, directory kept | `failed`         |
| A hook failed and the directory is gone            | `removed`        |
| A hook failed and the directory is still present   | `failed`         |

The executor runs the person's own hooks even in an untrusted workspace. When the workspace is not
trusted and the directory survives, the summary is
`left the tree in place (workspace not trusted, so the folder's own hooks did not run)`. A failed
hook with nothing left at the path logs `… but nothing is left at <path> — treating it as removed`.

## When WorktreeRemove fires

### Session worktrees (`--worktree`, EnterWorktree)

Only two paths remove a session worktree: the interactive exit dialog and ExitWorktree with
`action: "remove"`. Print mode (`-p`) renders no exit dialog, so a `--worktree` session started
with `-p` keeps its worktree, and WorktreeRemove does not fire unless the model calls ExitWorktree.

ExitWorktree with `action: "remove"` refuses when it cannot verify the worktree's state, and asks
the model to confirm with the user and re-invoke with `discard_changes: true`. Its state check needs
`originalHeadCommit`, which a hook-created worktree never has, so removing a hook-created worktree
through ExitWorktree always takes `discard_changes: true`.

`/exit` shows the dialog whenever the session state holds an active worktree, except in a
background session (`bg`), which exits without it. The dialog (`WorktreeExitDialog`) then does
the following:

1. Entered an existing worktree (`enteredExisting`): returns to the original cwd and leaves the
   worktree in place. No check, no prompt.
2. Filter-config screen: reads the worktree's local git config. If a filter driver is unsafe or
   unrepresentable, it runs `git rev-parse --git-dir` instead of a status, and the worktree is
   treated as unverifiable (`?` as the changed file, so the dialog asks).
3. Otherwise runs this in the worktree, and each output line is one changed file:

       git -c core.hooksPath=/dev/null -c core.fsmonitor= --no-optional-locks \
         status --porcelain --untracked-files=normal --ignore-submodules=dirty

4. If git exits non-zero, the worktree is treated as unverifiable (asks) unless one of two
   exemptions applies. If the directory is gone (ENOENT), a git-created worktree exits with
   `Worktree at … is no longer accessible`, and a hook-created one counts as clean. If the
   worktree is hook-created and no `.git` exists at its realpath or any ancestor, it also counts
   as clean. A non-git checkout (SVN, Perforce, plain directory) is therefore clean, not
   unverifiable.
5. Submodule scan, only after a successful status, with a 5-second deadline: tracked or untracked
   changes inside a submodule add to the changed files (`changes inside submodule …`). A nested
   repository that is not a configured submodule, a gitdir outside the worktree, nested submodules,
   too many submodules, a timeout or a read error count as `unverifiable`, which forces the prompt.
6. Commit count. A git-created worktree counts commits since `originalHeadCommit`, the worktree's
   starting commit recorded by the git creator. The hook creator never records `originalHeadCommit`,
   so a hook-created worktree gets `0` only when one of the step 4 exemptions applied (directory
   gone, or no `.git`); otherwise its count is unknown (`null`).
7. Silent removal requires all of: no changed files, commit count exactly `0`, no user-set title,
   and no unverifiable submodule. The title is `currentSessionTitle`, set by `/rename` and `--name`;
   the AI-generated title is a separate field and does not count. A hook-created worktree with an
   unknown commit count always goes to the prompt.
8. Anything else asks keep or remove. There is no path that keeps silently, apart from step 1 and
   background sessions.

Silent removal of a hook-created worktree runs inline: it fires WorktreeRemove, and prints
`Worktree removed (no changes)` or `Worktree could not be removed — kept at …`. A git-created clean
worktree is instead handed to the shutdown sequence and removed with git after the session exits.
Choosing Remove in the prompt follows the same split.

The session remover (`No WorktreeRemove hook configured; falling back`) fires WorktreeRemove for a
hook-created worktree. `removed` ends there. `not_configured` falls through to the same lock check
and `git worktree remove` that git-created worktrees use, run from the original cwd's git root.
`failed` keeps the worktree and logs `WorktreeRemove hook <summary>; kept worktree at: <path>`.

Consequences of steps 4, 6 and 7 for hook-created worktrees:

- A hook worktree that is a git checkout always asks at `/exit`, even with a clean status and no
  commits, because its commit count is unknown.
- A non-git hook worktree is removed without asking unless the session has a user-set title.
  Uncommitted VCS changes in it are invisible to the check.
- The `!1`-guarded changeset check (`originalChangeset`, `hook worktree status check for`) is dead
  in the public build: the changeset helpers are stubs that return `undefined`/`null`.

### Subagent worktrees (`isolation: "worktree"`)

The cleanup closure that runs when the subagent finishes keeps every hook-based worktree. It returns
early with `Hook-based agent worktree kept at:` unless the creator recorded both a `baseChangeset`
and a vetted real path, and the public build's `baseChangeset` helper is a stub that returns
`undefined`. The result is identical in interactive and print mode, with or without changes.
WorktreeRemove does not fire, and the tool result reports the kept `worktreePath` with no branch.

Git-created agent worktrees are different: when clean, they are removed with git (no hook), and when
dirty, or still the working directory of another live task, they are kept.

### Background sessions and jobs

Deleting a background session (agent view, `claude rm`) removes a hook-based job worktree through
the agent/job remover, which fires WorktreeRemove. A hook worktree with files left in it is kept
(`only an explicit discard may dispatch the remove hook`) until an explicit confirmation in agent
view or `claude rm --force-remove-worktree <digest>`. That forced delete (`job_delete_force_remove`)
also removes the directory itself when the WorktreeRemove hook is missing or failed. The agent/job
remover refuses a hook removal when the stored path, or a component of it, is a symlink, or when its
real path changed since creation.

The bridge (Remote Control) cleanup takes the same route for its `bridge-<id>` worktrees, and keeps
a worktree with uncommitted changes or commits (`[bridge:worktree] kept …`).

## Cleaning up kept subagent worktrees from hooks

Because the subagent cleanup closure keeps hook-created worktrees, cleanup falls to user hooks.

### Identity and paths available to the hooks

The worktree is named `agent-<agentId>`. The agent id comes from the id generator `a<16 hex>`, and
the brand cast applied to it is the identity. The id itself never carries `agent-`. That prefix is
added only for the worktree name and the transcript file `agent-<agentId>.jsonl`. `agent-a<16 hex>`
is also on the list of worktree names Claude Code reserves.

The generator takes an optional label and then returns `a<label>-<16 hex>`. The label is stripped
to `[\w-]` and capped at 63 characters, and the validator accepts both shapes. The Agent tool
calls it with no label. In-process teammates pass their name (`a<name>-<16 hex>`), and internal
forked agents pass a purpose label such as `extract_memories`. A hook that parses `agent_id`
should accept both shapes.

The Agent tool generates the id once per launch. The same id is:

- `agent_id` in SubagentStart and SubagentStop, and in every tool hook fired inside the subagent
- `agentId` in the Agent tool result, including `async_launched`, because the task id equals the
  agent id

`agent-<agent_id>` therefore reproduces the WorktreeCreate `name`. Neither SubagentStart nor
SubagentStop carries a worktree path field.

`cwd` in both events is the subagent's working directory. The Agent tool runs the subagent with its
project cwd set to the explicit `cwd` argument, else the worktree path, so SubagentStart sees the
worktree root. SubagentStop sees the agent's current directory, which can be a subdirectory of the
worktree after a Bash `cd`.

SubagentStart: the common fields plus `agent_id` and `agent_type`. It fires on every subagent run,
including resumes and teammate work cycles, after the worktree exists.

SubagentStop: built from the subagent's own context, so `permission_mode`, `agent_type` and
`effort` are present. On top of those it carries:

- `stop_hook_active` and `last_assistant_message`
- `agent_id` and `agent_type`
- `agent_transcript_path` (`agent-<agentId>.jsonl`)
- `background_tasks` and `session_crons`, which cover the whole session

### Ordering

The Agent tool hands the subagent stream to the task runner. On every exit (completion, error,
kill, stall watchdog), the runner calls the worktree cleanup closure only after the stream has
ended. The tool result or task notification is built after that. So SubagentStop always fires
before the cleanup closure and before the parent receives the result.

- Normal end: SubagentStop fires from the query loop's blockable turn end. Exit code 2 re-invokes
  the model, and the subagent keeps working in the worktree, with `stop_hook_active: true` on the
  next attempt, up to `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` (default 8).
- A turn ended by a tool result: SubagentStop fires from the non-blockable path (`[end-turn] Stop
  hook block discarded`).
- Interrupted or errored query: the `SubagentStop` stage of the runAgent cleanup fires it
  (`SubagentStop on interrupted query failed`). This call passes a 5-second default timeout, which
  a per-hook `timeout` overrides. `last_assistant_message` is absent.
- Max turns or a hook's `preventContinuation`: only the `turn_end_reactions` stage runs, which
  dispatches session function hooks only (`Turn-end reaction hook block discarded`). A settings
  `command` SubagentStop hook does not fire.

SubagentStop marks the end of one run, not the end of the agent:

- A background agent with live background children parks and wakes for further turns in the same
  worktree (`backgrounded owner awaits keepalive, resume pending`).
- SendMessage resumes a stopped agent from the `worktreePath` stored in its metadata. If that
  directory is gone, resume falls back to another directory only when the session's isolation fences
  cover it; otherwise it fails with `This agent cannot be resumed: its worktree …`, ending
  `the fallback directory is not covered by the session's isolation fences.`
- An agent that keeps running after its worktree disappears has its Bash refused with `the
  isolation worktree appears to have been removed`.

At a normal-end SubagentStop, the subagent's background shells and monitors are still running. The
`shellTasks` and `nonShellMonitors` stages kill them later, and the keepalive case skips those
stages.

### Locks

Only git-created worktrees are locked, with the reason
`claude agent <name> (pid <pid>[ start <time>])` for an agent worktree and `claude session …` for a
session worktree. Under a feature flag the lock marker is written straight into
`<commondir>/worktrees/<id>/locked` instead of running `git worktree lock`. The hook-created branch
never locks and records no git root. It runs one `git rev-parse HEAD` in the worktree at creation,
and the cleanup closure runs no git command on it. A hook can run `git status` in a hook-created
worktree at any point.

### PostToolUse on the Agent tool

PostToolUse receives the tool result data as `tool_response`.

- Foreground, completed (including recovered errors): `{ status: "completed", …, worktreePath }`.
  The `worktreePath` comes from the cleanup closure and is always present for a kept hook worktree.
  There is no `worktreeBranch`. The model sees it as a `worktreePath: <path>` line in the tool
  result text.
- Foreground, cancelled by the user: the tool throws, so PostToolUseFailure fires with no path.
- `run_in_background`, or a foreground agent backgrounded mid-run:
  `{ status: "async_launched", agentId, … }` at launch, with no `worktreePath`. Completion arrives
  later as a task notification whose text carries
  `<worktree><worktreePath>…</worktreePath></worktree>`, assembled from tag-name constants. That
  notification reaches the model, not a hook event.
- Teammates: the teammate spawn returns `teammate_spawned` before the isolation code runs, so
  teammates never get an `agent-<id>` worktree.

## Published docs vs. source

Checked against `/en/hooks`, `/en/worktrees` and `/en/agent-view` via the `claude-code-docs` MCP.

- WorktreeCreate input: the docs list only `name`, which matches the source.
- WorktreeRemove for subagents: the docs say a subagent's hook-created worktree is kept and the hook
  does not run, which matches the source.
- The docs say WorktreeRemove fires without a prompt when you exit an unnamed worktree session and
  "Claude Code finds no changed or untracked files". That holds for a non-git hook worktree. A hook
  worktree that is a git checkout always prompts, because its commit count is unknown.
- The docs' "named" session is the user-set title (`/rename`, `--name`); the AI-generated title does
  not stop silent removal. This is undocumented.
- Hook `cwd` on `--worktree` and EnterWorktree is the canonical git root, which for a bare-repo
  layout is the bare repository directory. This is undocumented.
