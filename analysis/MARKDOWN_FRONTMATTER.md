# Markdown Front-matter: Parsing, Schema, and Validation

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

This document is intended to serve as a specification for formatter and linter tooling targeting
Claude Code's Markdown configuration files.

---

## File Types

Claude Code reads four distinct types of Markdown files that carry YAML front-matter:

| Type            | Location pattern                          | Key field           |
| --------------- | ----------------------------------------- | ------------------- |
| Agent           | `.claude/agents/*.md` (recursive)         | `name` (required)   |
| Skill           | `.claude/skills/<name>/SKILL.md`          | directory name      |
| Output style    | `.claude/output-styles/*.md`              | filename            |
| CLAUDE.md/memory| `CLAUDE.md`, `memory/*.md`, etc.          | none required       |

Each type has a distinct set of valid frontmatter keys, types, and constraints.

---

## Parser

### Detection

Front-matter is detected by the regex at line 169170:

```
/^---\s*\n([\s\S]*?)---\s*\n?/
```

The opening `---` must be on the very first line of the file.  Trailing whitespace after either
delimiter is allowed.  The returned `content` is the file body with the delimiter block removed.
If no front-matter block is found, `frontmatter` is `{}` and `content` is the full file.

### Two-stage YAML parsing (`IJ`, line 169169)

Stage 1: parse the YAML block directly using the `yaml` npm package (Eemeli Aro).

Stage 2 (fallback): if stage 1 throws, run the block through the sanitizer `Ai5` then retry.
If stage 2 also throws, emit a `warn`-level log entry and return `frontmatter: {}`.

The sanitizer `Ai5` (line 169139) processes the block line by line.  For any line matching
`key: value` where the value is not already quoted and contains any character in
`/[{}[\]*&#!|>%@`]/`, it wraps the value in double-quotes after escaping `\` and `"`.  All
other lines pass through unchanged.

Linter implication: files that only parse because of the sanitizer should be flagged.  They
contain bare values with YAML special characters that would fail any standards-compliant YAML
parser.

### Runtime dispatch (`J28`, line 169132)

On Bun: uses `Bun.YAML.parse()`.
On Node: uses `yaml.parse()` from the bundled `yaml` package.

Both implement YAML 1.2.  No practical difference for front-matter content.

---

## Agent Files (`.claude/agents/*.md`)

Agent files have two required fields.  All others are optional.  The file body (after
front-matter) is the agent's system prompt; there is no `prompt` key in the front-matter.

The `name` field becomes the agent's identifier (`agentType`); the filename (without `.md`) is
stored separately as `filename` but not used as the identifier.

Validation function: `j7Y` (line 292449).

### Required fields

#### `name`

| Property | Value                           |
| -------- | ------------------------------- |
| Type     | string                          |
| Required | yes                             |
| On missing | agent silently dropped (null) |

Non-empty string.  This is the agent's identifier, used as the `agentType` in the Task tool
description and in `--agent` references.

#### `description`

| Property   | Value                                    |
| ---------- | ---------------------------------------- |
| Type       | string                                   |
| Required   | yes                                      |
| On missing | error logged, agent dropped              |

Non-empty string.  Becomes the agent's `whenToUse` text shown in the Task tool description.
Literal `\n` escape sequences in the value are expanded to real newlines before use.

### Optional fields

#### `model`

| Property      | Value                                                                       |
| ------------- | --------------------------------------------------------------------------- |
| Type          | string                                                                      |
| Valid values  | `sonnet`, `opus`, `haiku`, `best`, `sonnet[1m]`, `opus[1m]`, `opusplan`, `inherit` |
| On invalid    | warn logged, field silently ignored (agent loads without model override)    |

`inherit` causes the agent to use the same model as the calling session.
`best` resolves to the most capable available model.
The `[1m]` suffix requests a 1M-token context window variant.
`opusplan` selects an Opus model in plan mode.

#### `effort`

| Property     | Value                                            |
| ------------ | ------------------------------------------------ |
| Type         | string or integer                                |
| Valid values | `low`, `medium`, `high`, `max`, or any integer   |
| On invalid   | warn logged, field ignored                       |

Controls the thinking budget.  Named values map to preset budgets.  An integer is used directly
as the budget token count.

#### `permissionMode`

| Property     | Value                                                               |
| ------------ | ------------------------------------------------------------------- |
| Type         | string                                                              |
| Valid values | `acceptEdits`, `bypassPermissions`, `default`, `dontAsk`, `plan`   |
| On invalid   | warn logged, field ignored                                          |

#### `forkContext`

| Property     | Value                                                        |
| ------------ | ------------------------------------------------------------ |
| Type         | boolean or string                                            |
| Valid values | `true`, `false`, `"true"`, `"false"`                         |
| On invalid   | warn logged, treated as falsy                                |

When `true`, the agent receives the current session's conversation context.  If `true` and
`model` is not `inherit`, Claude Code overrides `model` to `inherit` with a warning.

#### `background`

| Property     | Value                                              |
| ------------ | -------------------------------------------------- |
| Type         | boolean or string                                  |
| Valid values | `true`, `false`, `"true"`, `"false"`               |
| On invalid   | warn logged                                        |

When `true`, the agent runs as a background task.

#### `memory`

| Property     | Value                                   |
| ------------ | --------------------------------------- |
| Type         | string                                  |
| Valid values | `user`, `project`, `local`              |
| On invalid   | warn logged, field ignored              |

Determines which memory store the agent has access to.  Only active when memory features are
enabled.

#### `isolation`

| Property     | Value          |
| ------------ | -------------- |
| Type         | string         |
| Valid values | `worktree`     |
| On invalid   | warn logged, field ignored |

When `worktree`, the agent runs in an isolated git worktree.

#### `maxTurns`

| Property     | Value                               |
| ------------ | ----------------------------------- |
| Type         | integer                             |
| Valid values | any positive integer (≥ 1)          |
| On invalid   | warn logged, field ignored          |

Limits the number of API round-trips the agent can make.

#### `color`

| Property     | Value                                                        |
| ------------ | ------------------------------------------------------------ |
| Type         | string                                                       |
| Valid values | `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan` |
| On invalid   | silently ignored, no warning                                 |

Used for visual identification in the UI.  No functional effect.

#### `tools`

| Property     | Value                                                         |
| ------------ | ------------------------------------------------------------- |
| Type         | string or array of strings                                    |
| Valid values | tool name strings, or the single value `*` meaning "all"      |
| On invalid   | non-string items silently filtered out                        |

Restricts the tools this agent can use.  `*` grants access to all tools.  If `memory` is also
set, memory-related tools are automatically appended.

#### `disallowedTools`

| Property     | Value                              |
| ------------ | ---------------------------------- |
| Type         | string or array of strings         |
| Valid values | tool name strings                  |
| On invalid   | non-string items silently filtered |

Explicitly denies named tools.  Complementary to `tools`; both can coexist.

#### `skills`

| Property     | Value                                                                        |
| ------------ | ---------------------------------------------------------------------------- |
| Type         | array of strings                                                             |
| Valid values | skill name strings (must match a loaded skill's `skillName`)                 |
| On invalid   | unknown names produce a `warn` log at activation time, not at load time      |

#### `mcpServers`

| Property | Value                                                                        |
| -------- | ---------------------------------------------------------------------------- |
| Type     | array                                                                        |

Each item is either:
- A string (reference to a named MCP server defined elsewhere), or
- An object with one of the following `type` discriminants:

  | type          | Required fields         | Optional fields                                |
  | ------------- | ----------------------- | ---------------------------------------------- |
  | `stdio`       | `command` (string)      | `args` (string[]), `env` (Record<str,str>)     |
  | `sse`         | `url` (string)          | `headers`, `headersHelper`, `oauth`            |
  | `sse-ide`     | `url`, `ideName`        | `ideRunningInWindows` (bool)                   |
  | `ws-ide`      | `url`, `ideName`        | `authToken`, `ideRunningInWindows`             |
  | `http`        | `url` (string)          | `headers`, `headersHelper`, `oauth`            |
  | `ws`          | `url` (string)          | `headers`, `headersHelper`                     |
  | `sdk`         | `name` (string)         |                                                |
  | `claudeai-proxy` | `url`, `id`          |                                                |

  Invalid items produce a warn log and are dropped; remaining items are kept.

#### `hooks`

| Property | Value                                                                |
| -------- | -------------------------------------------------------------------- |
| Type     | object                                                               |

Validated with the same Zod schema (`Yy`) as `settings.json`.  Invalid hooks produce a warn log
and the entire `hooks` field is ignored.

Structure:

```yaml
hooks:
  <EventName>:          # one of the valid event names below
    - matcher: "Write"  # optional string pattern (e.g. tool name)
      hooks:
        - type: command
          command: "shell command"
          timeout: 30           # optional, positive number (seconds)
          statusMessage: "..."  # optional string
          once: false           # optional bool; if true, runs once then removed
          async: false          # optional bool; if true, runs non-blocking

        - type: prompt
          prompt: "LLM prompt text"
          timeout: 30
          model: "claude-haiku-4-5"  # optional, any model string
          statusMessage: "..."
          once: false

        - type: http
          url: "https://example.com/webhook"
          timeout: 30
          headers:                   # optional Record<string, string>
            Authorization: "Bearer $TOKEN"
          allowedEnvVars: ["TOKEN"]  # required for env var interpolation in headers
          statusMessage: "..."
          once: false

        - type: agent
          prompt: "Verify that unit tests ran and passed."
          timeout: 60
          model: "claude-sonnet-4-6"  # optional
          statusMessage: "..."
          once: false
```

Valid event names:

```
PreToolUse         PostToolUse       PostToolUseFailure   Notification
UserPromptSubmit   SessionStart      SessionEnd           Stop
SubagentStart      SubagentStop      PreCompact           PermissionRequest
Setup              TeammateIdle      TaskCompleted        ConfigChange
WorktreeCreate     WorktreeRemove
```

---

## Skill Files (`.claude/skills/<name>/SKILL.md`)

The skill's identifier (`skillName`) is taken from the containing directory name, not from
any front-matter field.  All front-matter fields are optional.  There is almost no validation;
most bad values are silently coerced or ignored, with the sole exception of `hooks`.

Skill loading function: `TF6` (line 273021).

#### `name`

| Property  | Value             |
| --------- | ----------------- |
| Type      | any               |
| Coercion  | `String(value)`   |

Display name override.  If absent, the directory name is used.

#### `description`

| Property  | Value                                                                     |
| --------- | ------------------------------------------------------------------------- |
| Type      | string, number, or boolean                                                |
| Coercion  | strings are trimmed; numbers and booleans are stringified                 |
| On other  | warn logged, falls back to first heading or first sentence of body text   |

#### `allowed-tools`

| Property  | Value                                               |
| --------- | --------------------------------------------------- |
| Type      | string or array of strings                          |
| Coercion  | string → single-element array; `*` → `["*"]` (all tools) |

Tool allow-list for this skill.  Same semantics as agent `tools`.  Note the hyphenated key name.

#### `argument-hint`

| Property  | Value           |
| --------- | --------------- |
| Type      | any             |
| Coercion  | `String(value)` |

Short hint string shown when the skill is invoked, describing the expected argument format.

#### `user-invocable`

| Property  | Value                                             |
| --------- | ------------------------------------------------- |
| Type      | boolean or string                                 |
| Coercion  | `true` only for native `true` or string `"true"`; everything else → `false` |
| Default   | `true`                                            |

When `false`, the skill cannot be invoked directly by the user with `/skill-name`.  It can
still be referenced by agents via their `skills` field.

#### `disable-model-invocation`

| Property  | Value                                     |
| --------- | ----------------------------------------- |
| Type      | boolean or string                         |
| Coercion  | same as `user-invocable`                  |
| Default   | `false`                                   |

When `true`, prevents Claude from invoking the skill autonomously (model-side invocation).

#### `model`

| Property  | Value                                                                        |
| --------- | ---------------------------------------------------------------------------- |
| Type      | string                                                                       |
| Coercion  | alias resolution only (`sonnet` → full model ID, etc.)                       |
| Note      | `inherit` is stripped to `undefined` before being stored                     |

No validation — unrecognized strings are passed through to the model resolver.  A linter should
apply the same enum check as for agents.

Valid aliases: same as agent `model` field (see above), plus any full model ID string.

#### `context`

| Property      | Value                               |
| ------------- | ----------------------------------- |
| Type          | string                              |
| Valid values  | `fork`                              |
| Other values  | silently treated as absent          |

When `fork`, the skill is executed in a forked context that inherits the current conversation.

#### `agent`

| Property | Value             |
| -------- | ----------------- |
| Type     | string            |

Agent type override for this skill's execution.  Passed through as-is; not validated against
known agent types at load time.

#### `arguments`

| Property  | Value                                                             |
| --------- | ----------------------------------------------------------------- |
| Type      | string or array of strings                                        |
| Coercion  | string → split on whitespace; array → non-empty, non-numeric strings only |

Named argument slots.  Combined with `argument-hint` to describe the skill's invocation
interface.

#### `when_to_use`

| Property | Value  |
| -------- | ------ |
| Type     | string |

Note the underscore (not a hyphen).  Shown in the Task tool's agent list description when this
skill is used as a sub-agent.  Passed through as-is; not validated.

#### `version`

| Property | Value  |
| -------- | ------ |
| Type     | any    |

Version string for the skill.  Passed through as-is; not validated.

#### `paths`

| Property  | Value                                                                   |
| --------- | ----------------------------------------------------------------------- |
| Type      | string                                                                  |
| Format    | comma-separated glob patterns; brace expansion (`{a,b}`) supported     |

Scopes when this skill is active.  The skill is only available when the current working
directory matches at least one path.  A trailing `/**` is stripped.  A value of `**` alone
is ignored (treated as no scoping).  Non-string values are silently ignored.

Examples:
```yaml
paths: src/**
paths: src/{components,utils}/**
paths: src/**,tests/**
```

#### `hooks`

Same schema as agent `hooks` (see above).  Invalid hooks produce a warn log; the field is
then ignored.

---

## Output-Style Files (`.claude/output-styles/*.md`)

The file body is injected as output formatting instructions.  All fields are optional.

Loading function: `dMq` (line 515851).

#### `name`

| Property  | Value                    |
| --------- | ------------------------ |
| Type      | any                      |
| Default   | filename without `.md`   |

Display name for the style.

#### `description`

| Property  | Value                    |
| --------- | ------------------------ |
| Type      | string, number, boolean  |
| Coercion  | same as skill `description` |

#### `keep-coding-instructions`

| Property     | Value                                                       |
| ------------ | ----------------------------------------------------------- |
| Type         | boolean or string                                           |
| Valid values | `true`, `false`, `"true"`, `"false"`                        |
| Default      | `undefined` (unchanged behavior)                           |

When `true`, retains Claude Code's default coding behaviour instructions alongside this style.

#### `force-for-plugin`

| Property  | Value                                                                           |
| --------- | ------------------------------------------------------------------------------- |
| Type      | any                                                                             |

Reserved for plugin-defined output styles.  If present in a user or project style file, a
warn is logged and the field is ignored.

---

## CLAUDE.md and Memory Files

Only one frontmatter field is read:

#### `paths`

| Property  | Value                                                              |
| --------- | ------------------------------------------------------------------ |
| Type      | string                                                             |
| Format    | comma-separated glob patterns; brace expansion supported           |

Scopes the instructions in this file to specific file paths.  When present, the instructions
are only injected into contexts where the active file matches at least one glob.  A trailing
`/**` is stripped.  Non-string or absent → no scoping (instructions always applied).

---

## Summary: Validation Behaviour by Severity

The following table summarises what Claude Code does on semantic errors.  A well-written
linter should treat all of these as errors, since Claude Code's silent coercions hide
configuration mistakes.

| Situation                                  | Claude Code behaviour     | Linter should |
| ------------------------------------------ | ------------------------- | ------------- |
| Agent missing `name`                       | silently dropped          | error         |
| Agent missing `description`                | error logged, dropped     | error         |
| Agent invalid `model`                      | warn, field ignored       | error         |
| Agent invalid `effort`                     | warn, field ignored       | error         |
| Agent invalid `permissionMode`             | warn, field ignored       | error         |
| Agent invalid `forkContext` value          | warn, treated as falsy    | error         |
| Agent invalid `background` value           | warn                      | error         |
| Agent invalid `memory`                     | warn, field ignored       | error         |
| Agent invalid `isolation`                  | warn, field ignored       | error         |
| Agent invalid `maxTurns`                   | warn, field ignored       | error         |
| Agent `forkContext: true` + non-inherit model | warn + silent override | error         |
| Agent invalid `mcpServers` item            | warn, item dropped        | error         |
| Agent invalid `color`                      | silently ignored          | warning       |
| Agent/skill invalid `hooks`                | warn, hooks ignored       | error         |
| Agent `skills` references unknown skill    | warn at activation time   | warning       |
| Skill invalid `description` type           | warn, falls back          | warning       |
| Skill `user-invocable`/`disable-model-invocation` not bool/string | silently false | warning |
| Skill `context` unrecognized value         | silently absent           | warning       |
| Skill invalid `model` alias                | passed through            | error         |
| Skill non-string `paths`                   | silently ignored          | warning       |
| Output style `force-for-plugin` present    | warn, ignored             | warning       |
| YAML requires sanitizer to parse           | silently accepted         | error         |

---

## Field Name Conventions

Claude Code uses a mix of naming styles across file types:

| Style     | Examples                                              |
| --------- | ----------------------------------------------------- |
| kebab-case | `allowed-tools`, `argument-hint`, `user-invocable`, `disable-model-invocation`, `when-to-use` (output style), `keep-coding-instructions` |
| snake_case | `when_to_use` (skill only)                           |
| camelCase  | none in frontmatter                                  |
| plain      | `name`, `description`, `model`, `agent`, `tools`, `hooks`, `paths`, `memory`, `skills`, `version`, `context`, `background`, `isolation`, `color` |

Note: the skill field is `when_to_use` (underscore), not `when-to-use` (hyphen).
