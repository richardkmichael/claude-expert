# Markdown Front-matter: Parsing, Schema, and Validation

Verified against: cli.prettier.js 2.1.296 (2026-10-13)

This document is a specification for formatter and linter tooling that targets Claude Code's
Markdown configuration files.  A machine-readable JSON Schema derived from it lives at
[`schemas/frontmatter.schema.json`](./schemas/frontmatter.schema.json); see
[`schemas/README.md`](./schemas/README.md) for editor and CI wiring.  This document follows the
landmark style in `GUIDELINES.md`.

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
| Agent unknown-key warning | `does not recognize or apply`                          | diff of frontmatter keys against the agent shadow schema, with did-you-mean      |
| Plugin agent field parser | `which is ignored for plugin agents`                   | ignores `permissionMode`, `hooks`, `mcpServers`, `initialPrompt`, `observer*`    |
| Output style parser       | `has force-for-plugin set, but this option`            | shadow check with `"output-style"`, then `name`/`description`/`keep-coding-...`  |
| Memory and rules `paths`  | `Skipping non-text file in @include`                   | the function above it reads `frontmatter.paths` and strips a trailing `/**`      |
| Hook schemas              | `Permission rule syntax to filter when this hook runs` | five hook object schemas, then the discriminated union and the matcher group     |
| Hook event names          | `"PostToolBatch",` near `"DirectoryAdded",`            | the array that feeds the `hooks` record key enum                                 |
| Frontmatter hook pre-pass | `unknown hook event; entry ignored`                    | per-event and per-entry stripping with notes; guard events refuse to load        |
| Model aliases             | `"opusplan",` beside `"fable[1m]",`                    | alias array, followed by the family array `["sonnet", "opus", "haiku", "fable"]` |
| Effort presets            | `["low", "medium", "high", "xhigh", "max"]`            | the preset list, with `{ med: "medium" }` as an alias map in the effort parser   |
| Permission modes          | `"dontAsk",` and `=== "manual" ? "default"`            | six-mode array, `manual` normalised to `default`                                 |
| Agent colors              | `red_FOR_SUBAGENTS_ONLY`                               | eight-key map; its `Object.keys` is the accepted set                             |
| MCP server schemas        | `Command cannot be empty`, `"claudeai-proxy"`          | stdio, sse, sse-ide, ws-ide, http, ws, sdk, claudeai-proxy object schemas        |

---

## File Types

| Type          | Location pattern                                    | Identifier                | Shadow check   |
| ------------- | --------------------------------------------------- | ------------------------- | -------------- |
| Agent         | `.claude/agents/**/*.md`                            | `name` (required)         | `agent`        |
| Plugin agent  | `<plugin>/agents/**/*.md`                           | `name`, else the filename | none           |
| Skill         | `.claude/skills/<name>/SKILL.md`                    | directory name            | `skill`        |
| Command       | `.claude/commands/**/*.md`                          | path, `:`-joined          | `skill`        |
| Output style  | `.claude/output-styles/*.md`                        | `name`, else the filename | `output-style` |
| Memory, rules | `CLAUDE.md`, `.claude/rules/*.md`, `@include` files | none                      | none           |

Command files use the skill validator and the skill field parser.  The command loader then
overrides two results: it discards `name` (the display name stays the path-derived command name)
and it discards `paths` (a command is never path-scoped).

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
(`&name`), or opens more than 256 collections (`[`, `{`, or block `-`/`?` indicators).  The
refusal text is `the frontmatter is too long, too nested, or may hold a YAML anchor`.

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
(`<key>:<zod issue code>`), each once per process per type and key.

The shadow schemas check keys, not values.  Nearly every field is typed as the loose scalar
union `string | number | boolean | null`, list-capable fields as that union or a string list, and
`hooks`, `mcpServers` and the `@internal` skill slots as `unknown`.  The only value sets the
shadow layer enforces are skill `context` (`inline`, `fork`, `null`) and the object shape of
agent `experimental`.  Value validation lives in the runtime field parsers documented below.

Agent files get a second, user-visible check: any key outside the agent shadow schema logs `Agent
file <path> has a frontmatter key Claude Code does not recognize or apply: <keys>` at `warn`, with
a did-you-mean hint (`allowedTools` → `tools`, `whenToUse` → `description`, otherwise the
nearest known key).  Plugin agent files get the same warning, and also accept `when_to_use` and
`when-to-use`.  Skills, commands and output styles have no user-visible unknown-key warning.

---

## Agent Files (`.claude/agents/*.md`)

The file body is the system prompt.  `name` and `description` are required.

| Field               | Accepted values                                                            | On invalid                                     |
| ------------------- | -------------------------------------------------------------------------- | ---------------------------------------------- |
| `name`              | string; at most 256 chars; no leading `-`; no `:` after NFKC normalisation | missing: dropped silently; else error, dropped |
| `description`       | string; literal `\n` is expanded to a newline                              | logged, agent dropped                          |
| `model`             | alias (see Model aliases), full model ID, or `inherit` (any case)          | passed through unresolved                      |
| `effort`            | see Effort                                                                 | logged, ignored                                |
| `permissionMode`    | see Permission modes                                                       | logged, ignored                                |
| `tools`             | string or list of strings; `*` means all tools                             | non-strings dropped                            |
| `disallowedTools`   | string or list of strings                                                  | non-strings dropped                            |
| `skills`            | string or list of skill names                                              | unknown names warn at activation               |
| `mcpServers`        | list; each item a server name or a one-key map of name to server config    | item logged, dropped                           |
| `hooks`             | see Hooks                                                                  | see Hooks                                      |
| `maxTurns`          | positive integer, or a string that parses to one                           | logged, ignored                                |
| `autoCompactWindow` | integer from 100000 to 1000000, or a string that parses to one             | `warn`, ignored                                |
| `memory`            | `user`, `project`, `local`                                                 | logged, ignored                                |
| `background`        | `true`, `false`, `"true"`, `"false"`; only true is applied                 | logged, ignored                                |
| `omitClaudeMd`      | `true` or `"true"` turns it on; anything else is off                       | silently off                                   |
| `isolation`         | `worktree`, `remote`                                                       | logged, ignored                                |
| `color`             | see Agent colors                                                           | silently ignored                               |
| `initialPrompt`     | non-blank string                                                           | silently ignored                               |
| `observer`          | non-blank agent type; trimmed                                              | silently ignored                               |
| `observerMessage`   | non-blank string                                                           | silently ignored                               |
| `observeSubagents`  | `false` or `"false"` stops subagents inheriting the observer; default true | silently ignored                               |
| `experimental`      | map; only `cacheTtl` is read, as `5m` or `1h`                              | other keys and values ignored                  |

Field notes:

- `initialPrompt` is read only when the agent runs as the main session (`--agent` or the `agent`
  setting).
- `omitClaudeMd` drops the user, project and local CLAUDE.md files when the agent is spawned as a
  subagent; managed policy files still load.
- `observer` names an agent type that is spawned as a background observer whenever this agent
  runs.  `observerMessage` is appended to each activity digest sent to it.
- The `experimental` sub-key is matched without regard to case, `-` or `_`, so `cache_ttl` and
  `cache-ttl` also work.  `1h` is ignored while a Claude subscription is in overage.
- `memory` appends `Read`, `Edit` and `Write` to an explicit `tools` list and loads the agent's
  `MEMORY.md` into its system prompt; see `AGENT_MEMORY.md`.
- A `PreToolUse` or `PermissionRequest` key at the frontmatter top level, outside `hooks`, makes
  the agent fail to load (logged at `error`).

### Plugin agents

Plugin agent files use a separate parser.  `name` is optional (defaults to the filename), and
`description` falls back to `when_to_use`, then `when-to-use`, then `Agent from <plugin> plugin`.
`permissionMode`, `hooks`, `mcpServers`, `initialPrompt`, `observer`, `observerMessage` and
`observeSubagents` are each ignored with a `warn` naming the key.  `isolation` accepts only
`worktree`, and other values are dropped silently.

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
| `effort`                   | see Effort                                         | logged, ignored                                                         |
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

The strict shadow schema also accepts these keys, which the skill parser never reads:
`license`, `displayName`, `author`, `homepage`, `repository`, `keywords`, `userConfig`,
`defaultEnabled`, `mcpServers`, `lspServers`, `agents`, `outputStyles`, `themes`, `workflows`,
`channels`, `monitors`, `settings`, `experimental` and `dependencies`.  All are typed `unknown`
and described `@internal`, apart from `metadata`, which is now documented.

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
user-visible message, and the skill field parser reads neither, so both load and have no
effect.  The importer that copies skills from other tools (`.cursor`, `.codex`, `.gemini`,
`.agents`) keeps both keys when it rewrites `SKILL.md`; it drops `icon`, `color` and any key not
on its short list.

### Hook guards in skills

A `PreToolUse` or `PermissionRequest` key at the frontmatter top level, outside `hooks`, or a
guard-event hook entry that cannot be loaded, makes the skill load with no hooks and no
`allowed-tools` (logged at `error`).

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

`low`, `medium`, `high`, `xhigh`, `max`, matched without regard to case, plus `med` as an alias for
`medium`.  An integer is also accepted, as a number or as a string that `parseInt` reads as one.
`ultracode` is a `--effort` CLI value only; frontmatter rejects it.

### Permission modes

`acceptEdits`, `auto`, `bypassPermissions`, `default`, `dontAsk`, `plan`.  `manual` is accepted
and normalised to `default`.

### Agent colors

`red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan`.

---

## Hooks

Agent and skill `hooks` use the same schema as `settings.json` `hooks`, after a pre-pass:

- An unknown event name is removed with the note `hooks.<event>: unknown hook event; entry
  ignored`.
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

Each list item is a server name string or a map from name to one of these configs.  The schemas
are non-strict, so unknown keys are stripped.  `timeout` is a positive integer on every type.

| `type`                    | Required         | Optional                                                                                                |
| ------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------- |
| `stdio` (or omitted)      | `command`        | `args`, `env`, `timeout`, `alwaysLoad`, `bareElicitationCapability`, `role`                             |
| `sse`                     | `url`            | `headers`, `headersHelper`, `oauth`, `timeout`, `tools`, `alwaysLoad`, `bareElicitationCapability`,     |
|                           |                  | `discoveryCache`, `role`, `toolPermissions`                                                             |
| `http`, `streamable-http` | `url`            | same as `sse`; the type is normalised to `http`                                                         |
| `sse-ide`                 | `url`, `ideName` | `ideRunningInWindows`, `timeout`, `alwaysLoad`, `role`                                                  |
| `ws-ide`                  | `url`, `ideName` | `authToken`, `ideRunningInWindows`, `timeout`, `alwaysLoad`, `role`                                     |
| `ws`                      | `url`            | `headers`, `headersHelper`, `timeout`, `alwaysLoad`, `bareElicitationCapability`, `role`                |
| `sdk`                     | `name`           | `timeout`, `alwaysLoad`, `disableAutoBackground`                                                        |
| `claudeai-proxy`          | `url`, `id`      | `displayName`, `iconUrl`, `timeout`, `alwaysLoad`, `toolPermissions`, `stateless`, `enterpriseManaged`, |
|                           |                  | and connector cache fields                                                                              |

`role` accepts only `comms`; any other value is dropped silently.  `tools` is a list of
`{name, permission_policy}` with `always_allow`, `always_ask` or `always_deny`.
`toolPermissions` maps tool names to `allow`, `ask` or `blocked`.  `oauth` takes `clientId`,
`callbackPort`, `authServerMetadataUrl` (https only), `scopes` and `xaa`.

---

## Summary: Validation Behaviour by Severity

| Situation                                         | Claude Code behaviour                      | Linter should |
| ------------------------------------------------- | ------------------------------------------ | ------------- |
| Agent missing `name`                              | dropped silently                           | error         |
| Agent `name` with `:`, leading `-`, or over 256   | error logged, dropped                      | error         |
| Agent missing `description`                       | logged, dropped                            | error         |
| Agent unknown key                                 | `warn` with did-you-mean, ignored          | error         |
| Agent invalid `effort`/`permissionMode`/`memory`  | logged, field ignored                      | error         |
| Agent invalid `isolation`/`maxTurns`/`background` | logged, field ignored                      | error         |
| Agent invalid `autoCompactWindow`                 | `warn`, field ignored                      | error         |
| Agent invalid `mcpServers` item                   | logged, item dropped                       | error         |
| Agent invalid `color`                             | ignored silently                           | warning       |
| Guard hook invalid, or guard event at top level   | agent not loaded; skill loses hooks, tools | error         |
| Other invalid hook entry or unknown event         | `warn` note, entry dropped                 | error         |
| `if` on a hook matcher group                      | stripped silently; hooks run unfiltered    | error         |
| Skill/command unknown key                         | telemetry only                             | error         |
| Skill `argument-hint` given as a list             | joined with commas, brackets lost          | error         |
| Skill invalid `description` type                  | `warn`, falls back to body                 | warning       |
| Skill unrecognised boolean-like value             | read as false (or as unset)                | warning       |
| Skill `context` other than `fork`                 | runs inline                                | warning       |
| Skill invalid `effort`                            | logged, field ignored                      | error         |
| Skill invalid `shell`                             | `warn`, falls back to bash                 | error         |
| `name` or `paths` in a command file               | ignored silently                           | warning       |
| Output style `force-for-plugin` in a user style   | `warn`, ignored                            | warning       |
| YAML only parses through the sanitizer            | accepted silently                          | error         |
| YAML does not parse                               | `warn` (skills: `error`), no fields set    | error         |

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

---

## Changes since 2.1.143

- Agent keys added: `autoCompactWindow`, `omitClaudeMd`, `observer`, `observerMessage`,
  `observeSubagents`, `experimental` (with `cacheTtl`).  Agent unknown keys now warn.
- Skill keys added: `disallowed-tools`, `disallowedTools`, `background`.  Shadow-only keys added:
  `userConfig`, `defaultEnabled`, `displayName`, `author`, `homepage`, `repository`, `license`,
  `keywords`.  `metadata` is documented and preserved on the loaded skill.
- Output style and memory keys: no change.
- Model aliases added: `fable`, `fable[1m]`.  Permission mode alias added: `manual`.
  Isolation value added: `remote` (not for plugin agents).  Effort alias added: `med`.
- Hook events added: `PreModelSwitch`, `PostModelSwitch`, `DirectoryAdded`, `MessageDisplay`.
  Hook fields added: `onFailure` (command, http), `cloud` (`@internal`, command, http).
- Frontmatter hooks are now repaired per entry instead of dropped whole, except for guard
  events, which now block the agent or strip the skill's hooks and tools.
- The sanitizer leaves YAML flow lists alone, requires a non-space first value character, and
  the retry expands leading tabs.  Parse failures are returned as `parseError`; untrusted
  sources are size-, anchor- and nesting-limited.
