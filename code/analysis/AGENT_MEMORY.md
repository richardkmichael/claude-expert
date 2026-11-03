---
verified: 2.1.186
verified_on: 2026-06-26
section: Memory
style: landmark
scope: 'Per-subagent memory: `memory:` field, dirs, permissions'
landmarks:
  - Persistent Agent Memory
  - tengu_agent_memory_loaded
---
# Agent Memory (Persistent Agent Memory)

Per-subagent persistent memory. A subagent opts in with a `memory:` frontmatter field; from then on
it reads and writes its own memory directory across conversations, separate from the main session's
auto memory. Internally the store is called "Persistent Agent Memory."

This is a leaf of the memory system; read `MEMORY_SYSTEM.md` first for the shared machinery (the
`MEMORY.md` index pattern, memory types, save protocol, the `Gc()` gate). This doc covers only what
is specific to agent memory.

Public docs: `code.claude.com/docs/en/sub-agents#enable-persistent-memory` (the feature),
`code.claude.com/docs/en/claude-directory` (the directories). The wiring, permissions, and gitignore
behavior below are not in the public docs.


## The `memory:` frontmatter field

A subagent definition (a `.claude/agents/*.md` file, a JSON/settings agent, or a plugin agent) may
set `memory:` to one of `user`, `project`, or `local`. The agent's name (its `agentType`) plus this
scope select the directory. Declared in the agent schema — grep
`Scope for auto-loading agent memory files`, whose describe string enumerates the three directories.

Invalid values are rejected per source, not silently kept. Grep `has invalid memory value` for the
markdown parser's error; the value is dropped with a warning and the agent loads without memory.

The three agent-definition parsers each carry the same logic; relocate them by their error strings:
`has invalid memory value` (markdown), `Error parsing agent` (JSON), and
`which is ignored for plugin agents` (plugin).


## Directory layout

Resolution is one function — relocate it via the path literal `agent-memory` (its switch has cases
for `project`/`local`/`user`) — taking the agent name and scope:

| Scope     | Directory                                              | Checked into VC |
| --------- | ----------------------------------------------------- | --------------- |
| `user`    | `~/.claude/agent-memory/<name>/`                      | no (user home)  |
| `project` | `.claude/agent-memory/<name>/`                        | yes (tracked)   |
| `local`   | `.claude/agent-memory-local/<name>/`                  | no (git-excluded) |

`<name>` is the agent's name sanitized: every character outside `[a-zA-Z0-9\-_]` becomes `-`, and an
empty result becomes `unknown` (a small helper next to the resolver; grep the char class
`[^a-zA-Z0-9`). The user-scope root is the config dir (`CLAUDE_CONFIG_DIR` or `~/.claude`). Under
remote mode the local-scope path is relocated beneath
`CLAUDE_CODE_REMOTE_MEMORY_DIR/projects/<slug>/agent-memory-local/<name>/` (grep
`agent-memory-local` — the resolver checks `CLAUDE_CODE_REMOTE_MEMORY_DIR` first).

Inside the directory the store is identical to auto memory: a `MEMORY.md` index plus per-topic
memory files, same two-step save, same `[[name]]` links. The human-readable scope labels render via
grep `Project (.claude/agent-memory/)`.


## What the agent is told

The prompt section is built by the same shared builder as auto memory (relocate via the property key
`memoryDir:`), with `displayName` set to `Persistent Agent Memory` (grep that string) and one
scope-specific guideline line appended:

| Scope     | Verbatim guideline line                                                                                   |
| --------- | -------------------------------------------------------------------------------------------------------- |
| `user`    | `- Since this memory is user-scope, keep learnings general since they apply across all projects`          |
| `project` | `- Since this memory is project-scope and shared with your team via version control, tailor your memories to this project` |
| `local`   | `- Since this memory is local-scope (not checked into version control), tailor your memories to this project and machine` |

Relocate the builder of these by grepping `keep learnings general`.
`CLAUDE_COWORK_MEMORY_EXTRA_GUIDELINES`, if set, is appended as well.


## Wiring: frontmatter to loaded prompt

Each agent definition exposes a `getSystemPrompt()` closure shaped like:

> if the master gate is on and the agent's memory scope is set, return `basePrompt + "\n\n" +
> <agent-memory section>`; otherwise return `basePrompt`.

So the memory section is appended to the agent's base system prompt only when the master gate is on
and a scope is set. Building the section creates the directory first — grep
`ensureMemoryDirExists failed for` for the mkdir helper.

At spawn time the subagent launcher computes the system prompt, and when the agent has memory set
fires `tengu_agent_memory_loaded` with `source: "subagent"`, then passes the assembled prompt as the
spawned loop's system-prompt override. Relocate the launcher by grepping `tengu_agent_memory_loaded`
and the nearby `Failed to get system prompt for agent`.

Gate: agent memory rides the same master gate as the rest of the family (see `MEMORY_SYSTEM.md`).
`CLAUDE_CODE_DISABLE_AUTO_MEMORY` and `autoMemoryEnabled: false` disable it too. Whether a given
subagent gets memory, once the family is enabled, is driven purely by its `memory:` field. The
`memory_type: "agent"` telemetry value is cosmetic (display-name based), not a separate gate.


## Auto-appended tools

An agent with memory set needs file tools to use it. When the master gate is on, the agent has a
`memory` scope, and the agent declares an explicit `tools:` list, the parser appends `Read`, `Edit`,
and `Write` to that list if absent. This lives in the agent-definition parsers (relocate via the
invalid-value error `has invalid memory value`, which sits in the same parser). Agents with no
`tools:` field already have every tool, so the append is a no-op there. This matches the note in
`MARKDOWN_FRONTMATTER.md` under `tools`.


## Permissions: writing into the memory directory

Writes and reads inside an agent-memory directory are auto-allowed without a permission prompt,
narrowly. A validator confirms a path starts with a recognized agent-memory root and is not inside
an excluded subpath; relocate the allow decisions via the reason strings below.

- Write: a path ending in `.md` inside the memory dir is allowed — grep `Agent memory files are
  allowed for writing`.
- Read: a path inside the memory dir is allowed — grep `Agent memory files are allowed for reading`.

Writes outside the memory directory are not affected; they fall through to the normal permission
flow. The validator also excludes dangerous subpaths (e.g. `.git`, `hooks`, `node_modules`) even
within the memory root, so writes there are not auto-allowed.

Two more references to `/agent-memory/` and `/agent-memory-local/` (grep both, gated on `Gc()`)
classify paths as memory-related for UI/transcript handling (collapsing memory tool calls, marking
auto-managed memory) — they are not the permission decision.


## Git exclusion (local scope only)

Local-scope memory is kept out of version control, but not via a project `.gitignore`. The pattern
`**/.claude/agent-memory-local` is appended to the repo's local git exclude file
(`<git-common-dir>/info/exclude`) under a `# claude-code-runtime` marker block, alongside other
runtime paths (worktrees, checkpoints). Relocate by grepping `# claude-code-runtime` and
`**/.claude/agent-memory-local`. The writer runs at session startup (during session-lock
acquisition), is memoized per git dir, and returns early if the marker is already present. It
handles worktree `gitdir:` pointers via the common dir.

Project-scope memory (`.claude/agent-memory/`) is intentionally left tracked so it can be shared via
version control — matching the project-scope guideline line above.


## The `/agents` creation wizard

The wizard offers a memory-scope picker (grep `None (no persistent memory)`). The option order and
the recommended default depend on where the agent is being saved:

| Save location   | Recommended | Options                                            |
| --------------- | ----------- | -------------------------------------------------- |
| user settings   | User        | User (Recommended), None, Project, Local           |
| project settings | Project     | Project (Recommended), None, User, Local           |

Choosing a scope writes a `memory: <scope>` line into the generated agent markdown's frontmatter;
choosing None writes no `memory:` field. Creation telemetry `tengu_agent_created` records
`has_memory` and `memory_scope` (`none` when unset).


## Relocating in a new bundle

All anchors are version-stable strings, not minified symbol names.

| Concept                  | Grep anchor                                       |
| ------------------------ | ------------------------------------------------- |
| Directory resolver       | `agent-memory` (switch over `project`/`local`/`user`) |
| Name sanitizer           | char class `[^a-zA-Z0-9` (helper near resolver)   |
| Local-scope / remote     | `agent-memory-local`                              |
| Scope labels             | `Project (.claude/agent-memory/)`                 |
| Display name             | `Persistent Agent Memory`                         |
| Scope guideline lines    | `keep learnings general`                          |
| Frontmatter field schema | `Scope for auto-loading agent memory files`       |
| Invalid-value error      | `has invalid memory value`                        |
| Spawn-time load event    | `tengu_agent_memory_loaded`                       |
| Write/read allow         | `Agent memory files are allowed for writing`      |
| Git exclude              | `# claude-code-runtime` / `**/.claude/agent-memory-local` |
| Wizard picker            | `None (no persistent memory)`                     |
| Creation telemetry       | `tengu_agent_created`                             |


## Tripwires

- `□` `memory:` accepts exactly `user` / `project` / `local`; invalid logs a warning and is ignored.
- `□` Directories: user `~/.claude/agent-memory/<name>/`, project `.claude/agent-memory/<name>/`,
  local `.claude/agent-memory-local/<name>/`.
- `□` Agent name sanitized via `[^a-zA-Z0-9\-_] → -`, empty → `unknown`.
- `□` Store layout is the shared `MEMORY.md` index + per-topic files (same builder as auto memory).
- `□` Memory-set agents with an explicit `tools:` list get `Read`/`Edit`/`Write` appended.
- `□` `.md` writes and any reads inside the memory dir are auto-allowed; outside falls through.
- `□` Local-scope excluded via `.git/info/exclude` (not `.gitignore`); project-scope stays tracked.
- `□` Gated by the master gate — same gate and disable switches as the rest of the family.
