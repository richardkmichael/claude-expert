---
verified: 2.1.277
verified_on: 2026-09-18
section: Config, settings, and frontmatter
style: landmark
scope: Main-thread agent selection and model precedence
landmarks:
  - Overrides the 'agent' setting
  - agent_frontmatter
  - sdk-cli
---
# Main-thread agent and model selection

How a top-level session decides which agent definition, if any, governs its main thread, and which
model it runs on. Both resolutions are shared by interactive and headless (`-p`) sessions, which
makes this the reference for what a nested `claude -p` inherits from the machine it runs on. This
document follows the landmark style in `GUIDELINES.md`.

## Re-location recipes

| Target                                | Grep anchor                                                        |
|---------------------------------------|--------------------------------------------------------------------|
| `--agent` flag definition             | `Agent for the current session. Overrides the 'agent' setting.`    |
| `agent` settings key                  | `Name of an agent (built-in or custom) to use for the main thread` |
| Startup resolution of the two         | `--agent '` followed by `' not found. Available agents:`           |
| Soft fallback when the name is unknown| `not found. Available agents:` ... `Using default behavior.`       |
| Built-in `claude` agent definition    | `FleetView's default when no agent name is typed`                  |
| System-prompt composition             | `getCoordinatorSystemPrompt` (same function builds the normal path) |
| Model precedence                      | `agent_frontmatter` (the settings-layer label set beside `routine_frontmatter`, `env`, `cli`) |
| Print mode's entrypoint               | `sdk-cli`                                                          |

## Agent selection

Two inputs name the main-thread agent, in this order:

1. `--agent <agent>` — "Agent for the current session. Overrides the 'agent' setting."
2. The `agent` settings key — "Name of an agent (built-in or custom) to use for the main thread.
   Applies the agent's system prompt, tool restrictions, and model." It is read from the merged
   settings, so user, project and local layers all supply it.

When neither is set there is no main-thread agent definition. The session runs the ordinary default
system prompt with no agent identity, no agent-supplied tool restrictions and no agent-supplied
model. There is no implicit root agent standing in.

The built-in agent named `claude` is not that implicit default. Its `whenToUse` string
("Catch-all for any task that doesn't fit a more specific agent. FleetView's default when no agent
name is typed.") describes the agent-dispatch view, and its system prompt is the background-job
prompt that opens `This session is a background job.` It applies only when something names it.
Startup exempts that one name from the hard `--agent '<name>' not found` error, so `--agent claude`
is accepted even where the definition is not in the loaded set.

An unknown name behaves differently depending on where it came from. From `--agent` on a fresh,
non-`stream-json` session, startup fails with `--agent '<name>' not found. Available agents: ...`.
From the `agent` setting, or on a resumed/continued session, resolution logs
`Warning: agent "<name>" not found. Available agents: ... Using default behavior.` and proceeds
with no agent.

Where a definition is found, its prompt joins the system prompt one of two ways. A definition with
`appendSystemPrompt` set keeps the default prompt and appends the agent's text after it; without it
the agent's text replaces the default block entirely. Text from `--append-system-prompt` is
appended last in both cases, so that flag never competes with agent selection. `--allowedTools` is
likewise orthogonal: it filters the tool set whether or not an agent is in play.

Headless mode changes none of this. `-p` only flips the entrypoint stamp from `cli` to `sdk-cli`.

## Model selection

Precedence, highest first. The label in the right column is the settings-layer tag the resolver
records, and is the string to grep for.

| Source                                          | Label                                 |
|-------------------------------------------------|---------------------------------------|
| `--model <model>`                               | `cli` (`cli_default` for `--model default`) |
| Agent or routine frontmatter `model`, unless `inherit` | `agent_frontmatter` / `routine_frontmatter` |
| `ANTHROPIC_MODEL`                               | `env`                                 |
| The `model` settings key                        | `settings`                            |
| Built-in default                                | (none)                                |

The consequence for a nested session: `claude -p` with no `--model` resolves the `model` settings
key from the same on-disk settings an interactive session reads, which is where the `/model` picker
persists its choice. A nested session therefore bills at whatever model the machine's settings
currently name, not at a fixed rate, unless its launcher passes `--model`.

An org default can suppress a user-settings `model` value; policy and flag layers always win. That
path is the same for interactive and headless sessions.

## Tripwires

- □ `--agent` help text still reads "Overrides the 'agent' setting."
- □ The `agent` settings key still describes applying "system prompt, tool restrictions, and model".
- □ No agent named, no agent definition on the main thread (default prompt unchanged).
- □ `--agent claude` is still exempt from the startup not-found error.
- □ Unknown `agent` setting warns and falls back rather than failing startup.
- □ `--model` still outranks agent frontmatter, which outranks `ANTHROPIC_MODEL`, which outranks the
  `model` setting.
- □ `-p` still stamps the entrypoint `sdk-cli`.
