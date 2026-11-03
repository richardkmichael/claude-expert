---
verified: 2.1.169
section: Sessions, context, and history
style: landmark
scope: Background-session retire→wake flag/env preservation, respawn-state validation
landmarks:
  - retireIfSettled
  - respawnFlags
  - stripped non-allowlisted
  - tengu_bg_retired
---
# Background sessions: retire → wake flag/env preservation and respawn-state validation

This documents what "background sessions" are, the retire → wake lifecycle, and the allowlists that
decide which CLI flags and provider env vars survive a respawn. The 2.1.169 changelog line "Background
sessions now preserve `--ide`, `--chrome`, `--bare`, `--remote-control`, and other flags across
retire→wake, and respawn state validation was hardened" maps directly onto the four allowlist sets
and three validators described below.

## What "background sessions" means

A background session is a Claude Code session run as a daemon-managed worker process rather than in
your terminal. They are the jobs behind agent view. The in-bundle definition is explicit (grep
`The background daemon manages`):

> The background daemon manages `& <prompt>` jobs and `claude agents`. If the issue involves
> background sessions, look here.

Entry points (all gated by one feature switch):

- `claude agents` — agent view.
- `claude --bg "<prompt>"` / `claude --background` — start a backgrounded session (grep `Fj4 =
  ["--bg", "--background"]`).
- `& <prompt>` — background syntax from inside a session.
- `/background` (alias `/bg`) — background the current session.

All of the above, plus the on-demand daemon, are disabled together by `CLAUDE_CODE_DISABLE_AGENT_VIEW=1`
or `disableAgentView: true` (grep `Disable agent view`).

Each worker is a "short"-keyed handle held by the daemon. Per-job state is persisted to
`<jobsDir>/<short>/state.json`, where `jobsDir` is `join(<dataDir>, "jobs")` (grep `return YM.join(
q8(), "jobs")` and the literal `state.json`). A live-worker roster file sits alongside. The daemon
self-describes its on-disk state in the bug-report bundle (grep `roster contains user prompts and env
vars` and `<short>/state.json` ... `per-job state`).

## The retire → wake lifecycle

The terms differ from the official docs, which say "stops its process" / "starts a fresh process".
The source uses:

- Retire — tear down a settled worker's process to reclaim memory while keeping its `state.json` on
  disk. Implemented by `retireIfSettled` (grep `async retireIfSettled(`). A worker is eligible only
  when not transitioning, not attached, not pinned, past its idle/grace windows, and with no in-flight
  work; it then transitions to `{ kind: "retiring" }` and emits `tengu_bg_retired`. Retirement is
  driven by an idle sweep and, ahead of schedule, by memory pressure (grep `bg: low memory` and
  `tengu_bg_dispatch_low_mem`; pinned workers are shed last, grep `tengu_bg_retire_pinned_low_mem`).
- Wake / respawn — relaunch a retired (or stale, or crashed) worker from its persisted state. On
  daemon startup, surviving workers are re-adopted; ones whose process is gone are respawned (grep
  `bg adopt: adopted=` and `tengu_bg_adopt`). A stale idle worker is respawned in place (grep
  `respawnIfIdleStale` and `tengu_bg_respawn_stale`). Waking reconstructs the child process argv from
  the persisted `respawnFlags` and `providerEnv`.

The changelog phrase "across retire→wake" is exactly this: the flags you launched with must be
re-applied when the daemon respawns the worker, otherwise the woken process loses `--ide`, `--chrome`,
etc.

## What is preserved: four allowlists

Relocate via the literal flag lists (grep `"--remote-control-session-name-prefix"` to land in the
middle of the set definitions, or the warn strings `stripped non-allowlisted respawnFlags` /
`stripped non-allowlisted providerEnv`). Four sets, by role:

| Set role                | Membership (what it controls)                                                                 |
| ----------------------- | --------------------------------------------------------------------------------------------- |
| Value-bearing flags     | flags that take an argument and are preserved with their value                                |
| Multi-value flags       | subset of the above allowed to repeat / take several values (exempt from dedup)               |
| Boolean flags           | no-argument flags preserved as bare switches                                                   |
| Provider env allowlist  | env var names allowed to round-trip through `providerEnv`                                      |

Boolean set (the changelog's named flags live here): `--ide`, `--chrome`, `--no-chrome`, `--bare`,
`--remote-control`, `--rc`, plus `--dangerously-skip-permissions`,
`--allow-dangerously-skip-permissions`, `--strict-mcp-config`,
`--dangerously-allow-browser-network-access`, `--disable-slash-commands`, `--verbose`,
`--reply-on-resume`, `--mcp-debug`, `--brief`.

Value-bearing set ("and other flags"): `--exec`, `--model`/`-m`, `--permission-mode`,
`--agent`/`--agents`, `--routine`, `--effort`, `--add-dir`, `--mcp-config`, `--settings`,
`--setting-sources`, `--system-prompt[-file]`, `--append-system-prompt[-file]`, `--fallback-model`,
`--advisor`, `--channels`, `--permission-prompt-tool`, `--allowed-tools`/`--allowedTools`,
`--disallowed-tools`/`--disallowedTools`, `--tools`, `--session-id`, `--debug-file`, `-n`/`--name`,
`--autocompact`, `--betas`, `--file`, `--max-budget-usd`, `--max-thinking-tokens`, `--max-turns`,
`--task-budget`, `--plan-mode-instructions`, `--plugin-dir`, `--plugin-url`, `--resume-session-at`,
`--rewind-files`, `--thinking`, `--thinking-display`, `--remote-control-session-name-prefix`.

Multi-value subset (exempt from last-wins dedup, may appear more than once): `--allowed-tools`,
`--allowedTools`, `--disallowed-tools`, `--disallowedTools`, `--tools`, `--mcp-config`, `--betas`,
`--add-dir`, `--file`, `--channels`.

Provider env allowlist: `CLAUDE_CONFIG_DIR`, `CLAUDE_INTERNAL_FC_OVERRIDES`, `ANTHROPIC_MODEL`,
`AWS_REGION`, `AWS_DEFAULT_REGION`, `AWS_PROFILE`, `GOOGLE_APPLICATION_CREDENTIALS`,
`GOOGLE_CLOUD_PROJECT`, `GCLOUD_PROJECT`, `CLAUDE_SECURESTORAGE_CONFIG_DIR`.

## "Respawn state validation was hardened": three validators

Persisted job state is no longer trusted verbatim. The `state.json` zod schema runs three transforms
that filter or drop anything off-allowlist before the daemon respawns from it (grep the schema fields
`respawnFlags`, `providerEnv`, then the validator warn strings). The same `respawnFlags` filter is
re-applied at dispatch and at settle time, so a stale or hand-edited state file cannot smuggle flags
back in.

- Respawn-flags filter+dedup (the `respawnFlags` transform). Walks persisted tokens and keeps only
  allowlisted flags: an unknown flag, a bare positional argument, or a value attached to a boolean
  flag (e.g. `--bare=foo` keeps `--bare`, drops `=foo`) is rejected. Surviving value flags are then
  deduplicated last-wins, except the multi-value subset which may repeat. Dropped tokens are logged
  (grep `stripped non-allowlisted respawnFlags token(s) from persisted job state`).
- Provider-env filter (the `providerEnv` transform). Drops any key not in the provider env allowlist;
  returns `undefined` if nothing survives (grep `stripped non-allowlisted providerEnv key(s) from
  persisted job state`).
- Generic field validator (grep `dropped malformed ${...} from persisted job state`). Wraps a
  per-field predicate; on failure it warns and drops the field to `undefined`. Applied to
  `linkScanPath` (must be absolute, end `.jsonl`, with a valid session-id basename) and
  `resumeSessionId` (must match the session-id pattern).

A `state.json` that fails whole-schema validation is skipped at load with a logged reason (grep
`state.json schema validation failed`).

## Telemetry landmarks

Background-session events are `tengu_bg_*` and daemon events `daemon_bg_*`. Lifecycle-relevant ones:
`tengu_bg_retired`, `tengu_bg_respawn_stale`, `tengu_bg_respawn`, `tengu_bg_respawn_exhausted`,
`tengu_bg_adopt`, `tengu_bg_adopt_upgrade_respawn`, `tengu_bg_dispatch_low_mem`,
`tengu_bg_retire_pinned_low_mem`, `daemon_bg_session_create`. Grep `tengu_bg_` for the full list.

## Drift from the official docs

Official coverage lives at `agent-view.md` and `remote-control.md` (checked via the
`claude-code-docs` MCP). Where they diverge from the source:

- Flag-persistence list is incomplete. The docs name a persisting subset — `--mcp-config`,
  `--strict-mcp-config`, `--settings`, `--add-dir`, `--plugin-dir`, `--fallback-model`,
  `--allow-dangerously-skip-permissions`, plus mid-session model / permission-mode / effort. The
  source preserves a much larger allowlist (above). `--ide`, `--chrome`, `--bare`, `--remote-control`
  / `--rc`, `--agent`, and CLI-launch `--model` are preserved in source but absent from the docs;
  the 2.1.169 changelog line is the first acknowledgement of the first four.
- Terminology. Docs say a settled session's process is "stopped" and later "started fresh"; the
  source calls these retire and wake/respawn. "Respawn" surfaces in the docs only as the
  `claude respawn <id>` command name.
- Validation is undocumented. The allowlist filtering and malformed-field dropping of persisted
  state have no public counterpart.
- The `& <prompt>` background syntax is in the source's own help text but not in the docs.
- Remote control + background sessions. `remote-control.md` documents the feature in full but says
  nothing about how `--remote-control` / `--rc` behaves when a background session is retired and
  respawned. The source answer: it is a preserved boolean flag, so it is re-applied on wake.
