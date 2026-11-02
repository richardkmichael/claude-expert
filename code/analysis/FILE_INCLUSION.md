# @ File Inclusion and Completion

Verified against: cli.prettier.js 2.1.316 (2026-11-02)

This document follows the landmark style in `GUIDELINES.md`: features are identified by
version-stable anchors (literal strings, log messages, `tengu_*` telemetry names, config keys,
behavioral logic) with grep re-location recipes, not by minified symbol names or line numbers, which
churn every release. Several log strings contain an em dash that the prettified bundle spells as the
escape `\u2014`; the recipes below anchor on the text either side of it.

## Feature Overview

Typing `@` in the prompt triggers a file/resource completion mode. The suggestion list merges:

1. File suggestions: fuzzy search of the workspace file tree, powered by git ls-files (with a
   ripgrep fallback) and a custom in-process JavaScript index, or by the `fileSuggestion` hook.
2. Agent suggestions (`<agentType> (agent)`), built from the loaded agent list.
3. MCP resource and resource-template suggestions, drawn from connected MCP servers.

This document covers the file suggestion mechanism (1), how the sources merge, and the TAB
completion behavior.

## Entry Point

The token extractor pulls the `@...` token from user input using a Unicode-property regex:

  `@[\p{L}\p{N}\p{M}_\-./\\()[\]~:]*`

Grep the character class, `rg -nF '\p{L}\p{N}\p{M}_\-./\\()[\]~:'`: expect 5 hits in one block of
regex constants. The last of them matches the token at the cursor, with an alternative for the
quoted form `@"..."`. The query passed on is the token minus its `@` (and minus the quotes for
`@"..."`); a leading `./` is stripped and a leading `~` is expanded.

The completion entry dispatcher is the exported function the bundle also names
`generateFileSuggestionsWithBase` (grep that string to find its export list). In order it:

1. Returns nothing in a diskless session (a cloud-session mode with no local disk,
   `launchOptions.diskless()`).
2. In remote mode, sends the query over the control channel (see "Remote file-suggestions").
3. Returns nothing for an empty query unless the token began with `@` (`showOnEmpty`).
4. Runs the `fileSuggestion` hook when the setting resolves to `type === "command"`. Grep
   `fileSuggestion) : void 0)?.type === "command"`; the setting is read through a resolver that
   honors managed policy (see "`fileSuggestion` Hook").
5. Answers an empty query, `.` or `./` with a plain `readdir` of the cwd (directories get a trailing
   separator; failure logs `[FileSuggestions] readdir failed for cwd`).
6. Otherwise searches the in-process index, logging
   `[FileIndex] generateFileSuggestions: N results in Xms (partial|full index)` and emitting
   `tengu_file_suggestions_query`.

The dispatcher takes a flag that allows the hook; it defaults on. The prompt's `@` completion and
the host's answer to a remote `file_suggestions` control request run with it on. The host-side
`FileSuggestions` call (grep `"FileSuggestions"`) passes it off, so it always uses the internal
index.

## File Index Build Pipeline

Three layers, all locatable by their stable `[FileIndex]` log strings.

Layer 1: git ls-files. Grep `[FileIndex] getFilesUsingGit called`. It spawns git at the repo root
with the argv `["-c", "core.quotepath=false", "ls-files", "--recurse-submodules"]` and a 5-second
timeout, then re-bases every path from the repo root to the cwd (so files outside the cwd appear as
`../…`). It returns null when the directory is not a git repo
(`[FileIndex] not a git repo, returning null`), and also when `git ls-files` exits non-zero
(`[FileIndex] git ls-files failed (code=..., stderr=...), falling back to ripgrep`). When git's raw
output is unchanged since the last scan, the normalized list is reused
(`skipped path normalization`). Telemetry on success: `tengu_file_suggestions_git_ls_files`.

Layer 2: ripgrep fallback. Reached after
`[FileIndex] git ls-files returned null, falling back to ripgrep`. Grep
`tengu_file_suggestions_ripgrep` or the enclosing function's entry log
`[FileIndex] getProjectFiles called, respectGitignore=`. The args are `--files --follow --hidden`
plus a `--glob !<dir>/` pair for each entry of the VCS-directory constant
`[".git", ".svn", ".hg", ".bzr", ".jj", ".sl"]` (grep that array literal; expect 3 hits, the file
index's being next to the `getProjectFiles` log). The search directory passed to ripgrep is the
absolute cwd, and results are made relative to it. Which ripgrep binary runs, and the `--no-config`
it may carry, is decided by the resolver in `RIPGREP.md`.

Layer 3: index assembly. Grep `[FileIndex] cache refresh completed`. The assembly awaits both the
project-files lister (layers 1/2) and the `.claude/` scanner in a `Promise.all`, adds every parent
directory of the merged paths, and loads the result into the in-process index via
`loadFromFileListAsync`.

The `.claude/` scanner (separate from the file-tree scanner) iterates a module-level array of
subdirectory names and calls a per-name reader for each. The array is
`["commands", "agents", "output-styles", "skills", "workflows", "routines"]` (the prettifier puts
one element per line; grep `"output-styles",` and look for the six-element array). Results are
stored on the state object's `cachedConfigFiles` field and merged into the searchable index
alongside the project files. They are absolute paths, so these config files (and their ancestor
directories) are `@`-completable as absolute paths, not an internal-only list.

The per-name reader lists `*.md` files recursively with an in-process directory walker that follows
symlinks and skips circular ones, within a 3-second budget (grep `loadMarkdownFilesFromDir`). It
scans several source roots, each tagged `policySettings` / `userSettings` / `projectSettings`, and
emits `tengu_dir_search`:

- `policySettings`: `<managed-dir>/.claude/<subdir>`, where the managed dir is OS-fixed
  (`/Library/Application Support/ClaudeCode` on macOS, `/etc/claude-code` on Linux,
  `C:\Program Files\ClaudeCode` on Windows). Absent on a normal machine, so it contributes nothing;
  it exists for enterprise-managed deployments. It is skipped when the session takes its managed
  settings from its organization and the user's own account could have written the managed folder
  (grep `not read: this session takes its managed settings from its organization`).
- `userSettings`: `CLAUDE_CONFIG_DIR ?? ~/.claude`, then the `<subdir>`. This is why global
  `~/.claude` config files appear in `@` completion. Gated on the `userSettings` source being on.
- `projectSettings`: every `.claude/<subdir>` on the ancestor chain from the cwd upward (grep
  `getProjectDirsUpToHome: stat`). The walk stops before the home directory, and inside a git repo
  it stops at the repository root, inclusive (for a cwd inside a repo nested in the project's repo,
  at the project's root). `--project-config-root <dir>` starts the walk at that directory instead of
  the cwd. When the cwd is in a linked git worktree whose root has no `.claude/<subdir>`, the main
  repository's `.claude/<subdir>` is added (for worktrees of a bare repository, the bare repository
  directory's own `.claude/<subdir>`; not under `--project-config-root`). Gated on
  `projectSettings`.

A fourth variant, tagged `projectSettings` with `fromAdditionalDirectory`, applies to the `agents`
subdir only: it scans each additional working directory's `.claude/agents` (source
`additionalDirectoriesForClaudeMd`) for agent definitions, minus paths already found in the ancestor
chain (compared after `realpath`). It is not general file search of additional directories: regular
files in additional dirs are never indexed for `@`. Results are deduplicated by inode
(`Skipping duplicate file … same inode already loaded`).

Agent gating: the `agents` subdir is skipped for the `userSettings` and `projectSettings` sources
(including the additional-directory variant) when `policySettings.strictPluginOnlyCustomization` is
`true` or an array containing `"agents"` (grep `strictPluginOnlyCustomization`), so a managed policy
can force agents to come only from plugins and managed sources rather than from user or project
`.claude/agents` files.

### git ls-files runs first in a git repo; untracked files arrive by background fetch

`git ls-files` (with `--recurse-submodules`) is invoked unconditionally whenever the cwd is inside
a git repository and lists tracked files only. Because it returns a non-null value (even an empty
array) on success, the ripgrep fallback is never reached inside a git repo.

Untracked files enter the index through a second, background git call fired after the tracked list
lands: `git ls-files --others` with `--exclude-standard` appended when `respectGitignore` is true
(grep `background untracked fetch`; 10-second timeout). Its results are merged into the index as
the "untracked" component of `[FileIndex] rebuilt index with N tracked + M untracked files`.
Because the fetch is asynchronous, suggestions immediately after a cache refresh can briefly show
tracked files only.

Consequences:

- Untracked-but-not-ignored files do appear in `@` completion inside a git repo (via git, not
  ripgrep).
- With `respectGitignore: false`, `--exclude-standard` is dropped, so gitignored files (including
  those ignored via `core.excludesFile`) appear too. The value resolves per project (see the
  `respectGitignore` section), so a project setting can confine this to one repo.
- Side effect of `false`: the untracked list balloons to include everything git normally ignores
  (`node_modules`, build output, dotfiles), not just the files a user wanted. Since `@` search
  returns only the top 15 matches, a wanted ignored file can surface immediately in a small repo yet
  be crowded out by `node_modules` noise in a large one, even though both indexed it.
- A negation in `.ignore` / `.rgignore` can re-include specific gitignored paths without turning
  `respectGitignore` off (next section).
- The `fileSuggestion` hook (below) remains the override for full control of `@` results.

### `.ignore` / `.rgignore` post-filter and re-include

Independent of git, patterns from `.ignore` and `.rgignore` files in the repo root and the cwd are
parsed and applied as an exclusion filter to both the tracked and untracked lists (grep
`[FileIndex] loaded ignore patterns from` and `applied ignore patterns`). This runs on the git path,
not just the ripgrep fallback, so dropping a `.rgignore` in the repo trims `@` completion even when
`respectGitignore` is false.

Negated patterns (`!pattern`) in those files also re-include gitignored paths. When
`respectGitignore` is true and any loaded `.ignore` / `.rgignore` has a negation, the background
untracked fetch runs a ripgrep listing from the repo root alongside `git ls-files --others`:
`--files --hidden`, one `--glob` per negated pattern (as a whitelist) and per plain pattern (as an
exclusion), plus `--glob !<vcs-dir>` for the VCS directories. Ripgrep's `--glob` overrides beat
`.gitignore`, so this lists the gitignored files the negations name; they are merged into the
untracked list (grep `re-included by .ignore`; the log reads
`background untracked fetch: N files (M re-included by .ignore)`). A failed listing logs
`.ignore re-include listing failed`, reuses the previous result, and is retried after 5 minutes.

## `respectGitignore` Setting

`respectGitignore` is a Claude Code setting, not a ripgrep flag, and not a git config: setting it
changes nothing about the repo (files stay ignored, untracked, and absent from `git status`); it
only alters how Claude lists files internally. Its schema description reads "Whether file picker
should respect .gitignore files (default: true). Note: .ignore files are always respected." It is
read from merged settings first, then the global `~/.claude.json` config object, defaulting to
`true` (grep `respectGitignore ??`; the file index's hit ends `?? !0`). Because the merged-settings
layer wins, a project `.claude/settings.json` (or `settings.local.json`) can scope `false` to one
repo even when the global config sets the opposite. Two effects when false:

- The background untracked fetch drops `--exclude-standard`, so gitignored files enter the index
  inside git repos (the practically significant effect).
- The ripgrep fallback (non-git directories) appends `--no-ignore-vcs`, which disables only
  VCS-managed ignore files; ripgrep still honours `.ignore` and `.rgignore` on its own.

Getting one ignored directory into `@` without touching git: add a negation for it (for example
`!tmp/`) to a `.rgignore` (or `.ignore`) at the repo root and leave `respectGitignore` at its
default `true`. The re-include listing pulls that directory's files in, and `node_modules` and other
ignored bulk stay out. The alternative is `respectGitignore: false` in that repo's
`.claude/settings.json` plus a `.rgignore` listing the bulk ignored dirs (`node_modules/`, build
output) to exclude them again; the post-filter runs on both lists regardless of `respectGitignore`.
A repo-local un-ignore (`!tmp/` in `.gitignore` or `.git/info/exclude`) also works, through
`--exclude-standard`, but makes the files visible to `git status`.

## Symlinked directories

`git ls-files` never traverses a symlink: it records the link as a single entry and does not
enumerate the target's files. Both git invocations behave this way, so git never lists a symlinked
directory's contents inside a git repo, under any `respectGitignore` value (the untracked path is
still `git ls-files --others`, equally symlink-blind). Verified against a worktree with an
`s -> ../shared` link: `git ls-files` and `--others` yield zero `s/…` paths while
`rg --files --follow` and `find -L` enumerate the target. The `.ignore` re-include listing runs
ripgrep without `--follow`, so it does not descend links either.

The non-git ripgrep fallback carries `--follow`, so outside a git repo `@` does descend symlinks
(subject to the same ignore rules: a globally-ignored link name is skipped unless VCS-ignore is
off). Inside a git repo the fallback never runs, so the only way to surface a symlinked directory's
files as `<link>/…` paths is the `fileSuggestion` hook running a link-following lister
(`rg --files --follow`, `find -L`); its output is shown directly, bypassing both git and the
internal index. Adding the link target as a workspace directory does not help: regular files of
additional directories are not indexed at all.

## Result Limit

The file source caps results at 15 (a shared constant). It applies to `fileSuggestion` hook results,
the empty-query `readdir` results, and the index `search(query, limit)` call. The suggestion
assembler then caps the merged list (files, MCP resources, resource templates, agents) at 15 again:

- Empty query (bare `@`): files first, then MCP resources, templates and agents, cut to 15, so a cwd
  with 15 or more entries fills every slot with files.
- Non-empty query: the non-file candidates are fuzzy-matched (Fuse.js, `threshold: 0.6`, MCP
  resources penalized `+0.15`) and sorted together with the files by score, lower first. File scores
  are their rank divided by the result count, so the top file matches stay near the top.

The 15-result limit documented for `fileSuggestion` is therefore not specific to that hook: it
matches the cap on every source and on the merged list.

## `fileSuggestion` Hook

`fileSuggestion` redirects `@` file completion to a custom command (schema description "Custom file
suggestion configuration for @ mentions"). It runs through the same command runner as other hooks,
under the event name `FileSuggestion`.

Configuration:

```json
{ "fileSuggestion": { "type": "command", "command": "/path/to/script.sh" } }
```

The hook short-circuits: when the resolved setting has `type === "command"`, the entire internal
index system (git ls-files, ripgrep, the in-process index) is bypassed for that query.

Resolution and gates. The setting is read through a policy-aware resolver; grep
`policySettings")?.fileSuggestion`. It yields nothing, so `@` falls back to the internal index,
when:

- the managed policy sets `disableAllHooks: true`;
- workspace trust has not been accepted (non-interactive sessions count as trusted).

It yields only `policySettings.fileSuggestion`, ignoring user and project values, in managed-only
hook mode: policy `allowManagedHooksOnly`, `--safe-mode` / `CLAUDE_CODE_SAFE_MODE`, a non-policy
`disableAllHooks: true`, and a few other managed-only states. The runner itself (grep
`Skipping FileSuggestion command execution - workspace trust not accepted`) re-checks
`disableAllHooks`, its disable list (which turns `fileSuggestion` off only in a diskless session)
and trust, then re-resolves the setting.

Scope of the replacement: only the file source. The assembler runs the file source and the agent
source concurrently and merges MCP resource / resource-template suggestions from connected servers,
so the hook replaces only the files: agent (`… (agent)`) and MCP-resource completions are produced
elsewhere and still appear. What the hook does remove is everything the internal file index
contributed, which includes the `.claude/**` config files the dedicated scanner injects (project
`.claude/`, the main repository's when in a linked worktree, additional directories'
`.claude/agents`, global `~/.claude/`, and policy settings). A repo-rooted lister in the hook
re-lists the project's `.claude/` files but not the global `~/.claude/` ones, so those drop out
unless the hook emits them.

Stdin payload: the dispatcher builds the object as the base hook payload plus `query`, and the
runner writes it with `JSON.stringify`. The base builder (grep `scratchpad_dir: ` near
`prompt_id: `) is called with only the session and the cwd, so the command receives:

| Field             | Present                                                              |
| ----------------- | -------------------------------------------------------------------- |
| `session_id`      | always                                                               |
| `transcript_path` | always (blank only in diskless sessions, which never reach the hook) |
| `cwd`             | always                                                               |
| `query`           | always: the typed text after `@`                                     |
| `scratchpad_dir`  | when the session has a scratchpad directory                          |
| `prompt_id`       | when one is set                                                      |
| `agent_type`      | when the main thread runs as an agent (`--agent` / `agent` setting)  |

There is no `hook_event_name`, `permission_mode`, `agent_id` or `effort`: the builder produces the
last three only from the permission-mode and context arguments the dispatcher does not pass, and
`JSON.stringify` drops the `undefined` values.

Stdout: newline-separated file paths; each line is trimmed and blank lines dropped. Results are
displayed directly as completion suggestions without passing through the internal index, ranked in
output order and cut to 15. A non-zero exit, a timeout, or a thrown error
(`File suggestion helper failed`) yields no file suggestions at all; it does not fall back to the
internal index. The timeout is a fixed 5 seconds.

Hook environment: the command inherits the same environment as other hooks, including
`CLAUDE_PROJECT_DIR`.

Published-docs drift: the settings reference (`fileSuggestion`, "Command input and output") shows
the stdin payload as only `{"query": "src/comp"}`. It documents the five-second timeout, the
hook-style environment and the 15-result cap correctly, but not the base hook fields above.

Use case: full control of `@` results. For merely including gitignored files, a `.rgignore` negation
or `respectGitignore: false` suffices (see above); the hook is for anything beyond that, e.g. custom
ranking, filtering, link-following, or non-file sources.

## Ripgrep Binary Selection

Which ripgrep binary the fallback runs (embedded vs system), the `USE_BUILTIN_RIPGREP` switch, the
`--no-config` isolation, and the failure/timeout handling all live in `RIPGREP.md`: that doc is the
canonical reference for ripgrep bundling and selection. The short version relevant here: the
fallback invokes the resolved binary with the resolver's args prepended, so on the packaged native
build it runs the embedded ripgrep with `--no-config` (the user's `~/.ripgreprc` /
`RIPGREP_CONFIG_PATH` is ignored), and with `USE_BUILTIN_RIPGREP=0` plus a system `rg` on PATH it
runs that binary with the user's config honoured. The fallback also opts out of the macOS exclusion
of other apps' data (the walk that logs `ripgrep: leaving other apps' data out of the walk of`).

## Workspace Directories

Two parallel stores hold additional workspace directories (added via the `--add-dir` CLI flag or the
`/add-dir` slash command):

- A `Map` inside `toolPermissionContext.additionalWorkingDirectories`: the canonical,
  permission-aware store, updated via a permission-update action `type: "addDirectories"` (grep that
  string).
- A plain list held by the session host's extensions config, read through
  `additionalDirectoriesForClaudeMd()` and replaced through
  `replaceAdditionalDirectoriesForClaudeMd()` (grep either name). It is empty in a diskless session.

The file index reads neither for file search. Only the `.claude/` scanner reads the
`additionalDirectoriesForClaudeMd` list, and only for the `agents` subdir.

## File Index Implementation

The file index is a single pure-JavaScript class. Grep `loadFromFileListAsync` together with a
`charBits` field to find it.

Identify the class by:

- Instance fields `paths`, `lowerPaths`, `charBits` (`Int32Array`), `pathLens` (`Uint16Array`),
  `nameStarts` (`Uint16Array`), `nameCharBits` (`Int32Array`), `topLevelCache`, `readyCount`,
  `buildGen`.
- Methods `loadFromFileList` (sync), `loadFromFileListAsync` (returns `{ queryable, done }`),
  `buildAsync`, `buildIndex`, `resetArrays`, `indexPath`, `search(query, limit)`.
- A 26-bit a-z bitmap built per path in `indexPath` (char codes 97–122), plus a second bitmap over
  the basename only, used as fast prefilters before character-level matching.

Paths are de-duplicated on load. `buildAsync` yields to the event loop every 256 entries when a ~4
ms budget is exceeded, via a cooperative-yield helper that resolves a `setImmediate` promise.
`queryable` resolves after the first yielded chunk, so searches run against the `readyCount` paths
indexed so far (the `partial index` in the query log). This keeps large-repo index builds
non-blocking for the UI.

### Result ranking (`search`)

`search(query, limit)` is a fuzzy subsequence matcher, not a substring match. Locate it by the
`fuzzScore` field and the `charBits` prefilter. An empty query returns the top-level directory cache
(`topLevelCache`: the first 100 distinct first-path-segment names, sorted
shortest-then-alphabetical), though the dispatcher answers an empty query with `readdir` and never
asks the index. Otherwise the query is cut to 64 characters, and a path is a candidate only if the
query's a-z letters are all present (bitmap prefilter) and the query is an in-order subsequence of
the lowercased path (case-sensitive only when the query has an uppercase letter), matched greedily
left to right. `fuzzScore` (higher ranks higher) sums:

- Base `queryLen * 16`.
- Contiguity: `+4` for each query char immediately after the previous match (no gap).
- Gap penalty: `-(3 + gapLen)` for each gap between matched chars.
- Boundary bonus per matched char (grep the helper returning `8`/`6`/`0`): `+8` at a word boundary
  (the char is preceded by `/ \ - _ .` or a space, or is the first query char at position 0) and
  `+6` at a camelCase boundary (lowercase then uppercase).
- Short-path bonus: `+max(0, 32 - floor(pathLen / 4))`, so shorter paths score much higher and the
  bonus reaches 0 near length 128.

When the greedy match has gaps and starts before the basename, and the basename holds all the
query's letters, the whole query is also matched inside the basename alone; the better of the two
scores counts. A query that names a file therefore ranks its file well even when the directory part
of the path happens to contain the letters first.

Candidates are kept in a size-`limit` min-heap, sorted descending, then normalized to
`score = rank / count` (lower is better), with a small penalty that pushes any path containing
`test` down (`× 1.05`). Consequences for `@` completion: a query that is a path prefix scores near
the ceiling (position-0 + boundary + full contiguity), shorter paths beat deeper ones, and adding a
separator to the query (`@tmp/` vs `@tmp`) collapses fuzzy noise because `/` only matches the real
separator. A bloated index (e.g. `respectGitignore: false` pulling in `node_modules`) hurts ranking
only by adding competitors, not by changing the formula.

## Key handling

The keypress layer is Claude Code's own terminal UI with a keybinding registry, not an external
autocomplete library. Its default bindings include an `Autocomplete` context (grep
`context: "Autocomplete"`) mapping `tab` to `autocomplete:accept`, `escape` to
`autocomplete:dismiss`, `up` to `autocomplete:previous` and `down` to `autocomplete:next`. The
context is active while suggestions are showing. The prompt input's keydown handler receives an
event with `name`, `ctrl`, `shift`, `meta` and `preventDefault()`; it handles ENTER
(`name === "return"`), `ctrl+n` / `ctrl+p`, and TAB when no suggestions are showing.

## TAB Completion Dispatch

The autocomplete hook registers the four `autocomplete:*` actions above. Grep these to locate the
registration and the four callbacks.

`"autocomplete:accept"` maps to the TAB handler, an async callback that switches on the current
suggestion mode (`"command"`, `"mid-command"`, `"custom-title"`, `"directory"`, `"shell"`,
`"agent"`, `"slack-channel"`, `"emoji"`, `"file"`). A separate accept-selection callback, invoked by
ENTER from the keydown handler and by clicking a suggestion, carries its own copy of the same mode
switch. Both contain the `"file"` mode branch with the directory-completion gap.

### Two return paths: `fileSuggestion` hook vs. internal index

Results from the hook and from the internal index both flow through the same `"file"` mode handler
in the TAB and ENTER dispatch. From the dispatcher's view they are identical: a list of
`{ id, displayText, metadata }` with `metadata` holding only a score. The handler does not know
which source produced them.

Consequence: TAB directory drill-down needs different handling per source. The internal index marks
directory entries with a trailing path separator, added by the parent-directory adder, which walks
each path's `dirname` chain into a `Set` and appends `path.sep` to each (the empty-query `readdir`
does the same). The `fileSuggestion` hook has no typed results; a trailing `/` in the returned
string is the only available signal.

### Completion formatter

Grep a small function that destructures `displayText`, `mode`, `hasAtPrefix`, `needsQuotes`,
`isQuoted` and `isComplete`. It appends a trailing space when `isComplete`, prepends `@` when the
token had an `@` prefix, and wraps in `@"…"` when quoting is needed (bash mode omits the `@`). It is
called just before the input-replacement function in both the TAB and ENTER handlers.

### Directory vs. file distinction

The `"file"` mode branch first checks the selected suggestion's metadata for a typed
`{ replacement, partial }` pair (grep `"replacement" in` for the extractor); a `partial: true`
replacement is inserted with the cursor repositioned and suggestions re-requested. In `@` completion
only MCP resource templates emit that metadata; file entries do not. For them the branch inserts the
formatted text with `isComplete: true` (trailing space) and closes the suggestions, with no check
whether the selected item is a directory. The correct check is whether
`displayText.endsWith(path.sep)`; directory entries from the internal index always carry a trailing
separator. The `"directory"` mode handler (slash-command argument and bash-path completion) already
does the analogous check via `metadata.type === "directory"` and re-requests suggestions for a
directory.

### Common-prefix path (partial completion)

In the TAB handler, when no suggestion carries typed `{ replacement, partial }` metadata and all
suggestions share a common prefix longer than the current token, the handler fills in the common
prefix (formatter called with `isComplete: false`) and re-requests suggestions instead of closing.
Find it by the `isComplete: !1` formatter call; the specific-item block (where the directory gap
lives) follows as the `else if`. The ENTER path has no common-prefix step.

## Cache Invalidation

The file index is cached in a module-level state object (not React state), exported as
`globalFileIndexCache`. A `cacheGeneration` counter is incremented on reset, and async refreshes
compare the generation they started with to discard stale results
(`[FileIndex] discarding refresh results` followed by `cache was reset mid-refresh`). The cache is
reset when the conversation is cleared (`/clear`). The prompt input pre-warms the index on mount
(local mode only) and re-runs the open query when a build completes (`indexBuildComplete`).

Refresh is lazy: each suggestion generation calls a refresh gate. It does nothing while a refresh is
in flight or in a diskless session. Otherwise it re-scans when the `.git/index` mtime changed or
more than 5 seconds passed since the last refresh, and skips when the previous scan was slow (>1s)
and no git mtime is available. There is no filesystem watcher feeding the index. The mtime is read
from `<git root>/.git/index`; in a linked worktree or a submodule `.git` is a file, so there is no
mtime signal and only the 5-second window (or, after a slow scan, nothing) triggers a refresh.

New-file latency (why `@` does not see a just-created file immediately): the mtime trigger reads
`.git/index`, which only moves on git operations (stage/commit/checkout), not on creating an
untracked file. So a new untracked file has no mtime signal and surfaces only once the 5-second
staleness window elapses and `@` is reopened. Two further delays stack on top: the untracked list
comes from the background `git ls-files --others` fetch that fires after the tracked scan (see the
untracked-fetch section), and the signature skip suppresses a rebuild until the merged path set
actually changes. A git operation that rewrites `.git/index`, or waiting out the 5-second window,
forces the refresh sooner.

### Signature-based rebuild skip

The cache state carries `loadedTrackedSignature` and `loadedMergedSignature`. A signature is the
cwd, the path count and an FNV-1a-style hash over a sample of the path list (every
`floor(count / 500)`-th path, plus the last one). When a refresh's new signature matches the loaded
one, the rebuild is skipped with one of (grep `skipped index rebuild` and the suffix):

- `[FileIndex] skipped index rebuild` then `tracked paths unchanged`
- `[FileIndex] skipped index rebuild` then `merged paths unchanged`

Because the hash samples at most about 500 paths, a change that keeps the count and touches only
unsampled paths (a rename, say) in a list longer than 500 does not change the signature, and the
rebuild is skipped until something else changes. A successful rebuild logs
`[FileIndex] rebuilt index with N tracked + M untracked files`.

### Remote file-suggestions

In remote mode (the dispatcher checks the remote predicate right after the diskless check, before
the `fileSuggestion` short-circuit) the entire local file-index pipeline is bypassed and suggestions
come from a control-channel RPC. The remote helper sends a `{ subtype: "file_suggestions", query }`
request and returns the resulting `suggestions` array, falling back to `[]` on RPC failure
(`[FileIndex] remote file_suggestions RPC failed`) or when the remote has no control channel. The
viewing side never runs a hook. The host answering the `file_suggestions` request runs the same
dispatcher locally with the hook allowed, so the host's `fileSuggestion` setting applies. Agents and
MCP resources are left out of the merged list in remote mode.

## Search Strategy for a New Version

Recommended grep order:

1. `[FileIndex]`: anchors the entire file-index subsystem.
2. `tengu_file_suggestions_ripgrep`: anchors the ripgrep fallback call.
3. `[FileIndex] getProjectFiles called`: anchors the ripgrep argument build, next to the
   `[".git", ".svn", ".hg", ".bzr", ".jj", ".sl"]` constant. `background untracked fetch`: anchors
   the `git ls-files --others` merge, its `--exclude-standard` gating and the `.ignore` re-include
   listing (`re-included by .ignore`).
4. `autocomplete:accept`: anchors the keybinding defaults and the TAB handler registration.
5. `loadFromFileListAsync` together with a `charBits` field: anchors the index class; `fuzzScore`
   anchors its `search` ranking.
6. `type: "addDirectories"`: anchors the workspace-directory update logic.
7. `additionalDirectoriesForClaudeMd`: anchors the extra-dirs getter.
8. `generateFileSuggestionsWithBase`, then `fileSuggestion) : void 0)?.type === "command"`: anchor
   the completion entry dispatcher and its hook branch.
9. `\p{L}\p{N}\p{M}_\-./\\()[\]~:` (fixed string): anchors the token extractor.
10. `"output-styles",` with the six-element subdir array, and `loadMarkdownFilesFromDir`: anchor the
    `.claude/` subdirectory scanner.
11. `Skipping FileSuggestion command execution - workspace trust not accepted`: anchors the hook
    runner; `scratchpad_dir: ` near `prompt_id: ` anchors the payload builder.

Tripwires (each should hold against a new bundle):

- [ ] git argv is `-c core.quotepath=false ls-files --recurse-submodules`; untracked adds
  `--others`, plus `--exclude-standard` only when `respectGitignore` is true
- [ ] ripgrep fallback args `--files --follow --hidden` plus `--no-ignore-vcs` when false
- [ ] result cap constant is 15 for the file source and for the merged list
- [ ] refresh gate: 5000 ms staleness, 1000 ms slow-scan threshold, `.git/index` mtime
- [ ] `.claude/` subdirs are exactly `commands`, `agents`, `output-styles`, `skills`, `workflows`,
  `routines`
- [ ] the dispatcher calls the payload builder with two arguments, then adds `query`
- [ ] hook timeout 5000 ms; non-zero exit yields no suggestions
- [ ] the TAB and ENTER `"file"` branches still lack a trailing-separator directory check
