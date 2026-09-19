# Claude Code Entrypoints and Execution Surfaces

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)
Verified against: cli.prettier.js 2.1.76 (2026-06-06); entrypoint set, client-type resolution and
prompt-variant routing re-verified against 2.1.277 (2026-09-19).

## Overview

Claude Code (`cli.prettier.js`) is a Node.js application that runs across multiple execution
surfaces. It is never executed directly in a web browser -- even for web-based surfaces like
claude.ai/code, the Node.js process runs server-side with the browser providing a terminal UI over
WebSocket.

The execution surface is identified by the `CLAUDE_CODE_ENTRYPOINT` environment variable, which
influences behavior in authentication, telemetry, feature availability, and potentially system
prompt selection.

## Entrypoint Detection

### Setting the entrypoint

Relocate: `rg -n 'claude-code-github-action'`. The function that assigns
`process.env.CLAUDE_CODE_ENTRYPOINT` is the setter.

It returns immediately if `CLAUDE_CODE_ENTRYPOINT` is already set, so a hosting environment
(VSCode, Claude Desktop, remote infrastructure) always wins over the CLI's own detection. Failing
that it checks argv for `mcp serve` and sets `mcp`, then checks `CLAUDE_CODE_ACTION` and sets
`claude-code-github-action`, and otherwise sets `sdk-cli` when running non-interactively or `cli`
when not.

"Non-interactive" here means any of `--print`, `--init-only`, `--sdk-url`, or stdout not being a
TTY.

### Valid entrypoint values

At 2.1.277 the entrypoint is validated against a fixed set, and a value outside it is treated as
unset rather than passed through. Relocate by grepping `remote_cowork_trigger`, which appears
nowhere else.

    cli  mcp  bench
    sdk-cli  sdk-ts  sdk-py
    claude-vscode  claude-desktop  claude-desktop-3p  claude-coworker  claude-coworker-terminal
    claude-code-github-action  local-agent  local_agent
    remote  remote_baku  remote_cowork  remote_trigger  remote_cowork_trigger  remote_desktop
    remote_mobile
    claude_in_slack  claude-in-slack  claude-in-teams
    claude-security  ssh-remote

Tripwire: the set held 9 recognized values at 2.1.76 and 27 at 2.1.277, and unknown values were
accepted then and are rejected now. Re-read the set rather than trusting this list.

### Client type resolution

After the entrypoint is set, a display-friendly `clientType` is resolved and stored in global state.
Relocate by grepping `sdk-typescript`; the resolver and the enum of valid client types are separate
hits.

The resolver checks in order: `GITHUB_ACTIONS` truthy gives `github-action`; then the entrypoint
values `sdk-ts`, `sdk-py`, `sdk-cli`, `claude-vscode`, `local-agent` and `claude-desktop` map to
their own client types; then a remote credential of any kind, or an explicit `remote` entrypoint,
gives `remote`; otherwise `cli`.

The remote credentials are `CLAUDE_CODE_SESSION_ACCESS_TOKEN`,
`CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR`, `CLAUDE_SESSION_INGRESS_TOKEN_FILE`, and a truthy
`CLAUDE_CODE_REMOTE` combined with an available session credential. Any one of them yields `remote`
without an explicit entrypoint value.

Note that the client-type set is narrower than the entrypoint set: the many `remote_*` entrypoints
all collapse to the single `remote` client type.

## Known Entrypoints

| Entrypoint                                                    | Client type      | Surface                     | Set by                                   |
| ------------------------------------------------------------- | ---------------- | --------------------------- | ---------------------------------------- |
| `cli`                                                         | `cli`            | Standalone terminal         | Auto-detected, interactive TTY           |
| `sdk-cli`                                                     | `sdk-cli`        | Agent SDK via CLI           | Auto-detected, non-interactive           |
| `sdk-ts`                                                      | `sdk-typescript` | TypeScript Agent SDK        | TypeScript SDK package                   |
| `sdk-py`                                                      | `sdk-python`     | Python Agent SDK            | Python SDK wrapper                       |
| `claude-vscode`                                               | `claude-vscode`  | VSCode extension            | VSCode extension host                    |
| `claude-desktop`                                              | `claude-desktop` | Desktop app                 | Desktop app host                         |
| `remote` and `remote_*`                                       | `remote`         | Web and hosted sessions     | Remote infrastructure                    |
| `local-agent`, `local_agent`                                  | `local-agent`    | Local agent mode            | Hosting environment                      |
| `mcp`                                                         | `cli`            | MCP server mode             | Auto-detected from `mcp serve` in argv   |
| `claude-code-github-action`                                   | `github-action`  | GitHub Actions              | Auto-detected from `CLAUDE_CODE_ACTION`  |
| `claude_in_slack`, `claude-in-slack`, `claude-in-teams`       | `cli`            | Chat integrations           | Hosting environment                      |
| `claude-coworker`, `claude-coworker-terminal`                 | `cli`            | Coworker surfaces           | Hosting environment                      |
| `claude-security`, `ssh-remote`, `bench`, `claude-desktop-3p` | `cli`            | Other hosted surfaces       | Hosting environment                      |

An entrypoint with no client-type case of its own falls through to `cli` unless a remote credential
is present. `github-action` is the one client type derived from the environment rather than the
entrypoint: it is set when `GITHUB_ACTIONS` is truthy, which is checked before every entrypoint
comparison.

The `remote` client type is also reached by credential presence alone, without an explicit `remote`
entrypoint: see the resolution order above.

## Remote (Web) Surface Details

The `remote` surface is claude.ai/code -- Claude Code running as a web-accessible session. Key
environment variables:

| Variable                                     | Purpose                                         |
| -------------------------------------------- | ----------------------------------------------- |
| `CLAUDE_CODE_REMOTE`                         | Boolean flag, enables remote-specific behaviors |
| `CLAUDE_CODE_REMOTE_SESSION_ID`              | Session identifier for the web session          |
| `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE`        | Type of remote environment                      |
| `CLAUDE_CODE_REMOTE_MEMORY_DIR`              | Override for auto memory directory in remote    |
| `CLAUDE_CODE_SESSION_ACCESS_TOKEN`           | Session auth token for remote sessions          |
| `CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR` | File descriptor for WebSocket auth              |
| `CLAUDE_CODE_CONTAINER_ID`                   | Container ID in remote infrastructure           |

Remote sessions require claude.ai OAuth authentication. Grep
`API key authentication is not sufficient` for the refusal message.

## Authentication Context

### The claude.ai-authentication predicate

A small predicate answers "is this session authenticated through claude.ai OAuth rather than an API
key". It returns false unless OAuth is in use at all, and otherwise checks that the stored token's
scopes are the ones claude.ai issues.

The OAuth check rejects a raw API key, Bedrock, Vertex and Foundry. The scope check looks for
`user:inference`, which is the claude.ai OAuth scope.

So the predicate is true only for claude.ai OAuth, never for an API key.

This is significant because:
1. It gates the `client_data` API call, so only claude.ai-authenticated users receive server-side
   `system_prompt_variant` overrides.
2. It is reported in telemetry as `isClaudeAiAuth`.

### Auth source detection

The code detects auth from multiple sources:
1. `ANTHROPIC_AUTH_TOKEN` env var
2. `CLAUDE_CODE_OAUTH_TOKEN` env var
3. `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`
4. API key helper (`apiKeyHelper`)
5. claude.ai OAuth access token with the required scopes, reported as source `claude.ai`

## User-Agent Strings

### Anthropic API User-Agent

Sent with API requests to Anthropic:
```
claude-cli/<version> (external, ${CLAUDE_CODE_ENTRYPOINT}[, agent-sdk/${SDK_VERSION}][, client-app/${CLIENT_APP}])
```

Examples:
- CLI: `claude-cli/<version> (external, cli)`
- VSCode: `claude-cli/<version> (external, claude-vscode)`
- Remote: `claude-cli/<version> (external, remote)`
- Agent SDK: `claude-cli/<version> (external, sdk-ts, agent-sdk/1.0.0)`

### Attribution header

Sent as `x-anthropic-billing-header` when `tengu_attribution_header` feature flag is enabled:
```
x-anthropic-billing-header: cc_version=<version>.${MODEL_HASH}; cc_entrypoint=${ENTRYPOINT}; cch=00000;
```

## GrowthBook Feature Flag Targeting

### Attributes

The attributes sent to GrowthBook for feature flag evaluation:

| Attribute                | Value                                                   |
| ------------------------ | ------------------------------------------------------- |
| `id`, `deviceID`         | Device id                                               |
| `sessionId`              | Session id                                              |
| `platform`               | `process.platform`                                      |
| `organizationUUID`       | Present when authenticated through an org               |
| `accountUUID`            | Present when authenticated                              |
| `userType`               | Hardcoded `external`                                    |
| `subscriptionType`       | Pro, Max, Team, Enterprise and so on                    |
| `rateLimitTier`          | When available                                          |
| `firstTokenTime`         | When available                                          |
| `email`                  | When available                                          |
| `appVersion`             | Bundle version                                          |
| `githubActionsMetadata`  | Present when running in GitHub Actions                  |

Notably absent: the entrypoint and the client type. Flag targeting cannot discriminate by surface
through these attributes.

The GrowthBook attributes do NOT include `clientType`, `CLAUDE_CODE_ENTRYPOINT`, or any surface
identifier. Feature flags like `tengu_vinteuil_phrase` can be targeted by user, organization,
subscription type, or platform -- but not directly by execution surface.

### Cache Key Attributes

GrowthBook uses `id` and `organizationUUID` as cache key attributes, so flag evaluations are cached
per device and organization.

## Client Data API -- Server-Side Surface Override

### Endpoint

Relocate: `rg -n 'client_data'`. The fetch is skipped entirely unless the session is claude.ai
authenticated, and the path is `/api/oauth/claude_cli/client_data` under the configured base API
URL, sent with auth headers and the User-Agent described above.

The request includes:
- Auth headers (OAuth token)
- User-Agent: `claude-cli/<version> (external, ${ENTRYPOINT}...)`

The server response can include `system_prompt_variant`, which is checked at the prompt-routing
site:
The returned `system_prompt_variant` is compared against a known variant name, and a match routes
the session to the simple system-prompt path. The client treats the value opaquely: it is a string
equality check, not a parsed instruction.

At 2.1.76 the variant name was `tengu_vinteuil_phrase`. That string is absent from 2.1.277, as is
`tengu_velvet_cascade`, so relocate this by grepping `system_prompt_variant` and reading what the
result is compared against rather than by grepping a variant name.

This is the one mechanism where the server CAN differentiate by surface: the User-Agent header
contains the entrypoint, so the server could return different `system_prompt_variant` values for
`cli` vs `remote` vs `claude-vscode`.

However, the client code treats it opaquely -- it just checks if the returned string equals a known
variant name.

## Surface-Specific Behavior in the Codebase

### VSCode-Specific

- A predicate for "Agent SDK, but not VSCode" returns true when the session is non-interactive and
  the entrypoint is not `claude-vscode`. It gates two things:
  - The message `Fast mode is not available in the Agent SDK`, shown for non-interactive
    non-VSCode sessions only.
  - Special `ANTHROPIC_API_KEY` resolution for Agent SDK contexts, skipped for VSCode.

### Remote-Specific

- Memory directory override via `CLAUDE_CODE_REMOTE_MEMORY_DIR`
- Session tracking via `CLAUDE_CODE_REMOTE_SESSION_ID`
- Container tracking via `CLAUDE_CODE_CONTAINER_ID`
- Required claude.ai authentication
- Teleport requires a claude.ai account

### Claude Desktop Integration

There is no `claude-desktop` entrypoint. Claude Desktop interaction is limited to:
- The `add-from-claude-desktop` CLI command imports MCP servers from the Claude Desktop config, and
  describes itself as Mac and WSL only.
- The WebSocket transport marks its connection source as `electron` when the runtime reports an
  Electron version.

Claude Desktop appears to be a separate application that can share MCP server configuration with
Claude Code, not a host for the Claude Code process itself.

## Relationship to System Prompt Routing

The system prompt dual-path routing (documented in PROMPTS.md) is controlled by:

1. GrowthBook feature flag `tengu_vinteuil_phrase` -- targets by user/org/subscription, NOT by surface
2. Server-side `client_data.system_prompt_variant` -- CAN target by surface (via User-Agent parsing), but only for claude.ai-authenticated users

Neither mechanism is hardcoded to a specific surface in the client code. The server could in
principle serve the simple prompt to all `remote` sessions and the legacy prompt to `cli` sessions,
but we cannot confirm this without server-side code.

The wording differences in the simple prompt path ("interactive agent" vs "interactive CLI tool", no
CLI-specific framing, bulleted environment info instead of XML `<env>` tags) are consistent with a
prompt designed for non-CLI surfaces, but this is circumstantial.

## Telemetry Context

The full telemetry context reports:

| Field                       | Source                                       |
| --------------------------- | -------------------------------------------- |
| `platform`, `arch`          | `process.platform`, `process.arch`           |
| `nodeVersion`               | Runtime version                              |
| `terminal`                  | Terminal detection result                    |
| `isRunningWithBun`          | Runtime check                                |
| `isCi`                      | CI detection                                 |
| `isClaubbit`, `isConductor` | Host-environment detection                   |
| `isClaudeCodeRemote`        | `CLAUDE_CODE_REMOTE`                         |
| `isLocalAgentMode`          | Entrypoint equal to `local-agent`            |
| `remoteEnvironmentType`     | `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE`        |
| `claudeCodeContainerId`     | `CLAUDE_CODE_CONTAINER_ID`                   |
| `claudeCodeRemoteSessionId` | `CLAUDE_CODE_REMOTE_SESSION_ID`              |
| `isGithubAction`            | `GITHUB_ACTIONS`                             |
| `isClaudeCodeAction`        | `CLAUDE_CODE_ACTION`                         |
| `isClaudeAiAuth`            | The claude.ai-authentication predicate       |
| `version`                   | Bundle version                               |
| `deploymentEnvironment`     | Deployment environment                       |
| `clientType`                | Resolved client type                         |
| `entrypoint`                | `CLAUDE_CODE_ENTRYPOINT`                     |

The list is not exhaustive and grows between releases.

This confirms that Anthropic tracks both the surface (entrypoint/clientType) and auth type
(isClaudeAiAuth) in their analytics, allowing them to analyze prompt variant effectiveness per
surface server-side even if the client-side targeting is user/org-based.

## Version history

- 2.1.76: 9 recognized entrypoint values, accepted without validation. Prompt variant name
  `tengu_vinteuil_phrase`.
- 2.1.277: entrypoint validated against a 27-member set, and an unrecognized value is treated as
  unset. `claude-desktop` added as a client type. Remote detection extended with
  `CLAUDE_SESSION_INGRESS_TOKEN_FILE` and a truthy `CLAUDE_CODE_REMOTE` paired with an available
  session credential. `tengu_vinteuil_phrase` and `tengu_velvet_cascade` both absent.
