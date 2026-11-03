# Claude Code Tools and Execution Architecture

Verified against: cli.prettier.js 2.1.317 (2026-11-03)

TODO:

- Document ALL tool descriptions (the text Claude sees in the API) for ALL tools, since this
  influences:
  - When Claude decides to use the tool
  - HOW Claude uses it (what parameter values it generates)
  - Example: Agent tool description tells Claude to write "highly detailed task description"

## Overview

Claude Code provides tools to the model through the Anthropic API's `tools` parameter. Each built-in
tool is an object built by one shared tool builder, carrying a name, a `searchHint`, input and
output schemas, an `isEnabled()` predicate, and a `create()` that returns the call implementation.

Published reference: https://code.claude.com/docs/en/tools-reference

## How a session's tool list is built

A tool catalog object exposes three functions, under these literal keys:

- `getAllBaseTools` returns the registry: every built-in tool this build can offer.
- `getTools` filters the registry for one session or subagent.
- `assembleToolPool` merges the result with MCP tools, built-ins first, each group sorted, and
  dedupes by name.

Relocate: `rg -n 'getAllBaseTools: [\w$]+, getTools: [\w$]+, assembleToolPool'` lands on the
catalog; the first identifier is the registry function, the second the filter.

### The registry

The registry function returns one array literal. Entries take four shapes:

- Unconditional: a bare tool object.
- Additive-gated: `...(pred() ? [tool] : [])`, e.g. the task tools.
- Nullable slot: `...(x ? [x] : [])`, where `x` is a lazily required tool export. Several slots are
  permanently `null` in shipped builds and contribute nothing.
- Subtractive: `Glob` and `Grep` are listed unconditionally, then filtered through the omit-set (see
  "Embedded search"). A second omit-set filter covers a list of batched tool variants keyed by
  `underlyingV1ToolName`; that list's slot is `null` in shipped builds.

Relocate the subtractive filter with `rg -n '\]\.filter\(\(\w\) => !\w+\(\)\.has\(\w\.name\)\)'`
(one hit, inside the registry).

□ exactly one name-based omit-set filter, over Glob and Grep □ task tools behind one additive gate □
`TodoWrite` listed bare.

### The `getTools` filter

In order:

1. Bare mode (`CLAUDE_CODE_SIMPLE`, set by `--bare`) returns a fixed set instead of the registry:
   `Bash` when the shell is bash-capable, `PowerShell` when its gate passes, `Read`, `Edit`, plus
   `Agent`, `TaskStop`, `SendMessage` and `Workflow` in coordinator mode. Anchor:
   `skipSimpleModeFilter`.
2. `ListMcpResourcesTool`, `ReadMcpResourceTool`, `ReadMcpResourceDirTool` and `StructuredOutput`
   are removed by name (see "MCP tools" and "StructuredOutput").
3. Blanket deny rules (`--disallowedTools`, `permissions.deny`) remove the tools they name.
4. The `WebFetch`-to-subagent swap (see "Web") removes `WebFetch`.
5. Each remaining tool's `isEnabled()` runs; tools returning false drop out. Registry membership is
   necessary but not sufficient: most registry-unconditional tools carry their own `isEnabled()`
   gate.
6. When embedded search is on and `Bash` did not survive steps 3 and 5, `Glob` and `Grep` are added
   back (still subject to deny rules).
7. `WaitForMcpServers` is re-appended when MCP servers are still pending and no `ToolSearch` is in
   the list.

The tool builder's default `isEnabled()` returns true, so a tool without its own predicate passes
step 5.

## Built-in tools

"Registry" is the condition for the tool to be in the registry array. "Notes" gives aliases and,
where checked, the tool's own `isEnabled()` gate. Gates in the Registry column are described under
"Condition gates".

### Files and search

| Tool           | Registry | Notes                                                 |
| -------------- | -------- | ----------------------------------------------------- |
| `Read`         | Always   |                                                       |
| `Write`        | Always   |                                                       |
| `Edit`         | Always   |                                                       |
| `NotebookEdit` | Always   |                                                       |
| `Glob`         | Omit-set | Restored when `Bash` is denied; see "Embedded search" |
| `Grep`         | Omit-set | Restored when `Bash` is denied; see "Embedded search" |
| `LSP`          | LSP gate | Own `isEnabled()`; absent from a plain `-p` session   |

### Execution

| Tool         | Registry           | Notes                             |
| ------------ | ------------------ | --------------------------------- |
| `Bash`       | Bash-capable shell |                                   |
| `PowerShell` | PowerShell gate    | Nullable slot; `isEnabled()` true |

### Web

| Tool        | Registry | Notes                                                              |
| ----------- | -------- | ------------------------------------------------------------------ |
| `WebFetch`  | Always   | Off under `CLAUDE_CODE_DISABLE_WEB_FETCH` or `allow_web_fetch` off |
| `WebSearch` | Always   | Needs the `allow_web_search` policy and a supporting provider      |

`WebSearch` is on for the first-party API and Foundry, off behind a gateway, and on Vertex only for
supported models.

`WebFetch` is moved to a subagent when `CLAUDE_CODE_WEB_FETCH_AGENT` or the flag
`tengu_clever_orbit` is on, `CLAUDE_CODE_SIMPLE` and `CLAUDE_CODE_DISABLE_WEB_FETCH` are unset, the
`allow_web_fetch` policy allows it, the session is not in coordinator mode, the `Agent` tool is
present and not denied, and the `web-fetch` agent type is allowed at this depth. The session then
has no `WebFetch` tool, and a call to it is answered with
`is not available directly in this context` and a pointer to `subagent_type: "web-fetch"`. See
`SUBAGENTS.md` for the `web-fetch` agent.

### Agents, tasks and background work

| Tool         | Registry      | Notes                                             |
| ------------ | ------------- | ------------------------------------------------- |
| `Agent`      | Always        | Alias `Task`; the `init` event lists it as `Task` |
| `Skill`      | Always        | Off when the host disables slash commands         |
| `TaskCreate` | Task flavor   | Plus the todo-tools gate                          |
| `TaskGet`    | Task flavor   | Plus the todo-tools gate                          |
| `TaskUpdate` | Task flavor   | Plus the todo-tools gate                          |
| `TaskList`   | Task flavor   | Plus the todo-tools gate                          |
| `TodoWrite`  | Always        | Flavor off, plus the todo-tools gate              |
| `TaskStop`   | Always        | Aliases `KillShell`, `KillBash`; no `isEnabled()` |
| `GetTask`    | Always        | `isEnabled()` is always false                     |
| `Monitor`    | Nullable slot |                                                   |
| `Workflow`   | Always        | Alias `RunWorkflow`                               |
| `Poll`       | Nullable slot | "wait for and receive queued harness events"      |

`GetTask` is never offered. A call to it is answered with "GetTask is not a tool you can call. A
background command's result reaches you by itself when it finishes".

`TaskOutput` and its aliases `AgentOutputTool`, `BashOutputTool`, `AgentOutput`, `BashOutput` are
gone. They survive only in a set of removed tool names, together with `Frame`, `FrameRead`,
`TeamCreate`, `TeamDelete`, `SuggestBackgroundPR` and `AutofixPr`. A name in that set is skipped
with a debug log when it appears in a `--tools` exclusion (`--tools exclusion names a removed tool`)
or a deny or ask rule (`Permission ... rule names a removed tool`), and is not logged as a missing
loaded tool. Anchors: `"AgentOutputTool"`, `"SuggestBackgroundPR"`.

### Planning and worktrees

| Tool            | Registry      | Notes                                 |
| --------------- | ------------- | ------------------------------------- |
| `EnterPlanMode` | Always        | Shares `ExitPlanMode`'s `isEnabled()` |
| `ExitPlanMode`  | Always        | Absent from a plain `-p` session      |
| `EnterWorktree` | Worktree mode |                                       |
| `ExitWorktree`  | Worktree mode |                                       |

### Messaging and collaboration

| Tool                   | Registry      | Notes                                         |
| ---------------------- | ------------- | --------------------------------------------- |
| `SendMessage`          | Always        | No team or swarm gate                         |
| `ListAgents`           | Nullable slot | Alias `ListPeers`                             |
| `SendUserMessage`      | Always        | Alias `Brief`; own `isEnabled()`              |
| `SendUserFile`         | Always        | `allow_send_file` policy and a feature flag   |
| `SendFile`             | Always        | "send files to another Claude Code session"   |
| `FetchInboxMessage`    | Nullable slot |                                               |
| `SendToProject`        | Nullable slot | Shares a gate with `SendToProjectContext`     |
| `SendToProjectContext` | Nullable slot |                                               |
| `EndConversation`      | Nullable slot | Enabled only for some main-loop models        |
| `WrapUp`               | Always        | "offer the user a next step when a turn ends" |
| `ReadNotifications`    | Always        | Queued external notifications                 |

### Scheduling

| Tool             | Registry | Notes                                                         |
| ---------------- | -------- | ------------------------------------------------------------- |
| `CronCreate`     | Always   |                                                               |
| `CronDelete`     | Always   |                                                               |
| `CronList`       | Always   |                                                               |
| `ScheduleWakeup` | Always   | Dynamic `/loop` pacing                                        |
| `RemoteTrigger`  | Nullable | `allow_remote_sessions` and `allow_routines`; off when remote |

### User interaction and onboarding

| Tool                       | Registry | Notes                                       |
| -------------------------- | -------- | ------------------------------------------- |
| `AskUserQuestion`          | Always   | Off when nobody can answer (e.g. `-p`)      |
| `OfferChromeSetup`         | Always   |                                             |
| `ShareOnboardingGuide`     | Always   |                                             |
| `ShowOnboardingRolePicker` | Always   |                                             |
| `ProposeGoal`              | Always   | Off in background sessions                  |
| `propose_skills`           | Always   | Gated by `CLAUDE_CODE_SKILL_PROPOSALS` etc. |
| `SendFeedback`             | Always   | Own `isEnabled()`                           |
| `ReportFindings`           | Always   | Structured code-review findings             |

### MCP

| Tool                     | Registry         | Notes                                  |
| ------------------------ | ---------------- | -------------------------------------- |
| `ListMcpResourcesTool`   | Stripped         | Alias `ListMcpResources`               |
| `ReadMcpResourceTool`    | Stripped         | Alias `ReadMcpResource`                |
| `ReadMcpResourceDirTool` | Stripped         | Alias `ReadMcpResourceDir`             |
| `WaitForMcpServers`      | Always           | Re-appended while servers are pending  |
| `RefreshMcpTools`        | Env var          | `CLAUDE_CODE_ENABLE_REFRESH_MCP_TOOLS` |
| `SearchMcpRegistry`      | Nullable slot    |                                        |
| `SuggestConnectors`      | Nullable slot    |                                        |
| `ListConnectors`         | Nullable slot    |                                        |
| `ReadWidgetContext`      | Always           | State an MCP App view shared           |
| `ToolSearch`             | Tool search gate | Loads deferred tools                   |

"Stripped" means listed in the registry but removed by `getTools`. The three resource tools reach a
session through the MCP client instead: the first time a connected server advertises the `resources`
capability, they are appended to that server's tool list.

### claude.ai and Claude Design

| Tool               | Registry              | Notes                                      |
| ------------------ | --------------------- | ------------------------------------------ |
| `Artifact`         | Nullable slot         |                                            |
| `ArtifactComments` | Artifact add-on group |                                            |
| `ArtifactData`     | Artifact add-on group |                                            |
| `ArtifactCheck`    | Artifact add-on group |                                            |
| `AppifactRepl`     | Nullable slot         |                                            |
| `Projects`         | Always                | `allow_projects_tool` and a linked project |
| `DesignSync`       | Always                | Own `isEnabled()`                          |
| `ClaudeDesign`     | Traffic mode          | Null under essential-traffic mode          |
| `PublishPlugin`    | Always                | Own `isEnabled()`                          |
| `PushNotification` | Nullable slot         | Flag `tengu_kairos_push_notifications`     |

### Groups

- Plugins and skills, spread in from one list: `SearchPlugins`, `SearchSkills`,
  `SuggestPluginInstall`, `SuggestSkills`, `ListPlugins`, `ListSkills`.
- Memory stores, spread in from one list: `memory_list`, `memory_read`, `memory_write`, sharing one
  `isEnabled()` predicate. Anchor: `"list the memory stores and the documents in them"`.
- Device stubs, spread in from one list: `enable__mcp__claude-in-chrome`,
  `enable__mcp__remote-devices__Claude_Browser`, `enable__mcp__remote-devices__computer`,
  `request_computer`. They answer that the device tools are unavailable, and are enabled under a
  host condition or behind the flag `tengu_merry_tide`. Anchor: `"enable__mcp__claude-in-chrome"`.
- Self-hosted runner tools, behind a one-way launch latch (`setWizardOperatorToolsEnabled`): nine
  tools named `self_hosted_runner_<action>`, e.g. `self_hosted_runner_get_pool`.

### Not registry entries

- `StructuredOutput` is built per request when a caller forces schema-constrained output, and
  `getTools` strips the name if it ever appears. The tool-lookup path treats it, like MCP tool
  names, as expected to be absent from the built-in list.
- `SubagentHandback` is defined outside the registry and does not appear in it.
- MCP tools (`mcp__<server>__<tool>`) come from the MCP client and join in `assembleToolPool`.

### Observed tool lists

A 2.1.317 `claude -p` session with `--setting-sources project` on `claude-haiku-4-5`, signed in to
claude.ai, listed these built-ins in its `system` `init` event: `Bash`, `CronCreate`, `CronDelete`,
`CronList`, `DesignSync`, `Edit`, `EnterWorktree`, `ExitWorktree`, `ListAgents`,
`ListMcpResourcesTool`, `Monitor`, `NotebookEdit`, `PushNotification`, `Read`,
`ReadMcpResourceDirTool`, `ReadMcpResourceTool`, `RemoteTrigger`, `ReportFindings`,
`ScheduleWakeup`, `SendMessage`, `Skill`, `Task`, the four Task tools, `TaskStop`, `ToolSearch`,
`WebSearch`, `Workflow`, `Write`. `WebFetch` was absent because the web-fetch subagent swap was on
for that account. The account-flag-gated entries differ between accounts.

## Condition gates

Gates are described by what drives them. Minified predicate names churn every release, so each gate
names the literal to relocate it by.

Embedded search: on unless the search-tools opt-in is set, or `CLAUDE_CODE_ENTRYPOINT` is
`local-agent`. Its first check parses the literal `"true"` and always passes. Relocate:
`rg -n '^\s+return \w+\.CLAUDE_CODE_ENTRYPOINT !== "local-agent";$'` (one hit, the gate's last
line).

Search-tools opt-in: true when `Glob` or `Grep` is named in `--tools` or `--allowedTools`. The same
statement records the todo-tools opt-in from the five checklist tool names. The single writer sits
in the CLI tool-list parser just after `Ignoring --allowedTools rule`. The setter is exported as
`setSearchToolsOptIn`; the state lives behind `replaceSearchToolsOptIn`.

Bash-capable shell: true on any non-Windows platform; on Windows, only if git-bash is found, via
`CLAUDE_CODE_GIT_BASH_PATH` or the standard install locations. Relocate:
`rg -n 'return [\w$]+\(\) \? "bash" : "powershell"'` sits next to it.

PowerShell gate: off the Windows platform, true only when `CLAUDE_CODE_USE_POWERSHELL_TOOL` is
true-y. On Windows, an explicit `CLAUDE_CODE_USE_POWERSHELL_TOOL` value wins; otherwise true when
git-bash is missing, else the flag `tengu_cobalt_ridge` decides (default off). On Windows a blanket
deny of `Bash` also denies `PowerShell` unless the PowerShell tool is named or enabled explicitly,
with the warning `Denying Bash also turns off the PowerShell tool, so Claude has neither.` Anchors:
`tengu_cobalt_ridge`, `also turns off the`.

LSP gate: parses the literal `"true"`, so it always passes. `LSP` then has its own `isEnabled()`.

Worktree mode: returns true unconditionally. Anchor: `isWorktreeModeEnabled` (an export name).

ClaudeDesign: the registry slot is `null` when the traffic mode is `essential-traffic`, which
`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` selects.

Task list flavor: default on. Only `CLAUDE_CODE_ENABLE_TASKS` set to a false-y value turns it off.
When on, the session checklist is `TaskCreate` / `TaskGet` / `TaskUpdate` / `TaskList`. When off, it
is the single legacy `TodoWrite` tool. Relocate: `rg -n 'CLAUDE_CODE_ENABLE_TASKS === !1'`.

Todo tools available: a second gate, independent of the flavor and applied through `isEnabled()`.
`TaskCreate` and its siblings require flavor on and this gate; `TodoWrite` requires flavor off and
this gate. It passes when any of these holds:

- The session is a background session (`CLAUDE_CODE_SESSION_KIND=bg`) or a background takeover.
- `--tools` or `--allowedTools` names any of `TodoWrite`, `TaskCreate`, `TaskGet`, `TaskUpdate`,
  `TaskList` (the todo-tools opt-in).
- The main-loop model is not resolved yet, or is a Bedrock `application-inference-profile` ID.
- The main-loop model is in a fixed list of older families: `claude-3-opus`, `claude-3-sonnet`,
  `claude-3-haiku`, `claude-3-5-sonnet`, `claude-3-5-haiku`, `claude-3-7-sonnet`, Opus 4.0 through
  4.7, Sonnet 4.0 through 4.6, and `claude-haiku-4-5`. Later families are not in the list.
- `CLAUDE_CODE_ENABLE_TODO_TOOLS` is true-y.

On a model outside the list, with no opt-in, the session has no checklist tool at all. Relocate:
`rg -n 'CLAUDE_CODE_ENABLE_TODO_TOOLS === !0'` lands on the gate's last line; the model set sits
just above it and ends with `"claude-haiku-4-5"`. The tool search hints are
`"manage the session task checklist"` (`TodoWrite`) and `"create a task in the task list"`
(`TaskCreate`). All five tools set `shouldDefer`, so under tool search they appear by name until
loaded.

□ flavor off only on explicit false-y □ model set has 15 entries □ five opt-in names.

The published docs match the source: the tools reference ("Task tool availability"), the Agent SDK
todo-tracking page ("Model availability") and the env-vars page give the same model cut-off, the
opt-in routes, and `CLAUDE_CODE_ENABLE_TASKS=0` selecting `TodoWrite`. The docs say background and
cloud sessions get the tools on every model; the source's background clause is
`CLAUDE_CODE_SESSION_KIND=bg` or a background takeover.

Observed by running 2.1.317 headless (`claude -p`, `--setting-sources project`, the variables unset
unless listed, tool list read from the `system` `init` event). The task set is `TaskCreate`,
`TaskGet`, `TaskList` and `TaskUpdate`. `Task` and `TaskStop` are listed in every row:

| Model and options                                            | Listed                        |
| ------------------------------------------------------------ | ----------------------------- |
| `claude-haiku-4-5`                                           | task set                      |
| `claude-haiku-5-5`                                           | none                          |
| `claude-haiku-5-5`, `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`        | task set                      |
| above plus `CLAUDE_CODE_ENABLE_TASKS=0`                      | `TodoWrite`                   |
| `claude-haiku-5-5`, `--allowedTools TaskCreate`              | task set                      |
| `claude-haiku-5-5`, allow and `--disallowedTools TaskCreate` | task set without `TaskCreate` |
| `TODO_TOOLS=1`, `--disallowedTools TaskCreate`               | task set without `TaskCreate` |

A settings file that sets `CLAUDE_CODE_ENABLE_TODO_TOOLS` in `env` is applied to the process, so it
overrides the inherited environment and has to be excluded when testing the default. A deny rule
removes the named tool after the opt-in has been recorded, so naming a tool in both leaves the other
three enabled. The published docs do not state this interaction.

Subagents: both gates are process-wide, so a subagent's pool contains whichever set the session
registered. A sync subagent keeps the Task tools. A background subagent loses them to the async
built-in filter unless it is an Agent Teams teammate, and `TodoWrite`, which that filter allows, is
not registered under the Task flavor. A background subagent in a Task-flavor session therefore has
no checklist tool. Details in `SUBAGENTS.md`, "Background placement and the async built-in filter".

Related controls:

- `CLAUDE_CODE_TASK_LIST_ID` selects the task list directory. Without it, the list comes from the
  team name, else the session ID.
- `todoFeatureEnabled` is a global-config key ("Enable the todo / task tracking panel"), listed with
  the other `/config` panel keys. Nothing in the gating path reads it.

Tool search gate: the registry includes `ToolSearch` unless the tool search mode resolves to
`standard`. The mode resolves in this order:

1. `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` or the account's `hipaa` compliance setting forces
   `standard`, unless the force override applies.
2. The force override: first-party provider, no `hipaa`, and `ENABLE_TOOL_SEARCH=force` from managed
   settings or the host's policy. It turns tool search on even under
   `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`. Anchor: `isToolSearchForceOverride`.
3. `ENABLE_TOOL_SEARCH`: `auto:0` on, `auto:100` off, `auto` or `auto:N` threshold mode, true-y on,
   false-y off, unset on.

Per request, tool search is still turned off for a model without `tool_reference` support (Sonnet
and Opus before 4, Haiku before 4.5), for a pre-4.5 model on Vertex, for a Foundry deployment that
lacks it, for a conversation that has already run without `ToolSearch` until it is compacted or
cleared, and after the endpoint refused it. Each decision logs `tengu_tool_search_mode_decision`
with a `reason`. Anchor: `Tool search disabled for model`.

The env-truthiness helper accepts `1`/`true`/`yes`/`on`; its false-y twin accepts `0`/`false`/`no`/
`off`. Both return false for unset, so they are not complements; that is how tri-state defaults are
expressed.

## Embedded search (Glob and Grep removal)

On a native build, Claude Code drops the `Glob` and `Grep` tools and routes file search through the
Bash tool instead. The shell snapshot injects `find`, `grep`, and `rg` functions that re-exec the
`claude` binary with a forced `argv[0]`, so one multi-call binary acts as bfs, ugrep, or ripgrep.
See `BASH_TOOL_EXECUTION.md` ("Search-tool wrappers") for the wrapper mechanics and flag sets.

The omit-set is `{Glob, Grep}` when embedded search is on and the shell is bash-capable; otherwise
it is empty. The way back:

- Naming `Glob` or `Grep` in `--tools` or `--allowedTools`. That sets the opt-in, which turns
  embedded search off and restores both tools. A settings-file allow rule does not, and no env var
  or settings key reaches the opt-in.
- Removing `Bash`. When `Bash` is denied (blanket deny rule, `--disallowedTools Bash`) or disabled,
  `getTools` adds `Glob` and `Grep` back.
- A subagent whose resolved tools have no `Bash`: its `tools` entries naming `Glob` or `Grep`
  resolve to the real tools. With `Bash` available, those entries resolve to nothing.
- Windows without git-bash keeps `Glob` and `Grep`, because the omit-set requires a bash-capable
  shell.

Observed at 2.1.317 (`claude -p`): the default session lists neither; `--disallowedTools Bash` lists
`Glob` and `Grep` and no `Bash`; `--allowedTools Grep` lists `Bash`, `Glob` and `Grep`.

Built-in agent prompts branch on the same gate, telling the agent to use `` `find` `` and
`` `grep` `` via Bash instead of the tools. A call to an omitted tool is answered with
`is not available in this session` and the matching Bash command.

`EMBEDDED_SEARCH_TOOLS` does not control this. It is declared in the env schema and nothing reads
it. Setting it has no effect.

□ omit-set is exactly `{Glob, Grep}` □ the opt-in has one writer □ `EMBEDDED_SEARCH_TOOLS` occurs
once.

## Build-artifact caveat

The prettified bundle is extracted from a platform-specific native binary, and the build
constant-folds `process.platform` into the platform singleton: in the darwin-arm64 artifact its
source reads `platform: "darwin"`, so the accessor always returns `"macos"`. Every `=== "windows"`
and `=== "wsl"` branch is therefore dead in that artifact, including the Windows halves of the
bash-capable and PowerShell gates. Read those branches for source semantics, but do not conclude
from one artifact that a platform check is live or dead in general; per-platform bundles differ.
Relocate: `rg -n 'this.platform = "macos"'`.

## Tool descriptions

Tool descriptions are template literals with interpolations for runtime-varying values, and several
tools pick between a full and a lean variant per model. The Read tool's description is
representative: it interpolates the default line cap, includes its PDF sentence only when the model
supports PDFs, and has a lean variant beginning `Reads a file from the local filesystem.` alongside
the full one.

Relocate any tool's description by a distinctive sentence that cannot span an interpolation
boundary, for example `Results are returned using cat -n format`. The verbatim text of every
description is in `PROMPTS_RENDERED.md`; this doc does not duplicate it.

Tripwire: a description sentence that stops matching is either reworded or newly interpolated. Check
for the latter before recording the former as a change.

## Tool execution

### How tools are sent to Claude

Tools are sent in the `tools` array of the Messages API request. See `ANTHROPIC_API_USAGE.md` for
the full request shape and how each field is built.

### Permissions

Every tool call is checked against the tool permission context. The tool-use context exposes it
through `getToolPermissionContext`, which reads `toolPermissionContext` off the current app state
each time it is called, so a permission change made mid-session applies to the next tool call.

Permission modes: `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`. See
`AUTO_MODE_AND_COMMAND_CLASSIFIER.md` for `auto`.

Rules have the form `Tool` or `Tool(specifier)`, with `*` as the wildcard, e.g. `Bash(npm *)`. A
Bash rule ending in `:*` is still read as a prefix rule; an empty prefix is rejected with
`Prefix cannot be empty before :*`. A blanket deny rule removes the tool from the session's tool
list (step 3 of `getTools`); a scoped rule leaves the tool listed and denies matching calls.

## The Agent tool and subagents

See [SUBAGENTS.md](SUBAGENTS.md): built-in agents, agent teams and `SendMessage`, background
placement, the async built-in filter, agent loading and the Agent tool implementation.

## MCP tools

MCP servers provide tools named `mcp__<server>__<tool>`. They are fetched from each connected server
by the MCP client, converted to Claude Code's tool shape, and merged with the built-ins in
`assembleToolPool`. Subagents receive them unless a filter removes them. See `MCP.md`.

## Bash tool

The Bash tool runs a command in the foreground or, with `run_in_background: true`, as a background
task with an ID. A background command's result reaches the model by itself when it finishes; its
output file can be read with `Read`, and `TaskStop` stops it. There is no tool to poll it: `GetTask`
is disabled, and the `taskOutputMaxChars` setting is described as "Deprecated: no longer has any
effect (the TaskOutput tool was removed)". See `BASH_TOOL_EXECUTION.md` and
`BACKGROUND_BASH_TASKS.md`.
