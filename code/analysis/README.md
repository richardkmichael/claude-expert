# Analysis Index

The map of what has already been worked out about Claude Code, so a session can find prior research
before re-deriving it. Each row gives the doc, the question it answers, the `cli.prettier.js` version
it was last checked against, its anchoring style, and a few stable strings to grep when relocating
the behavior in a newer bundle.

How to use this: find the topic below, open the doc, then confirm it still holds against the latest
local source (`ls work/ | sort -V | tail -1`). If the doc's Verified column is behind that version,
treat its version-specific specifics as suspect and re-check against the current bundle.
`bin/analysis-index.py` in the repository root lists every doc stamped behind the latest version.
Methodology for writing and updating docs is in `GUIDELINES.md`; the doc-update loop is summarized
in `../CLAUDE.md`.

Style legend:

- `landmark` — anchored on version-stable strings and grep recipes (the `GUIDELINES.md` style).
  Behavioral claims travel across releases; re-check exact specifics against the current bundle.
- `legacy` — leans on line numbers and pasted minified code. Re-verify before trusting, and retrofit
  to landmark style when you touch it.
- `generated` — machine-produced snapshot. Never hand-edit; regenerate from the source bundle.
- `methodology` — how to analyze the bundle, not findings about it.

## System prompts and instructions

<!-- analysis-index: System prompts and instructions -->

| Doc                   | Scope                                                                                               | Verified | Style     | Key landmarks                                                                                                              |
| --------------------- | --------------------------------------------------------------------------------------------------- | -------- | --------- | -------------------------------------------------------------------------------------------------------------------------- |
| `GIT_USAGE.md`        | Git instructions in prompts and tool descriptions, per-model gating, attribution, gitStatus context | 2.1.317  | landmark  | `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS`, `includeGitInstructions`, `# Committing changes with git`, `tengu_reflective_wolf` |
| `OUTPUT_STYLES.md`    | Built-in output-style prompts, resolution, injection                                                | 2.1.220  | landmark  | `Learning Style Active`, `output_style_load`, `# Output Style: `                                                           |
| `PROMPTS.md`          | System-prompt assembly: sections, gates, routing                                                    | 2.1.316  | landmark  | `# Harness`, `CLAUDE_CODE_SIMPLE_SYSTEM_PROMPT`, `tengu_velvet_tide`                                                       |
| `PROMPTS_RENDERED.md` | Verbatim rendered prompt text, by anchor string                                                     | 2.1.317  | generated | `You are Claude Code`, `You are a security monitor`                                                                        |

<!-- /analysis-index -->

## Tools, skills, and execution

<!-- analysis-index: Tools, skills, and execution -->

| Doc                        | Scope                                                                                                                                     | Verified | Style    | Key landmarks                                                                                                                     |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `AT_MENTION_CONTEXT.md`    | `@` mentions at submit: file, directory and line-range reads, size and token caps, PDFs, MCP resources, agent and peer mentions           | 2.1.317  | landmark | `"at_mentioned_files", () =>`, `#L(\d+)(?:-(\d+))?`, `The user @-mentioned`                                                       |
| `BACKGROUND_BASH_TASKS.md` | `run_in_background` prompt text, detached `-c` spawn, task end on shell exit, group kill, hook visibility                                 | 2.1.316  | landmark | `runs the command detached`, `Stops a running background task by its ID`, `"group_kill"`, `background_tasks`                      |
| `BASH_TOOL_EXECUTION.md`   | Bash tool, shell snapshots, search-tool wrappers                                                                                          | 2.1.207  | landmark | `shell-snapshots`, `SNAPSHOT_FILE=`, `RIPGREP_FUNC_END`                                                                           |
| `CLAUDE_CODE_GUIDE.md`     | claude-code-guide agent, `claude-code-docs` skill, bundled refs                                                                           | 2.1.316  | landmark | `You are the Claude guide agent.`, `tengu_birch_kettle`                                                                           |
| `FILE_INCLUSION.md`        | `@` completion: sources and order, path completion, git/ripgrep index, `.ignore` re-include, `.claude/**`, `fileSuggestion` payload, caps | 2.1.317  | landmark | `[FileIndex]`, `generateFileSuggestionsWithBase`, `keepDotPrefix`, `mcp-template::`                                               |
| `RIPGREP.md`               | Ripgrep bundling, embedded/system selection, config                                                                                       | 2.1.207  | landmark | `USE_BUILTIN_RIPGREP`, `tengu_ripgrep_availability`, `no-config`                                                                  |
| `SKILLIFY.md`              | Live `propose_skills` skill proposals; dead Skillify prompt                                                                               | 2.1.316  | landmark | `propose_skills`, `CLAUDE_CODE_SKILL_PROPOSALS`, `# Skillify`                                                                     |
| `SKILLS.md`                | Skills: sources, filters and visibility, invocation (inline, fork, preload), `allowed-tools` paths, read-only loads, bundled catalog      | 2.1.317  | landmark | `bundledSkillsInitialized`, `allow_bundled_skills: {`, `survivesBundledKillSwitch: !0`, `No agent available for forked execution` |
| `SUBAGENTS.md`             | Agent tool and subagents: schema, launch, model resolution, tool set, background and fork placement, output, handback, isolation          | 2.1.317  | landmark | `delegate work to a subagent`, `tengu_agent_tool_completed`, `"tengu_fork_subagent_enabled"`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`  |
| `TOOLS_AND_EXECUTION.md`   | Built-in tool registry, the `getTools` filter and per-tool gates (embedded search, task list, tool search, PowerShell, web-fetch swap)    | 2.1.317  | landmark | `assembleToolPool`, `CLAUDE_CODE_ENABLE_TODO_TOOLS === !0`, `isToolSearchForceOverride`, `CLAUDE_CODE_ENABLE_TASKS`               |
| `TOOL_VALIDATION.md`       | Zod-then-business-logic validation, per-tool errors                                                                                       | 2.1.165  | landmark | `InputValidationError`, `Shell command failed`                                                                                    |

<!-- /analysis-index -->

## Permissions and safety

<!-- analysis-index: Permissions and safety -->

| Doc                                   | Scope                                                                                                                                                                                               | Verified | Style    | Key landmarks                                                                                                                                                                                           |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AUTO_MODE_AND_COMMAND_CLASSIFIER.md` | Regex destructive-command classifier + auto-mode LLM security classifier; embedded rules template; `autoMode` rule-config surface; server-side review; why subagent `git commit --amend` is blocked | 2.1.316  | landmark | `security monitor for autonomous`, `git_commit_amend`, `tengu_auto_mode_config`, `isSubagentLoop`, `<block>`, `permissions_external-`, `user_allow_rules_to_replace`, `$defaults`, `auto-mode defaults` |

<!-- /analysis-index -->

## Hooks

<!-- analysis-index: Hooks -->

| Doc                          | Scope                                                                                                                                                                   | Verified | Style    | Key landmarks                                                                                                                                                  |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `HOOKS.md`                   | Hook event inventory, I/O schemas, matchers and tool-name families, `onFailure`, restricted personal hooks, hook process env, relocation recipes                        | 2.1.317  | landmark | `hook_event_name`, `fieldToMatch`, `What a failure of this hook does`, `hook_additional_context`, `CLAUDE_CODE_CHILD_SESSION`                                  |
| `MODS.md`                    | Mods: sources, the 14 built-in plugins, refusal order, reloads, rollout gate (bounded wait, late load, mid-session follow), `plugin test`, dev mods                     | 2.1.317  | landmark | `tengu_plugin_hooks_modules`, `as loadPluginHooks`, `which governs installed plugins`, `builtinPluginsInitialized`, `hooksModulesSwitchJoin`                   |
| `SESSION_HOOKS_LIFECYCLE.md` | SessionStart/End order, shutdown signals and SessionEnd budget, hook spawn and `CLAUDE_PID`, background-session hook env                                                | 2.1.316  | landmark | `hook_event_name: "SessionEnd", reason:`, `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS`, `"shutdown_signal"`, `CLAUDE_CODE_SESSION_KIND: "bg"`                     |
| `WORKTREES.md`               | WorktreeCreate/Remove payloads and hook output, hook `cwd`, `baseRef`, the `hookBased` removal gate, exit dialog, agent/job removal, cleanup of kept subagent worktrees | 2.1.317  | landmark | `hook_event_name: "WorktreeCreate"`, `Hook-based agent worktree kept at:`, `No WorktreeRemove hook configured; falling back`, `worktree_resolved_to_main_repo` |

<!-- /analysis-index -->

## UI surfaces and plugin panes

<!-- analysis-index: UI surfaces and plugin panes -->

| Doc                            | Scope                                                                                                                                                                                                                                     | Verified | Style    | Key landmarks                                                                                                     |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------- | ----------------------------------------------------------------------------------------------------------------- |
| `NATIVE_DIFF_SIDEBAR.md`       | Native `/diff` sidebar as fallback to the default-on `diff` mod: command gating, tree, drag-to-attach, focus, close marks; plugin-API correspondence                                                                                      | 2.1.317  | landmark | `tengu_quiet_dolphin`, `isOwnedByPlugin`, `Diff panel shown`, `useReleaseOnEdit`, `selected_lines_in_diff`        |
| `PLUGIN_PANES_AND_COMPOSER.md` | `Pane` render site, placement and chrome, and the `$` plugin API; composer `leadingPill` vs `$.prompt.paint` decorations; drag-select-to-attach and `$.ui.selection`; pane focus keys; `prompt.edit`, Vim and undo; rows under the prompt | 2.1.317  | landmark | `leadingPill`, `diff_selection_attach`, `panelFileView`, `unasked below`, `prompt.edit: hooked`, `plugin-status-` |

<!-- /analysis-index -->

## Sessions, context, and history

<!-- analysis-index: Sessions, context, and history -->

| Doc                              | Scope                                                                                                                                                                     | Verified | Style    | Key landmarks                                                                                                                                                      |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `BACKGROUND_SESSIONS_RESPAWN.md` | Background-session retire→wake flag/env preservation, respawn-state validation                                                                                            | 2.1.169  | landmark | `retireIfSettled`, `respawnFlags`, `stripped non-allowlisted`, `tengu_bg_retired`                                                                                  |
| `CD_COMMAND.md`                  | `/cd`: moves transcript + cwd, leaves memory behind                                                                                                                       | 2.1.198  | landmark | `Move this session to a new working directory`, `tengu_cd_command`, `relocated`                                                                                    |
| `CLEAR_COMPACT_FORK_CONTEXT.md`  | /compact and auto-compaction (threshold, prompt-too-long, idle, /autocompact), compaction prompt arms, /clear, /branch, /fork, /rewind                                    | 2.1.317  | landmark | `compact_boundary`, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, `Your task is to create a detailed summary`, `tengu_curried_trinket`, `You are now in the new branch`       |
| `COMMAND_HISTORY.md`             | `~/.claude/history.jsonl` input history: record format, what is recorded, pasted text, up-arrow and ctrl+r scoping, retention and purge                                   | 2.1.317  | landmark | `Skipping malformed history line`, `"paste-cache"`, `historySearch:cycleScope`, `CLAUDE_CODE_SKIP_PROMPT_HISTORY`                                                  |
| `CONTEXT_OPS_DIAGRAMS.md`        | Diagrams: how /compact, Summarize, /clear, /branch, /fork and /rewind change the JSONL vs the model view; what removes history                                            | 2.1.317  | landmark | `content: "Conversation compacted"`, `Old tool result content cleared`, `Create a branch of the current conversation`, `rewind persist-failure remote heal failed` |
| `KEYBOARD_INPUT_DECODING.md`     | stdin key decoding (tokenizer, CSI-u/modifyOtherKeys/legacy), Kitty/extended-keys negotiation and probe, keybinding matching, push-to-talk hold detection                 | 2.1.317  | landmark | `CLAUDE_CODE_BS_AS_CTRL_BACKSPACE`, `pendingByteEvents`, `CSI ? u not asked`, `Terminal capabilities:`, `awaitingVoiceSubmitDoubleTap`                             |
| `SESSION_MEMORY_AND_SUMMARY.md`  | Background summary compaction (removed by 2.1.138)                                                                                                                        | 2.1.76   | landmark | `tengu_session_memory`, `session-memory/summary.md`                                                                                                                |
| `SESSION_RESUME.md`              | Post-resume "resume vs summary" prompt and dismissal                                                                                                                      | 2.1.277  | landmark | `tengu_gleaming_fair`, `tengu_gleaming_fair_reuse`, `resumeReturnDismissed`                                                                                        |
| `SESSION_TRANSCRIPT.md`          | JSONL transcript format, record types, linkage model                                                                                                                      | 2.1.281  | landmark | `parentUuid`, `logicalParentUuid`, `<sessionId>.jsonl`, `"atis-latch": "last-wins"`, `tengu_context_announcement`                                                  |
| `SLEEP_PREVENTION.md`            | macOS `caffeinate` inhibitor: held only while the session is busy; background Bash and Monitors do not hold it                                                            | 2.1.280  | landmark | `Restarting sleep inhibitor`, `caffeinate`, `in_process_teammate`, `local_bash`                                                                                    |
| `VOICE_MODE.md`                  | Voice dictation: enablement gates, hold vs tap, tap-mode self-termination, auto-submit and double-tap send, STT stream and recovery, what an external process can observe | 2.1.317  | landmark | `[voice] Toggle silence timeout`, `voice_transcript_insert`, `speech_to_text/voice_stream`, `allow_voice_mode`, `awaitingVoiceSubmitDoubleTap`                     |

<!-- /analysis-index -->

## Memory

<!-- analysis-index: Memory -->

| Doc                | Scope                                                    | Verified | Style    | Key landmarks                                                                    |
| ------------------ | -------------------------------------------------------- | -------- | -------- | -------------------------------------------------------------------------------- |
| `AGENT_MEMORY.md`  | Per-subagent memory: `memory:` field, dirs, permissions  | 2.1.186  | landmark | `Persistent Agent Memory`, `tengu_agent_memory_loaded`                           |
| `AUTO_MEMORY.md`   | Per-project auto memory: dir resolution, load, `/memory` | 2.1.316  | landmark | `"MEMORY.md"`, `autoMemoryDirectory`, `Edit CLAUDE.md files and memory settings` |
| `MEMORY_SYSTEM.md` | Hub: shared memory machinery, gates, stores comparison   | 2.1.186  | landmark | `tengu_memdir_loaded`                                                            |
| `TEAM_MEMORY.md`   | Shared memory-service memory: mounts, sync, prompt shape | 2.1.186  | landmark | `CLAUDE_MEMORY_STORES`, `fetched from memory-service`                            |

<!-- /analysis-index -->

The durable memory family is auto / agent / team; start at `MEMORY_SYSTEM.md`. Session memory
(`summary.md`, in `SESSION_MEMORY_AND_SUMMARY.md`) is a separate, removed compaction experiment —
not part of this family despite the name.

## Config, settings, and frontmatter

<!-- analysis-index: Config, settings, and frontmatter -->

| Doc                              | Scope                                                                                                                                   | Verified | Style    | Key landmarks                                                                               |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------- | ------------------------------------------------------------------------------------------- |
| `CLAUDE_MD_EXTERNAL_INCLUDES.md` | External CLAUDE.md `@import` and symlinked `.claude/rules` approval dialog and flags                                                    | 2.1.317  | landmark | `hasClaudeMdExternalIncludesApproved`, `showExternalIncludesDialog`                         |
| `CLI_OPTIONS.md`                 | Undocumented CLI flags and auto-mode behavior                                                                                           | 2.1.76   | legacy   | `--permission-mode`, `isAutoModeCircuitBroken`                                              |
| `FEATURE_FLAGS.md`               | `tengu_*` flags: remote-eval fetch, disk cache, read order                                                                              | 2.1.316  | landmark | `getFeatureValueWithSource`, `cachedGrowthBookFeatures`, `/api/eval/`                       |
| `IS_DEMO.md`                     | Demo flag: startup gates, identity redaction, cmd swap                                                                                  | 2.1.220  | landmark | `IS_DEMO`, `projectOnboardingSeenCount`, `policy_update_modal`                              |
| `MAIN_THREAD_AGENT_AND_MODEL.md` | Main-thread agent selection and model precedence                                                                                        | 2.1.277  | landmark | `Overrides the 'agent' setting`, `agent_frontmatter`, `sdk-cli`                             |
| `MANAGED_SETTINGS_PARENT.md`     | `--managed-settings` parent tier: restrictive filter, precedence                                                                        | 2.1.309  | landmark | `parent managed settings`, `parentSettingsBehavior`                                         |
| `MARKDOWN_FRONTMATTER.md`        | Frontmatter parsing, schema, per-file-type validation                                                                                   | 2.1.316  | landmark | `tengu_frontmatter_shadow_unknown_key`, `does not recognize or apply`                       |
| `PROJECT_FILES_AND_STATE.md`     | Files a session reads by walking directories, and the key each piece of per-project state uses (start dir vs canonical root); worktrees | 2.1.317  | landmark | `getProjectDirsUpToHome: stat`, `getProjectPathForConfig`, `tengu_resume_worktree_fallback` |
| `SETTINGS.md`                    | Settings scopes/precedence, merge, local-settings location, writes, symlink refusal                                                     | 2.1.317  | landmark | `onLegacyLocalSettingsRead`, `Refusing to write through symlink`, `Invalid setting source:` |

<!-- /analysis-index -->

## API, networking, and MCP

<!-- analysis-index: API, networking, and MCP -->

| Doc                      | Scope                                                                                                                                    | Verified | Style    | Key landmarks                                                                                                                                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ANTHROPIC_API_USAGE.md` | API call sites and request-construction pipeline                                                                                         | 2.1.76   | landmark | `beta.messages.stream`, `CLAUDE_CODE_EXTRA_BODY`, `DISABLE_PROMPT_CACHING`                                                                                                          |
| `API_REFERENCE.md`       | What the bundled Anthropic SDK adds to an outgoing request                                                                               | 2.1.277  | landmark | `/v1/messages`, `calculateNonstreamingTimeout`, `is deprecated`                                                                                                                     |
| `MCP.md`                 | MCP integration: `.mcp.json` approval and trust, `claude mcp add` scopes, timeouts, backgrounding, tasks extension, session ID, channels | 2.1.317  | landmark | `enabledMcpjsonServers`, `by: "non_interactive"`, `MCP tool idle timeout`, `tengu_mcp_auto_background`, `io.modelcontextprotocol/tasks`, `CLAUDE_CODE_SESSION_ID`, `claude/channel` |
| `OAUTH_LOGIN.md`         | First-party OAuth login: authorize params, redirects, token exchange, refresh, setup-token                                               | 2.1.289  | landmark | `MANUAL_REDIRECT_URL`, `code_challenge_method`, `grant_type: "refresh_token"`, `setup-token`                                                                                        |

<!-- /analysis-index -->

## Observability

<!-- analysis-index: Observability -->

| Doc                   | Scope                                                                                                                                                                                             | Verified | Style    | Key landmarks                                                                                                                                                                                             |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `COST_ESTIMATION.md`  | Session cost estimate: baked-in rate cards, bootstrap-fetched costs, formula, unknown models, what feeds the total                                                                                | 2.1.295  | landmark | `pricing_tiers`, `additional_model_costs`, `alder_ford`, `modelPricing`, `tengu_unknown_model_cost`, `costs may be inaccurate due to usage of unknown models`, `ephemeral_1h_input_tokens`, `long_prompt` |
| `MONITORING_USAGE.md` | Where token, cost and plan-limit usage can be observed (statusLine, `/usage`, subagent `<usage>`, OTel, cached blob, usage endpoint); cap-hit records, grace, auto-continue, `cedar_ember` resets | 2.1.317  | landmark | `What's contributing to your usage?`, `claude_code.session.count`, `cachedUsageUtilization`, `api/oauth/usage`, `hook_event_name: "StopFailure"`, `cedar_ember`                                           |
| `NOTIFICATIONS.md`    | Notification triggers, channels, idle and dialog timers, terminal write path, hook `terminalSequence`                                                                                             | 2.1.316  | landmark | `idle_prompt`, `preferredNotifChannel`, `tengu_idle_return_action`, `CLAUDE_CODE_DISABLE_PERMISSION_PROMPT_NOTIFY_HOOKS`, `TerminalWriteProvider`                                                         |

<!-- /analysis-index -->

## Architecture and dependencies

<!-- analysis-index: Architecture and dependencies -->

| Doc                       | Scope                                                                                                                                                                                     | Verified | Style    | Key landmarks                                                                                                                            |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `DEPENDENCIES.md`         | Third-party libraries inlined or embedded, version anchors, Bun built-ins used in their place, and libraries not bundled                                                                  | 2.1.317  | landmark | `"ajv implementation error"`, `X-Stainless-Package-Version`, `reconcilerVersion: "`, `This runtime has no Bun.Image`                     |
| `ENTRYPOINTS.md`          | How `CLAUDE_CODE_ENTRYPOINT` is set and what it drives: client type, `# Surface` prompt section, request headers and User-Agent, bootstrap `client_data`, GrowthBook targeting, telemetry | 2.1.317  | landmark | `CLAUDE_CODE_ENTRYPOINT_ON_REQUESTS ignored`, `"sdk-typescript"`, `/api/claude_cli/bootstrap`, `x-anthropic-billing-header: cc_version=` |
| `FUNCTIONAL_BREAKDOWN.md` | Orientation map: where app concerns live, and which doc owns each                                                                                                                         | 2.1.277  | landmark | `CLAUDE_CONFIG_DIR`, `.config.json`, `triBool`                                                                                           |
| `GITHUB_REPO_PATHS.md`    | `githubRepoPaths` in ~/.claude.json: when it is written, teleport and deep-link readers, stale entries                                                                                    | 2.1.316  | landmark | `githubRepoPaths`, `Teleport to Repo`, `No local clone found for repo`                                                                   |

<!-- /analysis-index -->

## Methodology (not findings)

<!-- analysis-index: Methodology (not findings) -->

| Doc                        | Scope                                                 | Verified | Style       |
| -------------------------- | ----------------------------------------------------- | -------- | ----------- |
| `ANALYSIS_IMPROVEMENTS.md` | ast-grep structural search techniques                 | 2.1.76   | methodology |
| `GUIDELINES.md`            | How to write and update analysis docs (authoritative) | 2.1.154  | methodology |
| `VERSION_BISECTION.md`     | Bun-era distribution; bisecting a behavior change     | 2.1.168  | methodology |

<!-- /analysis-index -->

## Related material outside analysis/

- `schemas/` — JSON Schemas for Claude Code's own files (frontmatter, transcript) derived from the
  docs above; see `schemas/README.md`.
- `../patches/README.md` — the patch corpus index: the per-patch catalog (`PATCHES.md`) and the
  regeneration methodology (`METHODOLOGY.md`).
- `../../mcp/README.md` — the expert server that turns this repo into an `ask_claude_code_expert`
  tool.

## Maintaining this index

The tables are generated: never edit them by hand. Each row comes from its doc's YAML frontmatter
(`verified`, `section`, `style`, `scope`, `landmarks`; see `GUIDELINES.md`, "Version stamping and
the index"). After adding a doc or changing its frontmatter, run `bin/analysis-index.py` from the
repository root and commit this file with the doc. A new section needs its heading and a pair of
`analysis-index` markers here first. Keep scope and landmarks anchored on stable strings, never on
line numbers or minified names.
