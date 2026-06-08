# Claude Code expert MCP server

An MCP server that turns this repository into a consultable expert. It exposes one tool,
`ask_claude_code_expert`, to any project's Claude Code session. Each call runs a nested headless
Claude session (`claude -p`) with its working directory set to this repo, so the nested session
inherits this project's `CLAUDE.md` and skills and researches the answer by exploring the prettified
sources under `work/<version>/` and the docs under `analysis/`. Only the question and the final
answer cross the boundary; the exploration stays inside the nested session.

## The tool

    ask_claude_code_expert(question: string, session_id?: string) -> text

The reply ends with a `Research session_id:` line. Pass that value back as `session_id` on a later
call to continue the same research conversation with its context retained — the calling Claude does
this automatically when it wants a follow-up.

## Register it

User scope makes it available in every project (recommended):

    claude mcp add claude-code-expert -s user -- \
      node /path/to/claude-code-analysis/mcp/expert-server.mjs

Or per project, in that project's `.mcp.json`:

    {
      "mcpServers": {
        "claude-code-expert": {
          "command": "node",
          "args": [
            "/path/to/claude-code-analysis/mcp/expert-server.mjs"
          ]
        }
      }
    }

The server resolves the repo it explores from its own location, so it always points at this
repository regardless of which project invokes it.

## Configuration

All optional, via environment variables on the server entry:

    CLAUDE_CODE_ANALYSIS_DIR   Repo root the expert explores (default: parent of the script)
    CLAUDE_BIN                 Path to the claude binary (default: claude on PATH)
    EXPERT_ALLOWED_TOOLS       Comma-separated tool allowlist (default: Read,Grep,Glob,Bash,WebFetch)
    EXPERT_TIMEOUT_MS          Per-question wall-clock budget (default: 300000)
    EXPERT_MODEL               Optional model override passed to claude --model

The default tool allowlist is read-only research: the expert can read, search, run shell commands,
and fetch web pages, but the absence of `Write`/`Edit` from the allowlist means it cannot modify
files in a non-interactive session.

## Billing

From 2026-06-15, `claude -p` on a subscription draws from a separate monthly Agent SDK credit pool,
distinct from the interactive usage limits you spend while working. Every expert call is a full
nested session, so it consumes that pool — point `CLAUDE_BIN` at a wrapper that sets
`ANTHROPIC_API_KEY` if you would rather meter it as pay-per-token API usage instead.
