---
verified: 2.1.317
verified_on: 2026-11-03
section: Memory
style: landmark
scope: 'Hub: shared memory machinery, gates, recall, stores comparison'
landmarks:
  - tengu_memdir_loaded
  - tengu_memdir_disabled
  - Saving a memory is a two-step process
  - 'Only part of it was loaded:'
  - 'Select memories relevant to:'
---
# Memory System

Claude Code has one persistent-memory mechanism pointed at several stores. This doc is the hub: it
describes the shared machinery, the gates, and how the stores differ, and routes to the per-store
docs. Read it first, then the leaf that matches the store you care about.

- `AUTO_MEMORY.md`: the per-project memory the main session reads and writes.
- `AGENT_MEMORY.md`: per-subagent memory, opted into by an agent's `memory:` frontmatter field.
- `TEAM_MEMORY.md`: shared memory synced from a remote memory-service via `CLAUDE_MEMORY_STORES`.

Synced project memory and account memory have no leaf doc; their hub-level facts are below.


## One mechanism, several stores

Every store is the same idea: a directory holding a `MEMORY.md` index plus one file per memory,
described to the model by prompt blocks that all stores share. The stores differ in where the
directory lives, how the index reaches the model, and a few scope-specific guideline lines.

The shared blocks live in one module. Relocate it with `rg -nF '## What NOT to save in memory'`; its
neighbors are the type taxonomies, `## Before recommending from memory`,
`## When to access memories`, and the save instructions
(`rg -nF 'Saving a memory is a two-step process'`, 4 hits: the shared save block and three
store-specific variants).

There are two assembly paths:

- The instruction builder emits `# <displayName>` and
  `You have a persistent, file-based memory system at <dir>`, then the shared blocks. The
  auto-memory prompt calls it with the display name `auto memory`.
- The agent-memory builder wraps the instruction builder and appends a `## MEMORY.md` section that
  holds the agent's index (or `Your MEMORY.md is currently empty` text). Relocate it with
  `rg -nF 'displayName: "Persistent Agent Memory"'` (1 hit, the agent-memory caller). It always
  inlines the type taxonomy, so the `memory-types` skill pointer below never applies to it.

Team memory, synced project memory and lean-prompt models use sibling builders (see "The session
dispatcher") that reuse the same blocks.


## The MEMORY.md index pattern

- Index file: `MEMORY.md`. Relocate the constants with `rg -n -A5 '= "MEMORY.md",$'`; the first hit
  is followed by `200`, `25000`, `4 * <that>`, `200`, `4096`: the index line cap, the index
  character cap, a read cap, and the recall line and byte caps for one memory file.
- The index is an index, not a memory: one line per entry, under about 150 characters, format
  `- [Title](file.md) — one-line hook`, no frontmatter.
- Memory files: each memory is its own `*.md` file with YAML frontmatter `name`, `description` and
  `metadata.type`. For `feedback` and `project` the body is the rule or fact followed by `**Why:**`
  and `**How to apply:**` lines. Memories cross-link with `[[name]]` slugs.
- Saving is two steps when the index is loaded: write the memory file, then add a one-line pointer
  to `MEMORY.md` (`Saving a memory is a two-step process`). In recall mode (below) the index is not
  loaded and the instructions drop step 2, adding instead a size rule
  (`Keep each memory file under`, then the 4096-byte cap, `including frontmatter`).

Loading the index truncates it to the first 200 lines and 25,000 characters, cutting at a line
boundary, whichever comes first. Over the cap a `> WARNING:` line replaces the dropped content. It
names the size, then says `Only part of it was loaded:` with what was cut, and ends
`Keep index entries to one line under ~200 chars; move detail into topic files.` Relocate the helper
with `rg -nF 'index entries are too long'`. The save instructions restate the line cap:
`lines after 200 will be truncated, so keep the index concise`.

How the index reaches the model depends on the store:

| Store                 | Index delivery                                                           |
| --------------------- | ------------------------------------------------------------------------ |
| Auto memory           | Context file of type `AutoMem` in the CLAUDE.md block (see below)        |
| Agent memory          | `## MEMORY.md` section of the subagent's system prompt                   |
| Team memory           | Per-mount fragments in the memory prompt (`fetched from memory-service`) |
| Synced project memory | Read through the memory tools; not mirrored to local files               |

The auto-memory index is loaded with the CLAUDE.md files, not built into the memory prompt. It
appears as `Contents of <path> (user's auto-memory, persists across conversations):` (grep that
parenthetical). `CLAUDE_COWORK_MEMORY_INDEX_CONTENT` replaces the file's content, and an empty value
suppresses the index. The loader skips the index in recall mode and when the read fence is up.


## Memory types

Four types, shared across stores (grep `"user", "feedback", "project", "reference"`, 2 hits: the
type list and the frontmatter schema):

| Type        | Captures                                                                        |
| ----------- | ------------------------------------------------------------------------------- |
| `user`      | the user's role, expertise, or working preferences                              |
| `feedback`  | a correction or confirmation of how to approach work (watch for quiet confirms) |
| `project`   | ongoing work, deadlines, decisions not derivable from code or git history       |
| `reference` | where to find information in an external system (tracker, dashboard, channel)   |

The full taxonomy (when to save, how to use, body structure, worked examples) is inlined in the
prompt under `## Types of memory`. When `tengu_ochre_finch` is on, the inline block is replaced by a
short type list and the line
`Invoke the memory-types skill for scope, body structure and examples once you've decided to save`
(grep `skill for scope, body structure and examples`). The `memory-types` skill (grep
`Full reference for the memory type taxonomy`) is not user-invocable and is enabled only when the
master gate is on and that flag is set.

A scoped variant tags each type `private` or `team` (grep `<scope>always private</scope>`). The
two-directory team prompt uses it, and the `memory-types` skill serves it when team memory is active
or synced project memory has connected stores. Otherwise the unscoped variant is used.

Blocks that travel with every store:

- `## What NOT to save in memory`: code patterns, git history, fix recipes, anything already in
  CLAUDE.md, ephemeral task state. The exclusions hold even when the user asks to save; the model is
  told to ask what was surprising instead.
- `## Before recommending from memory`: a memory naming a file, function or flag is a claim about
  when it was written; verify before recommending.
- `## When to access memories` and `## Memory and other forms of persistence` (plans and tasks
  versus memory).
- `## Project skill upkeep`, only when `tengu_gorse_fathom` is on: fold a `feedback` correction
  about a repeatable step into the project skill that drives it.
- `## Citing memories`, only when `tengu_salt_marsh` is on: wrap sentences that use a memory in
  `<cc-memory filenames="...">` tags.


## The master gate

All stores hang off one gate. Relocate its core with
`rg -n -B2 -A6 'process.env.CLAUDE_CODE_DISABLE_AUTO_MEMORY'` (1 hit). The enclosing function is a
tri-state switch (`off`, `forced_on`, `unset`); the gate wraps it. The gate is false, memory fully
off, when the first of these applies:

1. Memory is paused for the session (`memoryToggledOff`) or auto memory is off for the session
   (`autoMemoryOffThisSession`). Both are session state saved into session metadata and handed to
   background sessions as `CLAUDE_BG_MEMORY_TOGGLED_OFF` and `CLAUDE_BG_AUTO_MEMORY_OFF`. No control
   in this build sets them: `/pause-memory` (aliases `memory-pause`, `toggle-memory`) has
   `isEnabled` hardwired false, and the `/memory` dialog's per-session row is not built. Only the
   restore paths for resumed and background sessions set them.
2. The switch says `off`: safe mode (`CLAUDE_CODE_SAFE_MODE` or `--safe-mode`), a restricted session
   (`--restricted`, `CLAUDE_CODE_RESTRICTED`, or the SDK `restricted` option), a diskless process (a
   cloud session kind with no local disk), or a truthy `CLAUDE_CODE_DISABLE_AUTO_MEMORY`.
3. An explicitly falsy `CLAUDE_CODE_DISABLE_AUTO_MEMORY` makes the switch `forced_on`: memory is on
   and the rest of this list is skipped.
4. The switch says `off` because of `CLAUDE_CODE_SIMPLE` (set by `--bare`), or because
   `CLAUDE_CODE_REMOTE` is set with neither `CLAUDE_CODE_REMOTE_MEMORY_DIR` nor
   `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE`.
5. A model kill switch trips: the `tengu_sepia_cormorant` flag holds a list of model-name
   substrings, one matches the main-loop model case-insensitively, and `tengu_umber_petrel` is on.
6. Otherwise the `autoMemoryEnabled` setting decides, defaulting to on.

The gate covers every store: agent-memory prompts, team memory, synced project memory, recall and
the `memory-types` skill all check it. `CLAUDE_CODE_DISABLE_AUTO_MEMORY` and `autoMemoryEnabled`
therefore disable the whole family.

Two related checks sit beside the gate:

- Read fence. When the `blockReadsOutsideWorkingDirectories` permission is in force and the
  auto-memory directory is unresolved or chosen by a project or local `autoMemoryDirectory`, the
  dispatcher and the index loader treat memory as off. The disabled event then carries
  `read_block_fenced`.
- Turning memory back on. The `/memory` dialog's `Auto-memory` row writes `autoMemoryEnabled` to
  user settings and fires `tengu_auto_memory_toggled`. It refuses to turn memory on in a background
  session (`CLAUDE_CODE_SESSION_KIND` set), a teammate, or a child session
  (`CLAUDE_CODE_CHILD_SESSION`), showing
  `can't be turned on here; use a session started outside Claude Code`.


## The session dispatcher

One async function builds the main session's memory prompt. Relocate it with
`rg -nF 'read_block_fenced'` (1 hit, in its disabled tail). It takes the first branch that applies:

| Branch                                | Prompt (grep)                                            |
| ------------------------------------- | -------------------------------------------------------- |
| `CLAUDE_COWORK_MEMORY_GUIDELINES` set | that text verbatim under `# auto memory`                 |
| Synced project memory connected       | `You have persistent, shared memory reached through the` |
| Lean-prompt model (`PROMPTS.md`)      | `Each memory is one file holding one fact`               |
| Team memory active                    | `## Memory scope`, or a team-only variant                |
| Memory on                             | the instruction builder, display name `auto memory`      |
| Memory off                            | none; emits `tengu_memdir_disabled`                      |

The synced-project-memory branch applies only when `CLAUDE_MEMORY_STORES` is unset or invalid. The
lean branch also covers team directories when team memory is active. In the off branch the
`tengu_memdir_disabled` event carries `disabled_by_env_var`, `disabled_by_setting` and
`read_block_fenced`; `tengu_team_memdir_disabled` follows when `CLAUDE_MEMORY_STORES` is set.

`CLAUDE_COWORK_MEMORY_EXTRA_GUIDELINES` is appended to the memory prompt of every store, agent
memory included. With the SDK's `excludeDynamicSections`, the system prompt keeps the static
instructions (`The directory path is provided in your session context`) and the session context
carries a short `# auto memory` / `Memory directory:` block.


## Recall mode

Recall mode is on when `tengu_moth_copse` is on or `CLAUDE_MEMORY_STORES` is non-empty. Then:

- The auto-memory `MEMORY.md` index is not loaded into context, and the save instructions are the
  one-step form.
- Each main-session user turn of more than one word starts a background selector: a side query with
  the prompt `Select memories relevant to:` and a `selected_memories` JSON schema. The selected
  files arrive as a `relevant_memories` attachment, introduced to the model as
  `Retrieved for possible relevance — use only if it actually applies to what the user asked.`
  Subagents do not run it. When the message mentions `@agent-<name>` subagents that have `memory:`,
  their memory directories are searched instead of the auto-memory directory.
- Recall shows only the first 4096 bytes or 200 lines of a memory file. A post-write check warns
  when a memory file nears or passes that (`recall limit`) and flags `-2`-style continuation files.
- Telemetry: `tengu_memdir_prefetch_collected`, `tengu_memdir_prefetch_blocking_wait`, and the
  `memory_recall_select` outcome counter.


## Background writers

Besides the model writing memory files directly, two background passes write to auto memory:

- Post-turn extraction (`[extractMemories]` log prefix, `tengu_extract_memories_*` events). Runs at
  the end of main-session turns when `tengu_passport_quail` is on (non-interactive sessions also
  need `tengu_slate_thimble`) or when `CLAUDE_CODE_POST_TURN_MEMORY` is set with a valid
  `CLAUDE_CODE_POST_TURN_MEMORY_CONFIG`.
- Auto-dream consolidation (`# Dream: Memory Consolidation`, `tengu_auto_dream_*` events). Available
  when the `tengu_onyx_plover` config says `enabled` or `available`; the `autoDreamEnabled` setting
  overrides the config's `enabled` default. The `/memory` dialog has an `Auto-dream` row.


## Synced project memory and account memory

Synced project memory is an organization store reached through the `memory_list`, `memory_read` and
`memory_write` tools, not through local files. It is shared with the people and sessions working in
the organization's projects. It is available only when all of these hold:
`CLAUDE_CODE_DISABLE_ORG_MEMORY` is unset, safe mode is off, `tengu_haze_glass` is on,
`CLAUDE_MEMORY_STORES` is unset, and the session uses a claude.ai OAuth login with the required
scopes, among other checks. The org's `allow_memory_sync` policy must also allow it; HIPAA and ZDR
deny it. Memory access then switches from `files` to `tools` mode (`tengu_linen_orbit` also selects
`tools`). The `orgMemoryRead` and `orgMemoryWrites` rows in `/config` and `/memory` (labels starting
`Synced project memory` and `Write to synced project memory`) turn reads and writes on or off per
project. The personal auto-memory directory stays in use alongside it.

Account memory is referenced throughout the bundle: hook guards, Remote Control withholding, and the
`/pause-memory` description `Pause account memory and local auto-memory`. Its store module is
compiled out of this build (`this build has no account memory store`), so account recall never runs.


## Telemetry taxonomy

Loads fire `tengu_memdir_loaded` (relocate with `rg -n '"tengu_memdir_loaded"'`, 4 emit calls in one
helper) with a `memory_type` dimension of exactly three values:

| `memory_type` | Store                                                            |
| ------------- | ---------------------------------------------------------------- |
| `auto`        | the auto-memory directory, including the synced-memory branch    |
| `team`        | the `team/` directory mirror                                     |
| `agent`       | a subagent's memory directory (only when its index is non-empty) |

Every load also carries `memory_access_mode` (`files` or `tools`). Branches add `prompt_variant`
(`base` or `memory_tools`), `team_write_steered`, `tools_writable`, `connected_store_count`,
`index_loaded`, or the index size and truncation fields. Values pass through unhashed.

Keep this set distinct from the capitalized `User` / `Project` / `Local` / `Managed` taxonomy of the
CLAUDE.md instruction files, which the `InstructionsLoaded` hook reports as its `memory_type`.
Internally the auto-memory index is a fifth file type, `AutoMem`, in that same CLAUDE.md list.


## Environment variables

| Variable                                | Effect                                                 |
| --------------------------------------- | ------------------------------------------------------ |
| `CLAUDE_CODE_DISABLE_AUTO_MEMORY`       | Truthy: family off. Explicitly falsy: forced on        |
| `CLAUDE_CODE_SIMPLE`                    | Memory off (set by `--bare`) unless forced on          |
| `CLAUDE_CODE_SAFE_MODE`                 | Memory off, even when forced on                        |
| `CLAUDE_CODE_RESTRICTED`                | Restricted session: memory off, even when forced on    |
| `CLAUDE_CODE_REMOTE_MEMORY_DIR`         | Memory base for remote sessions; keeps them on         |
| `CLAUDE_COWORK_MEMORY_PATH_OVERRIDE`    | Auto-memory directory override; keeps remote on        |
| `CLAUDE_COWORK_MEMORY_GUIDELINES`       | Replaces the memory prompt, under `# auto memory`      |
| `CLAUDE_COWORK_MEMORY_EXTRA_GUIDELINES` | Appended to the memory prompt of every store           |
| `CLAUDE_COWORK_MEMORY_INDEX_CONTENT`    | Replaces the auto-memory index content; empty hides it |
| `CLAUDE_MEMORY_STORES`                  | JSON store list: team memory, recall mode              |
| `CLAUDE_CODE_DISABLE_ORG_MEMORY`        | Synced project memory off                              |
| `CLAUDE_BG_MEMORY_TOGGLED_OFF`          | Carries the session pause into a background session    |
| `CLAUDE_BG_AUTO_MEMORY_OFF`             | Carries the session auto-memory switch into one        |
| `CLAUDE_CODE_POST_TURN_MEMORY`          | Turns on post-turn extraction (with its `_CONFIG`)     |

`TEAM_MEMORY.md` covers the memory-service sync variables (`CLAUDE_CODE_DISABLE_MEMORY_*`,
`CLAUDE_CODE_MEMORY_PUSH_DELETE_MODE`).


## Feature flags

All default off.

| Flag                    | Role                                                   |
| ----------------------- | ------------------------------------------------------ |
| `tengu_moth_copse`      | Recall mode                                            |
| `tengu_ochre_finch`     | Swaps the inline taxonomy for the `memory-types` skill |
| `tengu_gorse_fathom`    | Adds `## Project skill upkeep`                         |
| `tengu_salt_marsh`      | Adds `## Citing memories` and `<cc-memory>` tagging    |
| `tengu_sepia_cormorant` | Model-substring list for the model kill switch         |
| `tengu_umber_petrel`    | Arms the model kill switch                             |
| `tengu_haze_glass`      | Makes synced project memory available                  |
| `tengu_linen_orbit`     | Forces `tools` memory access mode                      |
| `tengu_passport_quail`  | Post-turn extraction                                   |
| `tengu_slate_thimble`   | Post-turn extraction in non-interactive sessions       |
| `tengu_onyx_plover`     | Auto-dream availability and default (a config object)  |

Relocate each flag with `rg -n '"<flag>"'`.


## Settings keys

- `autoMemoryEnabled`: the setting step of the master gate (default on).
- `autoMemoryDirectory`: auto-memory directory override. See `AUTO_MEMORY.md` for its precedence.
- `autoDreamEnabled`: auto-dream on or off.
- `permissions.blockReadsOutsideWorkingDirectories`: can raise the read fence.
- `orgMemoryRead`, `orgMemoryWrites`: per-project synced-project-memory switches.


## Comparison

| Store                 | Used by          | Opt-in                                            |
| --------------------- | ---------------- | ------------------------------------------------- |
| Auto memory           | the main session | on by default (master gate)                       |
| Agent memory          | a subagent       | `memory:` set to `user`, `project` or `local`     |
| Team memory           | the main session | a `scope: "team"` entry in `CLAUDE_MEMORY_STORES` |
| Synced project memory | the main session | org gates above, claude.ai login                  |

| Store                 | Location                            | `memory_type` | Doc               |
| --------------------- | ----------------------------------- | ------------- | ----------------- |
| Auto memory           | `~/.claude/projects/<slug>/memory/` | `auto`        | `AUTO_MEMORY.md`  |
| Agent memory          | `.claude/agent-memory/<name>/` etc. | `agent`       | `AGENT_MEMORY.md` |
| Team memory           | `<auto-memory-dir>/team/`, synced   | `team`        | `TEAM_MEMORY.md`  |
| Synced project memory | remote, through the memory tools    | `auto`        | this doc          |

Agent memory's other roots: `<memory-base>/agent-memory/<name>/` for `user` scope, and
`.claude/agent-memory-local/<name>/` for `local` scope (under `CLAUDE_CODE_REMOTE_MEMORY_DIR` when
that is set).

The public docs cover the user-facing slices: `code.claude.com/docs/en/memory` (auto memory, the
`/memory` toggle, `autoMemoryEnabled`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY`),
`code.claude.com/docs/en/sub-agents` (agent memory), and `code.claude.com/docs/en/claude-directory`
(the on-disk directories). The gate order, truncation caps, recall mode, synced project memory and
the flags are not in the public docs.


## Relocating in a new bundle

| Concept                    | Grep anchor                                                         |
| -------------------------- | ------------------------------------------------------------------- |
| Shared prompt blocks       | `## What NOT to save in memory`                                     |
| Save instructions          | `Saving a memory is a two-step process`                             |
| Agent-memory builder       | `displayName: "Persistent Agent Memory"`                            |
| Index caps                 | `rg -n -A5 '= "MEMORY.md",$'` (first hit)                           |
| Truncation helper          | `index entries are too long` / `Only part of it was loaded:`        |
| Auto-memory index delivery | `user's auto-memory, persists across conversations`                 |
| Memory types               | `"user", "feedback", "project", "reference"` / `## Types of memory` |
| memory-types skill         | `Full reference for the memory type taxonomy`                       |
| Master gate switch         | `process.env.CLAUDE_CODE_DISABLE_AUTO_MEMORY`                       |
| Model kill switch          | `"tengu_sepia_cormorant"`                                           |
| Session switches           | `memoryToggledOff()` / `autoMemoryOffThisSession()`                 |
| Re-enable refusal          | `can't be turned on here; use a session started outside`            |
| Session dispatcher         | `read_block_fenced`                                                 |
| Recall selector            | `Select memories relevant to:`                                      |
| Recall attachment          | `Retrieved for possible relevance`                                  |
| Post-turn extraction       | `[extractMemories]`                                                 |
| Auto-dream                 | `# Dream: Memory Consolidation`                                     |
| Synced project memory gate | `CLAUDE_CODE_DISABLE_ORG_MEMORY` / `"tengu_haze_glass"`             |
| Account memory stub        | `this build has no account memory store`                            |


## Tripwires

- `□` The agent-memory builder is the only caller passing `displayName: "Persistent Agent Memory"`;
  auto memory's prompt uses the display name `auto memory`.
- `□` Index file is `MEMORY.md`; index caps are 200 lines and 25,000 characters; recall caps a
  memory file at 200 lines and 4096 bytes.
- `□` The auto-memory index is an `AutoMem` context file in the CLAUDE.md block, not a section of
  the memory prompt.
- `□` Four memory types: `user`, `feedback`, `project`, `reference`.
- `□` `memory_type` telemetry is exactly `auto` / `team` / `agent`.
- `□` One gate covers every store; truthy `CLAUDE_CODE_DISABLE_AUTO_MEMORY` or
  `autoMemoryEnabled: false` turns the whole family off; explicitly falsy forces it on past
  `CLAUDE_CODE_SIMPLE`, remote mode, the model kill switch and the setting.
- `□` `/pause-memory` has `isEnabled` false.
- `□` Recall mode = `tengu_moth_copse` or non-empty `CLAUDE_MEMORY_STORES`.
- `□` Account memory store module is compiled out (`this build has no account memory store`).
