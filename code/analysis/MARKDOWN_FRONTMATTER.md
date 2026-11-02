# Markdown Front-matter: Parsing, Schema, and Validation

Verified against: cli.prettier.js 2.1.316 (2026-11-02)

This document is a specification for formatter and linter tooling that targets Claude Code's
Markdown configuration files.  A machine-readable JSON Schema derived from it lives at
[`schemas/frontmatter.schema.json`](./schemas/frontmatter.schema.json); see
[`schemas/README.md`](./schemas/README.md) for editor and CI wiring.  This document follows the
landmark style in `GUIDELINES.md`.  Skill behaviour beyond frontmatter is in `SKILLS.md`, agent
behaviour in `SUBAGENTS.md`.

---

## Re-location recipes

Minified names change every release.  Relocate each piece by the anchor, then read the shape.

| Target                    | Grep anchor (`rg -n` over `cli.prettier.js`)           | Expected shape                                                                   |
| ------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------- |
| Strict shadow validator   | `tengu_frontmatter_shadow_unknown_key`                 | `safeParse` over a `{skill, agent, "output-style"}` map of `.strict()` schemas   |
| Shadow key lists          | `Canonical (normalized) alias of`                      | three `z.object({...})` blocks just above the validator, with `.describe()` text |
| Frontmatter parser        | `Failed to parse YAML frontmatter`                     | regex match on `---`, `Bun.YAML.parse`, sanitizer retry, returns `parseError`    |
| Fallback sanitizer        | `[{}[\]*&#!` (start of the regex)                      | line loop over `key: value`, quotes values that hit the regex                    |
| Untrusted-input refusal   | `too long, too nested, or may hold a YAML anchor`      | 64 KiB, anchor and nesting checks before parsing                                 |
| Skill field parser        | `hasUserSpecifiedDescription`                          | builds `displayName`, `argumentHint`, `allowedTools`, `disallowedTools`, ...     |
| Skill and command loaders | `[skills] YAML frontmatter in`, `"Custom command"`     | each calls the shadow check with `"skill"` then the skill field parser           |
| Agent field parser        | `has invalid isolation value`                          | per-field validation with `t(...)` log lines; returns the agent definition       |
| Agent load failure        | `tengu_agent_parse_error`                              | logs `Failed to parse agent from <path>: <reason>` when a named file is dropped  |
| Agent unknown-key warning | `does not recognize or apply`                          | diff of frontmatter keys against the agent shadow schema, with did-you-mean      |
| Plugin agent field parser | `which is ignored for plugin agents`                   | ignores `permissionMode`, `hooks`, `mcpServers`, `initialPrompt`, `observer*`    |
| Output style parser       | `has force-for-plugin set, but this option`            | shadow check with `"output-style"`, then `name`/`description`/`keep-coding-...`  |
| Memory and rules `paths`  | `Skipping non-text file in @include`                   | the function above it reads `frontmatter.paths` and strips a trailing `/**`      |
| Hook schemas              | `Permission rule syntax to filter when this hook runs` | five hook object schemas, then the discriminated union and the matcher group     |
| Hook event names          | `"PostToolBatch",` near `"DirectoryAdded",`            | the array that feeds the `hooks` record key enum                                 |
| Frontmatter hook pre-pass | `unknown hook event; entry ignored`                    | per-event and per-entry stripping with notes; guard events refuse to load        |
| Model aliases             | `"opusplan",` beside `"fable[1m]",`                    | alias array, followed by the family array `["sonnet", "opus", "haiku", "fable"]` |
| Effort presets            | `["low", "medium", "high", "xhigh", "max"]`            | the preset list, with `{ med: "medium" }` as an alias map in the effort parser   |
| Effort value parser       | `Unknown --effort value`                               | the CLI parser; the frontmatter parser follows it and also tries `parseInt`      |
| Effort field readers      | `has invalid effort '`                                 | 4 sites: agent, plugin agent, skill, plugin skill or command                     |
| Skill effort sources      | `getDefaultEffort?.(`                                  | 2 fork sites set the agent's `effort`; the inline prompt processor returns it    |
| Skill effort, Skill tool  | `SkillTool returning`                                  | below it, `{ kind: "effort", effort }` pushed onto the returned `contextLayers`  |
| Effort resolution         | `hookEffortValue: \w+, carriedEffort`                  | resolver: hook, then `CLAUDE_CODE_EFFORT_LEVEL`, turn, session, model default    |
| Effort on the wire        | `the server refused effort for model`                  | same request builder; only a string effort becomes `output_config.effort`        |
| Observer gate             | `CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS`             | env check, then `tengu_observer_agents_enabled`; fan-out adds a second gate      |
| Permission modes          | `"dontAsk",` and `=== "manual" ? "default"`            | six-mode array, `manual` normalised to `default`                                 |
| Agent colors              | `red_FOR_SUBAGENTS_ONLY`                               | eight-key map; its `Object.keys` is the accepted set                             |
| MCP server schemas        | `Command cannot be empty`, `"claudeai-proxy"`          | stdio, sse, sse-ide, ws-ide, http, ws, sdk, claudeai-proxy object schemas        |

---

## File Types

| Type                  | Location pattern                                               | Identifier                | Shadow check   |
| --------------------- | -------------------------------------------------------------- | ------------------------- | -------------- |
| Agent                 | `.claude/agents/**/*.md`                                       | `name` (required)         | `agent`        |
| Plugin agent          | `<plugin>/agents/**/*.md`                                      | `name`, else the filename | none           |
| Skill                 | `.claude/skills/<name>/SKILL.md`                               | directory name            | `skill`        |
| Command               | `.claude/commands/**/*.md`                                     | path, `:`-joined          | `skill`        |
| Plugin skill, command | `<plugin>/skills/<name>/SKILL.md`, `<plugin>/commands/**/*.md` | path, plugin-prefixed     | none           |
| Output style          | `.claude/output-styles/*.md`                                   | `name`, else the filename | `output-style` |
| Memory, rules         | `CLAUDE.md`, `.claude/rules/*.md`, `@include` files            | none                      | none           |

Command files use the skill validator and the skill field parser.  The command loader then
overrides two results: it discards `name` (the display name stays the path-derived command name)
and it discards `paths` (a command is never path-scoped).

Plugin skills and commands have their own parser (see Plugin skills and commands below).

---

## Parser

### Detection

The parser strips a leading UTF-8 BOM, then matches:

```
/^---\s*\n([\s\S]*?)---\s*\n?/
```

The opening `---` must be the first line.  If the text after the first three characters contains
no second `---`, the parser does not run the regex at all.  Without a match, `frontmatter` is
`{}` and `content` is the whole file.

### Two-stage YAML parsing

Stage 1 parses the block with `Bun.YAML.parse()`.  Stage 2 runs only when stage 1 throws: the
block goes through a line sanitizer, every leading tab is replaced by two spaces, and the result
is parsed again.  When stage 2 also throws, the parser logs `Failed to parse YAML frontmatter in
<path>: <error>` at `warn` level and returns `frontmatter: {}` with a `parseError` string.  A
document whose root is a list or a scalar also yields `{}`.

The sanitizer walks lines that match `^([a-zA-Z_-]+):\s+(\S.*)$` (top-level keys only; indented
lines and keys with digits or dots pass through).  For each such line:

1. A value already wrapped in matching `"` or `'` is left alone.
2. A value that starts with `[`, ends with `]`, and parses on its own as a YAML list is left
   alone, so `argument-hint: [file]` stays a list on the retry too.
3. A value that matches `/[{}[\]*&#!|>%@`]|: /` is wrapped in double quotes after escaping `\`
   and `"`.

The sanitizer therefore rescues single-line values containing `: ` or a YAML indicator
character.  It does not rescue a value continued on an indented next line, because the
continuation line is not a `key: value` line and stays invalid.

A ` #` inside an unquoted value is a comment to stage 1, which succeeds, so the sanitizer never
sees it: `description: a # b: c` loads as `description: "a"`.

Linter implication: flag any file that needs stage 2.  It holds bare values a standard YAML
parser rejects.

### How each loader reports a failed parse

| Loader             | On `parseError`                                                                              |
| ------------------ | -------------------------------------------------------------------------------------------- |
| Skill (`SKILL.md`) | logs `[skills] YAML frontmatter in <path> failed to parse and was ignored` at `error`; loads |
| Command            | the generic `warn` only; loads with no fields set                                            |
| Agent              | the generic `warn` only; `name` is then missing, so the agent is dropped silently            |
| Plugin agent       | the generic `warn` only; loads named after the file with a default description               |
| Output style       | the generic `warn` only; loads with filename defaults                                        |
| Untrusted sources  | refused outright (synced and MCP-served skills, untrusted plugin agents)                     |

Untrusted sources are refused before parsing when the block exceeds 64 KiB, holds a YAML anchor
(`&name`), or opens more than 256 collections (`[`, `{`, or block `-`/`?` indicators).  The refusal
text is `the frontmatter is too long, too nested, or may hold a YAML anchor`.  An untrusted skill
whose frontmatter is refused or does not parse fails with `frontmatter was not read: <reason>`; an
untrusted plugin agent fails with `the frontmatter is refused or does not parse`.

### Key normalisation

Loaders pass `normalizeKeys: true`, and the module carries a canonical key list (it includes
`compatibility`, `evals`, `commands`, `type`, `originSessionId` and
`hide-from-slash-command-tool` beside the documented keys).  The normalising function returns
its input unchanged, so keys are matched exactly as written.  `allowed_tools` is not read as
`allowed-tools`.

### Strict shadow validator

After parsing, agent, skill, command, and output-style frontmatter is checked against a Zod
`.strict()` schema for its type.  Failures do not block loading; they emit
`tengu_frontmatter_shadow_unknown_key` (unknown key) or `tengu_frontmatter_shadow_mismatch`
(`<key>:<zod issue code>`), each once per process per type and key.  The event carries the key name
when it matches `^[A-Za-z_][A-Za-z0-9_-]{0,31}$`, otherwise `other`.

The shadow schemas check keys, not values.  Nearly every field is typed as the loose scalar union
`string | number | boolean | null`, list-capable fields as that union or a string list, and `hooks`,
`mcpServers` and the `@internal` skill slots as `unknown`.  The only value sets the shadow layer
enforces are skill `context` (`inline`, `fork`, `null`) and the object shape of agent
`experimental`.  The agent schema marks `name` and `description` required, so an agent missing
either also records a mismatch.  Value validation lives in the runtime field parsers documented
below.

Agent files get a second, user-visible check: any key outside the agent shadow schema logs
`Agent file <path> has a frontmatter key Claude Code does not recognize or apply: <keys>` at `warn`,
once per file until its keys change.  Each key gets a did-you-mean hint.  Keys are compared with `-`
and `_` removed and case ignored, so `allowedTools`, `allowed-tools` and `allowed_tools` suggest
`tools`; `whenToUse` and `when_to_use` suggest `description`; `mode` gets no hint; any other key
suggests a known key that matches it so, else the nearest known key.  Plugin agent files get the
same warning, accept `when_to_use` and `when-to-use`, and never suggest the keys plugin agents
ignore.  Skills, commands and output styles have no user-visible unknown-key warning.

---

## Agent Files (`.claude/agents/*.md`)

The file body is the system prompt.  `name` and `description` are required.

| Field               | Accepted values                                                            | On invalid                                      |
| ------------------- | -------------------------------------------------------------------------- | ----------------------------------------------- |
| `name`              | string; at most 256 chars; no leading `-`; no `:` after NFKC normalisation | missing: dropped silently; else logged, dropped |
| `description`       | string; literal `\n` is expanded to a newline                              | logged, agent dropped                           |
| `model`             | alias (see Model aliases), full model ID, or `inherit` (any case)          | passed through unresolved                       |
| `effort`            | see Effort                                                                 | logged, ignored                                 |
| `permissionMode`    | see Permission modes                                                       | logged, ignored                                 |
| `tools`             | string or list of strings; `*` means all tools                             | see Tool lists                                  |
| `disallowedTools`   | string or list of strings                                                  | see Tool lists                                  |
| `skills`            | string or list of skill names                                              | unknown names warn at activation                |
| `mcpServers`        | list; each item a server name or a map of names to server configs          | item logged, dropped                            |
| `hooks`             | see Hooks                                                                  | see Hooks                                       |
| `maxTurns`          | positive integer, or a string that parses to one                           | logged, ignored                                 |
| `autoCompactWindow` | integer from 100000 to 1000000, or a string that parses to one             | `warn`, ignored                                 |
| `memory`            | `user`, `project`, `local`                                                 | logged, ignored                                 |
| `background`        | `true`, `false`, `"true"`, `"false"`; only true is applied                 | logged, ignored                                 |
| `omitClaudeMd`      | `true` or `"true"` turns it on; anything else is off                       | silently off                                    |
| `isolation`         | `worktree`, `remote`                                                       | logged, ignored                                 |
| `color`             | see Agent colors                                                           | silently ignored                                |
| `initialPrompt`     | non-blank string                                                           | silently ignored                                |
| `observer`          | non-blank agent type; trimmed                                              | silently ignored                                |
| `observerMessage`   | non-blank string                                                           | silently ignored                                |
| `observeSubagents`  | `false` or `"false"` stops subagents inheriting the observer; default true | silently ignored                                |
| `experimental`      | map; only `cacheTtl` is read, as `5m` or `1h`                              | other keys and values ignored                   |

A file that has a `name` but fails to load logs `Failed to parse agent from <path>: <reason>` (for
example `Missing required "description" field in frontmatter`) and emits `tengu_agent_parse_error`.
A file with no `name`, or an empty one, is dropped without a message. A non-string `name` counts as
present and is reported as missing.

Tool lists: a string is split on commas and spaces outside parentheses, so `Bash(git add:*)` stays
whole.  Non-string list items are dropped.  A list containing `*` means all tools.  A `tools` value
that is empty, or holds no strings, gives the agent no tools at all.

Field notes:

- `initialPrompt` is read only when the agent runs as the main session (`--agent` or the `agent`
  setting).
- `omitClaudeMd` drops the user, project and local CLAUDE.md files when the agent is spawned as a
  subagent; managed policy files still load.
- `effort` becomes the effort of every request the agent makes, for its whole run; see Effort at
  runtime.  The Agent tool's own `effort` input overrides it, and so does the `effort` of a
  `context: fork` skill that runs the agent.
- `observer`, `observerMessage` and `observeSubagents` are described under Observer agents.
- The `experimental` sub-key is matched without regard to case, `-` or `_`, so `cache_ttl` and
  `cache-ttl` also work.  `1h` is ignored while a Claude subscription is in overage.
- `memory` appends `Read`, `Edit` and `Write` to an explicit `tools` list and loads the agent's
  `MEMORY.md` into its system prompt; see `AGENT_MEMORY.md`.
- A `PreToolUse` or `PermissionRequest` key at the frontmatter top level, outside `hooks`, makes
  the agent fail to load (logged at `error`).

### Observer agents

The public docs do not describe these keys.  `observer` names an agent type that Claude Code spawns
as a background observer whenever the declaring agent runs, as the main session or as a subagent. It
needs all of:

- `CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS` set to a non-empty value;
- the gate `tengu_observer_agents_enabled` (default on);
- background agent launches allowed in the session.

The observer receives activity digests of the observed agent: tool calls and results, user and other
messages, turn ends, loaded guidance files and discovered skills, framed as read-only data and
capped at 64000 characters per delivery.  Each digest ends with a fixed postamble (grep
`The activity above is a read-only digest`) telling it that silence is the expected state;
`observerMessage` is appended after that postamble.  The observer's only way back is the
`ObserverReport` tool, a one-way advisory report to the observed agent, or to the coordinating agent
that spawned the observed worker.

When `observeSubagents` is not false, subagents the observed agent spawns inherit the same observer,
gated by `tengu_observer_subagent_fanout` (default on) and capped at a fan-out depth of 2. Observers
do not chain: an observer agent's own `observer` is ignored, and an observer is never fanned out to
itself.  A type that matches no available agent, or the built-in web-fetch agent, leaves the agent
unobserved with an `[agentObserver]` warning.

### Plugin agents

Plugin agent files use a separate parser.  `name` is optional (defaults to the filename), and
`description` falls back to `when_to_use`, then `when-to-use`, then `Agent from <plugin> plugin`.
`permissionMode`, `hooks`, `mcpServers`, `initialPrompt`, `observer`, `observerMessage` and
`observeSubagents` are each ignored with a `warn` naming the key.  `isolation` accepts only
`worktree`, and other values are dropped silently.  `background` accepts `true` or `"true"`; other
values are dropped without a message.  `effort`, `memory`, `maxTurns`, `autoCompactWindow` and
`experimental.cacheTtl` are read as for other agents.  A file over 1 MiB is skipped with a `warn`.

---

## Skill Files (`.claude/skills/<name>/SKILL.md`) and Command Files

All fields are optional.  Booleans marked "boolean-like" accept native booleans, numbers, and the
strings `true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off` in any case, with surrounding spaces
ignored.

| Field                      | Accepted values                                    | Runtime handling                                                        |
| -------------------------- | -------------------------------------------------- | ----------------------------------------------------------------------- |
| `name`                     | scalar, coerced with `String()`; at most 256 chars | display name; over 256 chars warns and is ignored; ignored for commands |
| `description`              | string (trimmed), number or boolean (stringified)  | other types warn; falls back to the body's first heading or sentence    |
| `when_to_use`              | scalar, coerced with `String()`                    | appended to the Skill tool listing                                      |
| `argument-hint`            | scalar, coerced with `String()`                    | inline hint shown while typing the command; see the list case below     |
| `arguments`                | string split on whitespace, or list of strings     | named slots; empty and all-digit names are dropped                      |
| `allowed-tools`            | string or list of strings                          | tools allowed while active; cleared when a hook guard fails to load     |
| `disallowed-tools`         | string or list of strings                          | tools removed while active; cleared on the next user message            |
| `disallowedTools`          | same as `disallowed-tools`                         | read only when `disallowed-tools` is absent                             |
| `model`                    | alias, full model ID, or `inherit`                 | aliases resolved at load; `inherit` kept; unknown strings pass through  |
| `effort`                   | see Effort                                         | applies for the rest of the turn, or the forked run; see Effort         |
| `shell`                    | `bash`, `powershell` (any case)                    | other values warn and fall back to bash                                 |
| `user-invocable`           | boolean-like; default true                         | unrecognised values read as false                                       |
| `disable-model-invocation` | boolean-like; default false                        | unrecognised values read as false                                       |
| `context`                  | `fork`, `inline`, null                             | only `fork` is acted on; anything else runs inline                      |
| `agent`                    | scalar, coerced with `String()`                    | agent type for `context: fork`                                          |
| `background`               | boolean-like                                       | with `context: fork`, `false` keeps the caller waiting; default true    |
| `paths`                    | string or list of strings                          | glob scoping; ignored for commands; see Paths                           |
| `hooks`                    | see Hooks                                          | see Hooks                                                               |
| `version`                  | scalar, coerced with `String()`                    | stored, not acted on                                                    |
| `metadata`                 | map                                                | preserved on the loaded skill; a non-map value is dropped               |
| `fallback`                 | boolean-like                                       | `@internal`: yields to a same-suffix plugin or MCP skill                |
| `created_by`               | string                                             | `@internal`: only `dream-proposal` is acted on                          |
| `improved_by`              | string                                             | `@internal`: only `dream-proposal` is acted on                          |

The strict shadow schema also accepts these keys, which the skill parser never reads: `license`,
`displayName`, `author`, `homepage`, `repository`, `keywords`, `userConfig`, `defaultEnabled`,
`mcpServers`, `lspServers`, `agents`, `outputStyles`, `themes`, `workflows`, `channels`, `monitors`,
`settings`, `experimental` and `dependencies`.  All are typed `unknown` and described `@internal`.

### `argument-hint` given as a YAML list

`argument-hint: [file]` parses as the list `["file"]`.  The skill parser coerces it with
`String()`, which joins list items with commas and drops the brackets, so the hint displays as
`file`.  `argument-hint: [a, b]` displays as `a,b`.  The shadow check also records a
`tengu_frontmatter_shadow_mismatch` for `argument-hint`.  `argument-hint: [file] [mode]` is not
valid YAML, so it only loads through the stage-2 sanitizer, which quotes it and keeps the text
`[file] [mode]`.  Quote the value to keep the brackets: `argument-hint: "[file]"`.

When `argument-hint` is absent and the skill declares `arguments`, the prompt input builds a hint
from the remaining argument names, each wrapped as `[name]`, once a space follows the command.

### `license` and `compatibility`

`license` is accepted by the strict skill schema as an `@internal` `unknown` slot.  `compatibility`
is not in the schema, so it records `tengu_frontmatter_shadow_unknown_key`.  Neither produces a
user-visible message, and the skill field parser reads neither, so both load and have no effect. The
importer that copies skills from other tools (`.cursor`, `.codex`, `.gemini`, `.agents`) rewrites
`SKILL.md` keeping only `description`, `paths`, `disable-model-invocation`, `user-invocable`,
`argument-hint`, `when_to_use`, `version`, `license` and `compatibility`.  It sets `name` to the
imported skill's name, renames `globs` to `paths` when `paths` is absent, and drops every other key.

### Hook guards in skills

A `PreToolUse` or `PermissionRequest` key at the frontmatter top level, outside `hooks`, or a
guard-event hook entry that cannot be loaded, makes the skill load with no hooks and no
`allowed-tools` (logged at `error`).

### Plugin skills and commands

Plugin `SKILL.md` and command files go through a separate parser with no shadow check.  It reads the
same keys as the skill parser except `paths`, `fallback`, `created_by` and `improved_by`, which it
ignores.  `name` replaces the last segment of the plugin-prefixed command name.  Only plugin skills
read `hooks`; in a plugin command, a `hooks` value that is not an event map is treated as an
unloadable guard.  An invalid `effort` logs `Plugin command <name> has invalid effort '<value>'`.

---

## Output-Style Files (`.claude/output-styles/*.md`)

The body is injected as output instructions.  All fields are optional.

| Field                      | Accepted values                 | Runtime handling                                       |
| -------------------------- | ------------------------------- | ------------------------------------------------------ |
| `name`                     | scalar, coerced with `String()` | defaults to the filename without `.md`                 |
| `description`              | string, number or boolean       | same coercion and fallback as skill `description`      |
| `keep-coding-instructions` | boolean-like                    | keeps the default coding instructions beside the style |
| `force-for-plugin`         | boolean-like                    | plugin styles only; in user styles it warns, ignored   |

---

## Memory and Rules Files

CLAUDE.md files, `.claude/rules/*.md` and `@include` targets are parsed without key
normalisation and without a shadow check.  Only `paths` is read; other keys are ignored.

### Paths

`paths` (here and in skills) is a string or a list of strings.  Each string is split on commas
outside braces, each piece has `{a,b}` brace expansion applied, a trailing `/**` is stripped, and
empty entries are dropped.  If nothing remains, or every entry is `**`, the file is not scoped.
Brace expansion is budgeted at 1000 results and 4 MiB; past that, the pattern is used unexpanded
with a `warn`.  Non-string list items are dropped silently.

```yaml
paths: src/**
paths: src/{components,utils}/**
paths: src/**,tests/**
paths:
  - src/**
  - tests/**
```

---

## Shared Value Sets

### Model aliases

`sonnet`, `opus`, `haiku`, `fable`, `best`, `sonnet[1m]`, `opus[1m]`, `fable[1m]`, `opusplan`,
plus `inherit` in frontmatter.  The alias check also accepts any alias with a `[1m]` suffix (for
example `haiku[1m]`).  Agents store the string unresolved; skills resolve it at load.

### Effort

All four effort readers (agent, plugin agent, skill or command, plugin skill or command) share one
value parser.  It accepts:

- a level: `low`, `medium`, `high`, `xhigh`, `max`, or `med` for `medium`, in any case.  The value
  is not trimmed, so a quoted `" high"` is rejected;
- an integer, either a YAML number (any integer, zero and negatives included) or a string that
  `parseInt` reads as one (`"8"`, and also `"8k"` and `"1.5"`, which read as 8 and 1).

`ultracode` is a `--effort` CLI value only; frontmatter rejects it.  An invalid value logs
`<file> has invalid effort '<value>'. Valid options: low, medium, high, xhigh, max or an integer`,
at debug level, and the field is ignored.

An integer is carried through as the effort, but a request only sends a string level as
`output_config.effort`.  With an integer, the request carries no effort field and the API applies
its own default.  When a `maxEffortLevel` cap is in force, from settings or the organization, an
integer becomes `high` before the cap applies.  Displays and `${CLAUDE_EFFORT}` show an integer as
`high`.  The public docs list only the five levels.

### Effort at runtime

Every request's effort comes from one resolver, which takes the first of these that is set:

1. an effort a hook substitutes into the request;
2. `CLAUDE_CODE_EFFORT_LEVEL`.  `auto` or `unset` select the model's default level and override
   everything below; with no cap in force, no effort is sent at all;
3. the turn effort: the last effort layer on the current context;
4. the session effort (`/effort`, `--effort`, `effortLevel` and per-model settings);
5. the model's default level.

The result is then clamped to any `maxEffortLevel` cap.  `max` becomes `high` on a model without max
effort, `xhigh` becomes `high` on a model without it, and a per-model effort hold the session has
recorded can lower a level further.  A model without effort support gets none.

A skill's `effort` reaches step 3 by four routes:

| Route                         | Applies                                                                  |
| ----------------------------- | ------------------------------------------------------------------------ |
| Typed `/name`, inline         | as an effort layer on that turn's context, for every request in the turn |
| Skill tool, inline            | as an effort layer on the context, for the rest of the turn              |
| `context: fork`, either entry | replaces the fork agent's `effort`, for every request of the forked run  |
| Agent `skills:` preload       | not applied: the preload renders only the body                           |

- The turn ends when the model stops and the next user message starts a fresh context, so the level
  reverts to the session effort.  The session effort itself is never changed.
- Typed input: the prompt processor returns the skill's `effort` beside `allowedTools` and `model`,
  in the interactive loop and in headless and SDK sessions alike.  When several queued inputs are
  processed together, the first one carrying an effort wins.  When one input expands stacked skills,
  the last skill that sets an effort wins.
- Skill tool: the tool result carries `{ kind: "effort" }` among its `contextLayers`, appended to
  the context of the loop that called it, main session or subagent.  The last layer wins, so a
  second skill invoked later in the same turn replaces the first one's effort.  The layer is not
  added when the coordinator-mode main session loads a skill.
- Subagents do not inherit the parent's layers.  A subagent spawned in a turn that a skill raised
  runs at the Agent tool's `effort` input, else its definition's `effort`, else the session effort,
  not at the skill's level.  `CLAUDE_CODE_SUBAGENT_EFFORT` supplies a default only when the
  definition has no `effort` and the spawning context has no turn effort, so a skill's turn effort
  also suppresses that default.  The chosen agent effort acts as a turn effort for the subagent's
  whole run, by the same layer mechanism.
- `${CLAUDE_EFFORT}` in a skill body expands to the level resolved with the skill's own `effort`
  (else the current turn effort), against the skill's `model` when it has one.

The public docs say the same for the turn and for `context: fork`, and that
`CLAUDE_CODE_EFFORT_LEVEL` wins.  They do not say that subagents spawned in the turn, and agent
`skills:` preloads, ignore it, that `CLAUDE_CODE_EFFORT_LEVEL=auto` cancels it, or that integers are
accepted.

### Permission modes

`acceptEdits`, `auto`, `bypassPermissions`, `default`, `dontAsk`, `plan`.  `manual` is accepted
and normalised to `default`.

### Agent colors

`red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan`.

---

## Hooks

Agent and skill `hooks` use the same schema as `settings.json` `hooks`, after a pre-pass:

- An unknown event name is removed with the note `hooks.<event>: unknown hook event; entry ignored`,
  unless it holds `PreToolUse` or `PermissionRequest` hooks, which makes it an unloadable guard.
- An event whose value is not a list is removed with a note ending `entry ignored`; for `PreToolUse`
  and `PermissionRequest` it is an unloadable guard instead.
- An invalid matcher group or hook entry is removed with a note ending `entry ignored`; the
  rest load.
- For `PreToolUse` and `PermissionRequest`, nothing is removed.  Any invalid entry makes the
  whole guard unloadable: the agent does not load, or the skill loads with no hooks and no
  `allowed-tools`.
- `hooks` given as a single matcher or a list of matchers, instead of an event map, is an
  unloadable guard.

Event names:

```
PreToolUse         PostToolUse        PostToolUseFailure   PostToolBatch
Notification       UserPromptSubmit   UserPromptExpansion  SessionStart
SessionEnd         Stop               StopFailure          SubagentStart
SubagentStop       PreCompact         PostCompact          PreModelSwitch
PostModelSwitch    PermissionRequest  PermissionDenied     Setup
TeammateIdle       TaskCreated        TaskCompleted        Elicitation
ElicitationResult  ConfigChange       WorktreeCreate       WorktreeRemove
InstructionsLoaded CwdChanged         FileChanged          DirectoryAdded
MessageDisplay
```

The matcher group has exactly two fields, `matcher` (optional string) and `hooks` (list).  The
group schema is a non-strict Zod object, so any other key, `if` included, is stripped without a
note.  An `if` placed on the group is therefore dropped, and its hooks run for every event the
`matcher` matches.  `if` is a field of each hook entry.

```yaml
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "shell command"
          args: ["--flag", "value"]  # exec form: no shell
          if: "Bash(git *)"          # permission-rule filter
          shell: bash                # bash | powershell
          timeout: 30                # seconds, > 0
          onFailure: continue        # continue | block
          statusMessage: "..."
          once: false
          async: false
          asyncRewake: false         # async, and wakes the model on exit 2
        - type: prompt
          prompt: "LLM prompt text, $ARGUMENTS for the hook input"
          if: "Bash(git *)"
          timeout: 30
          model: "claude-haiku-5-5"
          continueOnBlock: false
          statusMessage: "..."
          once: false
        - type: http
          url: "https://example.com/webhook"
          if: "Bash(git *)"
          timeout: 30
          onFailure: continue
          headers:
            Authorization: "Bearer $TOKEN"
          allowedEnvVars: ["TOKEN"]
          statusMessage: "..."
          once: false
        - type: agent
          prompt: "Verify that unit tests ran and passed."
          if: "Bash(git *)"
          timeout: 60
          model: "claude-sonnet-5-5"
          statusMessage: "..."
          once: false
        - type: mcp_tool
          server: "my-server"
          tool: "verify"
          input:
            file_path: "${tool_input.file_path}"
          if: "Bash(git *)"
          timeout: 30
          statusMessage: "..."
          once: false
```

`onFailure` (command and http) decides what a hook failure does: `continue` reports it and lets
the action proceed; `block` treats it as exit code 2.  It is ignored for async hooks and on
`Stop`, `SubagentStop`, `TaskCompleted` and `TeammateIdle`.  Command hooks also take the
`@internal` keys `rewakeMessage`, `rewakeSummary` and `cloud` (`device` or `skip`); http hooks
take `cloud`.  Hook entries are non-strict too, so unknown keys on an entry are stripped
silently.

---

## MCP Servers (agent `mcpServers`)

Each list item is a server name string or a map from one or more names to one of these configs. The
schemas are non-strict, so unknown keys are stripped.  `timeout` is a positive integer on every
type.

| `type`                    | Required         | Optional                                                                                                |
| ------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------- |
| `stdio` (or omitted)      | `command`        | `args`, `env`, `timeout`, `alwaysLoad`, `bareElicitationCapability`, `role`                             |
| `sse`                     | `url`            | `headers`, `headersHelper`, `oauth`, `timeout`, `request_timeout_ms`, `tools`, `alwaysLoad`,            |
|                           |                  | `bareElicitationCapability`, `discoveryCache`, `role`, `toolPermissions`                                |
| `http`, `streamable-http` | `url`            | same as `sse`; the type is normalised to `http`                                                         |
| `sse-ide`                 | `url`, `ideName` | `ideRunningInWindows`, `timeout`, `alwaysLoad`, `role`                                                  |
| `ws-ide`                  | `url`, `ideName` | `authToken`, `ideRunningInWindows`, `timeout`, `alwaysLoad`, `role`                                     |
| `ws`                      | `url`            | `headers`, `headersHelper`, `timeout`, `alwaysLoad`, `bareElicitationCapability`, `role`                |
| `sdk`                     | `name`           | `timeout`, `alwaysLoad`, `disableAutoBackground`, `tools`, `connectorId`                                |
| `claudeai-proxy`          | `url`, `id`      | `displayName`, `iconUrl`, `timeout`, `alwaysLoad`, `toolPermissions`, `stateless`, `enterpriseManaged`, |
|                           |                  | and connector cache fields                                                                              |

`role` accepts only `comms`; any other value is dropped silently.  `tools` is a list of
`{name, permission_policy}` with `always_allow`, `always_ask` or `always_deny`. `toolPermissions`
maps tool names to `allow`, `ask` or `blocked`.  `oauth` takes `clientId`, `callbackPort`,
`authServerMetadataUrl` (https only), `scopes` and `xaa`.  `request_timeout_ms` is `@internal`: when
`timeout` is absent it becomes the timeout, capped at 300000.  On `sdk`, invalid
`disableAutoBackground`, `tools` or `connectorId` values are dropped silently.

---

## Summary: Validation Behaviour by Severity

| Situation                                         | Claude Code behaviour                         | Linter should |
| ------------------------------------------------- | --------------------------------------------- | ------------- |
| Agent missing `name`                              | dropped silently                              | error         |
| Agent `name` not a string, with `:`, leading `-`, | logged, `tengu_agent_parse_error`, dropped    | error         |
| or over 256                                       |                                               |               |
| Agent missing `description`                       | logged, `tengu_agent_parse_error`, dropped    | error         |
| Agent unknown key                                 | `warn` with did-you-mean, ignored             | error         |
| Agent invalid `effort`/`permissionMode`/`memory`  | logged, field ignored                         | error         |
| Agent invalid `isolation`/`maxTurns`/`background` | logged, field ignored                         | error         |
| Agent invalid `autoCompactWindow`                 | `warn`, field ignored                         | error         |
| Agent invalid `mcpServers` item                   | logged, item dropped                          | error         |
| Agent invalid `color`                             | ignored silently                              | warning       |
| Agent `observer` naming no available agent        | `warn` when the agent runs, unobserved        | warning       |
| Agent or skill integer `effort`                   | accepted; no effort sent, or `high` under cap | warning       |
| Guard hook invalid, or guard event at top level   | agent not loaded; skill loses hooks, tools    | error         |
| Other invalid hook entry or unknown event         | `warn` note, entry dropped                    | error         |
| `if` on a hook matcher group                      | stripped silently; hooks run unfiltered       | error         |
| Skill/command unknown key                         | telemetry only                                | error         |
| Skill `argument-hint` given as a list             | joined with commas, brackets lost             | error         |
| Skill invalid `description` type                  | `warn`, falls back to body                    | warning       |
| Skill unrecognised boolean-like value             | read as false (or as unset)                   | warning       |
| Skill `context` other than `fork`                 | runs inline                                   | warning       |
| Skill invalid `effort`                            | logged, field ignored                         | error         |
| Skill invalid `shell`                             | `warn`, falls back to bash                    | error         |
| `name` or `paths` in a command file               | ignored silently                              | warning       |
| Output style `force-for-plugin` in a user style   | `warn`, ignored                               | warning       |
| YAML only parses through the sanitizer            | accepted silently                             | error         |
| YAML does not parse                               | `warn` (skills: `error`), no fields set       | error         |

---

## Field Name Conventions

| Style      | Examples                                                                                                               |
| ---------- | ---------------------------------------------------------------------------------------------------------------------- |
| kebab-case | `allowed-tools`, `disallowed-tools`, `argument-hint`, `user-invocable`, `disable-model-invocation`,                    |
|            | `keep-coding-instructions`, `force-for-plugin`                                                                         |
| snake_case | `when_to_use`, `created_by`, `improved_by`                                                                             |
| camelCase  | agents: `disallowedTools`, `mcpServers`, `maxTurns`, `permissionMode`, `initialPrompt`, `autoCompactWindow`,           |
|            | `omitClaudeMd`, `observerMessage`, `observeSubagents`, `cacheTtl`; skills: the `disallowedTools` alias only            |
| plain      | `name`, `description`, `model`, `agent`, `tools`, `hooks`, `paths`, `memory`, `skills`, `version`, `context`,          |
|            | `background`, `isolation`, `color`, `effort`, `shell`, `fallback`, `arguments`, `metadata`, `observer`, `experimental` |

Keys are matched exactly as written: `when-to-use` and `allowed_tools` are unknown keys in
skills.
