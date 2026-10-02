# Worktree hooks: WorktreeCreate / WorktreeRemove lifecycle

Verified against: cli.prettier.js 2.1.288 (2026-10-02)

How Claude Code builds the WorktreeCreate and WorktreeRemove hook payloads, which entry points
fire them, what `cwd` the hook receives, how `worktree.baseRef` interacts with a hook, and when a
hook-created worktree is (and is not) removed. `HOOKS.md` holds the event inventory; this doc
covers the worktree lifecycle around those two events.

## Re-location recipes

| Target                    | Grep anchor                                           |
|---------------------------|-------------------------------------------------------|
| WorktreeCreate payload    | `hook_event_name: "WorktreeCreate"` (one literal)     |
| WorktreeRemove payload    | `hook_event_name: "WorktreeRemove"` (one literal)     |
| Common input fields       | `scratchpad_dir:` beside `transcript_path:`           |
| Session worktree creator  | `Created hook-based worktree at:`                     |
| Agent worktree creator    | `Created hook-based agent worktree at:`               |
| `--worktree` chdir        | `worktree_resolved_to_main_repo`                      |
| `--worktree --tmux` path  | `"swift", "bright", "calm", "keen", "bold"`           |
| Subagent cleanup closure  | `Hook-based agent worktree kept at:`                  |
| Session worktree remove   | `No WorktreeRemove hook configured; falling back`     |
| Interactive exit dialog   | `Worktree removed (no changes)`, `WorktreeExitDialog` |
| Agent/job remover         | `removeAgentWorktree: kept hook-based worktree`       |
| Git branch name           | `` `worktree-${`` (`/` in the name becomes `+`)       |
| `worktree.baseRef` schema | `Which ref new worktrees branch from.`                |
| Canonical git root        | reads `commondir`, compares its basename with `.git`  |

## WorktreeCreate payload

There is exactly one builder. Its input is the common fields plus `hook_event_name` and `name`:

    { ...common, hook_event_name: "WorktreeCreate", name }

The common-fields builder is called with only the session and the current cwd, so
`permission_mode`, `agent_id` and `effort` are always absent. What a command hook receives:
`session_id`, `transcript_path`, `cwd`, `hook_event_name`, `name`, plus `prompt_id`,
`scratchpad_dir` and `agent_type` when they have a value.

No other worktree field exists. The Zod input schema
(`hook_event_name: x("WorktreeCreate"), name: o()`) and the SDK `WorktreeCreateHookInput` type
declare only `name`. `worktree_name`, `base_path`, `branch` and `base_ref` appear nowhere in the
bundle, under any flag. The hook process env adds no worktree-specific variable either; it gets
the usual `CLAUDE_PROJECT_DIR` and the session vars (see `HOOKS.md`, Hook process environment).

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

Outcomes: no hooks matched gives `not_configured`, and the caller falls back to
`git worktree remove`. A non-zero exit with the directory still present gives `failed`, and the
worktree is kept. A non-zero exit with the directory gone counts as removed.

## When WorktreeRemove fires

### Session worktrees (`--worktree`, EnterWorktree)

Only two paths remove a session worktree: the interactive exit dialog and ExitWorktree with
`action: "remove"`. Print mode (`-p`) renders no exit dialog, so a `--worktree` session started
with `-p` keeps its worktree, and WorktreeRemove does not fire unless the model calls ExitWorktree.

The interactive exit dialog, for a hook-based worktree:

1. Runs `git status --porcelain` (plus a submodule scan) inside the worktree. If git fails there,
   for example in a non-git checkout, the dialog treats the worktree as having changes.
2. Counts commits as 0. A hook-based session worktree records no starting commit, so commits made
   in it are not counted.
3. If there are no changes and the session has no user-set title (`/rename`, `--name`), it removes
   the worktree without asking: WorktreeRemove fires and `Worktree removed (no changes)` prints.
4. Otherwise it asks keep or remove. Remove fires WorktreeRemove. Keep leaves everything in place.

Step 2 means a hook worktree that is a git checkout with new commits and a clean status is removed
without asking. A WorktreeRemove hook that must not lose unpushed commits has to check for them
itself.

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

## Published docs vs. source (2.1.288)

Checked against `/en/hooks` and `/en/worktrees` via the `claude-code-docs` MCP.

- WorktreeCreate input: the docs list only `name`, which matches the source. The docs do not list
  `worktree_name`, `base_path`, `branch` or `base_ref`.
- WorktreeRemove "fires when a subagent with `isolation: "worktree"` finishes": not for
  hook-created worktrees in 2.1.288. The cleanup closure keeps every one of them.
- The docs say WorktreeRemove fires when "you exit a `--worktree` session and choose to remove
  it". The undocumented part is that a clean, untitled hook worktree is removed without a choice,
  with commits ignored.
- Hook `cwd` on `--worktree` and EnterWorktree is the canonical git root, which for a bare-repo
  layout is the bare repository directory. This is undocumented.

## Per-release appendix

- 2.1.288: verified. Payloads, entry points, cwd handling, the `baseRef` default and the removal
  paths as described above.
