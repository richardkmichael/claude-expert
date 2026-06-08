# Claude Code Analysis - Settings & Configuration

Analysis of how Claude Code reads, stores, and persists settings, based on
`cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`).

## Configuration File Locations

Claude Code uses two distinct configuration systems that are often confused with
each other.

### 1. Global user preferences — `~/.claude.json`

A flat JSON file storing per-user preferences, session state, and undocumented
settings. Read/written by the `k1()` / `Hfq()` functions.

Path is computed by `tD()` (a memoized thunk):

```
// Legacy fallback: if ~/.claude/.config.json exists, use that
if (existsSync(join(_A(), ".config.json")))
    return join(_A(), ".config.json");

// Default: ~/.claude.json  (CLAUDE_CONFIG_DIR replaces homedir())
return join(process.env.CLAUDE_CONFIG_DIR || homedir(), ".claude.json");
```

### 2. Settings files — `~/.claude/settings.json` et al.

A separate system for hooks, permissions, MCP servers, and environment
variables.  These are read by a different code path and support multiple scopes:

| File                           | Scope   | Git-committed | Purpose                        |
|--------------------------------|---------|---------------|--------------------------------|
| `~/.claude/settings.json`      | User    | N/A           | Personal, global               |
| `.claude/settings.json`        | Project | Yes           | Team-shared                    |
| `.claude/settings.local.json`  | Local   | No            | Personal per-project overrides |

## Effect of CLAUDE_CONFIG_DIR

`CLAUDE_CONFIG_DIR` affects both systems simultaneously because `_A()` (which
computes the `~/.claude/` directory) is defined as:

```
process.env.CLAUDE_CONFIG_DIR ?? join(homedir(), ".claude")
```

With `CLAUDE_CONFIG_DIR=/custom/dir` set:

| Without env var          | With CLAUDE_CONFIG_DIR=/custom/dir |
|--------------------------|------------------------------------|
| `~/.claude/`             | `/custom/dir/`                     |
| `~/.claude.json`         | `/custom/dir/.claude.json`         |
| `~/.claude/settings.json`| `/custom/dir/settings.json`        |

Note the asymmetry in the default layout: `~/.claude.json` lives in `~/` (not
inside `~/.claude/`), but when `CLAUDE_CONFIG_DIR` is set the equivalent file
moves inside the custom dir.  This means setting `CLAUDE_CONFIG_DIR` to a
project directory effectively gives you per-project isolation of the global
config.

## Settings writes refuse symlinks (project and local scopes)

Verified against `cli.prettier.js` 2.1.168 (2026-06-08). Landmark style; newer than the 2.1.76 baseline
above.

Claude Code persists each settings scope through a guarded writer that, for project and local settings,
refuses to write a file that is a symlink — silently, as far as the user can tell. A symlinked
`.claude/settings.local.json` (or `.claude/settings.json`) reads fine but is never written: MCP
approvals and any other local/project settings change are dropped, the change lives only in the
in-memory UI, and it is lost on restart. User settings (`~/.claude/settings.json`) are exempt.

Relocate: `rg -n 'Refusing to write through symlink|Refusing to write into symlinked directory|Writing through symlink'`.

The guarded writer takes options `allowSymlink` and `checkParentDir`, set by scope:

- `allowSymlink` is true only for user settings; false for project and local settings.
- `checkParentDir` is true for project and local settings.

With `allowSymlink: false`, before writing it:

1. opens the parent directory with `O_NOFOLLOW`; if the directory is itself a symlink (errno `ELOOP` /
   `ENOTDIR`) it throws `Refusing to write into symlinked directory: <dir>`;
2. `lstat`s the target; if it is a symlink it throws
   `Refusing to write through symlink: <path>. Resolve the symlink and pass the real target path explicitly.`

With `allowSymlink: true` (user settings) it does the opposite — `readlink`s the target and writes
through to the real file, logging `Writing through symlink: <path> -> <target>`. So a dotfiles-style
symlink for `~/.claude/settings.json` works; the same on project/local settings does not.

The throw is swallowed. The per-scope writer that merges a partial update and calls the guarded writer
wraps it in try/catch, logs the failure at `error` level (so it surfaces in `claude --debug` / the error
log, not the TUI), and returns an error the caller ignores — the UI shows the change applied but it is
never persisted.

Reads are unaffected: the settings watcher resolves a symlinked settings file to its real path and
watches the target's directory, logging `Settings file <link> is a symlink to <target>; also watching
<dir> so atomic-save edits to the target are detected`. The file loads correctly and only the write
fails.

Consequence for git-worktree workflows that share `settings.local.json` across worktrees via a symlink to
a workspace-level file: reads work, but every settings write (MCP approval, permission "always allow",
`/add-dir`, …) is silently refused. Use a plain per-worktree file instead.

Relocation aids (version-specific, will churn): the per-scope writer that catches the throw logs
`updateSettingsForSource: invalid JSON in settings file at`; the scope→path resolver returns
`.claude/settings.local.json` for the local scope.

Tripwire for a new version: □ `allowSymlink` true only for user scope □ project/local writes `lstat` the
target and throw on a symlink □ parent-dir `O_NOFOLLOW` check present □ the throw is caught and logged at
`error` level, not surfaced to the TUI □ user-settings symlink still writes through.

## Global Config Keys (DEFAULT_GLOBAL_CONFIG / ~/.claude.json)

The `BC` object defines defaults, and `$fq` (GLOBAL_CONFIG_KEYS) lists which
keys are persisted to disk.  Selected keys:

```
numStartups, installMethod, autoUpdates, theme, preferredNotifChannel,
verbose, editorMode, autoCompactEnabled, showTurnDuration, diffTool, env,
tipsHistory, todoFeatureEnabled, showExpandedTodos,
messageIdleNotifThresholdMs, autoConnectIde, autoInstallIdeExtension,
fileCheckpointingEnabled, terminalProgressBarEnabled, respectGitignore,
copyFullResponse, ...
```

## Project Config Keys (PROJECT_CONFIG_KEYS)

Only three keys live in project-scoped storage (`Ofq`):

- `allowedTools`
- `hasTrustDialogAccepted`
- `hasCompletedProjectOnboarding`

Everything else is global-only.

## Notable Undocumented Settings

### messageIdleNotifThresholdMs

Controls how long Claude Code waits (in milliseconds) before sending an
`idle_prompt` notification ("Claude is waiting for your input").

- Default: `60000` (60 seconds)  — line 538937
- Scope: global only (`GLOBAL_CONFIG_KEYS`)
- Not mentioned in official documentation

The timeout is used twice in the notification logic (lines 593593–593609): once
as the `setTimeout` delay, and once as a guard inside the callback to confirm
that the elapsed idle time still meets the threshold before firing.

To change it, edit `~/.claude.json` and set the key at the top level:

```json
{
  "messageIdleNotifThresholdMs": 30000
}
```

There is no per-project way to override this value.  A per-project workaround
would be a wrapper script or `.envrc` that sets `CLAUDE_CONFIG_DIR` to a
project-specific directory containing a `.claude.json` with the desired value.
