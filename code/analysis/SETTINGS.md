---
verified: 2.1.317
verified_on: 2026-11-03
section: Config, settings, and frontmatter
style: landmark
scope: Settings scopes/precedence, merge, local-settings location, writes, symlink refusal
landmarks:
  - onLegacyLocalSettingsRead
  - Refusing to write through symlink
  - 'Invalid setting source:'
---
# Claude Code Analysis - Settings & Configuration

How Claude Code reads, merges, stores, and persists settings. Landmark style: anchor on the stable
strings and relocate with the grep recipes; re-check version-specific specifics against the current
bundle.

Which directory each project-level file is read from, and how that differs in a subdirectory or a
linked worktree, is in [Project Files and State](PROJECT_FILES_AND_STATE.md). This doc covers the
settings system itself and links there instead of repeating the per-layout tables.

## Two configuration systems

Claude Code keeps two separate configuration systems that are easy to confuse.

### 1. Global user preferences — `~/.claude.json`

A flat JSON file storing per-user preferences, session state, and undocumented settings. The path:

1. Legacy fallback: `<config dir>/.config.json` is used instead when it is a regular file that is
   non-empty, or empty but writable while the primary file does not exist.
2. Otherwise `join(process.env.CLAUDE_CONFIG_DIR || homedir(), ".claude" + <oauth-suffix> + ".json")`.

The filename carries an OAuth-environment suffix: empty for production (so `~/.claude.json`), else
`-local-oauth` / `-staging-oauth` / `-custom-oauth` (the last whenever
`CLAUDE_CODE_CUSTOM_OAUTH_URL` is set). In normal production use it is `~/.claude.json`.

The config dir is `CLAUDE_CONFIG_DIR`, else `~/.claude`, NFC-normalized.

Relocate: `rg -n '"\.config\.json"'`; the legacy fallback is the hit followed by a `statSync` with a
size and write-mode check. The suffix list anchors on `rg -n '"-staging-oauth"'` (an array of the
four suffixes plus a switch returning one). The config dir is the cached getter returning
`<CLAUDE_CONFIG_DIR or join(homedir, ".claude")>.normalize("NFC")`; find its env read with
`rg -n 'return process.env.CLAUDE_CONFIG_DIR;'`.

### 2. Settings files — `~/.claude/settings.json` et al.

A separate system for hooks, permissions, MCP servers, model, environment, and most documented
options. Read across five scopes, plus a plugin base layer, merged into one effective settings
object. The rest of this doc is about this system.

## Settings scopes and precedence

Five scopes, defined by one array literal. Array order is the merge order, lowest precedence to
highest:

| Scope (identifier) | On-disk source                            | Committed       |
| ------------------ | ----------------------------------------- | --------------- |
| `userSettings`     | `<config dir>/settings.json`              | N/A             |
| `projectSettings`  | `<start dir>/.claude/settings.json`       | Yes             |
| `localSettings`    | `<local dir>/.claude/settings.local.json` | No (gitignored) |
| `flagSettings`     | the `--settings` value (path or JSON)     | N/A             |
| `policySettings`   | managed sources (see below)               | N/A             |

`<start dir>` is the directory the session was launched in. `<local dir>` is the repository's
canonical root when the ownership conditions in "Where local settings live" below hold, else the
start directory. The effective settings are a forward left-to-right fold over this list, so
`policySettings` (folded last) overrides everything.

Below `userSettings` sits a plugin base layer: the `settings` objects of enabled plugins, combined
key by key (a later plugin replaces an earlier one's top-level key, logged as
`Plugin "<name>" overrides setting "<key>" (previously set by another plugin)`). The debug line
`Cached plugin settings with keys:` records it.

`--setting-sources` restricts which scopes load, but only gates the first three
(`user`/`project`/`local`); `flagSettings` and `policySettings` are always added back. An unknown
name is rejected with `Invalid setting source: <name>. Valid options are: user, project, local` (the
list is built from the three names at runtime, so grep only the prefix). The settings source also
has a host-set workspace restriction that drops `projectSettings` and `localSettings`; nothing in
the CLI sets it in this build.

Relocate: `rg -n 'Invalid setting source:'` lands on the parser. A few lines below it, the
enabled-source function adds `flagSettings` and `policySettings` to the allowed set and filters the
five-element scope array (`"userSettings"`, `"projectSettings"`, `"localSettings"`,
`"flagSettings"`, `"policySettings"`) by it, preserving the array's order.

## How scopes merge

The fold uses lodash `mergeWith` with one custom handler. Per value type:

- Arrays union and dedupe: concat lower-then-higher, then `[...new Set(...)]`, first-seen order kept.
  Applies to `permissions.allow`/`deny`/`ask`, `enabledMcpjsonServers`, `disabledMcpjsonServers`,
  `additionalDirectories`, and similar list-valued keys. Higher scopes accumulate onto lower, not
  replace.
- Scalars override: the higher-precedence value wins (the handler returns `undefined`, deferring to
  `mergeWith`'s default).
- Objects deep-merge: recurse key-by-key with the same array-union / scalar-override rules.

Exceptions in the handler:

- `fallbackModel`: when both sides are arrays the higher-precedence array replaces the lower one. It
  is the only array-valued key that overrides rather than accumulates.
- `modelPicker`: a higher scope's value replaces the lower one whole.
- `extraKnownMarketplaces` and `managedMcpServers`: shallow merge. A higher scope's entry replaces
  the lower scope's entry of the same name whole instead of deep-merging into it.

After the fold, values from `policySettings` are re-applied whole: `availableModels`,
`enforceAvailableModels` and `modelPicker` take the policy value when policy sets them, and
`deniedModels` is taken only from policy (removed when policy does not set it).

Relocate: `rg -n '=== "fallbackModel"'` lands inside the handler, next to the `modelPicker` check
and the `extraKnownMarketplaces` / `managedMcpServers` shallow-merge branch. The fold itself is the
function just below it that logs `settings_load_started` / `settings_load_completed`.

### Per-scope filtering before the fold

- In some remote-hosting launch modes (an interactive `--remote` / `--cloud` session,
  `--attach-serve`), project and local settings lose the credential-helper keys (`apiKeyHelper`,
  `awsAuthRefresh`, `awsCredentialExport`, `gcpAuthRefresh`, `otelHeadersHelper`, `proxyAuthHelper`)
  and a set of launch-folder keys (`enabledPlugins`, `disableAllHooks`, `extraKnownMarketplaces`,
  `enableAllProjectMcpServers`, `enabledMcpjsonServers` and others). Relocate:
  `rg -n '"otelHeadersHelper", "proxyAuthHelper"'`; the launch-folder list follows it.
- When managed settings set `allowManagedReadPathsOnly` or `allowManagedDomainsOnly`, entries in
  `sandbox.filesystem.allowRead` / `sandbox.network.allowedDomains` from other scopes are ignored,
  with a warning naming the file (grep `managed settings set`). Under
  `allowManagedPermissionRulesOnly` the session applies permission rules from policy only; rules in
  other settings files still merge but are ignored by the permission layer.

### The policy scope

`policySettings` is assembled from its own sources before it enters the fold: server-managed
(remote) settings, MDM (the macOS managed plist, HKLM on Windows), and the managed directory's
`managed-settings.json` plus `managed-settings.d/*.json` drop-ins (under WSL, optionally the Windows
managed directory as well). `managedSourcesBehavior` decides how they compose: `first-wins` (the
default) uses the highest-priority source present alone (server-managed > MDM > file); `merge`
deep-merges them with the strictest value of each lock winning. A host's `--managed-settings` tier
joins only under `parentSettingsBehavior: "merge"`; see
[The SDK Parent Managed-Settings Tier](MANAGED_SETTINGS_PARENT.md). Relocate the composition rules
with `rg -n 'Controls how the managed settings sources compose'` (the schema description).

Tripwire: □ five scopes in the source array, order user→project→local→flag→policy □ plugin base
folded first □ arrays union+dedupe via `[...new Set]` □ scalars override by precedence □ objects
deep-merge □ `fallbackModel` the lone array-replace □ `modelPicker` whole-replace □
`extraKnownMarketplaces` / `managedMcpServers` shallow □ `--setting-sources` gates only
user/project/local.

## Where local settings live

`localSettings` is not always `<start dir>/.claude/settings.local.json`. Its directory is the
canonical root (the git top-level, or for a linked worktree the main repository) when all of these
hold:

- the canonical root differs from the start directory and is not the home directory;
- the platform has uid semantics (POSIX);
- the canonical root, its `.git` entry and its `.claude` entry (when present) are owned by the
  current user. A missing `.git` entry counts as unverifiable.

Otherwise it is the start directory. When the canonical file is used, the start directory's own
`.claude/settings.local.json` is still read beneath it in the fold, so its keys apply where the
canonical file does not set them. Each failed condition logs a warning beginning
`localSettings: not canonicalizing the consent store to` (no uid semantics, ownership mismatch, or
ownership unverifiable).

Consequences:

- A session in a subdirectory of a repository, or in a linked worktree of an ordinary checkout,
  reads and writes the top-level's (or main checkout's) `.claude/settings.local.json`.
- A worktree of a bare repository keeps its own file: the canonical root is the bare directory,
  which has no `.git` entry, so ownership is unverifiable and canonicalization is skipped.
- The hidden host flag `--project-config-root <dir>` replaces all of this: project and local
  settings come from `<dir>/.claude/`, with no canonical lookup and no start-directory read.
- `--add-dir` adds no settings file. The cascade has no source for additional directories; only the
  five scopes above load.

The canonical-root key is shared with the `projects` entry in `~/.claude.json`, exported as
`getProjectPathForConfig`. Per-layout tables, including what a bare-repository worktree shares:
[Project Files and State](PROJECT_FILES_AND_STATE.md), "Settings".

Relocate: `rg -n 'localSettings: not canonicalizing the consent store to'` (three warnings, in the
ownership check). The start-directory read fires `onLegacyLocalSettingsRead`
(`rg -n 'onLegacyLocalSettingsRead'`).

## Writing settings

There is a single settings-mutation entry point (the per-source updater, exported as
`updateSettingsForSource`, with a transform variant). Its first statement is a read-only guard: a
write to `policySettings` or `flagSettings` returns `{ error: null }` without doing anything, so
`--settings` and managed settings can never be persisted, even by callers that forward a dynamic
source (permission/plugin writers). A diskless session gets
`This session does not write settings to disk` instead.

For the three writable scopes the updater reads the scope's current file, merges a partial patch
into it, and calls a guarded atomic writer. The patch merge differs from the cross-scope fold: an
`undefined` value deletes the key, an array in the patch replaces the stored array, and
`extraKnownMarketplaces` is shallow-merged. A stored file that fails validation is merged as raw
JSON so unrecognized entries survive (`Using raw settings from`); invalid JSON aborts the write with
`Invalid JSON syntax in settings file at`.

Local settings writes have two extra steps:

- When the canonical file is used and the start directory has its own `settings.local.json`, the
  same change is applied to the start-directory file, but only its removals: entries the change
  deletes are revoked there too, and nothing is added. Failures log
  `Failed to revoke from legacy settings.local.json`.
- After each write, if `.claude/settings.local.json` is not already ignored in the repository,
  `**/.claude/settings.local.json` is appended to the user's global git excludes file. Failure logs
  `Failed to add gitignore entry to global gitignore`.

### Atomic write

Write to a temp file, then rename over the target:

- Temp name `<target>.tmp.<pid>.<12 hex chars>`. When a `.cc-writes` staging directory already
  exists beside the target (the sandbox setup creates `.claude/.cc-writes` and denies sandboxed
  commands writes to it and to the settings files), the temp file is staged there instead of beside
  the target.
- Opened `O_WRONLY|O_CREAT|O_EXCL` (plus `O_NOFOLLOW` unless `allowSymlink`), written, `fchmod` to
  the existing file's mode, `fsync`, `close`, then `rename` onto the target, logging
  `File <path> written atomically`.
- In-place fallback only for specific failures: the rename fails with `EXDEV`, `EPERM`, `EEXIST` or
  `EBUSY`, or creating the temp file fails with `EACCES` while the target exists. The target is then
  opened (still `O_NOFOLLOW` where applicable), truncated, written and `fsync`ed, logging
  `written via in-place fallback`. Any other failure removes the temp file and throws.

Relocate: `rg -n 'written atomically|written via in-place fallback|Writing to temp file'`. The async
writer and a sync twin sit together.

### Symlink refusal

The guarded writer takes `allowSymlink` and `checkParentDir`, set per write:

- `allowSymlink` is true for `userSettings`, and for any settings file whose directory is the config
  dir itself (for example the project file of a session started in the home directory). It is false
  for project and local settings everywhere else.
- `checkParentDir` is true for project and local settings outside the config dir.

With `allowSymlink: false`, before writing it:

1. opens the parent directory with `O_DIRECTORY|O_NOFOLLOW`; if the directory is itself a symlink
   (errno `ELOOP`/`ENOTDIR`) it throws `Refusing to write into symlinked directory: <dir>`;
2. `lstat`s the target; if it is a symlink it throws
   `Refusing to write through symlink: <path>. Resolve the symlink and pass the real target path explicitly.`

The throw is a `SymlinkWriteRefusedError`. A symlink-retry hook in the settings writer exists but
always declines in this build, so the error propagates to the updater, which catches it, logs
`Failed to read raw settings from <path>: SymlinkWriteRefusedError: Refusing to write through symlink: …`
at `error` level (so it surfaces in `claude --debug` / the error log, not the TUI), and returns it
as `{ error }`. Callers differ in what they do with it; the permission-rule writer logs
`Failed to add permission rules to <source> settings:` and returns `false`, and the
permission-update path ignores that result, so the rule applies for the session but is not saved. A
symlinked `.claude/settings.local.json` (or `.claude/settings.json`) therefore reads fine but drops
writes: MCP approvals (see `MCP.md`), permission "always allow", `/add-dir`, and the like live only
in memory and are lost on restart.

With `allowSymlink: true` it does the opposite: it `readlink`s the target and writes through to the
real file, logging `Writing through symlink: <path> -> <target>`. So a dotfiles-style symlink for
`~/.claude/settings.json` works; the same on project/local settings does not.

Reads follow symlinks at every scope, except a link that leads onto a network share or automount,
which is skipped with `Settings file leads to another host and was not read:`. The settings watcher
resolves a symlinked file to its real path and also watches the target's directory, logging
`Settings file <link> is a symlink to <target>; also watching <dir> so atomic-save edits to the target are detected`.

Consequence for worktree workflows that share `settings.local.json` across worktrees via a symlink
to a workspace-level file: reads work, but every settings write is refused. Linked worktrees of an
ordinary checkout already share the main checkout's file through canonicalization (above), so they
need no symlink. Worktrees of a bare repository do not canonicalize; give each a plain file.

Relocate:
`rg -n 'Refusing to write through symlink|Refusing to write into symlinked directory|Writing through symlink'`.

Tripwire: □ write guard no-ops `policySettings` / `flagSettings` □ `allowSymlink` true only for user
scope or a file in the config dir □ project/local writes `lstat` the target and throw on a symlink □
parent-dir `O_NOFOLLOW` check present □ the `SymlinkWriteRefusedError` is caught and logged at
`error` level, not surfaced to the TUI □ user-settings symlink still writes through □ local writes
revoke from the start-directory file.

## On-disk paths and relocation knobs

| Scope             | Resolved path                                   | Path override                  |
| ----------------- | ----------------------------------------------- | ------------------------------ |
| `userSettings`    | `<config dir>/settings.json`                    | `CLAUDE_CONFIG_DIR` (dir only) |
| `projectSettings` | `<start dir>/.claude/settings.json`             | `--project-config-root` (host) |
| `localSettings`   | `<local dir>/.claude/settings.local.json`       | `--project-config-root` (host) |
| `flagSettings`    | the `--settings <path>` value                   | the `--settings` flag itself   |
| `policySettings`  | `<managed dir>/managed-settings.json` and `.d/` | none effective in this build   |

The filename fragments are hard-coded literals: `settings.json`, `settings.local.json`,
`managed-settings.json`, and the drop-in dir `managed-settings.d`. The user file becomes
`cowork_settings.json` when `CLAUDE_CODE_USE_COWORK_PLUGINS` is set or the host enables cowork
plugins. The managed directory is platform-fixed: `/Library/Application Support/ClaudeCode` (macOS),
`C:\Program Files\ClaudeCode` (Windows), `/etc/claude-code` (Linux). Relocate the managed base with
`rg -n 'Library/Application Support/ClaudeCode'` (the switch next to a stub override function that
returns `undefined`).

Two env vars look like path overrides but are inert in this build:

- `CLAUDE_CODE_MANAGED_SETTINGS_PATH`: present in the env-var schema and in env pass-through lists,
  but nothing reads it; the managed path resolver's override hook returns `undefined`.
- `CLAUDE_CODE_REMOTE_SETTINGS_PATH`: the override-path reader compiles to `undefined`, so the
  `Remote settings: Using override file … (CLAUDE_CODE_REMOTE_SETTINGS_PATH), skipping API fetch`
  branch never runs. Remote settings feed the `policySettings` managed tier, not the three
  filesystem scopes.

## The `--settings` flag

`--settings <file-or-json>` ("Path to a settings JSON file or a JSON string to load additional
settings from") accepts either a file path or inline JSON. A trimmed value starting `{` and ending
`}` is parsed as JSON and held in memory under a synthetic `claude-settings-<hash>.json` path in the
temp directory; nothing is read from that path. Otherwise the value is a path: the file is read once
at startup and its content pinned, so editing the file later in the session has no effect. Either
way it loads into the `flagSettings` scope, above local and below policy. An SDK host's inline
settings fold in right after it at the same scope (`SDK inline settings`).

It is load-only: the write guard above makes any write to `flagSettings` a no-op. Errors:
`Error: Invalid JSON provided to --settings`, `Error: Settings file not found:`,
`Error: Settings file exceeds the`, `Error: Cannot use settings file`. Relocate:
`rg -n 'Invalid JSON provided to --settings'`.

## Effect of CLAUDE_CONFIG_DIR

`CLAUDE_CONFIG_DIR` moves both configuration systems' user-scoped files, because both the
`~/.claude/` base directory and the `~/.claude.json` path derive from it:

| Without env var           | With `CLAUDE_CONFIG_DIR=/custom/dir` |
| ------------------------- | ------------------------------------ |
| `~/.claude/`              | `/custom/dir/`                       |
| `~/.claude.json`          | `/custom/dir/.claude.json`           |
| `~/.claude/settings.json` | `/custom/dir/settings.json`          |

Note the default-layout asymmetry: `~/.claude.json` lives in `~/` (not inside `~/.claude/`), but
with `CLAUDE_CONFIG_DIR` set the equivalent file moves inside the custom dir. Pointing
`CLAUDE_CONFIG_DIR` at a project directory thus gives per-project isolation of the global config. It
does not move the project or local settings files, which stay under the start directory or the
canonical root.

## Notable config keys

### Global keys (`~/.claude.json`)

An allowlist (exported as `GLOBAL_CONFIG_KEYS`) controls which keys persist to `~/.claude.json`. It
is a large, fast-growing set, roughly fifty keys with several added most releases, so do not anchor
on the full list. Stable members include `theme`, `editorMode`, `autoUpdates`, `verbose`, `env`,
`diffTool`, `respectGitignore`, `preferredNotifChannel`, and `messageIdleNotifThresholdMs`. Relocate
the array via `rg -n 'messageIdleNotifThresholdMs'`: the array containing that key as a bare string
is the allowlist.

### Project keys (project storage)

Distinct from the settings files, a small allowlist (exported as `PROJECT_CONFIG_KEYS`) governs
project-scoped config storage. It is exactly two keys: `allowedTools` and `hasTrustDialogAccepted`.
The project-storage entry itself holds much more (`mcpServers`, `enabledMcpjsonServers`,
`projectOnboardingSeenCount`, `hasCompletedProjectOnboarding`, the `last*` statistics, and more);
what it holds and how it is keyed is in [Project Files and State](PROJECT_FILES_AND_STATE.md).
Relocate: `rg -n '"allowedTools", "hasTrustDialogAccepted"'`.

### messageIdleNotifThresholdMs

How long Claude Code waits before sending an `idle_prompt` notification ("Claude is waiting for your
input"). Default `60000` (60s), global-only (in `GLOBAL_CONFIG_KEYS`, absent from the project
allowlist), undocumented. The idle notifier reads it twice: as the `setTimeout` delay and as a guard
inside the callback confirming the elapsed idle time still meets the threshold before firing. No
per-project override; the workaround is a wrapper or `.envrc` that sets `CLAUDE_CONFIG_DIR` to a
project-specific dir with a `.claude.json` holding the desired value. Relocate:
`rg -n 'messageIdleNotifThresholdMs|getIdleNotifThresholdMs'`.
