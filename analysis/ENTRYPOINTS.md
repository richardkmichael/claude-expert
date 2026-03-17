# Claude Code Entrypoints and Execution Surfaces

Version: 2.1.39

## Overview

Claude Code (`cli.prettier.js`) is a Node.js application that runs across multiple execution surfaces. It is never executed directly in a web browser -- even for web-based surfaces like claude.ai/code, the Node.js process runs server-side with the browser providing a terminal UI over WebSocket.

The execution surface is identified by the `CLAUDE_CODE_ENTRYPOINT` environment variable, which influences behavior in authentication, telemetry, feature availability, and potentially system prompt selection.

## Entrypoint Detection

### Function `yZz()` at line 574159

Sets `CLAUDE_CODE_ENTRYPOINT` if not already set by the hosting environment:

```javascript
[source fragment removed]
```

The `A` parameter is `z` from line 574188, which is true when running non-interactively:
```javascript
[source fragment removed]
```

Note: The function exits immediately if `CLAUDE_CODE_ENTRYPOINT` is already set. This means hosting environments (VSCode, Claude Desktop, remote infrastructure) set it before the CLI's own detection runs.

### Client Type Resolution (line 574191-574206)

After entrypoint is set, a display-friendly `clientType` is resolved:

```javascript
[source fragment removed]
```

## Known Entrypoints

| Entrypoint | Client Type | Surface | Set By |
|-----------|-------------|---------|--------|
| `cli` | `"cli"` | Standalone terminal | Auto-detected (interactive TTY) |
| `sdk-cli` | `"sdk-cli"` | Agent SDK via CLI | Auto-detected (non-interactive) |
| `sdk-ts` | `"sdk-typescript"` | TypeScript Agent SDK | Set by `@anthropic-ai/claude-code` npm package |
| `sdk-py` | `"sdk-python"` | Python Agent SDK | Set by Python SDK wrapper |
| `claude-vscode` | `"claude-vscode"` | VSCode extension | Set by VSCode extension host |
| `remote` | `"remote"` | claude.ai/code web sessions | Set by remote infrastructure |
| `local-agent` | `"local-agent"` | Local agent mode | Set by hosting environment |
| `mcp` | `"mcp"` | MCP server mode (`mcp serve`) | Auto-detected from argv |
| `claude-code-github-action` | `"github-action"` | GitHub Actions | Auto-detected from `CLAUDE_CODE_ACTION` env var |

The `remote` client type is also triggered by the presence of `CLAUDE_CODE_SESSION_ACCESS_TOKEN` or `CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR`, even without an explicit `remote` entrypoint value.

## Remote (Web) Surface Details

The `remote` surface is claude.ai/code -- Claude Code running as a web-accessible session. Key environment variables:

| Variable | Purpose |
|----------|---------|
| `CLAUDE_CODE_REMOTE` | Boolean flag, enables remote-specific behaviors |
| `CLAUDE_CODE_REMOTE_SESSION_ID` | Session identifier for the web session |
| `CLAUDE_CODE_REMOTE_ENVIRONMENT_TYPE` | Type of remote environment |
| `CLAUDE_CODE_REMOTE_MEMORY_DIR` | Override for auto memory directory in remote |
| `CLAUDE_CODE_SESSION_ACCESS_TOKEN` | Session auth token for remote sessions |
| `CLAUDE_CODE_WEBSOCKET_AUTH_FILE_DESCRIPTOR` | File descriptor for WebSocket auth |
| `CLAUDE_CODE_CONTAINER_ID` | Container ID in remote infrastructure |

Remote sessions require claude.ai OAuth authentication (line 370119):
```
"Claude Code web sessions require authentication with a Claude.ai account.
 API key authentication is not sufficient."
```

## Authentication Context

### Function `i8()` at line 111928 -- "Is Claude.ai Authenticated"

```javascript
[source fragment removed]
```

Where `DV()` at line 111501 checks that the user is NOT using a raw API key, Bedrock, Vertex, or Foundry. And `Bg()` at line 50923 checks for the `"user:inference"` OAuth scope, which is the claude.ai OAuth scope.

So `i8()` returns true when authenticated via claude.ai OAuth (not API key).

This is significant because:
1. `i8()` gates the `client_data` API call (line 510977) -- only claude.ai-authenticated users get server-side `system_prompt_variant` overrides
2. `i8()` is reported in telemetry as `isClaudeAiAuth` (line 236401)

### Auth Source Detection (`un()` at line 111519)

The code detects auth from multiple sources:
1. `ANTHROPIC_AUTH_TOKEN` env var
2. `CLAUDE_CODE_OAUTH_TOKEN` env var
3. `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`
4. API key helper (`apiKeyHelper`)
5. claude.ai OAuth token (`s4()?.accessToken` with proper scopes) -> source: `"claude.ai"`

## User-Agent Strings

### Anthropic API User-Agent (line 133640-133646)

Sent with API requests to Anthropic:
```
claude-cli/2.1.39 (external, ${CLAUDE_CODE_ENTRYPOINT}[, agent-sdk/${SDK_VERSION}][, client-app/${CLIENT_APP}])
```

Examples:
- CLI: `claude-cli/2.1.39 (external, cli)`
- VSCode: `claude-cli/2.1.39 (external, claude-vscode)`
- Remote: `claude-cli/2.1.39 (external, remote)`
- Agent SDK: `claude-cli/2.1.39 (external, sdk-ts, agent-sdk/1.0.0)`

### Attribution Header (line 134296-134301)

Sent as `x-anthropic-billing-header` when `tengu_attribution_header` feature flag is enabled:
```
x-anthropic-billing-header: cc_version=2.1.39.${MODEL_HASH}; cc_entrypoint=${ENTRYPOINT}; cch=00000;
```

## GrowthBook Feature Flag Targeting

### Attributes (function `TXq()` at line 525334, built by `ep()` at line 525269)

The attributes sent to GrowthBook for feature flag evaluation:

```javascript
[source fragment removed]
```

The GrowthBook attributes do NOT include `clientType`, `CLAUDE_CODE_ENTRYPOINT`, or any surface identifier. Feature flags like `tengu_vinteuil_phrase` can be targeted by user, organization, subscription type, or platform -- but not directly by execution surface.

### Cache Key Attributes

GrowthBook uses `["id", "organizationUUID"]` as cache key attributes (line 525510), meaning feature flag evaluations are cached per device and organization.

## Client Data API -- Server-Side Surface Override

### Endpoint (function `YYz()` at line 510976)

```javascript
[source fragment removed]
```

The request includes:
- Auth headers (OAuth token)
- User-Agent: `claude-cli/2.1.39 (external, ${ENTRYPOINT}...)`

The server response can include `system_prompt_variant` (line 511012), which is checked at line 511374:
```javascript
[source fragment removed]
```

This is the one mechanism where the server CAN differentiate by surface: the User-Agent header contains the entrypoint, so the server could return different `system_prompt_variant` values for `cli` vs `remote` vs `claude-vscode`.

However, the client code treats it opaquely -- it just checks if the returned string equals a known variant name.

## Surface-Specific Behavior in the Codebase

### VSCode-Specific

- `EN1()` at line 2490: returns true when non-interactive AND NOT claude-vscode. Used to gate Agent SDK-specific behavior:
  - Fast mode unavailability message (line 132326): "Fast mode is not available in the Agent SDK" -- but only for non-interactive non-VSCode
  - API key resolution (line 111541): special ANTHROPIC_API_KEY handling for Agent SDK contexts but not VSCode

### Remote-Specific

- Memory directory override via `CLAUDE_CODE_REMOTE_MEMORY_DIR` (line 257849)
- Session tracking via `CLAUDE_CODE_REMOTE_SESSION_ID` (line 236393)
- Container tracking via `CLAUDE_CODE_CONTAINER_ID` (line 236390)
- Required claude.ai authentication (line 370119)
- Teleport feature requires claude.ai account (line 420952)

### Claude Desktop Integration

There is no `claude-desktop` entrypoint. Claude Desktop interaction is limited to:
- `add-from-claude-desktop` CLI command (line 575884): imports MCP servers from Claude Desktop config, described as "Mac and WSL only"
- Electron detection in WebSocket transport (line 526831): `if (n_.versions?.electron) q.from = "electron"` -- marks WebSocket connection source

Claude Desktop appears to be a separate application that can share MCP server configuration with Claude Code, not a host for the Claude Code process itself.

## Relationship to System Prompt Routing

The system prompt dual-path routing (documented in PROMPTS.md) is controlled by:

1. GrowthBook feature flag `tengu_vinteuil_phrase` -- targets by user/org/subscription, NOT by surface
2. Server-side `client_data.system_prompt_variant` -- CAN target by surface (via User-Agent parsing), but only for claude.ai-authenticated users

Neither mechanism is hardcoded to a specific surface in the client code. The server could in principle serve the simple prompt to all `remote` sessions and the legacy prompt to `cli` sessions, but we cannot confirm this without server-side code.

The wording differences in the simple prompt path ("interactive agent" vs "interactive CLI tool", no CLI-specific framing, bulleted environment info instead of XML `<env>` tags) are consistent with a prompt designed for non-CLI surfaces, but this is circumstantial.

## Telemetry Context

The full telemetry context (function at line 236360+) reports:

```javascript
[source fragment removed]
```

This confirms that Anthropic tracks both the surface (entrypoint/clientType) and auth type (isClaudeAiAuth) in their analytics, allowing them to analyze prompt variant effectiveness per surface server-side even if the client-side targeting is user/org-based.
