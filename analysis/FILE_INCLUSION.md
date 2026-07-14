# @ File Inclusion and Completion

Behavioral model verified against 2.1.207. This document follows the landmark style in
`GUIDELINES.md`: features are identified by version-stable anchors (literal strings, log messages,
`tengu_*` telemetry names, config keys, behavioral logic) with grep re-location recipes, not by
minified symbol names or line numbers, which churn every release. Per-release facts live in the
appendix.

## Feature Overview

Typing `@` in the prompt triggers a file/resource completion mode. Two sub-mechanisms:

1. File suggestions — fuzzy search of the workspace file tree, powered by git ls-files (with a
   ripgrep fallback) and a custom in-process JavaScript index.
2. MCP resource suggestions — drawn from connected MCP servers via `resources/list`.

This document covers the file suggestion mechanism (1) and the TAB completion behavior.

## Entry Point

The token extractor pulls the `@...` token from user input using a Unicode-property regex:

  `@[\p{L}\p{N}\p{M}_\-./\\()[\]~:]*`

It appears twice — once for unquoted tokens and once for the quoted form `@"..."`. Grep that regex
(`rg -n '\\p\{L\}\\p\{N\}'`) to find the token extractor; it runs whenever the input changes while
`@` mode is active.

The completion entry dispatcher is the function that checks whether the `fileSuggestion` setting
resolves to `type === "command"`. That check is the first branch after the remote-mode predicate;
the empty-query case and the main fuzzy-search path follow. Grep
`.fileSuggestion)?.type === "command"` — the setting is read through a resolver helper that lets a
managed `policySettings.fileSuggestion` override the local value (grep
`policySettings")?.fileSuggestion`). The hook runner itself also refuses to run when the hook is on
the disabled list or workspace trust has not been accepted (grep
`Skipping FileSuggestion command execution - workspace trust not accepted`).

## File Index Build Pipeline

Three layers, all locatable by their stable `[FileIndex]` log strings.

Layer 1 — git ls-files. Grep `[FileIndex] getFilesUsingGit called`. It spawns git with the argv
`["-c", "core.quotepath=false", "ls-files", "--recurse-submodules"]`. It returns null when the
directory is not a git repo (`[FileIndex] not a git repo, returning null`), and also when
`git ls-files` exits non-zero (`[FileIndex] git ls-files failed (code=..., stderr=...), falling back
to ripgrep`). Telemetry on success: `tengu_file_suggestions_git_ls_files`.

Layer 2 — ripgrep fallback. Reached after `[FileIndex] git ls-files returned null, falling back to
ripgrep`. Grep `tengu_file_suggestions_ripgrep` or the enclosing function's entry log
`[FileIndex] getProjectFiles called, respectGitignore=`. The args array is
`--files --follow --hidden` plus a `--glob !<dir>/` pair for each of `.git/`, `.svn/`, `.hg/`,
`.bzr/`, `.jj/`, `.sl/` (the prettifier emits one string per line, so grep a single element like
`"!.svn/"`, not the whole array). The search directory passed to ripgrep is the absolute cwd, and
results are made relative to it via `path.relative(cwd, absolutePath)`. Which ripgrep binary runs,
and the `--no-config` it may carry, is decided by the resolver in `RIPGREP.md`.

Layer 3 — index assembly. Grep `[FileIndex] cache refresh completed`. The assembly awaits both the
project-files lister (layers 1/2) and the `.claude/` scanner in a `Promise.all`, then loads the
merged paths into the in-process index via `loadFromFileListAsync`.

The `.claude/` scanner (separate from the file-tree scanner) iterates a module-level array of
subdirectory names and calls a per-name reader for each. The array is
`["commands", "agents", "output-styles", "skills", "workflows", "routines"]`. Results are stored on
the state object's cached-config-files field and merged into the searchable index alongside the
project files — so these config files are `@`-completable file paths, not an internal-only list.

Each subdir is scanned across four source roots, tagged `policySettings` / `userSettings` /
`projectSettings` (grep those literals in the per-name reader):

- `userSettings` — `CLAUDE_CONFIG_DIR ?? ~/.claude` (grep the root helper that returns
  `homedir()/.claude`). This is why global `~/.claude` config files appear in `@` completion.
- `policySettings` — the OS-managed dir (`/Library/Application Support/ClaudeCode` on macOS,
  `/etc/claude-code` on Linux, `C:\Program Files\ClaudeCode` on Windows).
- `projectSettings` — the project `.claude/` dirs, plus a `fromAdditionalDirectory` variant for
  each additional workspace directory's `.claude/`, plus the git-root `.claude/` when it differs
  from the cwd.

Results are deduplicated by inode (`Skipping duplicate file … same inode already loaded`), and each
source is gated by a source-enablement check (`userSettings` / `projectSettings`). The `agents`
subdir is skipped for `userSettings`/`projectSettings` when the agent feature is active, because
agents are surfaced through the separate agent-suggestion source (see the assembler below), not as
file paths.

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
  those ignored via `core.excludesFile`) appear too. The earlier claim that gitignored files can
  never surface inside a git repo is wrong for any version with the background untracked fetch.
  This is uniform: the value is read once from global config (see below), so it applies to every
  repo, not to a single worktree.
- Side effect of `false`: the untracked list balloons to include everything git normally ignores —
  `node_modules`, build output, dotfiles — not just the files a user wanted. Since `@` search
  returns only the top 15 fuzzy matches, a wanted ignored file can surface immediately in a small
  repo yet be crowded out by `node_modules` noise in a large one, even though both indexed it.
- The `fileSuggestion` hook (below) remains the override for full control of `@` results.

### `.ignore` / `.rgignore` post-filter

Independent of git, patterns from `.ignore` and `.rgignore` files in the repo root and the cwd are
parsed and applied as an exclusion filter to both the tracked and untracked lists (grep
`[FileIndex] loaded ignore patterns from` and `applied ignore patterns`). This runs on the git
path, not just the ripgrep fallback — so dropping a `.rgignore` in the repo trims `@` completion
even when `respectGitignore` is false.

## `respectGitignore` Setting

`respectGitignore` is a Claude Code setting, not a ripgrep flag, and not a git config — setting it
changes nothing about the repo (files stay ignored, untracked, and absent from `git status`); it
only alters how Claude lists files internally. It is read from merged settings first, then the
global `~/.claude.json` config object, defaulting to `true` (grep `respectGitignore ??`). Because
the merged-settings layer wins, a project `.claude/settings.json` (or `settings.local.json`) can
scope `false` to one repo even when the global config sets the opposite. Two effects when false:

- The background untracked fetch drops `--exclude-standard`, so gitignored files enter the index
  inside git repos (the practically significant effect).
- The ripgrep fallback (non-git directories) appends `--no-ignore-vcs`, which disables only
  VCS-managed ignore files; ripgrep still honours `.ignore` and `.rgignore` on its own.

Getting one ignored directory into `@` without touching git: rather than un-ignoring it (which
makes it untracked-visible to `git status`), set `respectGitignore: false` in that repo's
`.claude/settings.json` and add a `.rgignore` (or `.ignore`) listing the bulk ignored dirs —
`node_modules/`, build output — to exclude them again. The `.ignore`/`.rgignore` post-filter runs
on both the tracked and untracked lists regardless of `respectGitignore`, so this keeps the index
lean while `false` pulls the wanted directory in, and git's view of the repo is unchanged.

## Symlinked directories

`git ls-files` never traverses a symlink: it records the link as a single entry and does not
enumerate the target's files. Both git invocations behave this way, so a symlinked directory's
contents never appear in `@` completion inside a git repo, under any `respectGitignore` value (the
untracked path is still `git ls-files --others`, equally symlink-blind). Verified against a
worktree with an `s -> ../shared` link: `git ls-files` and `--others` yield zero `s/…` paths while
`rg --files --follow` and `find -L` enumerate the target.

The non-git ripgrep fallback carries `--follow`, so outside a git repo `@` does descend symlinks
(subject to the same ignore rules — a globally-ignored link name is skipped unless VCS-ignore is
off). Inside a git repo the fallback never runs, so the only way to surface a symlinked directory's
files as `<link>/…` paths is the `fileSuggestion` hook running a link-following lister
(`rg --files --follow`, `find -L`); its output is shown directly, bypassing both git and the
internal index. Adding the link target as a workspace directory does not help — those files index
under the target's own path, not the `<link>/` prefix.

## Result Limit

All search paths cap results at 15. The same constant is applied across every branch of the search
dispatcher: `fileSuggestion` hook results, the empty-query readdir results, the index `search(query,
limit)` call, and the index empty-query top-level cache slice. The 15-result limit documented for
`fileSuggestion` is therefore not specific to that hook — it matches the cap on all internal results.

## `fileSuggestion` Hook

`fileSuggestion` redirects `@` file completion to a custom command. It is implemented like other
hooks (PreToolUse, PostToolUse) and runs through the same hook runner.

Configuration:

```json
{ "fileSuggestion": { "type": "command", "command": "/path/to/script.sh" } }
```

The hook short-circuits: when `fileSuggestion.type === "command"` is present, the entire internal
index system (git ls-files, ripgrep, the in-process index) is bypassed.

Scope of the replacement — only the file source. The `@` suggestion list is assembled from several
independent sources: file suggestions (this hook or the internal index), agent suggestions (built
from the loaded agent list, `type: "agent"`), and MCP resource / resource-template suggestions
(from connected servers). The assembler runs the file source and the agent source concurrently and
merges all of them, so the hook replaces only the files — agent (`@agent-…`) and MCP-resource
completions are produced elsewhere and still appear. What the hook does remove is everything the
internal file index contributed, which includes the `.claude/**` config files the dedicated
scanner injects — project `.claude/`, git-root, additional workspace dirs, global `~/.claude/`, and
policy settings. A repo-rooted lister in the hook re-lists the project's `.claude/` files but not
the global `~/.claude/` ones, so those drop out unless the hook emits them.

Stdin payload — the command receives a JSON object whose fields are: `session_id`, `transcript_path`,
`cwd`, `agent_id`, `agent_type`, and `query` (the typed text after `@`). The base payload builder
also produces `permission_mode` and `effort`; the `fileSuggestion` dispatcher calls the builder with
no arguments, so `permission_mode` is `undefined` and dropped by `JSON.stringify`. `agent_id` /
`agent_type` reflect the active subagent context, if any.

Stdout — return up to 15 newline-separated file paths. Results are displayed directly as completion
suggestions without passing through the internal index; each line becomes one suggestion via the
same formatter used by the internal paths.

Hook environment — the command inherits the same environment as other hooks, including
`CLAUDE_PROJECT_DIR`.

Use case: full control of `@` results. For merely including gitignored files,
`respectGitignore: false` suffices (it reaches the untracked fetch inside git repos — see above);
the hook is for anything beyond that, e.g. custom ranking, filtering, or non-file sources.

## Ripgrep Binary Selection

Which ripgrep binary the fallback runs (embedded vs system), the `USE_BUILTIN_RIPGREP` switch, the
`--no-config` isolation, and the failure/timeout handling all live in `RIPGREP.md` — that doc is
the canonical reference for ripgrep bundling and selection. The short version relevant here: the
fallback invokes the resolved binary with the resolver's args prepended, so on the packaged native
build it runs the embedded ripgrep with `--no-config` (the user's `~/.ripgreprc` /
`RIPGREP_CONFIG_PATH` is ignored), and with `USE_BUILTIN_RIPGREP=0` plus a system `rg` on PATH it
runs that binary with the user's config honoured.

## Workspace Directories

Two parallel stores hold additional workspace directories (added via the `--add-dir` CLI flag or the
`/add-dir` slash command):

- A `Map` inside `toolPermissionContext.additionalWorkingDirectories` — the canonical,
  permission-aware store, updated via a reducer action `type: "addDirectories"` (grep that string).
- A module-level array, the convenience copy for non-React code, exposed by a getter that returns
  `additionalDirectoriesForClaudeMd` (grep that field). The matching setter appends new dirs to it.

The file index builder reads only the module-level array (it runs outside React). Verify by checking
which store the `Promise.all` assembly function reads.

## File Index Implementation

The file index is a single pure-JavaScript class. Grep `loadFromFileListAsync` together with a
`charBits` field to find it; the older Rust `.node` FileIndex and the inlined Fuse.js fallback are
gone (their log strings `[FileIndex] Rust module unavailable, falling back to Fuse.js` and
`[FileIndex] Not in bundled mode, using Fuse.js fallback` no longer exist).

Identify the class by:

- Instance fields `paths`, `lowerPaths`, `charBits` (`Int32Array`), `pathLens` (`Uint16Array`),
  `topLevelCache`, `readyCount`.
- Methods `loadFromFileList` (sync), `loadFromFileListAsync` (returns `{ queryable, done }`),
  `buildAsync`, `buildIndex`, `indexPath`, `search(query, limit)`.
- A 26-bit a-z bitmap built per path in `indexPath` (`K |= 1 << (T - 97)` for char codes 97–122),
  used as a fast prefilter before character-level matching.

`loadFromFileListAsync` yields to the event loop every 256 entries (`(O & 255) === 255`) when a ~4 ms
budget is exceeded, via a cooperative-yield helper that resolves a `setImmediate` promise. This keeps
large-repo index builds non-blocking for the UI.

### Result ranking (`search`)

`search(query, limit)` is a fuzzy subsequence matcher, not a substring match. Locate it by the
`fuzzScore` field and the `charBits` prefilter. An empty query returns the top-level directory
cache (`topLevelCache`, ≤100 first-path-segment names, shortest-then-alphabetical). Otherwise a
path is a candidate only if the query's a-z letters are all present (bitmap prefilter) and the
query is an in-order subsequence of the lowercased path (case-sensitive only when the query has an
uppercase letter). `fuzzScore` (higher ranks higher) sums:

- Base `queryLen * 16`.
- Contiguity: `+4` for each query char immediately after the previous match (no gap).
- Gap penalty: `-(3 + gapLen)` for each gap between matched chars.
- Boundary bonus per matched char (grep the helper returning `8`/`6`/`0`): `+8` at a word
  boundary — the char is preceded by `/ \ - _ . ` or space, or is at position 0 — and `+6` at a
  camelCase boundary (lowercase then uppercase).
- Short-path bonus: `+max(0, 32 - floor(pathLen / 4))`, so shorter paths score much higher and the
  bonus reaches 0 near length 128.

Candidates are kept in a size-`limit` min-heap, sorted descending, then normalized to
`score = rank / count` (lower is better) — with a small penalty that pushes any path containing
`test` down (`× 1.05`). Consequences for `@` completion: a query that is a path prefix scores near
the ceiling (position-0 + boundary + full contiguity), shorter paths beat deeper ones, and adding
a separator to the query (`@tmp/` vs `@tmp`) collapses fuzzy noise because `/` only matches the
real separator. A bloated index (e.g. `respectGitignore: false` pulling in `node_modules`) hurts
ranking only by adding competitors, not by changing the formula.

## External Libraries

### Ink `useInput`

The keypress layer is Ink's `useInput` hook (React for terminals). Find it among the Ink exports
alongside `render`, `useApp`, `useStdin`, `useFocus`. The callback `(input, key)` receives a `key`
with boolean fields `.tab`, `.return`, `.escape`, `.upArrow`, `.downArrow`, etc. The completion logic
is custom code on top of Ink — there is no external autocomplete library.

## TAB Completion Dispatch

The autocomplete hook registers keybinding actions `"autocomplete:accept"`, `"autocomplete:dismiss"`,
`"autocomplete:previous"`, `"autocomplete:next"`. Grep these to locate the registration and the four
callbacks.

`"autocomplete:accept"` maps to the TAB handler — an `async useCallback` that switches on the current
suggestion mode (`"command"`, `"file"`, `"directory"`, `"agent"`, `"shell"`). A separate ENTER
handler (invoked from `useInput` when `key.return` is true) carries its own copy of the same mode
switch. Both contain the `"file"` mode branch with the directory-completion bug.

### Two return paths: `fileSuggestion` hook vs. internal index

Results from the hook and from the internal index both flow through the same `"file"` mode handler in
the TAB and ENTER dispatch. From the dispatcher's view they are identical: a list of
`{ id, displayText, metadata }`. The handler does not know which source produced them.

Consequence: TAB directory drill-down needs different handling per source. The internal index marks
directory entries with a trailing path separator — added by the parent-directory adder, which walks
each path's `dirname` chain into a `Set` and appends `path.sep` to each. The `fileSuggestion` hook
has no typed results; a trailing `/` in the returned string is the only available signal. See
TAB_COMPLETION.md for the fix plan.

### Completion formatter

Grep a small (3–4 line) function with `let X = isComplete ? " " : ""`, followed by conditional
returns that prepend `@` when the token had an `@` prefix and wrap in quotes when quoting is needed.
It is called just before the cursor-update function in both the TAB and ENTER handlers.

### Directory vs. file distinction

The `"file"` mode branch first checks the selected suggestion's metadata for a typed
`{ replacement, partial }` pair (grep `"partial" in e` for the extractor); a `partial: true`
replacement is inserted with the cursor repositioned and suggestions left open. Only MCP resource
templates and argument-style suggestions emit that metadata — internal file-index entries do not.
For them the branch falls through to the original behavior: `isComplete: true` and the
close-suggestions call, with no check whether the selected item is a directory. The correct check
is whether `displayText.endsWith(path.sep)`; directory entries (from the parent-directory adder)
always carry a trailing separator. The `"directory"` mode handler (for slash-command argument
completion) already does the analogous check via `metadata.type === "directory"`. See
TAB_COMPLETION.md for the fix.

### Common-prefix path (partial completion)

When multiple suggestions share a common prefix longer than the current token, the handler fills in
the common prefix and calls the refresh-suggestions function (not close). Find it by the
`isComplete: false` call to the formatter immediately above the specific-item selection block; the
specific-item block (where the directory bug lives) follows in the same `else if`.

## Cache Invalidation

The file index is cached in module-level variables (not React state). A generation counter is
incremented on invalidation, and async refreshes check it to discard stale results — find the pattern
`let generation = counter; ... async work ... if (generation !== counter) return;`. Cache is cleared
on session start/reset. Refresh is lazy: each suggestion generation calls a refresh gate that
re-scans when the `.git/index` mtime changed or more than 5 seconds passed since the last refresh,
and skips when the previous scan was slow (>1s) and no git mtime is available. There is no
filesystem watcher feeding the index.

New-file latency (why `@` does not see a just-created file immediately): the mtime trigger reads
`.git/index`, which only moves on git operations (stage/commit/checkout), not on creating an
untracked file. So a new untracked file has no mtime signal and surfaces only once the 5-second
staleness window elapses and `@` is reopened. Two further delays stack on top: the untracked list
comes from the background `git ls-files --others` fetch that fires after the tracked scan (see the
untracked-fetch section), and the signature skip suppresses a rebuild until the merged path set
actually changes. A git operation that rewrites `.git/index`, or waiting out the 5-second window,
forces the refresh sooner.

### Signature-based rebuild skip

The cache state carries `loadedTrackedSignature` and `loadedMergedSignature` hashes (an FNV-1a-style
signature over the merged path list). When a refresh's new signature matches the loaded one, the
rebuild is skipped with one of:

- `[FileIndex] skipped index rebuild — tracked paths unchanged`
- `[FileIndex] skipped index rebuild — merged paths unchanged`

A successful rebuild logs `[FileIndex] rebuilt index with N tracked + M untracked files`.

### Remote file-suggestions

In remote/proxy mode (the dispatcher checks a remote predicate at the top of the completion entry,
before the `fileSuggestion` short-circuit) the entire local file-index pipeline is bypassed and
suggestions come from a control-channel RPC. The remote helper sends a
`{ subtype: "file_suggestions", query }` request and returns the resulting `suggestions` array,
falling back to `[]` on RPC failure (`[FileIndex] remote file_suggestions RPC failed`). Because the
hook short-circuit is checked after the remote-mode branch, a project hook fires only in local mode.

## Search Strategy for a New Version

Recommended grep order:

1. `[FileIndex]` — anchors the entire file-index subsystem.
2. `tengu_file_suggestions_ripgrep` — anchors the ripgrep fallback call.
3. `[FileIndex] getProjectFiles called` — anchors the ripgrep argument build (the args are emitted
   one string per line; single-line array greps miss them). `background untracked fetch` — anchors
   the `git ls-files --others` merge and its `--exclude-standard` gating.
4. `autocomplete:accept` — anchors the TAB handler.
5. `loadFromFileListAsync` together with a `charBits` field — anchors the index class (replaces the
   older Fuse.js `threshold: 0.5` anchor); `fuzzScore` anchors its `search` ranking.
6. `type: "addDirectories"` — anchors the workspace-directory update logic.
7. `additionalDirectoriesForClaudeMd` — anchors the module-level extra-dirs getter.
8. `.fileSuggestion)?.type === "command"` — anchors the completion entry dispatcher.
9. `@[\p{L}...]*` Unicode regex — anchors the token extractor.
10. `["commands", "agents", "output-styles", "skills", "workflows", "routines"]` — anchors the
    `.claude/` subdirectory scanner.

## Per-release notes

- 2.1.207: behavioral model above verified. Anchor drift since 2.1.165: the dispatcher's
  `fileSuggestion` check is now wrapped in a policy-settings-aware resolver, and the hook runner
  gained a workspace-trust gate; the ripgrep fallback args are unchanged but prettify one string
  per line. The TAB `"file"` branch gained the metadata `{ replacement, partial }` path. The
  "Ripgrep Binary Selection" section moved to `RIPGREP.md`.
- 2.1.207: corrected two claims that were already wrong at 2.1.165 (present since at least
  2.1.119): untracked files reach the index via the background `git ls-files --others` fetch, with
  `respectGitignore` gating `--exclude-standard` — so `respectGitignore: false` does surface
  gitignored files inside git repos (confirmed empirically against a repo using
  `core.excludesFile`); and the refresh trigger is the `.git/index` mtime / 5-second gate, not a
  filesystem watcher.
- 2.1.207: documented the `search` ranking formula (`fuzzScore`) and the new-untracked-file
  latency. A repo-local un-ignore (`!tmp/` in `.gitignore` or `.git/info/exclude`) re-includes a
  globally-ignored directory under `--exclude-standard`, so its files enter `@` completion with
  `respectGitignore` left at the default `true` and without the `node_modules` index bloat — both
  verified empirically.
- 2.1.165: behavioral model above verified. The ripgrep fallback searches the absolute cwd (not the
  literal `"."`). The hook payload builder produces an `effort` field in addition to the fields
  listed above.
- The `.claude/` subdir set added `workflows` and `routines` over earlier builds. The single
  pure-JS index class replaced an earlier Rust `.node` FileIndex plus a Fuse.js fallback.
