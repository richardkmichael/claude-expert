# @ File Inclusion and Completion

Source: `cli.prettier.js` 2.1.104 (`work/2.1.104/package/cli.prettier.js`)

All function and variable names are minified and will differ
between versions. The guidance below identifies features by stable string literals, log
messages, API patterns, and structural characteristics rather than by name.

---

## Feature Overview

Typing `@` in the prompt triggers a file/resource completion mode. Two sub-mechanisms:

1. File suggestions — fuzzy search of the workspace file tree, powered by git ls-files
   (with a ripgrep fallback) and a custom in-process JavaScript index (`x38`).
2. MCP resource suggestions — drawn from connected MCP servers via `resources/list`.

This document covers the file suggestion mechanism (1) and the TAB completion behavior.

---

## How to Find the Entry Point

Search for the regex literal used to extract the `@...` token from user input. It matches
Unicode word chars, digits, separators, and path characters after `@`:

  Pattern: `@[\p{L}\p{N}\p{M}_\-./\\()[\]~:]*`  (Unicode property escapes)

This regex appears twice — once for unquoted tokens and once for the quoted form `@"..."`.
The function that contains these regexes is the token extractor; it is called whenever the
input changes while `@` mode is active.

A second useful anchor: the completion entry function is the one that checks for
`fileSuggestion?.type === "command"` in the project settings object. This is the first
branch of the file-suggestion dispatcher; the branch that follows handles the empty-query
case, and then the main fuzzy-search path. This function is `rz7(state, query, force)`
in 2.1.104 (was `w5q` in 2.1.76).

---

## File Index Build Pipeline

The pipeline has three layers. Find them by their log messages (stable across minification):

- Layer 1 — git ls-files:
  Look for the log string `"[FileIndex] getFilesUsingGit called"` and nearby
  the spawned git command `["-c", "core.quotepath=false", "ls-files",
  "--recurse-submodules"]`. This function attempts git ls-files first; it returns
  `null` if the directory is not a git repo. If `git ls-files` exits non-zero it logs
  `"[FileIndex] git ls-files failed (code=..., stderr=...), falling back to ripgrep"`
  and also returns `null`. This function is `SkY()` in 2.1.104 (was `qeY()` in 2.1.76).

- Layer 2 — ripgrep fallback:
  The log `"[FileIndex] git ls-files returned null, falling back to ripgrep"` leads to
  the ripgrep invocation. Key signature: an array literal beginning `["--files",
  "--follow", "--hidden", "--glob", "!.git/", ...]` assembled just before the call.
  In 2.1.104 the array also excludes `.svn/`, `.hg/`, `.bzr/`, `.jj/`, and `.sl/`. The
  single directory argument passed to ripgrep is `"."` (cwd). The results are made
  relative to cwd via `path.relative(cwd, absolutePath)`.
  Telemetry event name (also stable): `"tengu_file_suggestions_ripgrep"`.
  This function is `bkY()` in 2.1.104.

- Layer 3 — index assembly:
  The function that awaits both the project-files function (`bkY`) and the `.claude/`
  dir scanner (`CkY`) in a `Promise.all`, then loads the merged paths into the
  in-process `x38` index via `loadFromFileListAsync`. Log:
  `"[FileIndex] cache refresh completed"`.
  Telemetry event: `"tengu_file_suggestions_git_ls_files"`.
  This function is `IkY()` in 2.1.104 (was `zeY()` in 2.1.76).

The `.claude/` scanner (separate from the file tree scanner) is `CkY()`, which iterates
the module-level array `PA4` of subdirectory names and calls `Ta(name, cwd)` for each.
In 2.1.104 the array is `["commands", "agents", "output-styles", "skills", "workflows",
"routines"]` — `workflows` and `routines` were added since 2.1.76. The results are
stored in `state.cachedConfigFiles`.

### git ls-files Always Runs First in a Git Repo

`git ls-files` is invoked unconditionally whenever the cwd is inside a git repository.
The flags are hard-coded as `--recurse-submodules` with no way to include gitignored files.
Because the function returns a non-null value (even an empty array) on success, the ripgrep
fallback is never reached inside a git repo. Setting `respectGitignore: false` (see below)
therefore has no effect on `git ls-files` — it only affects the ripgrep fallback path.

Consequence: files that are gitignored will not appear in `@` completion results when
working inside a git repo, regardless of `respectGitignore`. The `fileSuggestion` hook
(see below) is the only way to override this without patching.

---

## `respectGitignore` Setting

`respectGitignore` is a Claude Code setting (in `settings.json`, under the project or
user config). It is not a ripgrep flag. Its only effect is to conditionally add
`--no-ignore-vcs` to the ripgrep argument array:

```javascript
[source fragment removed]
```

Default is `true` (respect `.gitignore`). Set to `false` to have ripgrep include
gitignored files. However, because ripgrep is only the fallback (Layer 2 above), this
setting has no practical effect inside a git repo — `git ls-files` will have already
returned results, and ripgrep is never called.

Note: ripgrep also respects `.ignore` and `.rgignore` files independently of this setting.
The `--no-ignore-vcs` flag only disables VCS-managed ignore files (`.gitignore`).

---

## Result Limit

All search paths cap results at 15. This constant is `iz7 = 15` in 2.1.104 (was
`rT6 = 15` in 2.1.76). It is applied consistently across every branch of the search
dispatcher:

- `fileSuggestion` hook results:  `.slice(0, iz7)`
- Empty query (`"."` or `""`) readdir results: `.slice(0, iz7)`
- `x38` index search: `fileIndex.search(query, iz7)` — limit passed into the search loop
- `x38` empty-query path: served from `topLevelCache.slice(0, iz7)`

The 15-result limit documented for `fileSuggestion` is therefore not a constraint specific
to that hook — it matches the cap applied to all internal search results.

---

## `fileSuggestion` Hook

`fileSuggestion` is a Claude Code project setting that redirects `@` file completion to
a custom command. It is implemented identically to other hooks (PreToolUse, PostToolUse)
and runs through the same hook runner.

### Configuration

```json
{ "fileSuggestion": { "type": "command", "command": "/path/to/script.sh" } }
```

The hook is short-circuit: when `fileSuggestion.type === "command"` is present, the
entire internal index system (git ls-files, ripgrep, the `x38` index) is bypassed.

### Stdin Payload

The command receives a JSON object on stdin:

```json
{
  "session_id":      "...",
  "transcript_path": "...",
  "cwd":             "/current/working/dir",
  "agent_id":        "...",
  "agent_type":      "...",
  "query":           "the typed text after @"
}
```

The base hook payload comes from `_O()` (which returns `session_id`, `transcript_path`,
`cwd`, `permission_mode`, `agent_id`, `agent_type`) and `query` is then appended. The
`fileSuggestion` dispatcher calls `_O()` with no arguments, so `permission_mode` is
`undefined` and is dropped by `JSON.stringify`. `agent_id` and `agent_type` were added
since 2.1.76 — they reflect the active subagent context, if any.

### Stdout

Return up to 15 newline-separated file paths. Results are displayed directly as completion
suggestions without passing through the internal index. Each line becomes one suggestion
item via the same formatter (`nl6`) used by the internal paths.

### Hook Environment

The command inherits the same environment variables as other hooks, including
`CLAUDE_PROJECT_DIR`.

### Use Case: Gitignored Files

`fileSuggestion` is the recommended way to include gitignored files in `@` completion,
since setting `respectGitignore: false` does not help inside a git repo (see above).
A script that runs `rg --files --no-ignore-vcs` (or `find`) can return any files
regardless of gitignore status.

---

## Ripgrep Binary Selection

Claude Code bundles its own ripgrep binary. The selection logic runs once at startup
(lazy-initialised). This is the `sa6` lazy initialiser in 2.1.104 (was `Z81` in 2.1.76).
Priority order:

1. `USE_BUILTIN_RIPGREP=0` (or `false`/`no`/`off`) env var set:
   Try to find system `rg` via `findActualExecutable`. If found on PATH, use it
   (`mode: "system"`). If not found, fall through to the next option.

2. Running as a packaged executable (`J$()` true):
   Re-exec the host process as ripgrep —
   `{ command: process.execPath, args: ["--no-config"], argv0: "rg", mode: "embedded" }`.
   The `--no-config` flag suppresses `~/.ripgreprc`. If the current `process.execPath` is
   not actually a packaged executable (`pN(process.execPath)` false), prefer system `rg`
   on PATH and only fall back to the embedded form if no system `rg` is found.

3. Default fallback:
   Use the vendored binary at `vendor/ripgrep/{arch}-{platform}/rg`
   (`vendor/ripgrep/{arch}-win32/rg.exe` on Windows). `mode: "builtin"`.

Important: `--no-config` is only passed in mode "embedded". In modes "system" and
"builtin" (vendored), ripgrep will read `~/.ripgreprc` if present. This means setting
`USE_BUILTIN_RIPGREP=0` with a system `rg` and a `~/.ripgreprc` config file is one
way to influence ripgrep's behaviour from outside Claude Code.

The env var name `USE_BUILTIN_RIPGREP` is counter-intuitive: setting it to `0`/`false`
disables use of Claude's bundled binary and enables the system binary. The condition is
checked via an "is disabled" helper that returns `true` for `"0"`, `"false"`, `"no"`,
`"off"`.

Removed since 2.1.76: the separate `RIPGREP_EMBEDDED` env var and the Bun-specific
`process.execPath --ripgrep` invocation are no longer present in 2.1.104. Both have
been collapsed into the single "embedded" mode above.

---

## Workspace Directories

There are two parallel stores for additional workspace directories (added via `--add-dir`
CLI flag or `/add-dir` slash command). Both are updated by both mechanisms:

- A `Map` inside `toolPermissionContext.additionalWorkingDirectories` — the canonical,
  permission-aware store. Updated via a reducer-style function that accepts an action of
  `type: "addDirectories"`. Find this by searching for that string literal.

- A module-level array (the "ClaudeMd" alias) — a convenience copy maintained for
  non-React code that cannot access app state. Find it by searching for the log string
  `"working directory"` in the `/add-dir` command handler, or by looking for the pattern
  `if (!array.includes(newDir)) setArray([...array, newDir])` near the call that updates
  `toolPermissionContext`. The getter is `af()` in 2.1.104 (was `mT()` in 2.1.76):
  `function af() { return T8.additionalDirectoriesForClaudeMd; }`. The matching setter
  is `NB6(q)`.

The file index builder uses only the module-level array (not the Map), because it runs
outside React. Verify by checking which of the two stores the `Promise.all` assembly
function reads.

---

## File Index Implementation (`x38`)

Since 2.1.104 the file index is a single pure-JavaScript class `x38` (defined around
L503985 in 2.1.104). The Rust `.node` native FileIndex and the inlined Fuse.js fallback
that existed in 2.1.76 have both been removed, along with their identifying log
strings (`"[FileIndex] Rust module unavailable, falling back to Fuse.js"` and
`"[FileIndex] Not in bundled mode, using Fuse.js fallback"`).

Identify `x38` by:
- Instance fields `paths`, `lowerPaths`, `charBits` (`Int32Array`), `pathLens`
  (`Uint16Array`), `topLevelCache`, `readyCount`
- Methods `loadFromFileList(paths)` (sync), `loadFromFileListAsync(paths)` (returns
  `{ queryable, done }`), `buildAsync`, `buildIndex`, `indexPath`, `search(query, limit)`
- A 26-bit a-z bitmap built per path: `if (A >= 97 && A <= 122) z |= 1 << (A - 97)`
  in `indexPath`. This bitmap is used as a fast prefilter before character-level matching.

`loadFromFileListAsync` yields back to the event loop every 256 entries (`(O & 255) === 255`)
when a 4 ms budget is exceeded, calling a `Sl8()` cooperative-yield helper. This makes
large-repo index builds non-blocking for the UI.

## External Libraries

### Ink `useInput`

The keypress event layer is Ink's `useInput` hook (React for terminals). Find it in the
exports of the Ink module bundle — look for a `useInput` export alongside `render`,
`useApp`, `useStdin`, `useFocus`. The hook receives a callback `(input, key)` where
`key` has boolean fields: `.tab`, `.return`, `.escape`, `.upArrow`, `.downArrow`, etc.

The completion logic itself is custom code layered on top of Ink — there is no external
autocomplete library.

---

## TAB Completion Dispatch

The autocomplete hook registers keybinding actions: `"autocomplete:accept"`,
`"autocomplete:dismiss"`, `"autocomplete:previous"`, `"autocomplete:next"`. Find these
string literals to locate the keybinding registration and the four callbacks.

`"autocomplete:accept"` maps to the TAB handler. It is an `async useCallback` that
switches on the current suggestion mode string (`"command"`, `"file"`, `"directory"`,
`"agent"`, `"shell"`).

There is also a second ENTER handler (a separate `useCallback`, called in `useInput`
when `key.return` is true) with its own copy of the same mode switch. Both handlers
contain the "file" mode branch that has the directory-completion bug.

### Two Return Paths from `fileSuggestion` vs. Internal Index

Results from the `fileSuggestion` hook and results from the internal index both flow
through the same `"file"` mode handler in the TAB and ENTER dispatch. From the
dispatcher's perspective they are identical: a list of `{ id, displayText, metadata }`
objects. The handler does not know which source produced the results.

Consequence: implementing TAB directory drill-down requires different handling for each
source. The internal index produces directory entries with a trailing path separator —
inserted by the parent-directory adder, which in 2.1.104 is the async function `UhK(q)`
(was `Sg8` in 2.1.76). It walks each path's `dirname` chain via the helper `hkY` into a
`Set`, then returns `[...set].map(z => z + path.sep)`. The `fileSuggestion` hook has no
typed results — a trailing `/` in the returned string is the only signal available.
See TAB_COMPLETION.md for the fix plan.

### Finding the Completion Formatter

Look for a small function (3–4 lines) with the pattern:

  `let suffix = isComplete ? " " : ""`

followed by conditional returns that prepend `@` when `hasAtPrefix` is true, and wrap in
quotes when `needsQuotes` is true. This is the formatter called just before the
cursor-update function in both the TAB and ENTER handlers.

### Directory vs. File Distinction

The "file" mode branch unconditionally sets `isComplete: true` and calls the
close-suggestions function — it does not check whether the selected item is a directory.
The correct check is whether `displayText.endsWith(path.sep)`. Directory entries (inserted
by the parent-directory adder `UhK`) always have a trailing separator.

The "directory" mode handler (for slash-command argument completion) already does this
check correctly — it uses `metadata.type === "directory"`. The "file" mode is missing the
analogous check. See TAB_COMPLETION.md for the fix.

### Common-Prefix Path (partial completion)

When multiple suggestions share a common prefix longer than the current token, the handler
fills in the common prefix and calls the refresh-suggestions function (not the close
function). This is the correct partial-completion path — find it by the
`isComplete: false` call to the formatter immediately above the specific-item selection
block. The specific-item block (where the directory bug lives) follows in the same `else if`.

---

## Cache Invalidation

The file index is cached in module-level variables (not React state). A generation counter
is incremented whenever the cache is invalidated, and async refreshes check it to discard
stale results. Find by the pattern:

  `let generation = counter; ... async work ... if (generation !== counter) return;`

Cache is cleared (counter incremented) on session start/reset. The refresh is triggered
lazily — it is kicked off the first time `generateFileSuggestions` is called without a
warm cache, and also when file-system watch events arrive (untracked files added).

---

## Search Strategy for a New Version

When analyzing a newer version, recommended search order:

1. Find `"[FileIndex]"` log prefix — anchors the entire file-index subsystem
2. Find `"tengu_file_suggestions_ripgrep"` telemetry event — anchors the cwd ripgrep call
3. Find `["--files", "--follow", "--hidden"]` array — anchors the ripgrep argument build
4. Find `"autocomplete:accept"` string — anchors the TAB handler
5. Find `loadFromFileListAsync` together with a `charBits` field — anchors the `x38`
   index class (replaces the older Fuse.js `threshold: 0.5` anchor)
6. Find `type: "addDirectories"` — anchors the workspace directory update logic
7. Find `additionalDirectoriesForClaudeMd` — anchors the module-level extra-dirs getter
8. Find `fileSuggestion?.type === "command"` — anchors the completion entry dispatcher
9. Find the `@[\p{L}...]*` Unicode regex — anchors the token extractor
10. Find `["commands", "agents", "output-styles", "skills", "workflows", "routines"]` —
    anchors the `.claude/` subdirectory scanner (`PA4`)
