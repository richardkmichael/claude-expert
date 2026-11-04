---
verified: 2.1.317
verified_on: 2026-11-03
section: Memory
style: landmark
scope: 'Per-subagent memory: `memory:` field, dirs, link guard, permissions'
landmarks:
  - Persistent Agent Memory
  - tengu_agent_memory_loaded
  - tengu_agent_memory_entrypoint_skipped
  - Agent memory files are allowed for writing
---
# Agent Memory (Persistent Agent Memory)

Per-subagent persistent memory. An agent opts in with a `memory:` field; from then on it reads and
writes its own memory directory across conversations, separate from the main session's auto memory.
Internally the store is called "Persistent Agent Memory."

This is a leaf of the memory system. Read `MEMORY_SYSTEM.md` first for the shared machinery: the
`MEMORY.md` index pattern and its caps, memory types, save protocol, the master gate, and recall
mode. This doc covers only what is specific to agent memory.

Public docs: `code.claude.com/docs/en/sub-agents#enable-persistent-memory` (the feature),
`code.claude.com/docs/en/claude-directory` (the directories). The link guard, permissions, git
exclusion and telemetry below are not in the public docs.


## The `memory:` field

An agent definition may set `memory:` to `user`, `project` or `local`. The agent's name (its
`agentType`) plus this scope select the directory. All three definition sources honor it, each with
its own handling of a bad value:

| Source                             | Invalid value                                        |
| ---------------------------------- | ---------------------------------------------------- |
| `.claude/agents/*.md` (markdown)   | Warning `has invalid memory value`; loads w/o memory |
| Plugin agent markdown              | Same warning, prefixed `Plugin agent file`           |
| JSON agents (`--agents`, settings) | Schema error; the whole agent is dropped with        |
|                                    | `Error parsing agent '<name>' from JSON:`            |

Relocate the markdown and plugin parsers with `rg -n 'has invalid memory value'` (2 hits). The JSON
schema is the object that also holds `initialPrompt` and `observeSubagents`; its `memory` entry is
an enum of the three scopes. The SDK `agents` initialize option declares the same enum, described by
`Scope for auto-loading agent memory files` (1 hit).

Plugin agents keep `memory:`; it is not among the keys logged as
`which is ignored for plugin agents`.


## Directory layout

| Scope     | Directory                                  | Version control          |
| --------- | ------------------------------------------ | ------------------------ |
| `user`    | `<memory-base>/agent-memory/<name>/`       | outside the repo         |
| `project` | `<cwd>/.claude/agent-memory/<name>/`       | tracked                  |
| `local`   | `<cwd>/.claude/agent-memory-local/<name>/` | git-excluded (see below) |

- `<memory-base>` is `CLAUDE_CODE_REMOTE_MEMORY_DIR` when set, else the config dir
  (`CLAUDE_CONFIG_DIR` or `~/.claude`).
- `<cwd>` is the current working directory, not the repository root: a session started in a
  subdirectory gets that subdirectory's `.claude/agent-memory/`. `PROJECT_FILES_AND_STATE.md` covers
  what that means for worktrees.
- With `CLAUDE_CODE_REMOTE_MEMORY_DIR` set, `local` moves to
  `<remote>/projects/<project-slug>/agent-memory-local/<name>/`.
- `<name>` is the agent name with every character outside `[a-zA-Z0-9\-_]` replaced by `-`; an empty
  result becomes `unknown`.

Relocate with `rg -n -B3 -A28 '=== "" \? "unknown"'` (1 hit). Expect the sanitizer, then the
local-scope helper that checks `CLAUDE_CODE_REMOTE_MEMORY_DIR` first, then the resolver's switch
over `project`, `local` and `user`. The memory-base helper sits beside the auto-memory constants:
the first hit of `rg -n -A4 'process.env.CLAUDE_CODE_REMOTE_MEMORY_DIR\)$'` (2 hits; the second is
the local-scope helper) returns the env var, else the config dir.

Inside the directory the layout is the shared one: a `MEMORY.md` index plus one file per memory, the
same two-step save, the same `[[name]]` links.

`rg 'agent-memory'` also hits an Anthropic SDK beta header, `agent-memory-2026-07-22`, on the
`/v1/memory_stores` API client. That is the API's memory stores, not this feature.


## What the agent is told

The section is built by the agent-memory builder (`rg -nF 'displayName: "Persistent Agent Memory"'`,
1 hit), which calls the shared instruction builder with the type taxonomy always inlined and
`## Project skill upkeep` always omitted, then appends a `## MEMORY.md` section. It passes one
scope-specific guideline line, plus `CLAUDE_COWORK_MEMORY_EXTRA_GUIDELINES` when that is non-blank:

- `user`: "- Since this memory is user-scope, keep learnings general since they apply across all
  projects"
- `project`: "- Since this memory is project-scope and shared with your team via version control,
  tailor your memories to this project"
- `local`: "- Since this memory is local-scope (not checked into version control), tailor your
  memories to this project and machine"

Each quoted line is one string in the bundle, wrapped here. Relocate with
`rg -n 'keep learnings general'` (1 hit, in the same function as the display name).

The `## MEMORY.md` section holds one of three things:

- The index, truncated by the shared helper to 200 lines and 25,000 characters (see
  `MEMORY_SYSTEM.md`). This is the only case that fires `tengu_memdir_loaded` with
  `memory_type: "agent"`; that value is chosen by display name, it is not a separate gate.
- `Your MEMORY.md is currently empty. When you save new memories, they will appear here.` when the
  file is missing or blank.
- The read-only notice, when the link guard (below) refused the index. It begins
  `Your MEMORY.md was not loaded: it or its folder is a link or a special file` and includes
  `Treat this agent memory as read-only in this session` (it goes on to forbid writing `MEMORY.md`
  or other files in the folder). The builder then also drops the save instructions and says
  `This memory is read-only this session — you cannot save new memories to it.`

Recall mode does not change this: agent memory always inlines its index and always uses the two-step
save.

Building the section starts creating the directory (not awaited; failures log
`ensureMemoryDirExists failed for`), except when the link guard returns "none". For `user` scope,
when `<memory-base>` is the config dir, the index is pre-read through Claude Code's storage layer
(namespace `agentMemory`, layer `user`) and handed to the builder as `primedAgentMemory`; otherwise
the builder reads `MEMORY.md` from disk.


## The link guard (`project` and `local` scopes)

`project` and `local` memory live in the working copy, so a cloned repository controls them. Before
reading their `MEMORY.md` the builder classifies the directory:

- `user` scope: read normally, links followed.
- Directory lexically outside the cwd (only `local` under `CLAUDE_CODE_REMOTE_MEMORY_DIR`): read
  only if `MEMORY.md` is a regular file; a symlink or special file gets the read-only prompt.
- Directory under the cwd and, once resolved, still beneath the cwd's real path (or not yet
  created): the same regular-file rule.
- Directory under the cwd that resolves elsewhere (a folder link leading out, or a dangling link),
  or that cannot be resolved: not read at all, no mkdir, read-only prompt.

Each refusal fires `tengu_agent_memory_entrypoint_skipped` with `reason` `folder_link`,
`folder_unresolved`, `leaf_link` (the index is a symlink) or `leaf_special`, and logs a debug line
starting `agent memory:` (`leads out of the working copy or through a dangling link`,
`could not be resolved`, `is not a regular file; not read`). Relocate with
`rg -n 'tengu_agent_memory_entrypoint_skipped'` (2 hits: the folder check and the leaf check).

Recall applies the same containment. When a main-session message mentions `@agent-<name>` for agents
with `memory:` (see "Recall mode" in `MEMORY_SYSTEM.md`), each `project`/`local` directory is
resolved to its real path, dropped if it leaves the cwd's real path, and only regular files inside
that real path are attached. A directory that cannot be resolved logs `not read for recall`.


## Wiring: definition to loaded prompt

Each parser gives the definition a `getSystemPrompt` closure: when the master gate is on and the
agent has a scope, it returns `<body>` + blank line + the agent-memory section; otherwise just the
body. So the gate is checked at prompt-build time, and whether an agent gets memory once the family
is on depends only on its `memory:` field. `CLAUDE_CODE_DISABLE_AUTO_MEMORY` and
`autoMemoryEnabled: false` turn agent memory off with the rest of the family (`MEMORY_SYSTEM.md`,
"The master gate").

The section reaches the model in three launch paths, each firing `tengu_agent_memory_loaded` with
`scope` and `source` whenever the agent has `memory:` set. The event is not gated on the master
gate, so it fires even when memory is off and no section was built.

| `source`              | Path                                                                  |
| --------------------- | --------------------------------------------------------------------- |
| `subagent`            | Agent tool spawn; the prompt becomes the subagent's system prompt     |
| `main-thread`         | The agent runs as the main session (`--agent` or the `agent` setting) |
| `in-process-teammate` | An in-process teammate, under `# Custom Agent Instructions`           |

Relocate with `rg -n '"tengu_agent_memory_loaded"'` (3 hits). The subagent site sits beside
`Failed to get system prompt for agent`.


## Auto-appended tools

When the master gate is on, the agent has a scope, and it declares an explicit `tools:` list, each
parser appends `Write`, `Edit` and `Read` to that list if absent. Agents without `tools:` already
get every tool, so nothing changes for them. The check is in the parser, so it reflects the gate at
definition-load time. `MARKDOWN_FRONTMATTER.md` and `SUBAGENTS.md` note the same rule.


## Permissions

Reads and `.md` writes inside an agent-memory directory are allowed without a prompt. The check is
lexical: it normalizes the path (no link resolution), finds a recognized root, then rejects any path
whose remaining components include a protected name.

Recognized roots:

- `<memory-base>/agent-memory/` (skipped in a diskless process)
- `<cwd>/.claude/agent-memory/`
- With `CLAUDE_CODE_REMOTE_MEMORY_DIR`: `<remote>/projects/`, for a path containing
  `/agent-memory-local/`. Without it: `<cwd>/.claude/agent-memory-local/`.

Protected components, compared case-insensitively: `.git`, `hooks`, `.husky`, `.githooks`,
`node_modules`, `.vscode`, `.idea`, `head`, `config`, `objects`, `refs`, `.claude`, `skills`,
`commands`, `agents`, `.cargo`, `.devcontainer`, `.yarn`, `.mvn`. The agent's name is one of the
components checked, so an agent named, say, `config` or `skills` gets no automatic allow for its own
memory directory. Relocate the set with `rg -n -U '"\.husky",\n\s*"\.githooks",'` (1 hit) and the
root finder with `rg -n '\+ "agent-memory-local" \+'` (1 hit).

| Decision | Reason string (grep)                         | Not applied when                       |
| -------- | -------------------------------------------- | -------------------------------------- |
| Write    | `Agent memory files are allowed for writing` | restricted session; path not `.md`;    |
|          |                                              | `blockWritesOutsideWorkingDirectories` |
| Read     | `Agent memory files are allowed for reading` | restricted session; remote-surface     |
|          |                                              | check; `blockReadsOutsideWorkingDirs`  |

(`blockReadsOutsideWorkingDirs` is short for the `permissions.blockReadsOutsideWorkingDirectories`
setting.) The allow does not check the master gate. Paths that do not match fall through to the
normal permission flow.

Other references to `/agent-memory/` and `/agent-memory-local/`, all behind the master gate,
classify paths as memory for UI and transcript handling (collapsing memory tool calls, marking
memory files). They do not decide permissions. Relocate with `rg -nF '"/agent-memory-local/"'` and
`rg -nF '"agent-memory-local/"'`.


## Git exclusion (`local` scope only)

`local` memory is kept out of version control through the repository's local exclude file, not a
`.gitignore`. A `# claude-code-runtime` block is appended to `<git-common-dir>/info/exclude`. It
lists `**/.claude/agent-memory-local` alongside other runtime paths (`scheduled_tasks.lock`,
`scheduled_tasks.json`, `routines/.state/`, `worktrees/`, `checkpoints/`, `mailbox/`,
`agent-registry.json`, `first-run`, `assistant-daemon-state.json`). Relocate with
`rg -n '"\*\*/.claude/agent-memory-local"'` (1 hit, in that list).

- The writer runs when the scheduled-tasks scheduler tries to take its lock (the function that logs
  `[ScheduledTasks] acquired scheduler lock`), so a session in which that scheduler never starts
  does not write the block.
- It runs once per directory per process and skips the file if it already contains the marker.
- It follows worktree pointers to the common git dir. When it cannot confirm the checkout's `.git`
  belongs to it, or the git dir lacks its own `HEAD` file or `objects` folder, it writes nothing and
  logs `Not adding ignore rules for the files Claude Code writes under .claude/`.

`project` memory (`.claude/agent-memory/`) is left tracked so it can be shared through version
control, matching its guideline line.


## The `/memory` dialog and `/agents`

The `/memory` dialog shows one row per active agent with `memory:` set:
`Open <agentType> agent memory`, described `<scope> scope`, opening that agent's directory. The rows
appear only while memory is on (or in safe mode). Relocate with `rg -n '} agent memory'` (1 hit),
the label template.

There is no agent-creation wizard: `/agents` is hidden and prints
`The /agents wizard has been removed.`, pointing at `.claude/agents/` and `~/.claude/agents/`. A
`memory:` field is added by editing the agent file.


## Relocating in a new bundle

| Concept                | Grep anchor                                                  |
| ---------------------- | ------------------------------------------------------------ |
| Sanitizer and resolver | `=== "" \? "unknown"` (then the next ~28 lines)              |
| Memory base            | `process.env.CLAUDE_CODE_REMOTE_MEMORY_DIR\)$`               |
| Agent-memory builder   | `displayName: "Persistent Agent Memory"`                     |
| Scope guideline lines  | `keep learnings general`                                     |
| Read-only notice       | `Treat this agent memory as read-only`                       |
| Link guard             | `tengu_agent_memory_entrypoint_skipped`                      |
| Recall containment     | `not read for recall`                                        |
| Invalid-value warning  | `has invalid memory value`                                   |
| SDK field description  | `Scope for auto-loading agent memory files`                  |
| Launch event           | `"tengu_agent_memory_loaded"`                                |
| Write and read allow   | `Agent memory files are allowed for writing` / `for reading` |
| Protected components   | `"\.husky",\n\s*"\.githooks",` (multiline)                   |
| Git exclude            | `# claude-code-runtime` / `"**/.claude/agent-memory-local"`  |
| `/memory` rows         | `} agent memory` (label template)                            |
| `/agents` removal      | `The /agents wizard has been removed.`                       |


## Tripwires

- `□` `memory:` accepts exactly `user` / `project` / `local`; markdown and plugin parsers warn and
  drop a bad value; JSON agents with a bad value fail to load.
- `□` Directories: `<memory-base>/agent-memory/<name>/`, `<cwd>/.claude/agent-memory/<name>/`,
  `<cwd>/.claude/agent-memory-local/<name>/`; `CLAUDE_CODE_REMOTE_MEMORY_DIR` moves `user` and
  `local`.
- `□` Agent name sanitized `[^a-zA-Z0-9\-_] → -`, empty → `unknown`.
- `□` `project`/`local` index read only as a regular file inside the working copy; otherwise the
  read-only notice and `tengu_agent_memory_entrypoint_skipped`.
- `□` Memory-set agents with an explicit `tools:` list get `Write`/`Edit`/`Read` appended.
- `□` `tengu_agent_memory_loaded` has 3 sources: `subagent`, `main-thread`, `in-process-teammate`.
- `□` `.md` writes and reads under a recognized root are auto-allowed unless a component is in the
  protected set; not gated on the master gate.
- `□` `local` excluded via `info/exclude` under `# claude-code-runtime`; `project` stays tracked.
- `□` Prompt section gated by the master gate, same switches as the rest of the family.
- `□` `/agents` prints the removal notice; no creation wizard.
