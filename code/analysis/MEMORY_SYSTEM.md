---
verified: 2.1.186
verified_on: 2026-06-26
section: Memory
style: landmark
scope: 'Hub: shared memory machinery, gates, stores comparison'
landmarks:
  - tengu_memdir_loaded
---
# Memory System

Claude Code has one persistent-memory mechanism pointed at three different stores. This doc is the
hub: it describes the shared machinery and routes to the per-store docs. Read it first, then the
leaf that matches the store you care about.

- `AUTO_MEMORY.md` — the user-facing, per-project memory the main session reads and writes.
- `AGENT_MEMORY.md` — per-subagent memory, opted into by an agent's `memory:` frontmatter field.
- `TEAM_MEMORY.md` — shared memory synced from a remote memory-service.


## One mechanism, three stores

Auto, agent, and team memory are the same idea — a directory holding a `MEMORY.md` index plus
per-topic memory files — rendered into the system prompt by the same code with a different root
directory and a few different guideline lines.

The builder is one function (relocate via the property key `memoryDir:`, present at its call sites
and destructuring): it reads `<memoryDir>/MEMORY.md`, wraps the index content with the shared
instruction blocks, and appends a `## MEMORY.md` section (or "currently empty" text when the file is
missing). Auto memory and agent memory both call it; the only differences are the `displayName`
("auto memory" vs "Persistent Agent Memory") and the scope-specific guideline line. Team memory uses
sibling builders (grep the prompt strings in §"Relocating") but shares the index-file convention,
the memory-types taxonomy, and the staleness rules described below.

The instruction text comes from the prompt assembler — grep `How to save memories`. It is shared
across all stores; the differences between stores are which directory it points at and which
guideline lines get appended.


## The MEMORY.md index pattern

Every store uses the same layout: a single index file plus one file per memory.

- Index file: `MEMORY.md` (grep the quoted literal `"MEMORY.md"`). It is the only file loaded into
  context automatically. It is an index, not a memory — one line per entry, format
  `- [Title](file.md) — one-line hook`, no frontmatter.
- Memory files: each memory is its own `*.md` file with YAML frontmatter `name`, `description`, and
  `metadata.type`. The body holds the fact; for `feedback`/`project` it is structured as the rule
  followed by `**Why:**` and `**How to apply:**` lines. Memories cross-link with `[[name]]` slugs.
- Saving is two steps: write the memory file, then add a one-line pointer to it in `MEMORY.md`.
  Grep `Saving a memory is a two-step process`.

When the index is loaded, it is truncated: first 200 lines and ~25,000 characters, whichever hits
first. Over the cap, a warning is appended in place of the dropped content — grep
`Only part of it was loaded. Keep index entries`. The system-prompt guideline restates the line cap:
grep `lines after` near `will be truncated`. Truncation logic is one helper — grep
`index entries are too long`.


## Memory types

Four types, shared across stores (grep the list literal `"feedback", "project", "reference"`):

| Type        | Captures                                                                          |
| ----------- | --------------------------------------------------------------------------------- |
| `user`      | the user's role, expertise, or working preferences                                |
| `feedback`  | a correction or confirmation of how to approach work (watch for quiet confirms)   |
| `project`   | ongoing work, deadlines, decisions not derivable from code or git history         |
| `reference` | where to find information in an external system (issue tracker, dashboard, channel) |

The full taxonomy (when-to-save, how-to-use, body structure, worked examples) ships two ways. By
default it is embedded inline in the system prompt (grep `## Types of memory`). When the
`tengu_ochre_finch` flag is on, the inline block is replaced by a pointer to a non-user-invocable
skill named `memory-types` (grep `Full reference for the memory type taxonomy`), and the model is
told to invoke it before saving (grep `skill for scope, body structure and examples`).

Team-aware contexts use a scoped variant of the taxonomy that tags each type `private` or `team`
(grep `<scope>always private</scope>`); single-user contexts use the unscoped variant. The selector
is whether team memory is active, not a flag. See `TEAM_MEMORY.md`.

Two cross-cutting instruction blocks travel with every store:

- What not to save — grep `## What NOT to save in memory`. Excludes code patterns, git history, fix
  recipes, anything already in `CLAUDE.md`, and ephemeral task state. These exclusions hold even
  when the user asks to save; the model is told to instead extract what was surprising.
- Staleness — grep `## Before recommending from memory`. A memory naming a file/function/flag is a
  claim about when it was written; verify against current state before acting on it.


## The master gate: `Gc()`

All three stores hang off one gate. Relocate it via the inputs it reads —
`CLAUDE_CODE_DISABLE_AUTO_MEMORY` and the `autoMemoryEnabled` setting. It returns false — memory
fully off — when any of:

- memory was toggled off for the session (the `/toggle-memory` runtime kill-switch),
- safe mode is active,
- `CLAUDE_CODE_DISABLE_AUTO_MEMORY` is truthy (an explicit-affirmative value forces on instead),
- `CLAUDE_CODE_SIMPLE` is set,
- remote mode is active with neither `CLAUDE_CODE_REMOTE_MEMORY_DIR` nor
  `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE` set,
- a feature-flag kill-switch trips.

Otherwise it honors the `autoMemoryEnabled` setting, defaulting to on. The gate covers agent and
team memory too, not just auto memory — `CLAUDE_CODE_DISABLE_AUTO_MEMORY` and `autoMemoryEnabled`
disable the whole family.

The session dispatcher that turns this gate into the loaded prompt emits `tengu_memdir_loaded` on
success; relocate it there. Its disabled path emits `tengu_memdir_disabled` (with
`disabled_by_env_var` / `disabled_by_setting` dimensions) and, when team memory would otherwise have
been wanted, `tengu_team_memdir_disabled`.


## Telemetry taxonomy

Loads fire `tengu_memdir_loaded` carrying a `memory_type` dimension with exactly three values:

| `memory_type` | Store                                            |
| ------------- | ------------------------------------------------ |
| `auto`        | the per-project auto-memory directory            |
| `team`        | the `team/` subdirectory mirror                  |
| `agent`       | a subagent's persistent-memory directory         |

These pass through unhashed. Keep this set distinct from the capitalized
`User/Project/Local/Managed` taxonomy used by the separate, older `CLAUDE.md` memory feature (the
thing `/memory` edits — see `AUTO_MEMORY.md`).


## Environment variables

| Variable                              | Effect                                                                    |
| ------------------------------------- | ------------------------------------------------------------------------- |
| `CLAUDE_CODE_DISABLE_AUTO_MEMORY`     | Truthy disables the whole family; explicit-affirmative forces on          |
| `CLAUDE_MEMORY_STORES`                | JSON list of team memory mounts; presence also enables team memory        |
| `CLAUDE_CODE_REMOTE_MEMORY_DIR`       | Relocates memory roots under a remote dir (used in remote/teleport mode)  |
| `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE`  | Explicit auto-memory directory override                                   |
| `CLAUDE_COWORK_MEMORY_GUIDELINES`     | Replaces the built-in memory prompt with verbatim text under `# auto memory` |
| `CLAUDE_COWORK_MEMORY_EXTRA_GUIDELINES` | Appended to the memory prompt for every store                            |
| `CLAUDE_COWORK_MEMORY_INDEX_CONTENT`  | Injected index content (cowork integration)                               |

All `CLAUDE_COWORK_MEMORY_*` names are registered together — grep
`CLAUDE_COWORK_MEMORY_PATH_OVERRIDE`.


## Feature flags

| Flag                    | Role                                                                           |
| ----------------------- | ------------------------------------------------------------------------------ |
| `tengu_moth_copse`      | Umbrella for the newer memory-prompt behavior; also gates a per-turn "Memory:" reminder in the main session |
| `tengu_herring_clock`   | Enables team memory when `CLAUDE_MEMORY_STORES` is unset                        |
| `tengu_ochre_finch`     | Swaps the inline memory-types taxonomy for a pointer to the `memory-types` skill |
| `tengu_billiard_aviary` | Selects the `tiny_memory` leaf dir and the "immutable files / one fact per file" taxonomy family |

Defaults are off; verify against the current bundle with the tripwire below.


## Settings keys

- `autoMemoryEnabled` — gate honored by `Gc()` (default on).
- `autoMemoryDirectory` — auto-memory directory override (precedence: policy → flag → local/project
  when trusted → user). See `AUTO_MEMORY.md`.


## Comparison

| Aspect              | Auto memory                          | Agent memory                              | Team memory                                  |
| ------------------- | ------------------------------------ | ----------------------------------------- | -------------------------------------------- |
| Who uses it         | the main session                     | a subagent with `memory:` set             | the main session (team-enabled)              |
| Opt-in              | on by default (gate `Gc()`)          | per-agent `memory: user\|project\|local`  | `CLAUDE_MEMORY_STORES` or `tengu_herring_clock` |
| Default root        | `~/.claude/projects/<slug>/memory/`  | `.claude/agent-memory/<name>/` etc.       | `<auto-memory-dir>/team/` (local mirror)     |
| Backing store       | local filesystem                     | local filesystem                          | remote memory-service (synced to local)      |
| Scope selector      | n/a                                  | `user` / `project` / `local`              | per-mount `scope: user\|team`, `mode: rw\|ro` |
| Telemetry type      | `auto`                               | `agent`                                   | `team`                                       |
| Doc                 | `AUTO_MEMORY.md`                     | `AGENT_MEMORY.md`                         | `TEAM_MEMORY.md`                             |

Public docs cover the user-facing slices: `code.claude.com/docs/en/memory` (auto memory, `/memory`),
`code.claude.com/docs/en/sub-agents#enable-persistent-memory` (agent memory), and
`code.claude.com/docs/en/claude-directory` (the on-disk directories). The mechanics here — gates,
truncation caps, the memory-service client, the flags — are not in the public docs.


## Relocating in a new bundle

All anchors are version-stable strings. Where a behavior lives in a minified function, the anchor is
a stable string inside or emitted by it, not the (volatile) function name.

| Concept                       | Grep anchor                                            |
| ----------------------------- | ------------------------------------------------------ |
| Shared builder                | property key `memoryDir:`                              |
| Save instructions             | `How to save memories` / `Saving a memory is a two-step process` |
| Index filename                | `"MEMORY.md"`                                          |
| Index truncation (200 / 25k)  | `Only part of it was loaded. Keep index entries`       |
| Memory types                  | `"feedback", "project", "reference"` / `## Types of memory` |
| memory-types skill            | `Full reference for the memory type taxonomy`          |
| What-not-to-save / staleness  | `## What NOT to save in memory` / `## Before recommending from memory` |
| Master gate                   | `CLAUDE_CODE_DISABLE_AUTO_MEMORY` / `autoMemoryEnabled` |
| Session dispatcher            | `tengu_memdir_loaded` (emitted on load)               |
| Disabled telemetry            | `tengu_memdir_disabled` / `tengu_team_memdir_disabled` |


## Tripwires

- `□` One shared builder serves auto and agent memory (`displayName: t, memoryDir: n`).
- `□` Index file is `MEMORY.md`; load caps are 200 lines / 25,000 chars.
- `□` Four memory types: `user`, `feedback`, `project`, `reference`.
- `□` `memory_type` telemetry taxonomy is exactly `auto` / `team` / `agent`.
- `□` `Gc()` is the single gate for all three stores; `CLAUDE_CODE_DISABLE_AUTO_MEMORY` and
  `autoMemoryEnabled` disable the whole family.
