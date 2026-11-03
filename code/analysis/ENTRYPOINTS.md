---
verified: 2.1.317
verified_on: 2026-11-03
section: Architecture and dependencies
style: landmark
scope: >-
  How `CLAUDE_CODE_ENTRYPOINT` is set and what it drives: client type, `# Surface` prompt section,
  request headers and User-Agent, bootstrap `client_data`, GrowthBook targeting, telemetry
landmarks:
  - CLAUDE_CODE_ENTRYPOINT_ON_REQUESTS ignored
  - '"sdk-typescript"'
  - /api/claude_cli/bootstrap
  - 'x-anthropic-billing-header: cc_version='
---
# Claude Code Entrypoints and Execution Surfaces

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)

## Overview

Claude Code is one JavaScript application, shipped as a bun-compiled native binary, that runs behind
many execution surfaces: a terminal, the VS Code extension, the Claude desktop app and its Cowork
workspace, claude.ai/code and the mobile app, Slack and Teams, GitHub Actions, and the Agent SDKs.
On the web, mobile, Slack and Teams surfaces the process runs in a sandbox provisioned for the
session, not on the user's computer; the app relays its messages.

The surface is named by the `CLAUDE_CODE_ENTRYPOINT` environment variable. From it the code derives
a display client type, a `# Surface` system-prompt section, the name requests go out under, and a
set of per-surface gates in authentication, telemetry, feature-flag targeting and UI.

## Entrypoint Detection

### Setting the entrypoint

Relocate: `rg -n 'claude-code-github-action'`; the hit that assigns the value to
`CLAUDE_CODE_ENTRYPOINT` is in the setter.

If `CLAUDE_CODE_ENTRYPOINT` is already set, a hosting environment (VS Code, Claude Desktop, remote
infrastructure, an SDK) has named the surface and the setter keeps it, with two rewrites:
`local_agent` becomes `local-agent`, and `cli` becomes `sdk-cli` when the session is
non-interactive. Otherwise it checks argv for `mcp serve` and sets `mcp`, then a truthy
`CLAUDE_CODE_ACTION` and sets `claude-code-github-action`, and otherwise sets `sdk-cli` when
non-interactive or `cli` when not.

"Non-interactive" means the launch path declares the session non-interactive, or argv holds `-p`,
`--print`, `--init-only` or a `--sdk-url` flag, or stdout is not a TTY. The setter runs at startup,
before the client type is resolved.

### Valid entrypoint values

Relocate: `rg -n '"claude-coworker-terminal": '`. Of the two object literals it hits, the valid set
is the one whose every value is true; the other maps each entrypoint to an opaque code for the
`x-claude-code-wiggly-dove` header (see Request identification).

    cli  mcp  bench
    sdk-cli  sdk-ts  sdk-py
    claude-vscode  claude-desktop  claude-desktop-3p  claude-coworker  claude-coworker-terminal
    claude-code-github-action  local-agent  local_agent
    remote  remote_baku  remote_cowork  remote_trigger  remote_cowork_trigger  remote_desktop
    remote_mobile  remote_projects
    claude_in_slack  claude-in-slack  claude-in-teams
    claude-security  ssh-remote

The validated accessor returns the value only when it is in this set, so an unknown value reads as
unset wherever the code goes through it: telemetry, GrowthBook attributes, the bootstrap request,
the `# Surface` section. Not every reader validates. The User-Agent, the attribution block, the
`anthropic-client-platform` header, the client-type resolver and several single-value checks read
the raw variable and pass an unknown value through or treat it as `cli`.

Tripwire: □ the set has 27 members □ the setter rewrites `local_agent` to `local-agent` □ the setter
rewrites a preset `cli` to `sdk-cli` when non-interactive.

### Request entrypoint name

Requests can go out under a name other than `CLAUDE_CODE_ENTRYPOINT`. When this name is set, the
User-Agent, the attribution block and the `# Surface` lookup in diskless sessions use it in place of
the entrypoint; the entrypoint itself, telemetry and the client type are unchanged. Three routes set
it, and the first to claim it wins:

- `CLAUDE_CODE_ENTRYPOINT_ON_REQUESTS`, read only when the entrypoint is `claude-desktop-3p`. The
  name must be 1 to 32 characters of `a-z`, `0-9`, `_` and `-`, start with a letter and not start
  with `sdk`; an entrypoint name, any name beginning with `remote`, and `local_projects` are
  reserved. Each rejection is logged with a message starting
  `CLAUDE_CODE_ENTRYPOINT_ON_REQUESTS ignored`. The variable is unset after it is read.
- A Remote Control child (`CLAUDE_CODE_ENVIRONMENT_KIND=bridge`) with
  `CLAUDE_CODE_BRIDGE_CHILD_PROJECTS_ENTRYPOINT`, or a bridge grant asking for the projects
  entrypoint, sends requests as `local_projects`. Event: `bridge_projects_entrypoint_name`.
- A Remote Control child whose entrypoint is `sdk-cli`, with
  `CLAUDE_CODE_BRIDGE_CHILD_CLI_ENTRYPOINT` and the `tengu_gentle_orchard` flag (default on), sends
  requests as `cli`. Event: `bridge_cli_entrypoint_name`.

Relocate: `rg -nF 'CLAUDE_CODE_ENTRYPOINT_ON_REQUESTS ignored'`; the two bridge routes sit beside
it.

### Client type resolution

After the entrypoint is set, a display client type is resolved and stored in global state. Relocate:
`rg -n '"sdk-typescript"'`. The hits are the client-type enum, the resolver (just before the
`main_client_type_determined` checkpoint), and a lookup table in a separate module.

The resolver checks, in order: `GITHUB_ACTIONS` truthy gives `github-action`; then the entrypoint
values `sdk-ts`, `sdk-py`, `sdk-cli`, `claude-vscode`, `local-agent` and `claude-desktop` map to
`sdk-typescript`, `sdk-python`, `sdk-cli`, `claude-vscode`, `local-agent` and `claude-desktop`; then
a remote credential, or an explicit `remote` entrypoint, gives `remote`; otherwise `cli`.

The remote credentials are `CLAUDE_CODE_SESSION_ACCESS_TOKEN`,
`CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR`, `CLAUDE_SESSION_INGRESS_TOKEN_FILE`, and a truthy
`CLAUDE_CODE_REMOTE` combined with an available session credential. Any one of them yields `remote`
without an explicit entrypoint.

The enum has 9 client types: `cli`, `remote`, `github-action`, `sdk-typescript`, `sdk-python`,
`sdk-cli`, `claude-vscode`, `local-agent`, `claude-desktop`. Every `remote_*` entrypoint, and every
entrypoint without a case of its own, collapses to `remote` or `cli`.

The client type decides a few things directly. `CLAUDE_CODE_QUESTION_PREVIEW_FORMAT` (`markdown` or
`html`) is honored everywhere, and without it question previews default to markdown except for SDK,
`claude-desktop`, `local-agent` and `remote` sessions and non-interactive VS Code.
`CLAUDE_CODE_QUESTION_EXTENDED` and `CLAUDE_CODE_QUESTION_OPTIONAL_DESCRIPTIONS` take effect only
for an SDK, `local-agent`, `claude-desktop` or `claude-desktop-3p` entrypoint or a `remote` client
type. The Agent-SDK-but-not-VS-Code predicate (below) also reads the client type.

## Known Entrypoints

| Entrypoint                  | Client type      | Surface key      | Set by                     |
| --------------------------- | ---------------- | ---------------- | -------------------------- |
| `cli`                       | `cli`            | `terminal`       | Auto, interactive          |
| `sdk-cli`                   | `sdk-cli`        | `sdk`            | Auto, non-interactive      |
| `sdk-ts`                    | `sdk-typescript` | `sdk`            | TypeScript Agent SDK       |
| `sdk-py`                    | `sdk-python`     | `sdk`            | Python Agent SDK           |
| `mcp`                       | `cli`            | `sdk`            | Auto, `mcp serve` in argv  |
| `claude-vscode`             | `claude-vscode`  | `vscode`         | VS Code extension          |
| `claude-desktop`            | `claude-desktop` | `desktop`        | Desktop app                |
| `claude-desktop-3p`         | `cli`            | `desktop`        | Desktop app, 3P provider   |
| `local-agent`               | `local-agent`    | `cowork`         | Desktop app, Cowork        |
| `local_agent`               | `local-agent`    | `cowork`         | Rewritten to `local-agent` |
| `remote`                    | `remote`         | `web`            | claude.ai/code             |
| `remote_baku`               | `remote`         | `web`            | Hosted session             |
| `remote_projects`           | `remote`         | `web`            | Hosted session             |
| `remote_desktop`            | `remote`         | `desktop`        | Cloud, driven from Desktop |
| `remote_mobile`             | `remote`         | `mobile`         | Cloud, driven from mobile  |
| `remote_cowork`             | `remote`         | `cowork`         | Cloud Cowork               |
| `remote_trigger`            | `remote`         | `scheduled`      | Scheduled or triggered run |
| `remote_cowork_trigger`     | `remote`         | `scheduled`      | Scheduled Cowork run       |
| `claude_in_slack`           | `cli`/`remote`   | `slack`          | Slack relay                |
| `claude-in-slack`           | `cli`/`remote`   | `slack`          | Slack relay                |
| `claude-in-teams`           | `cli`/`remote`   | `slack`          | Teams relay                |
| `claude-code-github-action` | `github-action`  | `github_action`  | Auto, `CLAUDE_CODE_ACTION` |
| `claude-coworker`           | `cli`            | `terminal`/`sdk` | Coworker host              |
| `claude-coworker-terminal`  | `cli`            | `terminal`/`sdk` | Coworker host              |
| `claude-security`           | `cli`            | `terminal`/`sdk` | Hosting environment        |
| `ssh-remote`                | `cli`            | `terminal`/`sdk` | Hosting environment        |
| `bench`                     | `cli`            | `terminal`/`sdk` | Hosting environment        |

Client type `remote` for a `remote_*` or Slack/Teams entrypoint assumes the hosted session carries a
remote credential; without one, only the literal `remote` entrypoint yields `remote`.
`github-action` comes from `GITHUB_ACTIONS`, which a GitHub Actions runner sets, and it is checked
before every entrypoint comparison. `terminal`/`sdk` means `sdk` when non-interactive, else
`terminal`.

## Entrypoint Groups

The module holding the valid set also defines the groups the rest of the code tests. Relocate them
from the valid set; they are its neighbors.

- Remote workspace: every `remote*` value plus `claude_in_slack`, `claude-in-slack` and
  `claude-in-teams`. `# Surface` tells these sessions they run in a remote sandbox.
- Triggered: `remote_trigger`, `remote_cowork_trigger`. Scheduled-run behavior; surface `scheduled`.
- Cloud Cowork: `remote_cowork`, `remote_cowork_trigger`. Cowork behavior in cloud sessions.
- Desktop-hosted: `claude-desktop`, `claude-desktop-3p`, `local-agent`. Desktop-host behavior, such
  as naming `--model` rather than `/model` in hints.
- Slack and Teams: `claude_in_slack`, `claude-in-slack`, `claude-in-teams`. Relay behavior.
- SDK: `sdk-ts`, `sdk-py`, `sdk-cli`. SDK-only behavior.
- Settings hint off: the three Slack/Teams values, both triggered values, `remote_cowork` and
  `remote_baku`. Messages omit hints to raise a setting; the web-search limit message, for one,
  otherwise says to raise `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION`.
  `CLAUDE_CODE_HIDE_SETTINGS_HINT` truthy turns the hint off on every surface.
- Attended: `claude-vscode`, `claude-desktop`, `claude-desktop-3p`, `local-agent`, `local_agent`,
  `remote`, `remote_desktop`, `remote_mobile`, `remote_projects`, `remote_cowork`, `ssh-remote`, the
  three Slack/Teams values, `claude-coworker` and `claude-coworker-terminal`. A non-interactive
  session from one of these counts as attended unless it is a child session or
  `CLAUDE_CODE_SESSION_KIND` is `bg`, `daemon` or `daemon-worker`.
- Followed in app: `remote`, `remote_desktop`, `remote_mobile`, `remote_projects`, `remote_trigger`,
  with a truthy `CLAUDE_CODE_REMOTE`. `# Session-specific guidance` gains a bullet starting
  `The user follows this cloud session in the Claude app`, which steers files meant for the user
  into directories the app can open.

## Relationship to the System Prompt

### The `# Surface` section

On the lean-rewrite prompt path (see `PROMPTS.md`), the system prompt carries a `# Surface` section
keyed by the entrypoint. Relocate: `rg -nF 'You are running as Claude Code on the web'`; the
per-surface texts are its neighbors, followed by the entrypoint-to-key switch.

The key comes from the validated entrypoint, per the Surface key column above. In a diskless session
the lookup uses the CCR-derived surface, then the request entrypoint name, then the raw variable,
validated. Every key has a one-line text opening `You are running ...`: `terminal`, `vscode`,
`desktop`, `web`, `mobile`, `slack`, `scheduled`, `github_action`, `cowork`, `sdk`. A `coworker` key
exists with an empty text, and no entrypoint maps to it.

After the surface line comes a workspace line. `github_action` and `coworker` get none. Otherwise
the session is remote when it is diskless, its entrypoint is in the remote-workspace group, or the
entrypoint starts with `remote`. A remote session gets
`This session is running in a remote sandbox provisioned for it`; any other gets
`This session is running on a machine the user controls`.

Tripwire: □ 11 surface keys □ `coworker` text empty □ `claude-desktop-3p` and `remote_desktop` both
map to `desktop`.

### The identity line

The first system-prompt line is chosen from three strings by interactivity, not by entrypoint:
`You are Claude Code, Anthropic's official CLI for Claude.` for interactive sessions and always on
Vertex; for non-interactive sessions,
`You are Claude Code, Anthropic's official CLI for Claude, running within the Claude Agent SDK.`
when an append-system-prompt is given, else
`You are a Claude agent, built on Anthropic's Claude Agent SDK.` Relocate:
`rg -nF 'running within the Claude Agent SDK'`.

### Server-side targeting

Two server channels can vary the prompt by surface. The bootstrap request sends the entrypoint as a
query parameter, and its `client_data` feeds prompt and model-capability switches such as
`temporal_hare` and `breezy_horizon` (see Bootstrap). GrowthBook receives the entrypoint as a
targeting attribute. The client sends no `system_prompt_variant` and compares no variant name;
surface targeting happens on the server through these two channels and the local `# Surface` text.

## Request Identification

### Anthropic API User-Agent

Relocate: `rg -n 'claude-cli/'`; the builder is the hit that is a `return` template.

    claude-cli/<version> (external, <name>[, agent-sdk/<v>][, client-app/<app>][, workload/<w>])

`<name>` is the request entrypoint name, unless the caller asks for its own entrypoint, then the raw
`CLAUDE_CODE_ENTRYPOINT`, then `cli`. `agent-sdk/` comes from `CLAUDE_AGENT_SDK_VERSION`,
`client-app/` from `CLAUDE_AGENT_SDK_CLIENT_APP`, and `workload/` from the current workload context.

Examples: `claude-cli/<version> (external, cli)`, `claude-cli/<version> (external, claude-vscode)`,
`claude-cli/<version> (external, sdk-ts, agent-sdk/<v>)`.

MCP HTTP requests use a different form, built from the same parts:

    claude-code/<version> (<name>[, agent-sdk/<v>][, client-app/<app>])

where `<name>` is the request entrypoint name, else the raw `CLAUDE_CODE_ENTRYPOINT`, and the
parenthesis is omitted when all parts are empty. The bootstrap, sessions and Remote Control APIs and
GrowthBook send a bare `claude-code/<version>`.

### Attribution block

Relocate: `rg -nF 'x-anthropic-billing-header: cc_version='`. Despite the header-style text, this is
a text block placed first in the system prompt, not an HTTP header:

    x-anthropic-billing-header: cc_version=<version>.<fingerprint>; cc_entrypoint=<name>; ...

`<name>` is the request entrypoint name, else the raw `CLAUDE_CODE_ENTRYPOINT`, else `unknown`.
Optional fields follow, most of them first-party only: `cch=00000`, `cc_workload`, `cc_is_subagent`,
`cc_prev_req`, `cc_prompt_id`, `cc_turn_origin`, prompt and turn indexes, `cc_gateway`, `cc_project`
and `cc_project_src`, and `cc_prev_msg`. The block is on by default;
`CLAUDE_CODE_ATTRIBUTION_HEADER` set falsy (`0`, `false`, `no`, `off`) removes it, except where a
caller forces it.

### `anthropic-client-platform`

Requests to the sessions and Remote Control APIs carry `anthropic-client-platform`, mapped from the
raw entrypoint. Relocate: `rg -nF '"claude_code_github_action"'`.

| Entrypoint                  | Value                       |
| --------------------------- | --------------------------- |
| `claude-vscode`             | `claude_code_vscode`        |
| `remote`                    | `claude_code_remote`        |
| `remote_baku`               | `claude_code_remote`        |
| `remote_cowork`             | `claude_code_remote`        |
| `remote_desktop`            | `claude_code_remote`        |
| `remote_mobile`             | `claude_code_remote`        |
| `remote_projects`           | `claude_code_remote`        |
| `claude-in-teams`           | `claude_code_remote`        |
| `sdk-cli`                   | `claude_code_sdk`           |
| `sdk-ts`                    | `claude_code_sdk`           |
| `sdk-py`                    | `claude_code_sdk`           |
| `mcp`                       | `claude_code_mcp`           |
| `claude-code-github-action` | `claude_code_github_action` |
| `local-agent`               | `claude_code_local_agent`   |
| `claude_in_slack`           | `claude_in_slack`           |
| `claude-in-slack`           | `claude-in-slack`           |
| anything else               | `claude_code_cli`           |

### `x-claude-code-wiggly-dove`

When `tengu_wiggly_dove` is on, API requests carry an `x-claude-code-wiggly-dove` metadata header in
which the entrypoint is one member, encoded as an opaque two-letter code from a per-entrypoint table
(an unknown entrypoint gets a fallback code). Relocate: `rg -nF 'x-claude-code-wiggly-dove'`.

## Bootstrap and `client_data`

Relocate: `rg -nF '/api/claude_cli/bootstrap'`. The bootstrap fetch is a GET to
`/api/claude_cli/bootstrap` with the query parameters `entrypoint` and `model` and the User-Agent
`claude-code/<version>`. Its response carries `client_data` along with model options, costs, access
and the org default model.

The `entrypoint` parameter is the validated entrypoint. In a Cowork cloud session whose host fetches
client data, it is the CCR-derived surface instead.

The fetch is skipped when nonessential traffic is disabled, for a third-party provider, under
`ANTHROPIC_UNIX_SOCKET`, and when no usable credential exists. It authenticates with workload
identity, an OAuth access token or an API key; a gateway provider queries `/v1/models` instead, and
only with `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY`.

Because the entrypoint is an explicit parameter, the server can return different `client_data` per
surface. `client_data` keys drive prompt variants (`temporal_hare`, `breezy_horizon`; see
`PROMPTS.md`), model capabilities (`tengu_model_capability_from_client_data`), reminders and the
footer indicator.

## GrowthBook Feature Flag Targeting

### Attributes

Relocate: `rg -n 'cacheKeyAttributes'` for the client; the attribute builder sits beside the
`slackTagConnected` and `ccrDerivedSurface` fields.

| Attribute                 | Value                                               |
| ------------------------- | --------------------------------------------------- |
| `id`, `deviceID`          | Device id                                           |
| `sessionId`               | Session id                                          |
| `platform`                | Platform                                            |
| `apiBaseUrlHost`          | Host of a non-default `ANTHROPIC_BASE_URL`          |
| `organizationUUID`        | When authenticated through an org                   |
| `accountUUID`             | When authenticated                                  |
| `userType`                | `external`                                          |
| `subscriptionType`        | Pro, Max, Team, Enterprise and so on                |
| `rateLimitTier`           | When available                                      |
| `organizationRole`        | When the OAuth account matches                      |
| `subscriptionCreatedAt`   | When the OAuth account matches                      |
| `firstTokenTime`, `email` | When available                                      |
| `appVersion`              | Bundle version                                      |
| `githubActionsMetadata`   | When running in GitHub Actions                      |
| `entrypoint`              | Validated entrypoint                                |
| `sessionOrigin`           | `CLAUDE_CODE_SESSION_ORIGIN`, e.g. `claude_ai_chat` |
| `ccrDerivedSurface`       | CCR-derived surface, for Cowork sessions in CCR     |
| `atisPin`                 | When pinned                                         |
| `hasUsedRemoteSession`    | When true                                           |
| `hasRemoteEnvironment`    | When true                                           |
| `slackTagConnected`       | When true                                           |

Flags can target the surface directly through `entrypoint`, `sessionOrigin` and `ccrDerivedSurface`.
The client type is not an attribute.

### Cache key attributes

Flag evaluations are cached by `id`, `organizationUUID`, `slackTagConnected`, `atisPin`,
`ccrDerivedSurface` and `sdkCachePartition`. `entrypoint` is not a cache key.

## Authentication Context

### The claude.ai-authentication predicate

A predicate answers "is this session authenticated through claude.ai OAuth rather than an API key".
It returns false unless OAuth is in use at all, then checks that the stored token's scopes include
`user:inference`, the claude.ai OAuth scope.

OAuth counts as not in use for a third-party provider (Bedrock, Vertex, Foundry, a gateway), under
workload identity, in bare mode with an `apiKeyHelper`, and when `ANTHROPIC_AUTH_TOKEN`, an API key,
an `apiKeyHelper` or `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR` supplies the credential. Under
`ANTHROPIC_UNIX_SOCKET` it counts as in use only with `CLAUDE_CODE_OAUTH_TOKEN`.

The predicate is reported in telemetry as `isClaudeAiAuth`.

### Auth token source

Relocate: `rg -nF 'source: "claude.ai"'`. The token source resolves in order:

1. Bare mode (`--bare` or `CLAUDE_CODE_SIMPLE`): `apiKeyHelper` or `none`, nothing else.
2. `ANTHROPIC_AUTH_TOKEN`.
3. `CLAUDE_CODE_OAUTH_TOKEN`.
4. A token on a file descriptor: `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`, or
   `CCR_OAUTH_TOKEN_FILE` when the CCR host injected it.
5. `apiKeyHelper`.
6. `profile`, under workload identity.
7. `claude.ai`, a stored OAuth token whose scopes include `user:inference`.

## Remote (Web) Surface Details

| Variable                                     | Purpose                                         |
| -------------------------------------------- | ----------------------------------------------- |
| `CLAUDE_CODE_REMOTE`                         | Boolean flag, enables remote-specific behaviors |
| `CLAUDE_CODE_REMOTE_SESSION_ID`              | Session identifier for the cloud session        |
| `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE`        | Type of remote environment, e.g. `self_hosted`  |
| `CLAUDE_CODE_ENVIRONMENT_KIND`               | Kind: `byoc`, or `bridge` for Remote Control    |
| `CLAUDE_CODE_REMOTE_MEMORY_DIR`              | Overrides the auto-memory base directory        |
| `CLAUDE_CODE_SESSION_ACCESS_TOKEN`           | Session auth token for remote sessions          |
| `CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR` | File descriptor for WebSocket auth              |
| `CLAUDE_SESSION_INGRESS_TOKEN_FILE`          | Session-ingress token file                      |
| `CLAUDE_CODE_CONTAINER_ID`                   | Container ID in remote infrastructure           |

`CLAUDE_CODE_SESSION_ACCESS_TOKEN`, `CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR` and
`CLAUDE_SESSION_INGRESS_TOKEN_FILE` each make the client type `remote` (see Client type resolution).
The terminal's `/teleport` flow refuses without a claude.ai account and shows
`Teleport requires a Claude.ai account.`

## Surface-Specific Behavior in the Codebase

### Agent SDK and VS Code

A predicate for "Agent SDK, but not VS Code" is true when the session is non-interactive and the
client type is not `claude-vscode`. It gates two things:

- Fast mode in a non-interactive non-VS Code session needs an opt-in, from the session or from
  `fastMode` in flag settings. Without one the reason is `sdk_opt_in_required`, shown as
  `Fast mode is not available in the Agent SDK`.
- `ANTHROPIC_API_KEY` is used directly as the API key in that context.

### Claude Desktop

`claude-desktop` (Anthropic sign-in), `claude-desktop-3p` (third-party provider setup) and
`local-agent` (Cowork) are the entrypoints the desktop app sets. For `claude-desktop` and
`local-agent`, `CLAUDE_CODE_DESKTOP_APP_VERSION` is read and reported in telemetry as
`desktopAppVersion`. Only `claude-desktop-3p` honors `CLAUDE_CODE_ENTRYPOINT_ON_REQUESTS`.

Separately, `claude mcp add-from-claude-desktop` imports MCP servers from the Claude Desktop config;
its description says `Import MCP servers from Claude Desktop (Mac and WSL only)`.

### Pull request footer

With `tengu_pr_footer_surface_suffix` on, the PR footer `Generated with [Claude Code](...)` gains
` via <surface>`. The surface name comes from the validated entrypoint: `Claude Desktop` (both
desktop entrypoints and `remote_desktop`), `Mobile`, `Cowork` (`local-agent`, `remote_cowork`),
`Claude Tag in Slack`, `Claude Tag in Teams`, `GitHub Actions`; other surfaces get no suffix.
Relocate: `rg -nF 'tengu_pr_footer_surface_suffix'`.

## Telemetry Context

Relocate: `rg -nF 'isLocalAgentMode'`. The telemetry context reports, among other fields:

| Field                                  | Source                                                 |
| -------------------------------------- | ------------------------------------------------------ |
| `platform`, `platformRaw`, `arch`      | Platform, `CLAUDE_CODE_HOST_PLATFORM`, architecture    |
| `nodeVersion`, `isRunningWithBun`      | Runtime                                                |
| `terminal`, `shell`                    | Terminal and shell detection                           |
| `packageManagers`, `runtimes`          | Detected tools                                         |
| `isCi`                                 | CI detection                                           |
| `isClaubbit`, `isConductor`            | Host-environment detection                             |
| `isClaudeCodeRemote`                   | `CLAUDE_CODE_REMOTE`                                   |
| `isLocalAgentMode`                     | Raw entrypoint equal to `local-agent`                  |
| `remoteEnvironmentType`                | `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE`                  |
| `claudeCodeContainerId`                | `CLAUDE_CODE_CONTAINER_ID`                             |
| `claudeCodeRemoteSessionId`            | `CLAUDE_CODE_REMOTE_SESSION_ID`                        |
| `tags`                                 | `CLAUDE_CODE_TAGS`, comma-separated                    |
| `isGithubAction`, `isClaudeCodeAction` | `GITHUB_ACTIONS`, `CLAUDE_CODE_ACTION`                 |
| `isClaudeAiAuth`                       | The claude.ai-authentication predicate                 |
| `version`, `buildTime`                 | Bundle version and build time                          |
| `deploymentEnvironment`                | Deployment environment                                 |
| `entrypoint`                           | Validated entrypoint, or `other` when set but unknown  |
| `clientType`                           | Resolved client type                                   |
| `isInteractive`                        | Interactivity                                          |
| `agentSdkVersion`                      | `CLAUDE_AGENT_SDK_VERSION`                             |
| `desktopAppVersion`                    | `CLAUDE_CODE_DESKTOP_APP_VERSION`, desktop entrypoints |
| `remoteControlLane`, `projectsSession` | Remote Control lane, projects session                  |

`entrypoint` is omitted when `CLAUDE_CODE_ENTRYPOINT` is unset. Telemetry thus records both the
surface (entrypoint, client type) and the auth type (`isClaudeAiAuth`).
