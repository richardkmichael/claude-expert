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
