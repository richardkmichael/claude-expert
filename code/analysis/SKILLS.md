---
verified: 2.1.317
verified_on: 2026-11-03
section: Tools, skills, and execution
style: landmark
scope: >-
  Skills: sources, filters and visibility, invocation (inline, fork, preload), `allowed-tools`
  paths, read-only loads, bundled catalog
landmarks:
  - bundledSkillsInitialized
  - 'allow_bundled_skills: {'
  - 'survivesBundledKillSwitch: !0'
  - No agent available for forked execution
---
# Skills

The parent document for skills: where they come from, how they are registered and filtered, who can
invoke them, how they run, and where a skill's `allowed-tools` grant applies. It then catalogs the
skills that ship inside Claude Code. It records what the source shows beyond the public docs
(https://code.claude.com/docs/en/skills), and notes where the two disagree.

Related docs, linked rather than repeated:

- `MARKDOWN_FRONTMATTER.md`: every `SKILL.md` and command frontmatter key and how it parses.
- `SUBAGENTS.md`: the Agent tool, agent definitions, and the `skills:` field's host.
- `CLAUDE_CODE_GUIDE.md`: the bundled `claude-code-docs` skill in full.
- `SKILLIFY.md`: skill proposals (`propose_skills`) and the dead Skillify prompt.
- `MODS.md`: the built-in plugin registry, its entrypoint gating and each plugin's default.

Minified names collide across bun modules. Every recipe below anchors on a string; read the
enclosing module's `import` list to resolve any helper it calls.

## How skills work

### Sources

One loader gathers every skill. Its debug line, found by `rg -n 'getSkills returning'`, counts four
of the sources: skill dir commands, plugin skills, bundled skills and builtin plugin skills. The
caller then merges those with attached-folder skills, workflows, plugin commands and the built-in
command table into a single loaded command list, cached in `loadedCommands`. Account-synced skills
join last, after a name-collision check.

The marker is the command's `loadedFrom` value unless the row says otherwise.

| Source                 | Marker                              | Comes from                      |
| ---------------------- | ----------------------------------- | ------------------------------- |
| Skill directories      | `skills`, `commands_DEPRECATED`     | `.claude/skills/`, `commands/`  |
| Account-synced skills  | `syncedSkills`                      | claude.ai skills synced to disk |
| Attached folders       | `attachedFolder`                    | folders a host attaches         |
| Plugin skills          | `plugin`, with `source: "plugin"`   | installed plugins               |
| MCP skills             | `mcp`                               | MCP servers                     |
| Memory-store skills    | `memoryStore`                       | a mounted memory store          |
| Bundled skills         | `bundled`, with `source: "bundled"` | the binary; see the catalog     |
| Built-in plugin skills | `bundled`, plugin `<name>@builtin`  | the `cc-plugin-*` registry      |
| Built-in prompts       | none; `source: "builtin"`           | the built-in command table      |

The public docs cover the user-facing locations, precedence when names collide, and synced skills. A
memory-store skill is always built with `userInvocable: false`
(`rg -n 'loadedFrom: "memoryStore"'`).

Built-in prompt commands are slash commands written as prompts. The ones without
`disableModelInvocation` are eligible for the model's skill listing, which is how the docs' "A few
built-in commands are also available through the Skill tool, including `/init` and
`/security-review`" works: `init`, `security-review` and `commit-push-pr`. `insights`, `statusline`
and `team-onboarding` set `disableModelInvocation` and stay user-only. Relocate the list with
`rg -n 'source: "builtin"'`; `security-review` is built by a small factory whose object carries
`pluginName: "security-review"`.

### One list feeds both the user and the model

The loaded command list is filtered once, then serves both audiences:

- Every command passes three checks to stay in the list: its `availability` (claude.ai or Console
  accounts), its `policyGate`, and its `isEnabled()`. The policy-and-enabled check reads
  `policyGate.policy` as an org policy key, then calls `isEnabled?.()`, treating an absent function
  as enabled. A command that fails is gone for both audiences: typing it gives
  `Unknown command: /<name>`, and the Skill tool answers `Unknown skill: <name>`.
- The `/` menu shows what survives, minus `isHidden` entries.
- The model's skill listing (the `skill_listing` attachment and the Skill tool's own list) keeps a
  prompt-type command only when `disableModelInvocation` is false, `skillOverrides` does not resolve
  to `user-invocable-only` or `off`, and its source is one the listing accepts. Relocate that
  predicate by the source names it tests together: `"commands_DEPRECATED"` beside
  `hasUserSpecifiedDescription`.

### Registering a bundled skill

`rg -n 'loadedFrom: "bundled"'` returns two object literals (`source: "bundled"` also matches an
unrelated TLS certificate list). One is the bundled-skill registrar, whose caller pushes the object
onto `bundledSkills` and, when `survivesBundledKillSwitch` is set, onto
`bundledSkillKillSwitchSurvivors`. The other wires a built-in plugin's skills, caching them in
`builtinPluginWiredSkills`. Both build the same command shape:

- `type: "prompt"`, `contentLength: 0`, `hasUserSpecifiedDescription: true`.
- `userInvocable` defaults to true, and `isHidden` is always `!(userInvocable ?? true)`. A skill is
  never hidden from the menu while still user-invocable, and never shown while not.
- `disableModelInvocation` defaults to false. When the definition passes a function, the literal is
  first set to true and then replaced by a live getter, so the value is re-read on every access.
  `description`, `menuDescription`, `argumentHint`, `whenToUse` and `policyGate` get the same getter
  treatment when given as functions.
- `progressMessage` defaults to `"running"`.
- `isEnabled` is passed through by the bundled registrar (absent means enabled). The built-in plugin
  registrar defaults it to `() => true`.

Registration happens once per process, guarded by `bundledSkillsInitialized`
(`rg -n 'bundledSkillsInitialized'`). The initializer calls each registration function in turn, then
requires several from their own modules by exported name: `registerCoworkSetupSkill`,
`registerLoopSkill`, `registerScheduleRemoteAgentsSkill`, `registerContinueInProjectsSkill`,
`registerClaudeApiSkill`, `registerClaudeCodeSkill`, `registerWorkflowAuthoringSkill`,
`registerRunSkill` and `registerRunSkillGeneratorSkill`.

When `CLAUDE_CODE_ENTRYPOINT` is `local-agent` the initializer takes an early branch. It registers
`design` (with its hub and sync modes off), and, only when Artifacts are wired into that host,
`artifact-design`, `artifact-diagramming`, `slides` and `artifact-capabilities`. Nothing else.

Seven registration functions the initializer calls register nothing. Four have the body `return;`:
two sit right after unreferenced prompts (Skillify, and the `/stuck` prompt anchored on
`diagnose frozen/slow Claude Code sessions`), two have no prompt beside them. Three have an empty
body. See `SKILLIFY.md`.

### Filters, in order

1. Kill switch. `CLAUDE_CODE_DISABLE_BUNDLED_SKILLS`, or the setting `disableBundledSkills: true`.
   The bundled-skill collector then returns only the kill-switch survivors, which are `design` and
   `doctor` (`rg -n 'survivesBundledKillSwitch: !0'`, two hits). Built-in prompt commands stay
   typable but resolve to `user-invocable-only`, so the model loses them. The skills of built-in
   plugins are not dropped by the kill switch, with one exception: `cc-plugin-claude-platform`
   withholds its `claude-api` copy. The setting's own description: "bundled skills and workflows are
   removed entirely; built-in slash commands stay typable but are hidden from the model."

2. Org policy `allow_bundled_skills`. Defined beside the other policy keys
   (`rg -n 'allow_bundled_skills: \{'`): denied under `hipaa`, `onCacheMiss: "allow"`, labelled
   `Bundled skills`. When the policy denies, a bundled skill survives only if it is a kill-switch
   survivor or named in the core list, and a built-in plugin's skill only if it is named in the core
   list. The core list is the server's `core_skills` from the policy verdict, remembered from the
   last one served; a hardcoded default stands in when none was ever served: `artifact-diagramming`,
   `batch`, `claude-code-docs`, `code-review`, `commit`, `dataviz`, `debug`, `explain-usage`,
   `fewer-permission-prompts`, `keybindings-help`, `loop`, `memory-types`, `plugin-authoring`, `pr`,
   `simplify`, `update-config`, `verify`, `workflow-authoring`. Relocate the default by grepping
   `"fewer-permission-prompts",` beside `"memory-types",`. Built-in prompt commands become
   `user-invocable-only`. Typing a dropped bundled skill in an interactive session yields a policy
   notice for `Bundled skills` rather than `Unknown command`.

3. `policyGate`, then `isEnabled()`, per command (see above). Each bundled skill's gate is in the
   catalog.

4. `userInvocable: false` (frontmatter `user-invocable: false`). Hidden from the menu. Typing it
   returns "This skill can only be invoked by Claude, not directly by users. Ask Claude to use the
   "<name>" skill for you." The model still lists and invokes it.

5. `disableModelInvocation: true` (frontmatter `disable-model-invocation: true`). Not in the model's
   listing. Unless the user typed `/<name>` in the current turn, the Skill tool refuses it with a
   message that begins "Skill <name> cannot be used with Skill tool due to
   disable-model-invocation." and adds "Do not replicate this skill's workflow by other means".

6. `skillOverrides`. Values `on`, `name-only`, `user-invocable-only`, `off`; most restrictive wins
   across matching entries. The public docs cover the menu and the alias rules. The source adds the
   refusal texts: typed while `off` gives `Skill "<name>" is disabled via skillOverrides.`; the
   Skill tool reports `Skill <name> is disabled for model invocation in skillOverrides settings`, or
   names the kill switch or the denying policy when either is the cause.

In the table, "Unknown command" and "Unknown skill" are the `Unknown command: /<name>` and
`Unknown skill: <name>` messages, and the policy notice appears only in an interactive session.

| Setting on the skill              | User types `/name`    | Listed    | Model invokes           |
| --------------------------------- | --------------------- | --------- | ----------------------- |
| `isEnabled` or `policyGate` fails | Unknown command       | No        | Unknown skill           |
| Kill switch, bundled non-survivor | Unknown command       | No        | Unknown skill           |
| Kill switch, built-in prompt      | Yes                   | No        | Refused (kill switch)   |
| Policy denies, not on core list   | Policy notice         | No        | Unknown skill           |
| `userInvocable: false`            | Refused (Claude only) | Yes       | Yes                     |
| `disableModelInvocation: true`    | Yes                   | No        | Only if typed this turn |
| Override `name-only`              | Yes                   | Name only | Yes                     |
| Override `user-invocable-only`    | Yes                   | No        | Only if typed this turn |
| Override `off`                    | Refused (override)    | No        | Refused                 |

### Three execution paths

| Path              | Trigger                        | Context the skill sees             |
| ----------------- | ------------------------------ | ---------------------------------- |
| Inline            | `/name` or Skill tool, no fork | Whole conversation; body inline    |
| `context: fork`   | Either trigger, fork resolved  | Only the skill body, new subagent  |
| `skills:` preload | An agent definition lists it   | The subagent's context, body first |

Fork is resolved per call: a skill's `getContext()` wins over its `context` field, else `"inline"`.
The bundled `code-review` uses this to fork by default and run inline in some sessions. `agent:` is
read only on the fork path.

`context: fork` does not fork the conversation, unlike the Agent tool's `fork` subagent and `/fork`
(see `SUBAGENTS.md`, `CLEAR_COMPACT_FORK_CONTEXT.md`). Both fork entry points, the user's `/name`
and the Skill tool, prepare the fork through the function exported as `prepareForkedCommandContext`
(`rg -n 'No agent available for forked execution'`), and neither passes `forkContextMessages`. The
forked subagent gets:

- A single meta user message holding the rendered skill body, plus attachments extracted from that
  text (its `@` mentions).
- A fresh read-file state, not the parent's.
- The agent named by `agent:`, else `general-purpose`, else the first active agent. A named agent
  that is missing logs `Forked command <name>: agent '<x>' is not available as a fork base` and
  names the agent it runs on instead. A named agent that exists but whose plugin fails to load it
  refuses the fork: `could not be loaded from its plugin, and <name> runs on no other`.
- The parent's tool list, narrowed by the agent definition.
- With `background` left at its default, the result arrives later:
  `Running in the background as @<name>`.

The preload path is described in `SUBAGENTS.md`'s territory, but its permission behavior is below.
Preload resolves each name against the model's skill listing, so a `disable-model-invocation` skill
is "not found", as the public docs say. It skips, with a debug warning each, a skill that is not
found, `is not a prompt-based skill`, `is disabled by policy` (fails the policy-and-enabled check),
`is turned off by the organization's Skills setting`, or is an account-synced skill while skills
sync is off. Survivors render in parallel with `isSkillPreload` set, then log
`Preloaded skill '<name>'` and `tengu_skill_tool_invocation` with `execution_context: "preload"`.

A preload is not a read-only load: it sets `isSkillPreload` but not `readOnlySkillLoad`, so the
body's `` !`cmd` `` lines run, checked against the skill's own `allowed-tools` as described under
Injected commands. In auto mode a command the check would ask about can instead be handed to the
agent through the loop's hand-off list, as an inline instruction that begins
`run this first, exactly as written`.

### Where `allowed-tools` applies

A skill's `allowed-tools` entries land in `toolPermissionContext.alwaysAllowRules.command`;
`disallowed-tools` land in `alwaysDenyRules.command`. Frontmatter parsing, including how an entry
naming `${CLAUDE_SKILL_DIR}` is dropped from a skill with no folder
(`naming CLAUDE_SKILL_DIR, because the skill has no folder of its own`), is in
`MARKDOWN_FRONTMATTER.md`.

| Path                  | Grant       | Mechanism                                                 |
| --------------------- | ----------- | --------------------------------------------------------- |
| Typed `/name`, inline | Yes         | Input's `allowedTools` replace `command` rules for a turn |
| Skill tool, inline    | Yes         | An `allowed_tools` layer, unioned into `command` rules    |
| `context: fork`       | Yes         | Wrapped `getAppState`, plus allow and deny layers         |
| `skills:` preload     | No          | The loop renders the body, never reads `allowedTools`     |
| Injected `` !`cmd` `` | Yes, scoped | Checked with `command` set to the skill's own list        |

Typed `/name`. The prompt slash-command processor (`rg -n 'type: "command_permissions"'`) returns
`allowedTools`, `disallowedTools`, `model` and `effort`, and appends a `command_permissions`
message. When the query engine processes each user input it sets `alwaysAllowRules.command` to that
input's `allowedTools`, unless the input carries `skipSkillPermissionReset`. A plain prompt carries
none, so the grant lasts until the next message, as the public docs say.

Skill tool, inline. The tool returns the grant as a permission layer of kind `allowed_tools`
(relocate with `rg -n 'case "allowed_tools"'`), which unions the list into the existing `command`
rules. On the coordinator (the main session in coordinator mode) the Skill tool loads the skill
read-only instead: no grant, model or effort applies, and the skill's `` !`cmd` `` lines do not run
(see Read-only skill loads). Under `pollEventDeliveryGuard` no grant is applied.

Fork. The fork preparation wraps `getAppState` so `command` becomes the de-duplicated union of the
existing rules and the skill's list (or replaces them when the caller asks), merges
`disallowed-tools` into `alwaysDenyRules.command`, and records both as layers.

Injected commands. Before a skill body's `` !`cmd` `` lines run, the runner is handed a
`getAppState` whose `command` rules are exactly the skill's `allowed-tools`. That is the only effect
of the grant during rendering; it does not reach the caller.

The preload gap. The preload loop resolves the skill object, which carries `allowedTools`, and never
reads it. The agent runner (exported as `runAgent`) does accept an `allowedTools` argument, which
replaces the subagent's allow rules with the parent's `cliArg` (and `mcpServerPolicy`) rules plus
the list as `session` rules. Only the in-process teammate runner passes it
(`rg -n 'In-process teammate: '` finds that caller); the Agent tool does not. The runner builds its
permission wrapper before the preload loop, so the loop's skills could not feed it anyway. To
pre-approve tools for a preloading subagent, use `--allowedTools`, `permissions.allow` in settings,
or session grants.

Neither agent nor skill frontmatter has a key for the other's axis. Agent `tools` and
`disallowedTools` control which tools exist for the subagent; skill `allowed-tools` pre-approves and
`disallowed-tools` denies. A preloaded skill's `allowed-tools` does not widen an agent's `tools`,
and an agent's `tools` does not pre-approve anything.

### Skill-loading metadata tags

A skill body enters the conversation as a meta user message preceded by a metadata text block. The
tag names are constants: `command-name`, `command-message`, `command-args`, `skill-format`. Grep a
tag name, not a rendered line, because the lines are assembled from the constants. Both formats
carry `command-message`.

| Format       | Produced for                     | `command-name` | Third tag              |
| ------------ | -------------------------------- | -------------- | ---------------------- |
| Slash format | A user-invocable skill           | `/name`        | `command-args`, if any |
| Skill format | Preloads, most model-only skills | `name`         | `skill-format`         |

The skill format is exported as `formatSkillLoadingMetadata`; the preload loop calls it directly. A
dispatcher picks the slash format for any skill whose `userInvocable` is not false. A
non-user-invocable skill gets the skill format only when it is loaded from skill directories, synced
skills, a plugin, MCP, a memory store or an attached folder; a non-user-invocable bundled skill
(`artifact-design`, `keybindings-help`) still gets the slash format. The model sees the tags; the UI
parses them back out to render `Skill(name)` versus `/name args`.

### Bundled skill files

A bundled skill may ship a `files` map (or a function returning one). Its prompt function is then
wrapped so that on first invocation the files are written out, once per process:

- Location: `<Claude temp dir>/bundled-skills/<version>/<random hex>/<skill name>`, or a host's
  `bundledSkillFilesElsewhere` writer when one is set.
- Writes refuse to overwrite (exclusive create, no symlink following), files are mode 0600 and
  directories 0700, and a relative path that climbs out throws
  `bundled file path escapes its extraction dir`. An existing file passes only if its content
  matches.
- Success logs `skill_bundled_extract`; failure logs `skill_bundled_extract_write_failed` and
  `Failed to extract bundled skill '<name>' to <dir>`, and the skill runs without its files.
- On success the prompt is prefixed with `Base directory for this skill: <dir>`, the same prefix a
  disk skill gets for its own folder.

The skill bodies and reference files themselves are embedded in the binary's `$bunfs` as
zstd-compressed `.md.zst` assets (`rg -o 'SKILL-[0-9a-f]+\.md\.zst'`), decompressed on load. A
missing or corrupt asset throws `embedded asset is missing or corrupt`.

Per-session caches inside a bundled skill clear through session-reset hooks; a failing hook logs
`[skills] session-reset hook failed:`.

### Template variables

The public docs list `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_SESSION_ID}` and
`${CLAUDE_EFFORT}` and say where each is substituted. The source matches. Substitution order:
arguments first, then `${CLAUDE_SKILL_DIR}`, then `${CLAUDE_PROJECT_DIR}` and `${CLAUDE_SESSION_ID}`
(skipped for MCP, memory-store and attached-folder skills, and for synced skills outside remote and
Cowork sessions), then `${CLAUDE_EFFORT}`, then injected commands. Injected commands are skipped for
the same skills. For skill-directory, synced and plugin skills not from managed settings, the
`disableSkillShellExecution` setting or `CLAUDE_CODE_IS_COWORK` replaces them with a placeholder
instead of running them.

### Read-only skill loads

`readOnlySkillLoad` is an internal option on a skill load's tool-use context. Neither the user nor
the model can set it, and no frontmatter key maps to it. The model sees only its effect.

Its one reader is the injected-command step. With the option set, the skill body renders without
running any `` !`cmd` `` line; each is replaced by a bracketed placeholder that reads
`shell command not executed: read-only skill load on the coordinator`, then an em dash (stored as a
`\u2014` escape) and `delegate to a worker to run it`. Grep the first part. Injected commands are
the only part of rendering that executes anything, so the load has no side effects.

It is set in two places:

1. The Skill tool on the coordinator. The prompt slash-command processor (exported as
   `processPromptSlashCommand`), called with its read-only argument, renders the body with both
   `isSkillPreload` and `readOnlySkillLoad` set. Grep `isSkillPreload: !0, readOnlySkillLoad: !0`.
2. A served request to render a skill for another process. The request carries the skill name and
   arguments, a `readOnly` option, an optional expected SHA-256 of the skill file, and the caller's
   session permission rules. The load is read-only when the request asks for it or when the caller's
   rules cannot be applied. A file whose hash no longer matches is refused with "this skill's file
   changed after the session listed it, so it was not rendered". A successful response holds the
   rendered text blocks, an optional `handedOff` list of the commands not run, and `fromHostCatalog`
   when the skill came from the host's catalog.

The placeholder's wording reflects the coordinator design: a coordinator session plans and delegates
instead of running tools, so a skill it loads hands its commands to a worker. A related branch has
the same effect without the option: a served call in auto mode with no hand-off list also renders
the placeholder; it sits in the same function, a few lines below the `readOnlySkillLoad` check.

## Bundled skills

31 bundled skills register through the bundled registrar:

| Skill (aliases)                 | Summary                                            |
| ------------------------------- | -------------------------------------------------- |
| `artifact-capabilities`         | Runtime capabilities for published Artifacts       |
| `artifact-design`               | Design pass before writing any Artifact            |
| `artifact-diagramming`          | Diagramming guidance for Artifacts                 |
| `slides`                        | New Slides deck Artifact from a brief              |
| `design`                        | Claude Design: new design, hub, or consent         |
| `design-sync`                   | Push a React design system to claude.ai/design     |
| `batch`                         | Plan a large change; worktree agents each open PRs |
| `claude-in-chrome`              | Drive the user's Chrome                            |
| `code-review` (`review`)        | Review the diff or a PR for bugs                   |
| `commit`                        | Create a git commit                                |
| `pr`                            | Create a pull request                              |
| `cowork-plugin`                 | Create or customize a Cowork plugin                |
| `dataviz`                       | Chart and dashboard design guidance                |
| `debug`                         | Turn on debug logging and investigate              |
| `doctor` (`checkup`)            | Health-check the setup and fix issues              |
| `explain-usage`                 | Where this session's tokens went                   |
| `fewer-permission-prompts`      | Allowlist read-only calls from transcripts         |
| `keybindings-help`              | Customize `~/.claude/keybindings.json`             |
| `memory-types`                  | Memory type taxonomy reference                     |
| `simplify`                      | Cleanups only, then apply the fixes                |
| `update-config`                 | Configure the harness via `settings.json`          |
| `verify`                        | Try the change and report if it works              |
| `setup-claude` (`setup-cowork`) | Guided Cowork setup                                |
| `loop` (`proactive`)            | Repeat a prompt on an interval                     |
| `schedule` (`routines`)         | Cloud agents on a cron schedule                    |
| `send-to-project`               | Send this session's work to a Claude Project       |
| `claude-api`                    | Claude API and SDK reference                       |
| `claude-code-docs`              | Answer questions about Claude Code                 |
| `workflow-authoring`            | Reference for Workflow tool scripts                |
| `run`                           | Launch the project's app to see a change           |
| `run-skill-generator`           | Write a project skill that runs the app            |

Visibility and gates. U is user-invocable, M is model-invocable (and listed), Files is a `files` map
extracted on first use. "Core" means the skill is on the default core list that survives a policy
denial of `allow_bundled_skills`.

| Skill                      | Gate                                           | U   | M    | Files |
| -------------------------- | ---------------------------------------------- | --- | ---- | ----- |
| `artifact-capabilities`    | Artifacts, capabilities on                     | Yes | Yes  | Yes   |
| `artifact-design`          | Artifacts                                      | No  | Yes  | No    |
| `artifact-diagramming`     | Artifacts; core                                | Yes | Yes  | No    |
| `slides`                   | Artifact types, `allow_cobalt_plinth_juniper`  | Yes | No   | No    |
| `design`                   | See below; survives kill switch                | Yes | No   | No    |
| `design-sync`              | `allow_design_sync`                            | Yes | No   | Yes   |
| `batch`                    | None; core                                     | Yes | No   | No    |
| `claude-in-chrome`         | Extension wired, or install upsell             | Yes | Yes  | No    |
| `code-review`              | None; core                                     | Yes | Yes  | No    |
| `commit`                   | `tengu_cinder_relay`; core                     | Yes | Yes  | No    |
| `pr`                       | `tengu_cinder_relay`; core                     | Yes | Yes  | No    |
| `cowork-plugin`            | Cowork                                         | No  | Yes  | Yes   |
| `dataviz`                  | None; core                                     | Yes | Yes  | Yes   |
| `debug`                    | None; core                                     | Yes | No   | No    |
| `doctor`                   | `DISABLE_DOCTOR_COMMAND`; survives             | Yes | No   | No    |
| `explain-usage`            | Cowork; core                                   | Yes | Yes  | No    |
| `fewer-permission-prompts` | None; core                                     | Yes | Yes  | No    |
| `keybindings-help`         | `tengu_keybinding_customization_release`; core | No  | Yes  | No    |
| `memory-types`             | Auto memory, `tengu_ochre_finch`; core         | No  | Yes  | No    |
| `simplify`                 | None; core                                     | Yes | Yes  | No    |
| `update-config`            | None; core                                     | Yes | Yes  | No    |
| `verify`                   | None; core                                     | Yes | Flag | Yes   |
| `setup-claude`             | Cowork                                         | Yes | Yes  | No    |
| `loop`                     | `tengu_kairos_cron`; core                      | Yes | Yes  | No    |
| `schedule`                 | Routines, see below                            | Yes | Yes  | No    |
| `send-to-project`          | `tengu_amber_tributary_dotterel`               | Yes | No   | No    |
| `claude-api`               | `CLAUDE_CODE_DISABLE_CLAUDE_API_SKILL`         | Yes | Yes  | Yes   |
| `claude-code-docs`         | `tengu_birch_kettle`; core                     | Yes | Yes  | Yes   |
| `workflow-authoring`       | Workflow tool available; core                  | Yes | Yes  | No    |
| `run`                      | None                                           | Yes | Yes  | Yes   |
| `run-skill-generator`      | None                                           | Yes | No   | Yes   |

Dedicated doc: `claude-code-docs` is covered in `CLAUDE_CODE_GUIDE.md`. No other bundled skill has
one; `code-review`, `doctor`, `verify` and `run` are covered in depth by the public docs.

Gate notes. A flag's default follows its name in parentheses.

- Artifacts. The Artifacts availability check: first-party API, not essential-traffic-only,
  `CLAUDE_CODE_ARTIFACT` not set falsy, `tengu_cobalt_plinth` (on by default for claude.ai consumer
  sign-in or no auth), org policy `allow_cobalt_plinth`, and Artifacts not switched off in settings.
  It is off by default on the SDK entrypoints, `claude-code-github-action` and `mcp` unless
  `CLAUDE_CODE_ARTIFACT` is set truthy, and off on `claude-coworker*` entrypoints and on
  `local-agent` unless Artifacts are wired into that host. The three `artifact-*` skills are also
  off when the built-in Artifact tool is hidden in favour of an MCP artifact server.
  `artifact-capabilities` fetches its type-definition files from the server at invocation
  (`artifact_capability_section` logs the outcome). `slides` also needs Artifact types available.
- `design`. Its mode decides description, gate and behavior. With bundled skills killed or denied by
  policy: consent mode when design-sync is available (the `design-sync` gate below), else disabled.
  With Artifact types available: types mode (a new Design artifact) when
  `allow_cobalt_plinth_bramble` allows, else consent mode or disabled on the same rule. Otherwise
  hub mode when the registration allows it (not on `local-agent`), `allow_design_sync` allows, the
  session is first-party and not essential-traffic-only, and `tengu_omelette_fouet` (false) is on.
  Otherwise consent mode (`consent`, `revoke`) when design-sync is available, else disabled. Every
  mode but types carries `policyGate: { policy: "allow_design_sync" }`. The source also carries the
  notice "Standalone Claude Design (claude.ai/design) closes by December 14, 2026."
- `design-sync`. `allow_design_sync`, not essential-traffic-only, first-party API; also its
  `policyGate`.
- `claude-in-chrome`. On when the Chrome extension was wired this session or an install upsell
  applies. Off with `CLAUDE_CODE_DISABLE_CFC_PROMPT`, and off when a managed MCP configuration
  (`managed-mcp.json`) is in force unless device policy sets `allowClaudeInChromeWithManagedMcp`.
- `commit`, `pr`. `tengu_cinder_relay` (false), latched for the session on first read.
  `allowedTools` pre-approve the git commands each needs. The built-in `commit-push-pr` prompt
  command is not gated by this flag.
- `verify`. Always enabled and user-invocable. `disableModelInvocation` is a getter that returns
  `!tengu_opal_circuit` (false), also latched for the session on first read, so the model can invoke
  it only with that flag on.
- Cowork. `CLAUDE_CODE_ENTRYPOINT` is `remote_cowork`, or a diskless session whose derived surface
  is `remote_cowork`.
- `memory-types`. Auto memory on (see `AUTO_MEMORY.md`) and `tengu_ochre_finch` (false).
- `keybindings-help`. `tengu_keybinding_customization_release` (true).
- `loop`. `CLAUDE_CODE_DISABLE_CRON` unset and `tengu_kairos_cron` (true).
- `schedule`. claude.ai sign-in, first-party API, not `CLAUDE_CODE_REMOTE`, and org policy
  `allow_routines`; `policyGate` is `allow_remote_sessions`.
- `send-to-project`. `tengu_amber_tributary_dotterel` (false), a local workspace, not
  `CLAUDE_CODE_REMOTE`, a remote-session eligibility check, first-party API, claude.ai sign-in with
  org policy `allow_remote_sessions`, not essential-traffic-only; `policyGate` is
  `allow_remote_sessions`.
- `claude-api`. `CLAUDE_CODE_DISABLE_CLAUDE_API_SKILL` turns it off. It pre-approves
  `WebFetch(domain:platform.claude.com)`, denies `Agent(web-fetch)`, and sets
  `disableBridgeInvocation`.
- `claude-code-docs`. `tengu_birch_kettle` (false); `CLAUDE_CODE_DISABLE_CLAUDE_CODE_SKILL` turns it
  off.
- `workflow-authoring`. The Workflow tool's availability: `tengu_workflows_enabled` (true),
  `CLAUDE_CODE_WORKFLOWS`, `CLAUDE_CODE_DISABLE_WORKFLOWS`, the `enableWorkflows` and
  `disableWorkflows` settings, and org policy `allow_workflows`.
- `doctor`. `DISABLE_DOCTOR_COMMAND` turns it off; it needs a workspace.

Drift from the public docs:

- The skills and commands pages do not mention `slides`, `explain-usage`, `send-to-project`,
  `setup-claude`, `memory-types`, `cowork-plugin` or `keybindings-help`; most are gated to Cowork
  sessions, Artifacts hosts or off-by-default flags.
- The docs say `/verify` runs only when the user invokes it. True by default; the source keeps a
  flag (`tengu_opal_circuit`) that makes it model-invocable.
- The docs list `/doctor` as the skill that stays typable under `disableBundledSkills`. `design`
  also survives the kill switch, in consent mode.

### Built-in plugins

A separate registry, guarded by `builtinPluginsInitialized` (`rg -n 'builtinPluginsInitialized'`),
registers the built-in plugins, one lazily required `"cc-plugin-…"` module each. `MODS.md` owns the
list: all 14 ids, the entrypoints each registers on, and how each is enabled (`enabledPlugins` under
`<name>@builtin`, else the plugin's own `defaultEnabled`, else on). Only three supply skills:

| Plugin                       | Skills it supplies                                        |
| ---------------------------- | --------------------------------------------------------- |
| `cc-plugin-plugin-authoring` | `plugin-authoring`                                        |
| `cc-plugin-claude-platform`  | `claude-api`                                              |
| `cc-plugin-claude-test`      | `claude-test`, `claude-test-execute`, `claude-test-draft` |

- `plugin-authoring` is user- and model-invocable, ships files, and is on the core list.
- `cc-plugin-claude-platform` supplies its `claude-api` copy only when no bundled `claude-api` is
  registered (the `local-agent` entrypoint registers none) and `claude-api` is neither killed nor
  policy-denied; its availability includes `tengu_peppy_crescent` (false).
- `cc-plugin-claude-test` sets no `defaultEnabled`, so it is on once available. Its availability
  needs `tengu_mellow_hollerith` (false) answered on for the signed-in account, Linux, macOS or WSL,
  a non-root user, settled compliance taints with neither `hipaa` nor `zdr`, and a policy verdict.
  `claude-test` is user- and model-invocable. `claude-test-execute` and `claude-test-draft` are
  model-only (`userInvocable: false`) forked skills, running on agents `claude-test:runner` and
  `claude-test:author`. All three need a workspace. Relocate the names with
  `rg -n 'execute: "claude-test-execute"'`.

Built-in plugins' skills are dropped by an `allow_bundled_skills` denial unless on the core list,
but not by the kill switch.

## Re-verify

- □ `rg -n 'loadedFrom: "bundled"'`: 2 hits, each object setting `isHidden` to the negation of
  `userInvocable` defaulted to true.
- □ `rg -n 'survivesBundledKillSwitch: !0'`: 2 hits, `design` and `doctor`.
- □ The default core list holds 18 names, beginning `"artifact-diagramming"`.
- □ `allow_bundled_skills` is denied under `hipaa` with `onCacheMiss: "allow"`.
- □ The `bundledSkillsInitialized` initializer's `local-agent` branch registers design plus the
  Artifacts skills only.
- □ The preload loop's warnings (`is not a prompt-based skill`, `is disabled by policy`,
  `is turned off by the organization's Skills setting`) are present; it never reads `allowedTools`,
  and its render options set `isSkillPreload` without `readOnlySkillLoad`.
- □ `rg -n 'isSkillPreload: !0, readOnlySkillLoad: !0'`: 1 hit, in the module exporting
  `processPromptSlashCommand`.
- □ `rg -n 'In-process teammate: '` is the only `runAgent` caller passing `allowedTools`.
- □ The `builtinPluginsInitialized` initializer registers 14 `"cc-plugin-…"` ids (list in
  `MODS.md`); only the `plugin-authoring`, `claude-platform` and `claude-test` modules define
  skills.
