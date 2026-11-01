# Claude Code and Claude Desktop Analysis

Notes on the operation Claude Code and Claude Desktop.  Complements the `@claude-code-guide` agent
native to Claude Code.  Anthropic documentation occasionally lags or is incomplete, examining the
source code is a helpful way to better understand the harnesses.

## What's here

| Path              | Contents                                                                           |
| ----------------- | ---------------------------------------------------------------------------------- |
| `code/`           | Claude Code: findings, generators, patches, extracted bundles (`code/README.md`)   |
| `desktop/`        | Claude Desktop: findings (`desktop/README.md`)                                     |
| `.claude/skills/` | Skills for fetching a Claude Code version, matching code patterns, porting patches |
| `mcp/`            | An MCP server that makes this repo consultable from another project                |

## Claude Expert MCP server

`mcp/expert-server.mjs` exposes two MCP tools:

- `ask_claude_code_expert`
- `ask_claude_desktop_expert`

Another project's session can use them to ask a question about either product without adding this
repo to its context. Each call runs a nested headless session in the product's subdirectory, and
that session adds its findings to the documentation here.  See `mcp/README.md` for registration.
