# Claude Code Analysis - Settings & Configuration

Verified against: cli.prettier.js 2.1.168 (2026-06-08)

How Claude Code reads, merges, stores, and persists settings. Landmark style: anchor on the stable
strings and relocate with the grep recipes; re-check version-specific specifics against the current
bundle.

## Two configuration systems

Claude Code keeps two separate configuration systems that are easy to confuse.

### 1. Global user preferences — `~/.claude.json`

A flat JSON file storing per-user preferences, session state, and undocumented settings. The path:

1. Legacy fallback: if `<base>/.config.json` exists, use it.
2. Otherwise `join(process.env.CLAUDE_CONFIG_DIR || homedir(), ".claude" + <oauth-suffix> + ".json")`.

The filename carries an OAuth-environment suffix: empty for production (so `~/.claude.json`), else
`-local-oauth` / `-staging-oauth` / `-custom-oauth`. In normal production use it is `~/.claude.json`.

Relocate: `rg -n '"\.config\.json"'` lands on the legacy-fallback closure; the OAuth suffix anchors on
`rg -n '"-staging-oauth"'`. The base directory is
`(process.env.CLAUDE_CONFIG_DIR ?? join(homedir(), ".claude")).normalize("NFC")` — relocate with
`rg -n 'CLAUDE_CONFIG_DIR \?\? '`.

### 2. Settings files — `~/.claude/settings.json` et al.

A separate system for hooks, permissions, MCP servers, model, environment, and most documented
options. Read across five scopes, merged into one effective settings object. The rest of this doc is
about this system.

## Settings scopes and precedence

Five scopes, defined by one array literal (`allowedSettingSources`). Array order is the merge order,
lowest precedence to highest:

| Scope (identifier) | On-disk source                         | Committed     | Notes                          |
| ------------------ | -------------------------------------- | ------------- | ------------------------------ |
| `userSettings`     | `<user dir>/settings.json`             | N/A           | Personal, global               |
| `projectSettings`  | `<cwd>/.claude/settings.json`          | Yes           | Team-shared                    |
| `localSettings`    | `<cwd>/.claude/settings.local.json`    | No (gitignored) | Personal per-project overrides |
| `flagSettings`     | the `--settings` value (path or JSON)  | N/A           | Load-only; never written       |
| `policySettings`   | `<managed base>/managed-settings.json` | N/A           | Enterprise/MDM; always wins    |

`<user dir>` is `CLAUDE_CONFIG_DIR` or `~/.claude`. The effective settings are a forward left-to-right
reduce over this list from `{}`, so `policySettings` (folded last) overrides everything.

`--setting-sources` lets a user restrict which scopes load, but only gates the first three
(`user`/`project`/`local`); `flagSettings` and `policySettings` always apply. Relocate the parser via
`rg -n 'Valid options are: user, project, local'` (rejection message `Invalid setting source:`).

Relocate the scope set and order: `rg -n '"flagSettings"|"policySettings"'` lands on the
`allowedSettingSources` array (the five scope strings in precedence order) and the scope→path switch.

## How scopes merge

The reduce folds each scope with lodash `mergeWith` plus one custom handler. Per value type:

- Arrays union and dedupe: concat lower-then-higher, then `[...new Set(...)]`, first-seen order kept.
  Applies to `permissions.allow`/`deny`/`ask`, `enabledMcpjsonServers`, `disabledMcpjsonServers`,
  `additionalDirectories`, and similar list-valued keys. Higher scopes accumulate onto lower, not
  replace.
- Scalars override: the higher-precedence value wins (the handler returns `undefined`, deferring to
  `mergeWith`'s default).
- Objects deep-merge: recurse key-by-key with the same array-union / scalar-override rules.

One key breaks the array rule: `fallbackModel` is replaced, not unioned — when both sides are arrays
the handler returns the higher-precedence array as-is. It is the only array-valued key that overrides
rather than accumulates. Relocate: `rg -n 'fallbackModel'` lands on the handler's
`Array.isArray(...)` branch containing the `return` that short-circuits the union.

Managed settings (`policySettings`) can additionally hard-lock values, suppressing lower-scope
allowlists: `allowManagedPermissionRulesOnly`, `allowManagedDomainsOnly`, `allowManagedReadPathsOnly`.
Its own sub-tiers (remote, MDM/plist/registry, the on-disk file plus `managed-settings.d/` drop-ins,
and an optional SDK parent via `parentSettingsBehavior`) are pre-merged with the same handler before
the policy scope enters the cross-scope reduce.

Tripwire: □ five scopes in `allowedSettingSources`, order user→project→local→flag→policy □ arrays
union+dedupe via `[...new Set]` □ scalars override by precedence □ objects deep-merge □ `fallbackModel`
the lone array-replace □ `--setting-sources` gates only user/project/local.

## Writing settings: atomic, with a symlink refusal

There is a single settings-mutation entry point (the per-source updater, `updateSettingsForSource`).
Its first statement is a read-only guard:

    if (source === "policySettings" || source === "flagSettings") return { error: null };

So `flagSettings` and `policySettings` are no-ops — `--settings` and managed settings can never be
persisted, even by callers that forward a dynamic source (permission/plugin writers). For the three
writable scopes the updater merges a partial patch into the scope's current file and calls a guarded
atomic writer.

### Atomic write

Write to a temp sibling, then rename over the target:

- Temp name `${target}.tmp.${pid}.${randomBytes(6)}`, opened `O_WRONLY|O_CREAT|O_EXCL` (plus
  `O_NOFOLLOW` unless `allowSymlink`), written, optional `fchmod` to preserve mode, `fsync`, `close`,
  then `renameSync(temp, target)`.
- On failure it removes the temp file and falls back to a non-atomic write (`O_TRUNC`, still `fsync`).

Relocate: `rg -n 'written atomically|Writing to temp file|Falling back to non-atomic write'`. The sync
writer and an identical async twin sit together.

### Symlink refusal (project and local scopes)

The guarded writer takes `allowSymlink` and `checkParentDir`, set by scope:

- `allowSymlink` is true only for user settings; false for project and local.
- `checkParentDir` is true for project and local.

With `allowSymlink: false` (project/local), before writing it:

1. opens the parent directory with `O_DIRECTORY|O_NOFOLLOW`; if the directory is itself a symlink
   (errno `ELOOP`/`ENOTDIR`) it throws `Refusing to write into symlinked directory: <dir>`;
2. `lstat`s the target; if it is a symlink it throws
   `Refusing to write through symlink: <path>. Resolve the symlink and pass the real target path explicitly.`

The throw is a `SymlinkWriteRefusedError`. It is swallowed: the per-scope updater try/catches, logs at
`error` level (so it surfaces in `claude --debug` / the error log, not the TUI), and returns an error
the caller ignores — the UI shows the change applied but it is never persisted. A symlinked
`.claude/settings.local.json` (or `.claude/settings.json`) therefore reads fine but drops every write:
MCP approvals, permission "always allow", `/add-dir`, and the like live only in memory and are lost on
restart.

With `allowSymlink: true` (user settings) it does the opposite — `readlink`s the target and writes
through to the real file, logging `Writing through symlink: <path> -> <target>`. So a dotfiles-style
symlink for `~/.claude/settings.json` works; the same on project/local settings does not.

Reads are unaffected at every scope: the settings watcher resolves a symlinked file to its real path
and watches the target's directory, logging `Settings file <link> is a symlink to <target>; also
watching <dir> so atomic-save edits to the target are detected`.

This refusal was introduced in 2.1.138 (bisected: 2.1.137 lacks it, 2.1.138 has it). Through 2.1.137
the writer took no `allowSymlink` option and unconditionally `readlink`ed the target and wrote the real
file for every scope, logging `Writing through symlink`.

Consequence for git-worktree workflows that share `settings.local.json` across worktrees via a symlink
to a workspace-level file: reads work, but every settings write is silently refused. Use a plain
per-worktree file. There is no relocation knob to move the file outside the symlink (see below).

Relocate: `rg -n 'Refusing to write through symlink|Refusing to write into symlinked directory|Writing through symlink'`.

Tripwire: □ `allowSymlink` true only for user scope □ project/local writes `lstat` the target and throw
on a symlink □ parent-dir `O_NOFOLLOW` check present □ the throw (`SymlinkWriteRefusedError`) is caught
and logged at `error` level, not surfaced to the TUI □ user-settings symlink still writes through.

## On-disk path resolution and relocation knobs

A scope→directory→filename resolver maps each scope to a path. The filename fragments are hard-coded
string literals: `settings.json`, `settings.local.json`, `managed-settings.json`, and the drop-in dir
`managed-settings.d`.

| Scope             | Resolved path                                  | Path env override                        |
| ----------------- | ---------------------------------------------- | ---------------------------------------- |
| `userSettings`    | `<CLAUDE_CONFIG_DIR or ~/.claude>/settings.json` | `CLAUDE_CONFIG_DIR` (moves the dir only) |
| `projectSettings` | `<cwd>/.claude/settings.json`                  | none                                     |
| `localSettings`   | `<cwd>/.claude/settings.local.json`            | none                                     |
| `flagSettings`    | the `--settings <path>` value, verbatim        | the `--settings` flag itself             |
| `policySettings`  | `<managed base>/managed-settings.json`         | none effective in this build             |

The user file becomes `cowork_settings.json` when `CLAUDE_CODE_USE_COWORK_PLUGINS` is set. Managed base
directories are platform-fixed: `/Library/Application Support/ClaudeCode` (macOS),
`C:\Program Files\ClaudeCode` (Windows), `/etc/claude-code` (Linux). Relocate the local-scope builder
with `rg -n 'settings\.local\.json'` and the managed base with `rg -n 'managed-settings\.json'`.

No relocation knob for `settings.local.json`: there is no env var, flag, or config key that moves the
local file outside `<cwd>/.claude/`. The path is built from the resolved cwd plus the fixed literals
`.claude` and `settings.local.json`. `CLAUDE_CONFIG_DIR` relocates the user scope only. (`--add-dir`
adds an additional `<root>/.claude/settings.local.json` under each added root; it does not rename the
cwd file.)

Two env vars look like path overrides but are inert in this build:

- `CLAUDE_CODE_MANAGED_SETTINGS_PATH` — present in the env-var schema but with no read site; the managed
  path resolver hard-codes `<platform base>/managed-settings.json`.
- `CLAUDE_CODE_REMOTE_SETTINGS_PATH` — the override-path reader compiles to `undefined`, so it has no
  effect. Remote settings feed the `policySettings` managed tier, not the three filesystem scopes.
  Landmark: `Remote settings: Using override file ... skipping API fetch`.

## The `--settings` flag

`--settings <file-or-json>` ("Path to a settings JSON file or a JSON string to load additional settings
from") accepts either a file path or inline JSON: a trimmed value starting `{` and ending `}` is parsed
inline and materialized to a temp file; otherwise it is read as a path. It loads into the `flagSettings`
scope, which sits above local and below policy. It is load-only — the writer guard above makes any
write to `flagSettings` a no-op, so `--settings` can never be persisted back. Errors:
`Settings file not found:`, `Invalid JSON provided to --settings`.

## Effect of CLAUDE_CONFIG_DIR

`CLAUDE_CONFIG_DIR` moves both configuration systems' user-scoped files, because both the `~/.claude/`
base directory and the `~/.claude.json` path derive from it:

| Without env var           | With `CLAUDE_CONFIG_DIR=/custom/dir` |
| ------------------------- | ------------------------------------ |
| `~/.claude/`              | `/custom/dir/`                       |
| `~/.claude.json`          | `/custom/dir/.claude.json`           |
| `~/.claude/settings.json` | `/custom/dir/settings.json`          |

Note the default-layout asymmetry: `~/.claude.json` lives in `~/` (not inside `~/.claude/`), but with
`CLAUDE_CONFIG_DIR` set the equivalent file moves inside the custom dir. Pointing `CLAUDE_CONFIG_DIR` at
a project directory thus gives per-project isolation of the global config. It does not move the
project/local settings files, which are always under `<cwd>/.claude/`.

## Notable config keys

### Global keys (`~/.claude.json`)

An allowlist (`GLOBAL_CONFIG_KEYS`) controls which keys persist to `~/.claude.json`. It is a large,
fast-growing set — roughly forty keys, several added most releases — so do not anchor on the full list.
Stable members include `theme`, `editorMode`, `autoUpdates`, `verbose`, `env`, `diffTool`,
`respectGitignore`, `preferredNotifChannel`, and `messageIdleNotifThresholdMs`. Relocate the array via
`rg -n 'messageIdleNotifThresholdMs'` — the array containing that key is the allowlist.

### Project keys (project storage)

Distinct from the settings files, a small allowlist governs project-scoped config storage. It is
exactly three keys: `allowedTools`, `hasTrustDialogAccepted`, `hasCompletedProjectOnboarding`.
(The project-storage default object is larger — `mcpServers`, `enabledMcpjsonServers`,
`projectOnboardingSeenCount`, and more — but the dedicated project-key allowlist is these three.)
Relocate: `rg -n 'hasTrustDialogAccepted|hasCompletedProjectOnboarding'`.

### messageIdleNotifThresholdMs

How long Claude Code waits before sending an `idle_prompt` notification ("Claude is waiting for your
input"). Default `60000` (60s), global-only (in `GLOBAL_CONFIG_KEYS`, absent from the project
allowlist), undocumented. Used twice in the notification logic — as the `setTimeout` delay and as a
guard inside the callback confirming the elapsed idle time still meets the threshold before firing. No
per-project override; the workaround is a wrapper or `.envrc` that sets `CLAUDE_CONFIG_DIR` to a
project-specific dir with a `.claude.json` holding the desired value. Relocate:
`rg -n 'messageIdleNotifThresholdMs'`.
