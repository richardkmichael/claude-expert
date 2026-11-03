---
verified: 2.1.277
verified_on: 2026-09-19
section: Architecture and dependencies
style: landmark
scope: 'Orientation map: where app concerns live, and which doc owns each'
landmarks:
  - CLAUDE_CONFIG_DIR
  - .config.json
  - triBool
---
# Application Functional Breakdown

An orientation map: which app-level concerns live in the bundle, how to find each one, and which
doc covers it in depth. This doc deliberately holds no detail that another doc owns.

## Finding app code at all

App and library code are interleaved, and the application is split across a thousand-odd
content-hashed chunk modules. Neither module boundaries nor ordering are stable, so orient by
grepping app-specific strings rather than by position: `tengu_*` event names, `CLAUDE_CODE_*` env
vars, config keys, tool names, and literal prompt or UI text. None of those appear inside bundled
third-party libraries.

Read the `// ==== bun module:` banner above a hit only to know which module you landed in. Chunk
names are content hashes and change every release.

## Configuration and settings

| Concern            | Landmark                          | Depth                     |
| ------------------ | --------------------------------- | ------------------------- |
| Config directory   | `CLAUDE_CONFIG_DIR`               | `SETTINGS.md`             |
| Global config file | `.config.json`, `.claude`+`.json` | `SETTINGS.md`             |
| Settings merge     | `settings.json`, `errors` array   | `SETTINGS.md`             |
| Boolean env values | truthy set `1/true/yes/on`        | `GIT_USAGE.md`            |

The config directory is `CLAUDE_CONFIG_DIR` when set, otherwise `.claude` under the home directory.

The global config file has a two-step resolution worth knowing: a `.config.json` inside the config
directory wins if it exists, and otherwise the path is `.claude<suffix>.json` in `CLAUDE_CONFIG_DIR`
or the home directory. The suffix is not a constant. It is empty in production and one of
`-staging-oauth`, `-local-oauth` or `-custom-oauth` when pointed at a non-production auth
environment, with `CLAUDE_CODE_CUSTOM_OAUTH_URL` forcing the custom variant.

That interpolation is why grepping for the literal `.claude.json` finds call sites and comments but
not the construction site. Grep `.config.json` instead and read the function next to it, or grep the
suffix list.

Boolean env vars are parsed by shared helpers with fixed token sets rather than ad hoc per call
site: truthy is `1`, `true`, `yes`, `on`; falsy is `0`, `false`, `no`, `off`; both trimmed and
case-insensitive. Most call sites reach these through a typed env-accessor layer that declares each
variable as a boolean or tri-state boolean, so the parsing does not appear inline at the call site.
Grep `triBool` for the tri-state declarations.

## Agents and skills

| Concern                  | Landmark                     | Depth                            |
| ------------------------ | ---------------------------- | -------------------------------- |
| Agent directory          | `agents` under `.claude`     | `SUBAGENTS.md`                   |
| Agent frontmatter schema | `whenToUse`, `allowed-tools` | `MARKDOWN_FRONTMATTER.md`        |
| Agent discovery          | `agent-` display prefix      | `SUBAGENTS.md`                   |
| Model resolution         | `CLAUDE_CODE_SUBAGENT_MODEL` | `MAIN_THREAD_AGENT_AND_MODEL.md` |

A discovered agent is surfaced as a completion entry whose display text is `agent-` followed by the
agent type, with the description taken from the agent's `whenToUse` and a per-type color.

## Terminal and environment detection

Detection runs once at startup from env vars, in a fixed priority order, and its result drives
notification channel selection among other things. `NOTIFICATIONS.md` holds the order and the
consequences.

## Tool surface

Tool registration, availability gating and permission checks are in `TOOLS_AND_EXECUTION.md`.
Per-tool validation behavior is in `TOOL_VALIDATION.md`. Tool descriptions are template literals
with interpolated values; the verbatim text is in `PROMPTS_RENDERED.md`.

Tools that show a confirmation render their own description string for the prompt, for example the
web search tool rendering the pending query. Those strings are part of the UI surface, not the
model-facing description.

## State and files

| Written                        | Read                                      |
| ------------------------------ | ----------------------------------------- |
| Global config file             | Global config file                        |
| `settings.json` at each scope  | `settings.json` at each scope             |
| Session transcripts as JSONL   | Agent and skill markdown with frontmatter |
| Shell snapshots                | `CLAUDE.md` and its includes              |

Transcript layout is in `SESSION_TRANSCRIPT.md` with a JSON Schema under `schemas/`. Shell snapshot
behavior is in `BASH_TOOL_EXECUTION.md`. `CLAUDE.md` discovery and includes are in
`CLAUDE_MD_EXTERNAL_INCLUDES.md`.
