# Worktree hooks: WorktreeCreate / WorktreeRemove lifecycle

Verified against: cli.prettier.js 2.1.288 (2026-10-03)

How Claude Code builds the WorktreeCreate and WorktreeRemove hook payloads, which entry points
fire them, what `cwd` the hook receives, how `worktree.baseRef` interacts with a hook, and when a
hook-created worktree is (and is not) removed. `HOOKS.md` holds the event inventory; this doc
covers the worktree lifecycle around those two events.

## Re-location recipes

| Target                         | Grep anchor                                           |
|--------------------------------|-------------------------------------------------------|
| WorktreeCreate payload         | `hook_event_name: "WorktreeCreate"` (one literal)     |
| WorktreeRemove payload         | `hook_event_name: "WorktreeRemove"` (one literal)     |
| Common input fields            | `scratchpad_dir:` beside `transcript_path:`           |
| Session worktree creator       | `Created hook-based worktree at:`                     |
| Agent worktree creator         | `Created hook-based agent worktree at:`               |
| `--worktree` chdir             | `worktree_resolved_to_main_repo`                      |
| `--worktree --tmux` path       | `"swift", "bright", "calm", "keen", "bold"`           |
| Subagent cleanup closure       | `Hook-based agent worktree kept at:`                  |
| Session worktree remove        | `No WorktreeRemove hook configured; falling back`     |
| Interactive exit dialog        | `Worktree removed (no changes)`, `WorktreeExitDialog` |
| Exit-dialog status command     | `"--ignore-submodules=dirty",` in a `status` array    |
| Exit-dialog submodule scan     | `submodule inspection deadline`                       |
| User-set vs AI session title   | `currentSessionTitle` vs `currentSessionAiTitle`      |
| Agent/job remover              | `removeAgentWorktree: kept hook-based worktree`       |
| Remove-only config message     | `the repo defines only WorktreeCreate`                |
| Git post-creation setup        | `Configured worktree to use hooks from main`          |
| Git branch name                | `` `worktree-${`` (`/` in the name becomes `+`)       |
| `worktree.baseRef` schema      | `Which ref new worktrees branch from.`                |
| Canonical git root             | reads `commondir`, compares its basename with `.git`  |
| SubagentStop, interrupted run  | `SubagentStop on interrupted query failed`            |
| Agent id generator             | `` `a${t}-${s}` : `a${s}` `` (16 hex chars)           |
| Resume with a missing worktree | `This agent cannot be resumed: its worktree`          |

## WorktreeCreate payload

There is exactly one builder. Its input is the common fields plus `hook_event_name` and `name`:

    { ...common, hook_event_name: "WorktreeCreate", name }

The common-fields builder is called with only the session and the current cwd, so
`permission_mode`, `agent_id` and `effort` are always absent. What a command hook receives:
`session_id`, `transcript_path`, `cwd`, `hook_event_name`, `name`, plus `prompt_id`,
`scratchpad_dir` and `agent_type` when they have a value.

No other worktree field exists. The Zod input schema
(`hook_event_name: x("WorktreeCreate"), name: o()`) and the SDK `WorktreeCreateHookInput` type
declare only `name`. `worktree_name`, `base_path`, `base_ref` and `repo_root` appear nowhere in the
bundle, under any flag. `pr_number` appears only in unrelated GitHub and PR-subscription payloads,
and no hook payload carries a `branch` field. The hook process env adds no worktree-specific
variable either; it gets the usual `CLAUDE_PROJECT_DIR` and the session vars (see `HOOKS.md`, Hook
process environment).

### `name` per entry point

| Entry point                      | `name` value                                          |
|----------------------------------|-------------------------------------------------------|
| `claude --worktree <name>`       | `<name>` as given                                     |
| `claude --worktree` (no name)    | the session's plan slug                               |
| `claude --worktree <PR#/URL>`    | `pr-<N>`                                              |
| `--worktree --tmux` (no name)    | `<adjective>-<noun>-<4 base36>`, e.g. `bold-oak-a3f2` |
| EnterWorktree tool               | its `name` argument, else the plan slug               |
| Subagent `isolation: "worktree"` | `agent-<agentId>`, e.g. `agent-a321c56d3b6ffa445`     |
| Remote Control bridge            | `bridge-<id>`                                         |
| Background session               | via EnterWorktree, called before the first edit       |

Every name passes the slug validator first (`Invalid worktree name`): `/`-separated segments of
letters, digits, `.`, `_`, `-`, with no `.`/`..` segments and no `.git` segment.

### Hook `cwd`

`cwd` is the process cwd at the moment the hook fires. The entry points differ in whether they
chdir before calling it:

- `--worktree`: when the launch directory is inside a linked worktree, the CLI logs
  `worktree_resolved_to_main_repo` and chdirs to the canonical git root first.
- EnterWorktree (and so background sessions): chdirs to the canonical git root whenever it differs
  from the current cwd, and restores the cwd if creation fails.
- Subagent isolation and the bridge: no chdir. `cwd` is the launching session's current cwd.
- `--worktree --tmux`: no chdir. `cwd` is the launch directory.

The canonical git root follows a linked worktree's `.git` file to its `gitdir`, then to
`commondir`. If the common dir's basename is `.git`, the root is its parent (the main checkout).
Otherwise the common dir is a bare repository, and the root is the bare repository directory
itself. So for a linked worktree of `project/project.git`, `--worktree` and EnterWorktree hand the
hook `cwd: "…/project/project.git"`, while a subagent hands it the launching worktree.

A relative path printed by the hook resolves against that same `cwd`.

## What the hook replaces

When any WorktreeCreate hook is configured, it replaces git worktree creation entirely. The git
path (`.claude/worktrees/<name>`, branch `worktree-<name>`, `worktree.baseRef`, `.worktreeinclude`,
`sparsePaths`, `symlinkDirectories`, PR fetch) runs only when no hook is configured.

"Configured" means a settings WorktreeCreate hook is in the hooks snapshot, or a loaded
function-hook module subscribes to `classic.WorktreeCreate`. All four creators (`--worktree`,
`--worktree --tmux`, EnterWorktree, agent isolation) test that same predicate. The `--worktree`
"not a git repository" pre-check reads only the settings hooks.

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

After the hook returns, the path is screened. It is rejected if it contains `.`/`..` segments or
passes through a symlink below the repository root, and it must be an existing directory.

## `worktree.baseRef`

Schema: `j(["fresh", "head"]).optional()`, described as "Which ref new worktrees branch from.
'fresh' (default) branches from origin/<default-branch> … 'head' branches from your current local
HEAD … Applies to --worktree, EnterWorktree, and agent isolation." `/config` exposes it as
`Worktree base ref` (`worktreeBaseRef`), defaulting to `fresh`.

The git creator branches from local HEAD when the caller passes `fromHead`, or when there is no PR
and `baseRef === "head"`. Otherwise it uses `origin/<default branch>`, falling back to `HEAD`.

History:

- 2.1.119: setting absent.
- 2.1.133: added with default `fresh` (changelog). Per the changelog, EnterWorktree had branched
  from local HEAD since 2.1.128, so the `fresh` default moved EnterWorktree back to
  `origin/<default>`.
- 2.1.138 through 2.1.288 (every local snapshot): `fresh` default, `["fresh", "head"]` enum, no
  further default change.
- 2.1.208 (docs): `fresh` began fetching `origin/HEAD` when the last fetch is over 24 hours old.

## WorktreeRemove payload

One builder: `{ ...common, hook_event_name: "WorktreeRemove", worktree_path }`, where
`worktree_path` is the path WorktreeCreate returned. It runs only for hook-created worktrees.
Git-created worktrees are removed with git, and the hook never fires for them.

The gate is the `hookBased` flag on the worktree record, not whether a WorktreeRemove hook is
configured. Only the hook branches of the creators set `hookBased: true`, and the record carries
it through to background jobs as `worktreeHookBased`. The executor has two callers, the session
remover and the agent/job remover, and each reaches it only inside an `if (hookBased)` branch. The
stale-worktree cleanup, the job retention sweep and the workflow tool call the agent/job remover
with `hookBased` false, so they never fire it.

So a configuration with only a WorktreeRemove hook never fires it: every worktree is git-created,
and every removal path (exit dialog, ExitWorktree `action: "remove"`, subagent cleanup, background
session delete) uses git. The reverse case, a hook-created worktree with no WorktreeRemove hook,
falls back to `git worktree remove` for session worktrees and keeps agent and job worktrees, with
the log reason `no WorktreeRemove hook is enabled here (hooks are disabled, or the repo defines
only WorktreeCreate)`.

Outcomes: no hooks matched gives `not_configured`, and the caller falls back to
`git worktree remove`. A non-zero exit with the directory still present gives `failed`, and the
worktree is kept. A non-zero exit with the directory gone counts as removed.

## When WorktreeRemove fires

### Session worktrees (`--worktree`, EnterWorktree)

Only two paths remove a session worktree: the interactive exit dialog and ExitWorktree with
`action: "remove"`. Print mode (`-p`) renders no exit dialog, so a `--worktree` session started
with `-p` keeps its worktree, and WorktreeRemove does not fire unless the model calls ExitWorktree.

`/exit` shows the dialog whenever the session state holds an active worktree, except in a
background session (`bg`), which exits without it. The dialog (`WorktreeExitDialog`) then does
the following:

1. Entered an existing worktree (`enteredExisting`): returns to the original cwd and leaves the
   worktree in place. No check, no prompt.
2. Filter-config screen: reads the worktree's local git config. If a filter driver is unsafe or
   unrepresentable, it runs `git rev-parse --git-dir` instead of a status, and the worktree is
   treated as unverifiable (`?` as the changed file, so the dialog asks).
3. Otherwise runs `git -c core.hooksPath=/dev/null -c core.fsmonitor= status --porcelain
   --untracked-files=normal --ignore-submodules=dirty` in the worktree. Each output line is one
   changed file.
4. If git exits non-zero, the worktree is treated as unverifiable (asks) unless one of two
   exemptions applies. If the directory is gone (ENOENT), a git-created worktree exits with
   `Worktree at … is no longer accessible`, and a hook-created one counts as clean. If the
   worktree is hook-created and no `.git` exists at its realpath or any ancestor, it also counts
   as clean. A non-git checkout (SVN, Perforce, plain directory) is therefore clean, not
   unverifiable.
5. Submodule scan, only after a successful status, with a 5-second deadline: tracked or untracked
   changes inside a submodule add to the changed files (`changes inside submodule …`). A nested
   repository that is not a configured submodule, a gitdir outside the worktree, a timeout or a
   read error count as `unverifiable`, which forces the prompt.
6. Commit count starts at `0` for a hook-created worktree and `null` for a git-created one. Only
   when the state has `originalHeadCommit` does it run `git rev-list --count
   <originalHeadCommit>..HEAD`, with a failure giving `null`. The git creator records
   `originalHeadCommit` as the worktree's starting commit. The hook creator never sets it, so a
   hook-created worktree always counts 0 commits.
7. Silent removal requires all of: no changed files, commit count exactly `0`, no user-set title,
   and no unverifiable submodule. The title is `currentSessionTitle`, set by `/rename` and
   `--name`; the AI-generated title is a separate field and does not count.
8. Anything else asks keep or remove. There is no path that keeps silently, apart from step 1 and
   background sessions.

Silent removal of a hook-created worktree runs inline: it fires WorktreeRemove, and prints
`Worktree removed (no changes)` or `Worktree could not be removed — kept at …`. A git-created
clean worktree is instead handed to the shutdown sequence and removed with `git worktree remove
--force` after the session exits. Choosing Remove in the prompt follows the same split.

The session remover (`No WorktreeRemove hook configured; falling back`) fires WorktreeRemove for a
hook-created worktree. `removed` ends there. `not_configured` falls through to the same lock check
and `git worktree remove --force <path>` that git-created worktrees use, run from the original
cwd's git root. `failed` keeps the worktree and reports it could not be removed.

Consequences of steps 4 and 6 for hook-created worktrees:

- A hook worktree that is a git checkout with new commits and a clean status is removed without
  asking. A WorktreeRemove hook that must not lose unpushed commits has to check for them itself.
- A non-git hook worktree is always removed without asking unless the session has a user-set
  title. Uncommitted VCS changes in it are invisible to the check.
- The `!1`-guarded changeset check (`originalChangeset`, `hook worktree status check for`) is dead
  in the public build: the changeset helpers are stubs that return `undefined`/`null`.

### Subagent worktrees (`isolation: "worktree"`)

The cleanup closure that runs when the subagent finishes keeps every hook-based worktree. It
returns early with `Hook-based agent worktree kept at:` unless the creator recorded a
`baseChangeset`, and the public build's `baseChangeset` helper is a stub that returns `undefined`.
The result is identical in interactive and print mode, with or without changes. WorktreeRemove
does not fire, and the tool result reports the kept `worktreePath` with no branch.

Git-created agent worktrees are different: when clean, they are removed with git (no hook), and
when dirty, they are kept.

### Background sessions and jobs

Deleting a background session (agent view, `claude rm`) removes a hook-based job worktree through
the agent/job remover, which fires WorktreeRemove. A worktree with files left in it is removed only
after an explicit confirmation in agent view. The bridge (Remote Control) cleanup takes the same
route for its `bridge-<id>` worktrees.

## Cleaning up kept subagent worktrees from hooks

Because the subagent cleanup closure keeps hook-created worktrees, cleanup falls to user hooks.

### Identity and paths available to the hooks

The worktree is named `agent-<agentId>`. The agent id comes from the id generator `a<16 hex>`,
and the brand cast applied to it is the identity. The same id is:

- `agent_id` in SubagentStart and SubagentStop
- `agentId` in the Agent tool result, including `async_launched`, because the task id equals the
  agent id

`agent-<agent_id>` therefore reproduces the WorktreeCreate `name`. Neither SubagentStart nor
SubagentStop carries a worktree path field.

`cwd` in both events is the subagent's working directory. The Agent tool runs the subagent inside a
cwd scope set to the worktree path (`An(ft, …)` → `e.run({ cwd })`), so SubagentStart sees the
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
  next attempt, up to `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`.
- A turn ended by a tool result: SubagentStop fires from the non-blockable path (`[end-turn] Stop
  hook block discarded`).
- Interrupted or errored query: the `SubagentStop` stage of the runAgent cleanup fires it
  (`SubagentStop on interrupted query failed`). This call passes a 5-second default timeout, which
  a per-hook `timeout` overrides. `last_assistant_message` is absent.
- Max turns or `preventContinuation`: only `turn_end_reactions` runs, which dispatches session
  function hooks only. A settings `command` SubagentStop hook does not fire.

SubagentStop marks the end of one run, not the end of the agent:

- A background agent with live background children parks and wakes for further turns in the same
  worktree (`backgrounded owner awaits keepalive, resume pending`).
- SendMessage resumes a stopped agent from the `worktreePath` stored in its metadata. If that
  directory is gone, resume fails with `This agent cannot be resumed: its worktree no longer
  exists` unless the session's worktree fences cover the fallback directory.
- An agent that keeps running after its worktree disappears has its Bash refused with `the
  isolation worktree appears to have been removed`.

At a normal-end SubagentStop, the subagent's background shells and monitors are still running. The
`shellTasks` and `nonShellMonitors` stages kill them later, and the keepalive case skips those
stages.

### Locks

Only git-created agent worktrees are locked (`git worktree lock --reason "claude agent <name> (pid
…)"`). The hook-created branch never locks, records no git root, and the cleanup closure runs no
git command on it. A hook can run `git status` in a hook-created worktree at any point.

### PostToolUse on the Agent tool

PostToolUse receives the tool result data as `tool_response`.

- Foreground, completed (including recovered errors): `{ status: "completed", …, worktreePath }`.
  The `worktreePath` comes from the cleanup closure and is always present for a kept hook
  worktree. There is no `worktreeBranch`.
- Foreground, cancelled by the user: the tool throws, so PostToolUseFailure fires with no path.
- `run_in_background`, or a foreground agent backgrounded mid-run: `{ status: "async_launched",
  agentId, … }` at launch, with no `worktreePath`. Completion arrives later as a task notification
  whose text carries `<worktree><worktreePath>…</worktreePath></worktree>`. That notification
  reaches the model, not a hook event.
- Teammates: the teammate spawn returns `teammate_spawned` before the isolation code runs, so
  teammates never get an `agent-<id>` worktree.

## Published docs vs. source (2.1.288)

Checked against `/en/hooks` and `/en/worktrees` via the `claude-code-docs` MCP.

- WorktreeCreate input: the docs list only `name`, which matches the source. The docs do not list
  `worktree_name`, `base_path`, `branch` or `base_ref`.
- WorktreeRemove "fires when a subagent with `isolation: "worktree"` finishes": not for
  hook-created worktrees in 2.1.288. The cleanup closure keeps every one of them.
- The docs say WorktreeRemove fires when "you exit a `--worktree` session and choose to remove
  it". The undocumented part is that a clean, untitled hook worktree is removed without a choice,
  with commits ignored, and that a non-git hook worktree always counts as clean.
- Hook `cwd` on `--worktree` and EnterWorktree is the canonical git root, which for a bare-repo
  layout is the bare repository directory. This is undocumented.

## Per-release appendix

- 2.1.288: verified. Payloads, entry points, cwd handling, the `baseRef` default and the removal
  paths as described above.
- 2.1.288: added hook-driven cleanup of kept subagent worktrees: SubagentStart/Stop identity and
  `cwd`, ordering against the cleanup closure, coverage gaps (max turns), locks, and the
  PostToolUse(Agent) `tool_response` shapes.
- 2.1.288: corrected the exit dialog. A non-git hook worktree counts as clean, not as changed
  (the no-`.git`-ancestor exemption is present in 2.1.283 and 2.1.286 too). Added the full
  decision order, the filter-config screen, submodule `unverifiable`, and the inline vs.
  post-exit removal split.
- 2.1.288: added the `hookBased` gate on WorktreeRemove (a remove-only config never fires), the
  function-hook half of the "hook configured" predicate, and the git-only post-creation setup.
