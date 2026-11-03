---
verified: 2.1.317
verified_on: 2026-11-03
section: Tools, skills, and execution
style: landmark
scope: >-
  `@` completion: sources and order, path completion, git/ripgrep index, `.ignore` re-include,
  `.claude/**`, `fileSuggestion` payload, caps
landmarks:
  - '[FileIndex]'
  - generateFileSuggestionsWithBase
  - keepDotPrefix
  - 'mcp-template::'
---
# @ File Inclusion and Completion

This document follows the landmark style in `GUIDELINES.md`: features are identified by
version-stable anchors (literal strings, log messages, `tengu_*` telemetry names, config keys,
behavioral logic) with grep re-location recipes, not by minified symbol names or line numbers, which
churn every release. Several log strings contain an em dash that the prettified bundle spells as the
escape `\u2014`; the recipes below anchor on the text either side of it. A literal `\u200C` in an
`rg -F` pattern can be mangled by the shell, so the one recipe that needs it uses a regex.

Scope: what typing `@` in the prompt offers, where each suggestion comes from, and what accepting
one inserts. What a submitted `@` mention turns into (file contents, directory listings, MCP
resource reads, agent and session mentions) is in `AT_MENTION_CONTEXT.md`.

## Feature Overview

Typing `@` at the start of the input or after whitespace (or after the CJK punctuation `。、？！`) opens
completion. The prompt's input handler tries these sources in order, and the first that yields rows
owns the list:

1. Message targets: `@name` rows labelled `send message` for teammates, named background agents and
   other live sessions (see "Message-target rows"). These pre-empt everything below, including for a
   bare `@` when the session has named agents or teammates.
2. Path completion: a token shaped like a path (`./`, `../`, `~/`, `/`, or exactly `~`, `.`, `..`)
   lists one directory's entries (see "Path completion").
3. MCP resource-template argument completion: a token `server:<uri-prefix>` that matches one of the
   server's resource templates asks the server for argument values (see "MCP resources and resource
   templates").
4. The merged list: file suggestions (the in-process index, or the `fileSuggestion` hook), MCP
   resources, MCP resource templates and agents (`<agentType> (agent)`), capped at 15.

Sources 1 and 2 run as you type; sources 3 and 4 run on a 50 ms debounce. `#` (Slack channels, when
a connected MCP server's name contains `slack`) and `:` (emoji shortcodes) are sibling completion
modes, not `@` sources. In shell mode (`!`) `@` tokens are not completed. Rows from mods'
`prompt.autocomplete` hooks are appended below whichever list shows (see "Mod rows").

## Entry Point

The token extractor pulls the `@...` token from user input using a Unicode-property regex:

  `@[\p{L}\p{N}\p{M}_\-./\\()[\]~:]*`

Grep the character class, `rg -nF '\p{L}\p{N}\p{M}_\-./\\()[\]~:'`: expect 5 hits in one block of
regex constants. The last of them matches the token at the cursor, with an alternative for the
quoted form `@"..."`. The query passed on is the token minus its `@` (and minus the quotes for
`@"..."`). The file dispatcher then strips a leading `./` and expands a leading `~`.

A second, narrower regex, `@([\p{L}\p{N}\p{M}\u200C\u200D_-]*)$`, drives the message-target rows
(grep `rg -n 'p\{M\}\\u200C\\u200D_-'`, 1 hit). It has no `/`, `.` or `:`, so typing any of those
ends message-target completion and hands the token to the file sources.

The completion entry dispatcher for files is the exported function the bundle also names
`generateFileSuggestionsWithBase` (grep that string to find its export list). In order it:

1. Returns nothing in a diskless session (a cloud-session mode with no local disk,
   `launchOptions.diskless()`).
2. In remote mode returns nothing for an empty query without `showOnEmpty`, otherwise sends the
   query over the control channel (see "Remote file-suggestions").
3. Returns nothing for an empty query unless the token began with `@` (`showOnEmpty`).
4. Runs the `fileSuggestion` hook when the setting resolves to `type === "command"`. Grep
   `fileSuggestion) : void 0)?.type === "command"`; the setting is read through a resolver that
   honors managed policy (see "`fileSuggestion` Hook").
5. Answers an empty query, `.` or `./` with a plain `readdir` of the cwd, dotfiles included
   (directories get a trailing separator; failure logs `[FileSuggestions] readdir failed for cwd`).
6. Otherwise searches the in-process index, logging
   `[FileIndex] generateFileSuggestions: N results in Xms (partial|full index)` and emitting
   `tengu_file_suggestions_query`.

The dispatcher takes a flag that allows the hook; it defaults on. The prompt's `@` completion, the
host's answer to a remote or SDK `file_suggestions` control request, and the Remote Control bridge's
`onFileSuggestions` run with it on. The host-side `FileSuggestions` served tool (grep
`"FileSuggestions"`) passes it off, so it always uses the internal index.

## Message-target rows

When the text before the cursor matches the `@name` regex above, the input handler builds rows with
id prefix `dm-`, display `@<name>`, and replaces the token with `@<name> ` on accept. Matching is a
prefix match on the name normalized (NFKC, lowercased, whitespace to `-`). Sources, in order:

- Teammates of the current agent team (when agent teams are on), description `send message`.
- Named background agents in the session's agent-name registry, description
  `send message · <status>` (grep `send message \xB7`).
- Other sessions (rows `dm-peer-…`, description `message session · <where> · active … ago`; grep
  `message session`): sessions on this machine, cloud sessions and Remote Control sessions, up to
  20, only for a non-empty partial, never in remote mode. The roster is refreshed at most every 5
  seconds. Gated on `CLAUDE_CODE_HARBOR_KITE` when set, else the `tengu_harbor_kite` flag (default
  on; on Windows also `tengu_harbor_kite_win`), and off when policy sets
  `messagingBeyondOwnAgentsDisabled`.

Because the teammate and named-agent matches use `startsWith` on the partial, an empty partial
matches all of them: a bare `@` in a session with running named agents shows only their rows, and
the file list appears once a typed character stops matching every name. What a submitted session
mention does is in `AT_MENTION_CONTEXT.md`.

## Path completion

A token after `@` that starts `~/`, `/`, `./` or `../`, or is exactly `~`, `.` or `..`, goes first
to the same path completer the shell mode uses (grep `keepDotPrefix`; the predicate is the function
that checks `h.startsWith("~/") ||`). It resolves the token against the cwd (expanding `~`), splits
it into a directory and a name prefix, and reads that one directory:

- dotfiles and dot-directories are left out; directories sort first, then names alphabetically;
- at most 5000 entries are read, then filtered by a case-insensitive name prefix and cut to 10;
- each directory read is cached for 5 minutes (500 directories); a missing or unreadable directory
  caches an empty result for 15 seconds (`Path completion: … is inaccessible`), other failures for
  2.5 seconds (`Failed to scan directory for path completion`);
- a leading `./` is dropped from the inserted text, other prefixes (`~/`, `../`, `/`) are kept.

When it yields rows the list is in `directory` mode: accepting a directory inserts `@<path>/` and
re-opens completion inside it; accepting a file inserts `@<path> `. The insertion never quotes, so a
name containing a space produces an unquoted `@path with space`. When the directory read yields
nothing (no match, or only dotfiles match), the token falls through to the merged list, where the
dispatcher strips `./`, expands `~` and runs a fuzzy index search.

This is the only `@` route into files outside the index: an absolute or `~/` path browses any
readable directory, including additional working directories. The 5-minute cache means a file
created in an already-listed directory can take up to 5 minutes to appear here.

## MCP resources and resource templates

MCP rows come from the app state of connected servers. Both lists drop MCP Apps UI resources (a
`ui://` URI or the `text/html;profile=mcp-app` media type).

- Resources render as `<server>:<uri>`, description from `description`, `name` or the URI.
- Templates render as `<server>:<template up to its first {>` with typed
  `{ replacement, partial: true }` metadata, so accepting one inserts `@server:prefix` (quoted when
  it holds a space) and re-opens completion instead of closing. Grep `mcp-template::`.

Opening `@` also refreshes resource templates for connected servers that have none cached yet.
Before the merged list runs, a token `server:<rest>` whose server has templates is matched against
them: the best match (most resolved variables, then longest literal prefix, then most variables)
names the variable being typed. The server is then asked for values with MCP `completion/complete`
(`ref/resource`, the variable's name and partial value, earlier variables as `context.arguments`),
only when the server declares the `completions` capability; telemetry
`mcp_complete_resource_template`. Up to 15 values come back as rows (`mcp-template-value::`), each
partial when another variable follows. A server reached through a cached client is reconnected for
this (`MCP template completion` is the connect context); repeated failures back off per server, and
a failure logs `Template completion skipped for <server>`. If no template matches but some template
starts with `<rest>`, those templates are offered instead.

## Agents

The agent source is the session's active agent definitions (built-in, plugin, user, project and
managed agents). Each renders as `<agentType> (agent)` (grep `` (agent)`  ``) with the `whenToUse`
text, cut to 60 characters, as its description. A non-empty query keeps agents whose type or display
text contains the query, case-insensitively; the merged-list ranking below then orders them. Because
the display text has a space, accepting one inserts `@"<agentType> (agent)" `.

## Mod rows (`prompt.autocomplete`)

Mods can add rows to any prompt completion, `@` included, through the `prompt.autocomplete` hook
event (grep `"prompt.autocomplete"`). While the prompt input is open in prompt mode it is asked on
every text or cursor change with `{ text, cursor, token, start }` and answers
`{ suggestions: [{ text, label?, description? }] }`. Its rows are appended below Claude Code's own
rows in one list that the arrow keys walk. TAB or ENTER on a selected mod row, TAB when Claude
Code's own list is empty (the top mod row), or a click, replaces the text from the token start to
the cursor with the row's text (telemetry `plugin_function_hooks_autocomplete`; a failure logs
`the row was not taken`). ENTER with only mod rows showing and none selected submits the prompt.
These rows bypass every gate above, including the `fileSuggestion` hook. Mods themselves are covered
in `MODS.md`.

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
project-files lister (layers 1/2) and the `.claude/` scanner in a `Promise.all` under a 10-second
abort signal, adds every parent directory of the merged paths, and loads the result into the
in-process index via `loadFromFileListAsync`.

The `.claude/` scanner (separate from the file-tree scanner) iterates a module-level array of
subdirectory names and calls a per-name reader for each. The array is
`["commands", "agents", "output-styles", "skills", "workflows", "routines"]` (the prettifier puts
one element per line; grep `"output-styles",` and look for the six-element array). Results are
stored on the state object's `cachedConfigFiles` field and merged into the searchable index
alongside the project files. They are absolute paths, so these config files (and every ancestor
directory short of `/`) are `@`-completable as absolute paths, not an internal-only list.

The per-name reader is the shared loader the command, agent, skill and output-style loaders use
(grep `loadMarkdownFilesFromDir`). It lists `*.md` files recursively with an in-process directory
walker that follows symlinks and skips circular ones, within a 3-second budget, then reads and
parses each file: a file over 1 MiB, or not a regular file, is skipped (log
`not a regular file or exceeds`), so it is not `@`-completable either. Results are memoized per
subdirectory and cwd in the loaders' shared cache, so a `.claude/` file added or removed mid-session
shows in `@` only once something clears that cache (the skill, agent and output-style reloads do).
It scans several source roots, each tagged `policySettings` / `userSettings` / `projectSettings`,
and emits `tengu_dir_search`:

- `policySettings`: `<managed-dir>/.claude/<subdir>`, where the managed dir is OS-fixed
  (`/Library/Application Support/ClaudeCode` on macOS, `/etc/claude-code` on Linux,
  `C:\Program Files\ClaudeCode` on Windows). Absent on a normal machine, so it contributes nothing;
  it exists for enterprise-managed deployments. It is skipped when the session takes its managed
  settings from its organization and the user's own account could have written the managed folder
  (grep `not read: this session takes its managed settings from its organization`).
- `userSettings`: `CLAUDE_CONFIG_DIR ?? ~/.claude`, then the `<subdir>`. This is why global
  `~/.claude` config files appear in `@` completion. Gated on the `userSettings` source being on;
  absent in a diskless session.
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

On the git path, patterns from `.ignore` and `.rgignore` files in the repo root and the cwd are
parsed and applied as an exclusion filter to both the tracked and untracked lists (grep
`[FileIndex] loaded ignore patterns from` and `applied ignore patterns`). The filter runs whatever
`respectGitignore` says, so dropping a `.rgignore` in the repo trims `@` completion even when
`respectGitignore` is false. (The non-git ripgrep fallback has no post-filter; ripgrep honours those
files itself.) The filter tests the cwd-relative paths the index holds, with the raw patterns of
both files, so when the cwd is below the repo root an anchored pattern in the root's file is matched
from the cwd, and paths outside the cwd (`../…`) are never filtered.

Negated patterns (`!pattern`) in those files also re-include gitignored paths. When
`respectGitignore` is true and any loaded `.ignore` / `.rgignore` has a negation, the background
untracked fetch runs a ripgrep listing from the repo root alongside `git ls-files --others`:
`--files --hidden`, one `--glob` per negated pattern (as a whitelist, plus a `<dir>/**` companion
glob for a negated directory) and per plain pattern (as an exclusion), plus `--glob !<vcs-dir>` for
the VCS directories. A cwd-level file's patterns are prefixed with the cwd's path from the root.
Ripgrep's `--glob` overrides beat `.gitignore`, so this lists the gitignored files the negations
name; they are merged into the untracked list (grep `re-included by .ignore`; the log reads
`background untracked fetch: N files (M re-included by .ignore)`). A failed or truncated listing
logs `.ignore re-include listing failed`, reuses the previous result, and is retried after 5
minutes.

## `respectGitignore` Setting

`respectGitignore` is a Claude Code setting, not a ripgrep flag, and not a git config: setting it
changes nothing about the repo (files stay ignored, untracked, and absent from `git status`); it
only alters how Claude lists files internally. Its schema description reads "Whether file picker
should respect .gitignore files (default: true). Note: .ignore files are always respected." It is
read from merged settings first, then the global `~/.claude.json` config object, defaulting to
`true` (grep `respectGitignore ??`; the file index's hit ends `?? !0`). Because the merged-settings
layer wins, a project `.claude/settings.json` (or `settings.local.json`) can scope `false` to one
repo even when the global config sets the opposite.

The `/config` row `Respect .gitignore in file picker` reads and writes only the global-config value
(telemetry `tengu_respect_gitignore_setting_changed`). When any settings file sets the key, the row
shows and changes a value the file index ignores.

Two effects when false:

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
`--exclude-standard`, but makes the files visible to `git status`. For a one-off, typing a path
(`@./tmp/`) uses path completion, which reads the directory directly and ignores every ignore file.

## Symlinked directories

`git ls-files` never traverses a symlink: it records the link as a single entry and does not
enumerate the target's files. Both git invocations behave this way, so git never lists a symlinked
directory's contents inside a git repo, under any `respectGitignore` value (the untracked path is
still `git ls-files --others`, equally symlink-blind). Verified against a symlinked directory inside
a git repo: `git ls-files` and `--others` yield no paths under the link while `rg --files --follow`
and `find -L` enumerate the target. The `.ignore` re-include listing runs ripgrep without
`--follow`, so it does not descend links either.

The non-git ripgrep fallback carries `--follow`, so outside a git repo the index does descend
symlinks (subject to the same ignore rules: a globally-ignored link name is skipped unless
VCS-ignore is off). Inside a git repo the index never holds a link's contents; two routes reach
them:

- Path completion: typing `@./<link>/` reads the link's target directory like any other (its
  `readdir` follows the link), one level at a time. In the parent's listing the link itself is typed
  from its directory entry, so it shows as a file without a trailing `/` and accepting it closes the
  list; type the `/` yourself.
- The `fileSuggestion` hook running a link-following lister (`rg --files --follow`, `find -L`); its
  output is shown directly, bypassing both git and the internal index.

Adding the link target as a workspace directory does not help the index: regular files of additional
directories are not indexed at all.

## Result Limit

The file source caps results at 15 (a shared constant). It applies to `fileSuggestion` hook results,
the empty-query `readdir` results, and the index `search(query, limit)` call. The suggestion
assembler then caps the merged list (files, MCP resources, resource templates, agents) at 15 again:

- Empty query (bare `@`): files first, then MCP resources, templates and agents, cut to 15, so a cwd
  with 15 or more entries fills every slot with files.
- Non-empty query: the non-file candidates are fuzzy-matched (Fuse.js, `threshold: 0.6`, weighted
  keys `name` and `agentType` 3, `displayText` and `uriTemplate` 2, `server` and `description` 1;
  MCP resources penalized `+0.15`) and sorted together with the files by score, lower first. File
  scores are their rank divided by the result count, so the top file matches stay near the top.

The other `@` sources have their own caps: path completion 10, resource-template values 15,
peer-session rows 20. The 15-result limit documented for `fileSuggestion` is therefore not specific
to that hook: it matches the cap on the file source and on the merged list.

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
`disableAllHooks: true`, and an organization managed-settings question still unanswered. The runner
itself (grep `Skipping FileSuggestion command execution - workspace trust not accepted`) re-checks
`disableAllHooks`, its disable list (which turns `fileSuggestion` off only in a diskless session;
`--bare` leaves it on) and trust, then re-resolves the setting.

Scope of the replacement: only the file source. The assembler runs the file source and the agent
source concurrently and merges MCP resource / resource-template suggestions from connected servers,
so the hook replaces only the files: agent (`… (agent)`), MCP-resource, message-target and
path-completion rows are produced elsewhere and still appear. What the hook does remove is
everything the internal file index contributed, which includes the `.claude/**` config files the
dedicated scanner injects (project `.claude/`, the main repository's when in a linked worktree,
additional directories' `.claude/agents`, global `~/.claude/`, and policy settings). A repo-rooted
lister in the hook re-lists the project's `.claude/` files but not the global `~/.claude/` ones, so
those drop out unless the hook emits them. A path-shaped token (`@./`, `@~/`, `@/`) that the path
completer can list never reaches the hook.

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
`JSON.stringify` drops the `undefined` values. The `query` is the raw token text: a leading `./` is
not stripped and `~` is not expanded for the hook.

Stdout: newline-separated file paths; each line is trimmed and blank lines dropped. Results are
displayed directly as completion suggestions without passing through the internal index, ranked in
output order and cut to 15. A non-zero exit, a timeout, or a thrown error
(`File suggestion helper failed`) yields no file suggestions at all; it does not fall back to the
internal index. The timeout is a fixed 5 seconds.

Hook environment: the command inherits the same environment as other hooks, including
`CLAUDE_PROJECT_DIR`.

Use case: full control of `@` results. For merely including gitignored files, a `.rgignore` negation
or `respectGitignore: false` suffices (see above); the hook is for anything beyond that, e.g. custom
ranking, filtering, link-following, or non-file sources.

## Published-docs drift

Checked against the published docs on 2026-11-03:

- Settings reference, `fileSuggestion`: shows the stdin payload as only `{"query": "src/comp"}`; the
  command also gets `session_id`, `transcript_path`, `cwd` and the optional fields above. It calls
  the built-in source "fast filesystem traversal"; inside a git repo it is `git ls-files`. Its link
  to "status line and file suggestion gates" points at an anchor the page does not define. The
  five-second timeout, hook-style environment and 15-result cap are correct.
- Settings reference, `respectGitignore`: correct that a settings file wins and the `/config` toggle
  writes `~/.claude.json`. It does not say that `.ignore` / `.rgignore` are always applied, or that
  their negations re-include gitignored files.
- Interactive mode, `@` row: says live sessions on this machine are suggested after one letter; the
  roster also holds cloud and Remote Control sessions, and teammates and named agents are offered on
  a bare `@`. No page describes path completion for `@./`, `@~/` or `@/` (only the shell-mode
  equivalent), nor its 10-row cap, hidden-file exclusion and 5-minute directory cache.
- MCP, "Use MCP resources": does not mention resource templates in `@` completion or the argument
  completion through the server's `completions` capability. Its note that MCP Apps UI resources stay
  out of `@` is correct.
- Subagents: `@"code-reviewer (agent)"` matches the inserted form, and "Named background subagents
  currently running in the session also appear in the typeahead, showing their status" matches the
  message-target rows (accepting one inserts `@<name>`, a message target, not an agent mention).

## Ripgrep Binary Selection

Which ripgrep binary the fallback runs (embedded vs system), the `USE_BUILTIN_RIPGREP` switch, the
`--no-config` isolation, and the failure/timeout handling all live in `RIPGREP.md`: that doc is the
canonical reference for ripgrep bundling and selection. The short version relevant here: the
fallback invokes the resolved binary with the resolver's args prepended, so on the packaged native
build it runs the embedded ripgrep with `--no-config` (the user's `~/.ripgreprc` /
`RIPGREP_CONFIG_PATH` is ignored), and with `USE_BUILTIN_RIPGREP=0` plus a system `rg` on PATH it
runs that binary with the user's config honoured. The fallback also opts out of the macOS exclusion
of other apps' data (the walk that logs `ripgrep: leaving other apps' data out of the walk of`); the
`.ignore` re-include listing does not opt out.

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
`additionalDirectoriesForClaudeMd` list, and only for the `agents` subdir. Files in an additional
directory are reachable from `@` only through path completion with an absolute or `~/` path.

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
context is active while suggestions (or inline ghost text) are showing. The prompt input's keydown
handler receives an event with `name`, `ctrl`, `shift`, `meta` and `preventDefault()`; it handles
ENTER (`name === "return"`) and `ctrl+n` / `ctrl+p` while suggestions show, and TAB while none show
(mid-line slash-command completion, accepting a prompt suggestion, or the thinking-toggle hint on an
empty input). In fullscreen rendering a click on a row accepts it.

## TAB Completion Dispatch

The autocomplete hook registers the four `autocomplete:*` actions above. Grep these to locate the
registration and the four callbacks.

`"autocomplete:accept"` maps to the TAB handler, an async callback that switches on the current
suggestion mode (`"command"`, `"mid-command"`, `"custom-title"`, `"directory"`, `"shell"`,
`"agent"`, `"slack-channel"`, `"emoji"`, `"file"`). A separate accept-selection callback, invoked by
ENTER from the keydown handler and by clicking a suggestion, carries its own copy of the same mode
switch. Both contain the `"file"` mode branch with the directory-completion gap. In `@` completion
the merged list and template rows use `"file"` mode, path completion uses `"directory"` mode, and
message-target rows use `"agent"` mode.

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
only MCP resource templates and their argument values emit that metadata; file entries do not. For
them the branch inserts the formatted text with `isComplete: true` (trailing space) and closes the
suggestions, with no check whether the selected item is a directory. The correct check is whether
`displayText.endsWith(path.sep)`; directory entries from the internal index always carry a trailing
separator. The `"directory"` mode handler (path completion, slash-command argument and bash-path
completion) already does the analogous check via `metadata.type === "directory"` and re-requests
suggestions for a directory, which is why `@./src` then TAB drills into `src/` while `@src` then TAB
on the same directory closes the list with `@src/ `.

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
reset with the other session caches when the conversation is cleared (`/clear`) and when a session
is continued or resumed at startup. The prompt input pre-warms the index on mount (local mode only)
and re-runs the open query when a build completes (`indexBuildComplete`).

Refresh is lazy: each suggestion generation calls a refresh gate. It does nothing while a refresh is
in flight or in a diskless session. Otherwise it re-scans when the `.git/index` mtime changed or
more than 5 seconds passed since the last refresh, and skips when the previous scan was slow (>1s)
and no git mtime is available. There is no filesystem watcher feeding the index. The mtime is read
from `<git root>/.git/index`; in a linked worktree or a submodule `.git` is a file, so there is no
mtime signal and only the 5-second window (or, after a slow scan, nothing until the next reset)
triggers a refresh.

New-file latency (why `@` does not see a just-created file immediately): the mtime trigger reads
`.git/index`, which only moves on git operations (stage/commit/checkout), not on creating an
untracked file. So a new untracked file has no mtime signal and surfaces only once the 5-second
staleness window elapses and `@` is reopened. Two further delays stack on top: the untracked list
comes from the background `git ls-files --others` fetch that fires after the tracked scan (see the
untracked-fetch section), and the signature skip suppresses a rebuild until the merged path set
actually changes. A git operation that rewrites `.git/index`, or waiting out the 5-second window,
forces the refresh sooner. Path completion has its own 5-minute per-directory cache, and the
`.claude/` listing its own loader cache (see above).

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

In remote mode (a session attached to a remote host, or a surface whose workspace is remote; the
dispatcher checks this right after the diskless check, before the `fileSuggestion` short-circuit)
the entire local file-index pipeline is bypassed and suggestions come from a control-channel RPC.
The remote helper sends a `{ subtype: "file_suggestions", query }` request and returns the resulting
`suggestions` array, falling back to `[]` on RPC failure
(`[FileIndex] remote file_suggestions RPC failed`) or when the remote has no control channel or the
client is view-only. The viewing side never runs a hook. The host answering the `file_suggestions`
request runs the same dispatcher locally with the hook allowed, so the host's `fileSuggestion`
setting applies. The same request is part of the SDK control protocol (schema description "Requests
at-mention file autocomplete suggestions for a partial path prefix"); a host that has not registered
a handler answers `onFileSuggestions callback not registered`. In remote mode agents, MCP resources,
resource-template completion, path completion and peer-session rows are left out.

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
9. `\p{L}\p{N}\p{M}_\-./\\()[\]~:` (fixed string): anchors the token extractor; the input handler
   that runs every `@` source is the function using its cursor regex, next to the
   `p\{M\}\\u200C\\u200D_-` (regex) message-target pattern.
10. `"output-styles",` with the six-element subdir array, and `loadMarkdownFilesFromDir`: anchor the
    `.claude/` subdirectory scanner.
11. `Skipping FileSuggestion command execution - workspace trust not accepted`: anchors the hook
    runner; `scratchpad_dir: ` near `prompt_id: ` anchors the payload builder.
12. `keepDotPrefix` and `Failed to scan directory for path completion`: anchor path completion.
13. `mcp-template::`, `mcp_complete_resource_template` and `Template completion skipped for`: anchor
    MCP resource and template rows.
14. `send message \xB7` and `message session`: anchor the message-target rows; `tengu_harbor_kite`
    their peer-session gate.

Tripwires (each should hold against a new bundle):

- [ ] git argv is `-c core.quotepath=false ls-files --recurse-submodules`; untracked adds
  `--others`, plus `--exclude-standard` only when `respectGitignore` is true
- [ ] ripgrep fallback args `--files --follow --hidden` plus `--no-ignore-vcs` when false
- [ ] result cap constant is 15 for the file source and for the merged list; path completion 10
- [ ] refresh gate: 5000 ms staleness, 1000 ms slow-scan threshold, `.git/index` mtime
- [ ] `.claude/` subdirs are exactly `commands`, `agents`, `output-styles`, `skills`, `workflows`,
  `routines`; files over 1048576 bytes skipped
- [ ] the dispatcher calls the payload builder with two arguments, then adds `query`
- [ ] hook timeout 5000 ms; non-zero exit yields no suggestions
- [ ] the TAB and ENTER `"file"` branches still lack a trailing-separator directory check
- [ ] message-target rows are tried before path and file completion; teammate and named-agent rows
  match an empty partial
- [ ] path completion skips dotfiles, caches a directory for 300000 ms, and inserts without quoting
- [ ] the `/config` gitignore row writes only the global config
