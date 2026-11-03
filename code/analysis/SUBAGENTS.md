# The Agent Tool and Subagents

Verified against: cli.prettier.js 2.1.317 (2026-11-03)

This document follows the landmark style in `GUIDELINES.md`: it anchors on version-stable strings
(tool names, the tool's `.describe(...)` and prompt strings, config keys, env vars, `tengu_*` names,
behavioral logic) with grep re-location recipes, not on minified symbol names or line numbers, which
churn every release. Verbatim prompt text lives in `PROMPTS_RENDERED.md`; this doc references stable
phrases as anchors rather than reproducing them. Many prompt strings in the bundle store non-ASCII
characters such as an em dash as `\u` escape sequences, so grep a substring that avoids them.

## Agent and Task

The subagent tool's canonical name is `Agent`. `Task` is a retained back-compat alias. Re-locate the
tool object by grepping `searchHint: "delegate work to a subagent"`; it sits beside `name` bound to
the `Agent` constant and `aliases` holding the `Task` constant. The two constants are defined
together in a small module that also holds
`"Launch a new agent to handle complex, multi-step tasks"` and the parameter descriptions. Every
dispatch site accepts either name: the analytics extractor that records `agentCount` and
`agentDescriptions`, and the per-run tool-stats switch, where the two names fall through together.
Existing `Task`-keyed configs still resolve; the tool presents itself as `Agent`.

## The Agent tool

Re-locate the tool object by `searchHint: "delegate work to a subagent"`. Stable properties:

- `isReadOnly()` returns true and `isConcurrencySafe()` returns true. Multiple Agent calls in one
  message run concurrently.
- `maxResultSizeChars` is 100,000 (see truncation below).
- `checkPermissions` returns `allow` in every permission mode except auto mode (and plan mode while
  the auto classifier runs). There it returns `passthrough` with "Agent tool requires permission to
  spawn subagents.", so the auto-mode classifier judges the spawn from
  `(<subagent_type>): <prompt>`. One exception skips the classifier: a spawn of the built-in
  `web-fetch` agent whose prompt names at most 8 URLs, each of which `WebFetch` would itself allow.
  The spawned agent's own tool calls are gated normally.
- `userFacingName` renders the `subagent_type` as the displayed tool name, except `general-purpose`,
  which renders as `Agent`; the built-in `worker`, which renders as `Agent` unless a non-built-in
  definition named `worker` exists; and `web-fetch`, which renders as `Fetch`.

Spawn limits, each refused with a model-facing message:

- Nesting depth. "Subagent nesting limit reached" when the caller's depth reaches the cap:
  `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, else the config `tengu_hazel_trellis`, default 3. The
  per-agent tool filter also drops `Agent` from any agent at the cap.
- Concurrency. "Concurrent subagent limit reached" at `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` running
  subagents, default 20.
- Budget. A spawn after `--max-budget-usd` is spent is refused with "Budget limit reached".

### Input schema

Re-locate via the description string "A short (3-5 word) description of the task". Parameters:

All parameters but `description` and `prompt` are optional.

| Param               | Type    | Notes                                                     |
| ------------------- | ------- | --------------------------------------------------------- |
| `description`       | string  | "A short (3-5 word) description of the task"              |
| `prompt`            | string  | "The task for the agent to perform"                       |
| `subagent_type`     | string  | agent type; omitted means general-purpose                 |
| `model`             | enum    | `sonnet`/`opus`/`haiku`/`fable`; overrides the definition |
| `effort`            | enum    | `low` … `max`; only when explicitly asked                 |
| `run_in_background` | boolean | background is the default; see below                      |
| `name`              | string  | Agent Teams only: spawns a teammate                       |
| `team_name`         | string  | Agent Teams only: "Deprecated; ignored."                  |
| `mode`              | enum    | Agent Teams only: "Deprecated; ignored."                  |
| `isolation`         | enum    | `worktree` (git worktree) or `remote` (cloud CCR session) |

A fork ignores `model`.

Schema shaping:

- `name`, `team_name` and `mode` are deleted from the wire schema unless Agent Teams is enabled.
  Relocate the strip map by `["name", "team_name", "mode"]`. Agent Teams is
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` or `--agent-teams`, plus the gate `tengu_amber_flint`
  (default on).
- `run_in_background` is removed when background agents cannot launch (host-disabled background
  tasks, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, `CLAUDE_CODE_SIMPLE` / `--bare`) and when the fork
  gate forces every spawn into the background (see "Background placement"). Its description reads
  "Agents run in the background by default".
- `model` is removed when `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is set. `inherit` is a definition
  frontmatter value, not a tool parameter.
- `effort` is removed when `CLAUDE_CODE_EFFORT_LEVEL` pins the session effort. With the gate
  `tengu_snappy_pelican` (env `CLAUDE_CODE_SNAPPY_PELICAN`) on, it also accepts the relative values
  `lower` and `higher`, one step from the agent's usual effort. The gate is forced off while
  `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, `CLAUDE_CODE_SUBAGENT_EFFORT` or
  `CLAUDE_CODE_EFFORT_LEVEL` is set. Otherwise a stray `lower`/`higher` is dropped from the input
  before validation.
- `cwd` is defined internally ("Absolute path to run the agent in") but omitted from the schema the
  model sees. A plugin's `agent.spawn` hook can still set it on a spawn.

### The description prompt

The tool's description is assembled dynamically; grep "Each agent type has specific capabilities and
tools available to it". Variants depend on fork mode, whether general-purpose is available, whether
the caller has `SendMessage`, and a lean-prompt mode for some models. Stable phrases (full text in
`PROMPTS_RENDERED.md`):

- Non-fork mode: "When using the ${Agent} tool, specify a subagent_type parameter to select which
  agent type to use. If omitted, the general-purpose agent is used."
- Fork mode: "specify a subagent_type to select an agent: `"fork"` forks yourself", then "any other
  type" or omitting it "starts a fresh agent (general-purpose by default)".
- General-purpose unavailable (absent, or excluded by the allowed agent types): "subagent_type is
  required: the general-purpose agent is not available in this session". An omitted `subagent_type`
  then throws that message with the available list.
- "relay what matters": "The agent's final report is not shown to the user" when agents background,
  else "The agent's final message is returned to you as the tool result; it is not shown to the
  user".
- "Trust but verify: an agent's summary describes what it intended to do, not necessarily what it
  did."
- "you MUST send a single message with multiple ${Agent} tool use content blocks", in the default
  prompt variant only.
- Sections `## When to fork` (fork mode only), `## Writing the prompt`, `## When to use`, and
  `## When not to use` (non-fork only).
- A plan guard: "Do not spawn agents unless the user asks." It applies on the Pro plan, or when
  `CLAUDE_CODE_WITTY_DEWDROP` is set.
- Continuation: "Use ${SendMessage} with the agent's ID or name to continue a previously spawned
  agent" when the caller has `SendMessage`, else "A previously spawned agent cannot be continued
  from here".

## Agent definitions: sources and precedence

Agent definitions come from several sources, merged last-writer-wins by `agentType`. Re-locate the
merge with `rg -n 'source === "projectSettings" && \w+\.fromAdditionalDirectory'`; the function
groups definitions by source and writes them into a map in precedence order. Lowest to highest:

```
built-in  <  plugin  <  userSettings  <  projectSettings  <  flagSettings  <  policySettings
```

So a project agent overrides a user agent of the same type; policy settings override everything.
Within `projectSettings`, agents from `--add-dir` directories rank below the project's own. Loading
locations: user/project agents live in a `.claude/agents` directory; plugin agents in the plugin's
`agents/` subdir or manifest-declared paths (validated with the recurring error fragment "specified
in manifest but").

Markdown frontmatter an agent definition supports (grep the validation strings 'Missing required
"name" field in frontmatter' / 'Missing required "description" field in frontmatter'): `name`,
`description` (both required), `tools` (`["*"]` = all), `disallowedTools`, `model` (`inherit` or a
model name), `effort` (level or integer), `permissionMode`, `color`, `mcpServers`, `hooks`,
`maxTurns`, `autoCompactWindow`, `skills`, `initialPrompt`, `memory` (`user`/`project`/`local`),
`background`, `omitClaudeMd`, `isolation` (`worktree` or `remote`), `observer`, `observerMessage`,
`observeSubagents`. A `name` must not start with `-` or contain `:`. JSON-sourced (flag) definitions
supply `prompt` in place of the markdown body.

Plugin agents ignore `permissionMode`, `hooks`, `mcpServers`, `initialPrompt`, `observer`,
`observerMessage` and `observeSubagents`, logging that the key "is ignored for plugin agents", and
accept only `worktree` isolation.

`memory` gives the subagent its own persistent memory directory and auto-appends
`Read`/`Edit`/`Write`; mechanics are in `AGENT_MEMORY.md` (shared machinery in `MEMORY_SYSTEM.md`).

## Availability in headless (`-p`) mode

The Agent tool works in `claude -p` as in interactive mode, gated by the same
`--allowedTools`/`--disallowedTools` mechanism as any other tool. Include `Agent` (or its `Task`
alias) and a nested `-p` session can spawn subagents. Project (`.claude/agents/`) and user
(`~/.claude/agents/`) definitions load the same way, since headless mode reads the same
`CLAUDE_CONFIG_DIR` and project directory unless a caller overrides them.

The built-in set differs. A non-interactive launch sets `CLAUDE_CODE_ENTRYPOINT` to `sdk-cli` when
the caller left it unset or set it to `cli` (relocate with `rg -n '"sdk-cli" : "cli"'`), and
`claude-code-guide` is not registered for the `sdk-ts`, `sdk-py` and `sdk-cli` entrypoints. So a
plain `claude -p` session has no `claude-code-guide`, while a caller that sets another entrypoint
(for example `claude-desktop` or `local-agent`) keeps it. `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS`
in a non-interactive session removes every built-in agent.

Background is the default in `-p` too. The fork gate is on in `-p` (see "Background placement"), but
it does not force spawns into the background there, so `run_in_background` stays in the schema. A
spawn from the main thread that omits it still runs in the background. A spawn from a subagent in a
non-interactive session defaults to foreground. A `-p` invocation is a single round-trip with no
later turn to check a background agent's result, so a script that needs a spawned subagent's work
(e.g. a commit) to have landed before the process exits should have the calling prompt ask for
`run_in_background: false`. A definition with `background: true` still runs in the background.

## Built-in agents

Relocate the default list with `rg -n 'CLAUDE_CODE_ENTRYPOINT !== "sdk-ts"'`; the enclosing function
builds the list. In order:

- `general-purpose`, always.
- `statusline-setup`, unless safe mode (`CLAUDE_CODE_SAFE_MODE` or `--safe-mode`).
- `claude`, unless agent view is disabled (`CLAUDE_CODE_DISABLE_AGENT_VIEW` or the
  `disableAgentView` setting).
- `Explore` and `Plan`, unless `CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS`.
- `web-fetch`, when `CLAUDE_CODE_WEB_FETCH_AGENT` or the gate `tengu_clever_orbit` is on, web fetch
  is allowed by policy, and neither `CLAUDE_CODE_SIMPLE` nor `CLAUDE_CODE_DISABLE_WEB_FETCH` is set.
- `claude-code-guide`, unless `CLAUDE_CODE_ENTRYPOINT` is `sdk-ts`, `sdk-py` or `sdk-cli`.

Coordinator mode (`CLAUDE_CODE_COORDINATOR_MODE`) replaces the whole list with the single `worker`
agent. `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS` in a non-interactive session empties it. `fork` and
`workflow-subagent` are not in the list: `fork` is selected by `subagent_type: "fork"`, and
`workflow-subagent` runs Workflow scripts.

Model "default" means the definition sets none: the agent runs on the configured default subagent
model, else the parent's (see "Subagent model" below). `bubble` is the definition's
`permissionMode`.

| Agent type          | Model                | Tools                 | Role                       |
| ------------------- | -------------------- | --------------------- | -------------------------- |
| `general-purpose`   | default              | `["*"]`               | used for an omitted type   |
| `statusline-setup`  | `sonnet`             | `Read`, `Edit`        | configures the status line |
| `claude`            | default              | `["*"]`               | catch-all                  |
| `Explore`           | `inherit`, opus cap  | wildcard minus writes | read-only search           |
| `Plan`              | `inherit`            | same as Explore       | read-only planning         |
| `web-fetch`         | `haiku` or `inherit` | `WebFetch`            | reads URLs; maxTurns 15    |
| `claude-code-guide` | `haiku`              | explicit list, below  | product questions          |
| `worker`            | default              | `["*"]`, maxTurns 500 | coordinator only; `bubble` |
| `fork`              | `inherit`            | parent's exact tools  | explicit only; `bubble`    |
| `workflow-subagent` | default              | `["*"]` minus three   | Workflow orchestration     |

`workflow-subagent` disallows `Agent`, `Workflow` and `SendUserMessage`. `fork` has maxTurns 200.
The `claude` agent's `whenToUse` reads "Catch-all for any task that doesn't fit a more specific
agent. FleetView's default when no agent name is typed."

Notes:

- `Explore` and `Plan` disallow `Agent`, `Artifact`, `ArtifactComments`, `ArtifactData`,
  `ArtifactCheck`, `ExitPlanMode`, `Edit`, `Write` and `NotebookEdit`, and set `omitClaudeMd`.
  `Explore` has a shorter `whenToUseLean` description for lean prompts. Its inheritance is capped
  (see "Subagent model"). Their result handling is special-cased (grep
  `new Set(["Explore", "Plan"])`).
- `web-fetch` runs on `haiku` when a first-party condition and the gate `tengu_nimble_wren` hold,
  otherwise `inherit`. It never takes isolation, defaults to foreground, sets `omitClaudeMd`, and
  renders as "Fetching in background" when backgrounded.
- Agent Teams teammates are not built-ins. An in-process teammate gets a synthesized definition
  named after the teammate (`whenToUse` "In-process teammate: <name>", source `projectSettings`).

### Subagent model

Relocate the resolver with `rg -n '\[\w+, "frontmatter"\]'` (one hit): that line sits in the
function that labels the winning source `tool`, `frontmatter`, `env` or `inherit` and logs
`subagent_model_resolve`. A non-fork subagent's model resolves in this order:

1. the Agent tool call's `model`;
2. the agent definition's `model`, where `inherit` means the parent's model;
3. `CLAUDE_CODE_SUBAGENT_MODEL` (unless `inherit`), only when the definition sets no model;
4. otherwise the parent's model.

`CLAUDE_CODE_SUBAGENT_MODEL_FORCE` drops the first two, keeping only an explicit `inherit` from the
tool call, so the env model or the parent's model applies; it also removes `model` from the tool
schema. Inside a Workflow run, `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` (unless `inherit`) replaces the
first two. An alias that names the parent's own family resolves to the parent's exact model. A model
outside the `availableModels` allowlist steps down within its family or falls back to the parent's
model, with the warning "is not in the availableModels allowlist". A fork always runs on the
parent's model.

Explore's `model: "inherit"` carries a cap. Relocate it with
`rg -nF 'CLAUDE_CODE_DISABLE_EXPLORE_INHERIT_CAP) return "inherit"'`: on the first-party API,
when the parent's model belongs to a catalog family ranked above Opus, Explore runs on `opus`
instead. `CLAUDE_CODE_DISABLE_EXPLORE_INHERIT_CAP` lifts the cap, and other providers inherit
uncapped. Under `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` the cap survives only while
`CLAUDE_CODE_SUBAGENT_MODEL` is unset. Plan inherits uncapped.

The resolved model also selects the Bash tool's description, and with it the git instructions a
subagent sees: `GIT_USAGE.md`, "Subagents and the Model Axis".

### claude-code-guide

Its availability, model, tools, documentation sources and prompt, and the related bundled
`claude-code-docs` skill, are in `CLAUDE_CODE_GUIDE.md`. Relocate the definition with
`rg -n 'You are the Claude guide agent.'`.

## Subagent tool set and MCP tools

Pool. A non-fork subagent's pool is rebuilt at spawn from the built-in tools plus the connected MCP
tools in app state and the parent's own MCP tools, through the same deny-rule filter the main thread
uses, with the parent's permission context. Relocate with
`rg -n 'getAppState\(\)\.mcp\.tools\.concat\('`; the helper it calls wraps
`toolCatalog.assembleToolPool(`. A `permissions.deny` rule hides a tool from main thread and
subagents alike. No settings-level rule scope targets subagents only.

Base filter. A per-agent filter then runs over the pool. Its first test drops account-memory MCP
tools the agent's memory mode excludes; its second passes any tool whose name starts with `mcp__`
(or that has `isMcp`) before the built-in-only checks run, including the check that narrows
background (async) subagents to a short built-in list. MCP tools therefore survive the base filter
for every agent type, sync or background. Relocate the predicate with
`rg -n -A1 'function \w+\(e\) \{$' | rg 'startsWith\("mcp__"\) \|\| e.isMcp'` and the filter by its
destructured parameters `isTeammate`, `agentDepth`, `subagentMemoryMode`.

`tools` and `disallowedTools`. The resolver applies `disallowedTools` first, then `tools`. Relocate
it by the result fields `hasWildcard`, `invalidTools`, `unavailableTools`, `resolvedTools`.

- `tools` omitted, or `"*"` with only `Agent(type1,type2)` entries beside it, is a wildcard: the
  agent receives the whole filtered pool, MCP tools included. The `Agent(...)` entries restrict
  spawnable agent types.
- `tools` as an explicit list keeps only the named tools. MCP tools must be named: an exact
  `mcp__server__tool`, or a server-level `mcp__server` / `mcp__server__*`. `mcp__*` is not
  recognized in `tools`. A server-level entry that matches no connected server logs "takes no tool:
  no connected MCP server of that name has one."
- Embedded search drops `Glob` and `Grep` from the session on a native build (see
  `TOOLS_AND_EXECUTION.md`, "Embedded search"). An explicit list whose resolved tools have no `Bash`
  still receives the real `Glob`/`Grep` tools for entries naming them, unless the agent disallows
  them; with `Bash` resolved, those entries resolve to nothing. Denying or disabling `Bash` for the
  session puts `Glob` and `Grep` back into the session's tool set, and so into the pool subagents
  draw from. A list that resolves `Bash`, `PowerShell` or `REPL` also receives `GetTask`.
- `disallowedTools` removes exact names, `mcp__server`, `mcp__server__*`, and `mcp__*` (every MCP
  tool). Relocate its matcher by the returned `isServerLevelDisallowed`.
- Agent-frontmatter `mcpServers` tools are appended after resolution. They are filtered by
  `disallowedTools` but not by the `tools` allowlist. Relocate with
  `rg -n 'Skipping frontmatter MCP servers'`.

MCP column: whether the agent receives the session's MCP tools.

| Agent type          | `tools`                        | `disallowedTools`           | MCP |
| ------------------- | ------------------------------ | --------------------------- | --- |
| `general-purpose`   | `["*"]`                        | —                           | yes |
| `claude`            | `["*"]`                        | —                           | yes |
| `Explore`           | omitted (wildcard)             | Agent, Artifact, edit tools | yes |
| `Plan`              | omitted (wildcard)             | same as Explore             | yes |
| `statusline-setup`  | `Read`, `Edit`                 | —                           | no  |
| `claude-code-guide` | Glob/Grep or Bash, Read, Web\* | —                           | no  |
| `web-fetch`         | `WebFetch`                     | —                           | no  |
| `fork`              | parent's exact tool array      | —                           | yes |

`Web*` is `WebFetch` and `WebSearch`.

Fork. A fork launch passes the parent's `options.tools` as `availableTools` with `useExactTools`,
which skips the filter and the resolver, so a fork has the parent's exact tool array including MCP
tools. Relocate with `rg -n -B1 '&& \{ useExactTools: !0 \}'` (two hits) and keep the one whose
previous line sets `forkContextMessages`.

Hiding one MCP tool from subagents only:

- Custom agents: `disallowedTools: mcp__server__tool` (or `mcp__server` for the whole server).
- Built-ins: a user or project agent file with the same `name` overrides the built-in by the
  definition precedence above, so it can add `disallowedTools`. It replaces the built-in system
  prompt as well.
- A PreToolUse hook matching the tool can deny when the input has `agent_id`. The hook runs at
  call time, so the tool stays in the subagent's tool list and the model receives the denial as
  the tool result.

Hooks inside subagents. A subagent runs tools through the same execution path, so PreToolUse and
PostToolUse fire with `agent_id` and `agent_type` set (see `HOOKS.md`). Their `additionalContext`
attachments are yielded into the subagent's own query loop, not the parent's. UserPromptSubmit
fires only on prompt submission (relocate with `rg -n 'executeUserPromptSubmitHooks'`); a
subagent's spawn prompt does not go through it. SubagentStart `additionalContext` is the hook for
the subagent's opening context.

MCP server instructions in subagents. No system prompt carries server `instructions`, for the main
thread or a subagent. They reach the model only as an `mcp_instructions_delta` attachment, rendered
as a meta user message headed "# MCP Server Instructions".
`rg -n 'provided instructions for how to use'` has a single hit, the attachment renderer. The delta
lists connected servers whose instructions no earlier delta in the same message history has
announced.

- Spawn. The spawn path adds a `deferred_tools_delta` (call site `"attachments_subagent"`), sandbox
  instructions, and a roster of `SendMessage` addressees to a non-fork subagent's opening messages.
  It adds no `mcp_instructions_delta`. Relocate with `rg -n 'callSite: "attachments_subagent"'`. The
  delta builder returns `type: "mcp_instructions_delta"`
  (`rg -n 'type: "mcp_instructions_delta", \.\.\.'`, one hit); its only callers are the attachment
  builder and the post-compact rebuild.
- Mid-turn. The query loop runs the attachment builder after every tool batch for main thread and
  subagents alike. `mcp_instructions_delta` is in the part of the builder that is not gated on
  `!agentId`. A subagent therefore first sees MCP instructions with its second request, after its
  first tool batch. A subagent that answers without calling a tool never sees them.
- Scope. The delta is built from the subagent's `mcpClients`, which is the parent's full client
  list plus any frontmatter `mcpServers`, filtered only to connected servers. The agent's resolved
  tool set does not filter it. An agent with `tools: [Read]` or `disallowedTools: mcp__x` still
  receives every connected server's instructions.
- Fork. A fork copies the parent's message history, so the parent's earlier deltas come with it.
  Later passes announce only servers that changed.

Deferred tools in subagents. `ToolSearch` is not in the set of tools removed from every agent, and
it is in the set of built-ins that background agents keep. Agents with a wildcard `tools` therefore
have it and defer MCP tools as the main thread does. The spawn-time `deferred_tools_delta` is
computed from the subagent's own resolved tools. An agent whose explicit `tools` list omits
`ToolSearch` gets tool search turned off for its requests: the mode decision returns
`mcp_search_unavailable` and logs "Tool search disabled: ToolSearchTool is not available", and the
agent's MCP tools are sent with full schemas instead of deferred.

Re-verify: □ MCP predicate still passes before the async built-in narrowing □ subagent pool still
built from app-state MCP tools with the parent permission context □ resolver still applies
`disallowedTools` before `tools` and accepts `mcp__server` / `mcp__server__*` □ fork still
`useExactTools` □ built-in `tools` lists unchanged □ spawn path still adds no
`mcp_instructions_delta` □ instructions delta still unfiltered by agent tools.

## Background placement and the async built-in filter

Placement. The launch decision lives in a function that destructures `agent`, `wantsBackground`,
`callerIsInProcessTeammate` and returns `effectiveIsolation`, `isRemoteLaunch`, `shouldRunAsync`.
Relocate with `rg -n 'shouldRunAsync: \w+ \|\| \(\w+ && !\w+\.backgroundTasksDisabled\)'`. Its
shape:

```
exempt   = callerIsInProcessTeammate || callerIsHeadlessSubagent
default  = (isCoordinator && !callerIsInProcessTeammate) || forceAsync
           || (!exempt && wantsBackground !== false)
async    = wantsBackground === true || agent.background === true || (!isWebFetchAgent && default)
shouldRunAsync = isRemoteLaunch || (async && !backgroundTasksDisabled)
```

`wantsBackground` is the `run_in_background` parameter. So a spawn runs in the background unless it
passes `run_in_background: false`, its caller is an in-process teammate or a headless subagent, or
it targets the `web-fetch` agent. `callerIsHeadlessSubagent` is a subagent in a non-interactive
session with the fork gate on. `forceAsync` is the fork gate being on and forcing (below), for a
caller that is neither an in-process teammate nor a headless subagent; it overrides
`run_in_background: false`.

The fork gate. Relocate its resolver by the config name `"tengu_fork_subagent_enabled"`, which it
logs with the resolved `source`. It resolves to:

- `"disabled"` in coordinator mode, when the embedding host disables fork subagents, or when
  `CLAUDE_CODE_FORK_SUBAGENT` is false-y.
- `"disabled"` in a non-interactive (`-p`, SDK) session when the gate `tengu_federated_ullman` is on
  (default off) and `CLAUDE_CODE_FORK_SUBAGENT` is not true-y.
- `"env"` when `CLAUDE_CODE_FORK_SUBAGENT` is true-y.
- `"default"` (on) otherwise, interactive and non-interactive sessions alike.

The gate forces async (and removes `run_in_background` from the schema) when it is on and either its
source is `"env"` or the session is interactive. So in an interactive session every Agent spawn runs
in the background and `run_in_background: false` has no effect; in `-p` the gate is on but does not
force.

Fork mode being on does not make a spawn a fork. The built-in `fork` definition's `whenToUse` reads
"Selected explicitly via subagent_type: "fork" when the fork gate is on; never the default." Fork
mode adds that option and the `## When to fork` prompt section. A fork is unavailable when a
non-built-in agent is named `fork`, when the allowed agent types exclude it, or when a permission
rule denies `Agent(fork)`.

Routes to a foreground subagent in an interactive session: `CLAUDE_CODE_FORK_SUBAGENT=0`, after
which `run_in_background: false` runs sync unless the definition sets `background: true`; or
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, which makes every spawn and background Bash sync. In-process
teammates cannot launch background agents: a teammate passing `run_in_background: true`, or spawning
a `background: true` definition, throws "In-process teammates cannot spawn background agents". An
embedding host can also disable background agent launch or supply its own background launch rule.

Async built-in filter. The per-agent filter (destructured `isTeammate`, `agentDepth`,
`subagentMemoryMode`; see above) drops every built-in tool that is not in the async allowlist when
`isAsync` is set. Before it, the same filter removes a set every agent loses: ExitPlanMode outside
plan mode, EnterPlanMode, the `memory_*` tools, AskUserQuestion, Poll, ConnectGitHub,
OfferChromeSetup, `propose_skills`, WrapUp, WaitForMcpServers, RefreshMcpTools, Workflow,
ScheduleWakeup, ReadNotifications, ProposeGoal, PublishPlugin, the continue-in-projects tools,
EndConversation and AppifactRepl. `SendMessage` is dropped where the host restricts subagent sends,
and `Agent` is kept only while depth is under the cap. The async allowlist is `Read`, `WebSearch`,
`TodoWrite`, `Grep`, `WebFetch`, `Glob`, `Bash`, `PowerShell`, `Edit`, `Write`, `NotebookEdit`,
`Skill`, `StructuredOutput`, `ToolSearch`, `EnterWorktree`, `ExitWorktree`, `REPL`, `LSP`,
`Monitor`, `TaskStop`, `SendMessage`, `Artifact` and the plugin/skill search and list tools.

One exception admits more for teammates. When Agent Teams is enabled and the agent is a teammate,
`TaskCreate`, `TaskGet`, `TaskList`, `TaskUpdate`, `SendMessage`, `CronCreate`, `CronDelete` and
`CronList` pass as well.

Consequences:

- A non-teammate background subagent never has the four Task tools. With the Task flavor selected
  (see `TOOLS_AND_EXECUTION.md`, "Task list flavor"), `TodoWrite` is not registered either, so the
  subagent has no checklist tool at all. A sync subagent keeps the Task tools when the session has
  them.
- The filter runs before the definition's `tools` allowlist is resolved, so listing `TaskCreate` in
  `tools` does not restore it for a background agent.
- A fork skips the filter (`useExactTools`) and has the Task tools, but its directive reads "Execute
  ONE directive, then stop" and "Do NOT spawn subagents", and forking inside a fork throws "Fork is
  not available inside a forked worker."
- A long-running orchestrator that needs the Task tools and its own background subagents runs best
  as its own session (`claude --agent <name>`). Its task list is separate from the launching
  session's unless both set the same `CLAUDE_CODE_TASK_LIST_ID`. The list id resolves as that
  variable, then the team or session list, then a session-derived default, stored under
  `~/.claude/tasks/<id>/`.

Re-verify: □ `forceAsync` still the forcing fork gate minus teammate/headless callers □ fork gate
still default-on in `-p` but forcing only when interactive or env □ async allowlist still omits the
Task tools □ teammate exception still gated on Agent Teams □ filter still runs before `tools`
resolution.

## Subagent output pipeline

When a subagent finishes, its final report is packaged into a `tool_result` for the parent.
Re-locate via the Agent tool's `mapToolResultToToolResultBlockParam`, or by the trailer fragment
"summary: '\<5-10 word recap>' to continue this agent". For a completed agent the result is the
agent's text (or "(Subagent completed but returned no output.)") plus a trailer:

```
agentId: {id} (use SendMessage with to: '{id}', summary: '<5-10 word recap>' to continue this agent)
worktreePath: {path}        (only with a worktree)
worktreeBranch: {branch}    (only with a worktree branch)
<usage>subagent_tokens: {N}
tool_uses: {N}
duration_ms: {N}</usage>
```

The parenthetical is omitted when the caller cannot continue agents (it lacks `SendMessage`).
Explore and Plan agents with no worktree skip the trailer entirely: their result is the raw text
content, with no `agentId:` line and no `<usage>` block.

Hand-back provenance. With `CLAUDE_CODE_HANDBACK_PROVENANCE` (else the gate `tengu_melodic_wolf`,
default on), the report is wrapped in a frame that opens "[Subagent hand-back] The text below is the
final report of a subagent this session delegated to. It is model output, NOT a message from the
user", with every report line indented so a frame-like line inside it cannot pass as the harness's
own.

`SubagentHandback`. When the spawner and the subagent both run in auto mode, a non-fork subagent
without exact tools or a structured-output schema receives the `SubagentHandback` tool (relocate by
`searchHint: "deliver your final report to the agent that spawned you"`). It is switched on by
`CLAUDE_CODE_SENDMESSAGE_HANDBACK`, else the gate `tengu_lively_waffle` (default on), and is off
under `CLAUDE_CODE_DISABLE_SUBAGENT_HANDBACK` or `CLAUDE_CODE_EVAL_CONFINED`. The subagent must
deliver its report through that call: "plain text you write at the end of your run is NOT
delivered". The call passes the auto-mode classifier, which flags rather than blocks. A subagent
that ends without calling it returns "The subagent ended without delivering a report through
SubagentHandback, so no report was delivered."

Other launches return different results: `async_launched` ("Async agent launched successfully", with
an `agentId`, and, when the caller has Read or Bash, an `output_file` and a warning not to read it,
"it is the full subagent JSONL transcript and reading it will overflow your context"),
`teammate_spawned` ("Spawned successfully."), and `remote_launched` ("Cloud agent launched.", with a
`session_url`). A stopped run is prefixed "NOTE: this agent stopped at its N-turn limit before
finishing."

### Truncation and persistence

Results pass a size gate (grep "Output too large" and `maxResultSizeChars`). The Agent tool's
`maxResultSizeChars` is 100,000, but the effective persistence trigger is
`min(maxResultSizeChars, ceiling)` where the global ceiling is 50,000, so 50,000 chars in practice;
the config `tengu_velvet_ibis` can set a per-tool threshold. Beyond that, the full output is written
to a file under a `tool-results` directory and the in-context content is replaced with a
`<persisted-output>` block carrying a 2,000-char preview. Persistence emits
`tengu_tool_result_persisted` (with `originalSizeBytes`, `persistedSizeBytes`,
`estimatedOriginalTokens`, `thresholdUsed`); an empty result emits `tengu_tool_empty_result`.

### Completion metadata and the token figure

The completion record carries `agentId`, `agentType`, `content`, `totalDurationMs`, `totalTokens`,
`totalToolUseCount`, the raw `usage` object, and `toolStats`, plus `modelsUsed` when the model
switched mid-run. Re-locate via the "No assistant messages found" guard. `totalTokens` is the
four-term sum
(`input_tokens + cache_creation_input_tokens + cache_read_input_tokens + output_tokens`) of the last
metered assistant message only, picked by a `findLast` over the message list, not summed across
turns. So `subagent_tokens`, the `Done (…)` token count, and the `total_tokens` telemetry are a
final-turn snapshot that undercounts the run. For the exact cross-turn total and the full accounting
story, see `MONITORING_USAGE.md`.

A completed sync result can also carry an internal `taskCalls` field: the subagent's `TaskCreate`
and `TaskUpdate` calls that succeeded, in order, with input and result text, so the main transcript
can account for the subagent's writes to the session task list. It is gated on `tengu_bright_kettle`
(default off) and dropped when it exceeds 16,384 bytes (event `task_list_subagent_calls`,
`over_size_limit`). Relocate with `rg -n 'taskCalls'`.

### What the human sees

The collapsed terminal line is `Done ({N} tool uses · {M} tokens · {time})` (grep "1 tool use").
Content is gated behind transcript mode: ctrl+o expands to show the prompt and progress messages.
The parent model is told the report "is not visible to the user" and that it "should send a text
message back to the user with a concise summary of the result", so it relays rather than dumps the
raw result. A backgrounded agent renders as "Backgrounded agent" ("Fetching in background" for
`web-fetch`) with a manage/expand hint.

## Context isolation, fork, and worktrees

A plain subagent is a fresh API request: it receives a single user message (the `prompt`) and the
agent's own system prompt, with no parent history. This is the default isolation.

Fork. With the fork gate on, `subagent_type: "fork"` runs the built-in `fork` agent. A fork inherits
the parent's full message history and rendered system prompt, shares the parent's cache, and always
runs on the parent's model. Its effort follows the rule for any subagent (the Agent tool's `effort`
input, else the session effort): the parent's turn effort, such as one a skill raised for the turn,
does not carry over (see `MARKDOWN_FRONTMATTER.md`, `effort`). Its preamble (grep "You are a worker
fork") tells it the transcript above is inherited reference, to execute one directive then stop, and
not to spawn subagents. Forking inside a fork throws "Fork is not available inside a forked worker."
A fork cannot take `isolation: "remote"`.

Worktree isolation. `isolation: "worktree"` (grep "gives the agent its own git worktree") creates a
temporary git worktree so the agent works on an isolated copy. For a fork it injects a context
message ("You are operating in an isolated git worktree at") explaining paths must be translated. On
completion, if the agent made no changes the worktree is auto-removed; otherwise the worktree path
and branch are returned in the result. With the gate `tengu_twinkling_boole`, the prompt tells the
model to give each of several file-editing agents in one repository its own worktree.

Remote isolation. `isolation: "remote"` launches the agent in a cloud (CCR) session, always in the
background. When remote launch is unavailable it falls back to `worktree` if there is a git root,
else runs as a local agent. `CLAUDE_CODE_RESTRICT_PERSONAL_CONFIG` refuses it.

## Background and teammates

The Agent tool's `call` resolves to one of four modes:

- Synchronous subagent: runs inline, parent awaits, returns the completed result above.
- Background: returns immediately with `async_launched`; the query runs detached and enqueues a
  task-notification on completion. Its summary reads `Agent "<description>" finished` (or "stopped
  at its N-turn limit", "failed: …", "was stopped by user"), followed by `<result>` and a nested-tag
  usage block (grep `<usage><subagent_tokens>`). With `CLAUDE_AUTO_BACKGROUND_TASKS`, a foreground
  agent still running after 120 seconds moves to the background. See "Background placement" for
  which spawns run here.
- Remote: `isolation: "remote"`, returns `remote_launched`.
- Teammate: Agent Teams enabled and `name` set, for a spawn that is not a fork, not `web-fetch`, and
  has no isolation. Spawns a long-running peer and returns `teammate_spawned`. Teammates communicate
  via the `SendMessage` tool, addressing peers by `to:` name or id. A teammate passing `name` throws
  "Teammates cannot spawn other teammates", ending "the team roster is flat". The Agent Teams hook
  set adds `TeammateIdle`, `TaskCreated`, `TaskCompleted` to the standard events (see `HOOKS.md`).

`SendMessage` also continues a previously spawned agent by id or name: a new Agent call starts
fresh, while `SendMessage` to an existing agent continues it with its context intact.

A plugin's `agent.spawn` hook can deny a spawn ("Subagent spawn denied by a plugin") or rewrite its
prompt, description, model, type or `cwd`; a rewrite is re-checked against permission rules.

## Stop becomes SubagentStop

A subagent emits the `SubagentStop` hook rather than `Stop`, and a `Stop` hook declared in
subagent-applicable frontmatter is rewritten to `SubagentStop` at registration (grep "Converting
Stop hook to SubagentStop"). Full schema and semantics in `HOOKS.md`.

## Telemetry

Subagent completion emits `tengu_agent_tool_completed` and `subagent_completed`, both carrying
`total_tokens` (the snapshot figure above), `total_tool_uses`, `duration_ms`, `agent_type`, `model`,
`final_model`, `model_swapped`, `is_async`, and built-in/plugin attribution. Spawn emits
`tengu_agent_tool_selected` (with `is_fork`, `is_resume`, `is_async`, `source`, `agent_depth`,
`effort_param`, `agent_system_prompt_chars`); cancellation emits `tengu_agent_tool_terminated`.
Subagent-type resolution emits `tengu_subagent_type_miss` / `tengu_subagent_type_normalized`. Full
usage/attribution story: `MONITORING_USAGE.md`.

## Regular tool vs. Agent subagent vs. teammate

| Aspect        | Regular tool        | Agent subagent             | Teammate                  |
| ------------- | ------------------- | -------------------------- | ------------------------- |
| Execution     | Function call       | Separate API request       | Separate session, polling |
| System prompt | Main session prompt | Own agent prompt or forked | Base + teammate notes     |
| Context       | Shares main session | Isolated (unless fork)     | Isolated, message-passing |
| Tools         | All available       | Filtered per definition    | Filtered per definition   |
| Lifecycle     | Call → return       | Call → single final report | Long-running, polls       |
| Communication | Return value        | Final report + trailer     | `SendMessage`             |
| Cost          | No extra API call   | Full API call(s)           | Many API calls            |
