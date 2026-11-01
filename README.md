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

## Using it from another project: Expert MCP server

`mcp/expert-server.mjs` exposes this repository as an MCP tool, so another project's session can ask
a question about Claude Code without adding this repo to its context. The call runs a nested
headless session rooted here; only the question and the answer cross the boundary. See
`mcp/README.md` for registration.
