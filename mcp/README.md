# Claude Code expert MCP server

An MCP server that turns this repository into a consultable expert. It exposes one tool,
`ask_claude_code_expert`, to any project's Claude Code session. Each call runs a nested headless
Claude session (`claude -p`) with its working directory set to this repo, so the nested session
inherits this project's `CLAUDE.md` and skills and researches the answer by exploring the prettified
sources under `work/<version>/` and the docs under `analysis/`. Only the question and the final
answer cross the boundary; the exploration stays inside the nested session.

When the research turns up something durable — a confirmed, corrected, or newly discovered
behavior — the nested session writes it back into `analysis/` following this repo's normal
"Documenting findings" loop, the same as an interactive session would. It does not commit the
change itself; it delegates that to the `git-wright` subagent, which stages the specific file(s)
by path and commits with its usual `Curated-by: git-wright` trailer plus an additional
`Consulted-by: claude-code-expert` trailer, so every commit made on the expert's behalf is
identifiable and revertible (`git log --grep 'Consulted-by: claude-code-expert'`, `git revert <sha>`
for a wrong one). This is why asking the same or a similar question again later is faster and
cheaper — the answer may already be sitting in `analysis/` rather than re-derived from source.

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
    EXPERT_ALLOWED_TOOLS       Comma-separated tool allowlist
                               (default: Read,Grep,Glob,Bash,WebFetch,Write,Edit,Agent)
    EXPERT_TIMEOUT_MS          Per-question wall-clock budget (default: 300000)
    EXPERT_MODEL               Optional model override passed to claude --model

The default allowlist lets the expert research (`Read`/`Grep`/`Glob`/`Bash`/`WebFetch`), write or
edit `analysis/` docs directly (`Write`/`Edit`), and delegate the commit to a subagent (`Agent`).
Its system prompt forbids running `git add`/`git commit` itself even though `Bash` is allowed, and
requires it to check `git status --short` first and skip the write-back entirely if the working
tree already has unrelated pending changes — since this repo's checkout may be in active interactive
use at the same time a question arrives from another project. Set `EXPERT_ALLOWED_TOOLS` back to
the original `Read,Grep,Glob,Bash,WebFetch` to restore a strictly read-only expert.

## Billing

From 2026-06-15, `claude -p` on a subscription draws from a separate monthly Agent SDK credit pool,
distinct from the interactive usage limits you spend while working. Every expert call is a full
nested session, so it consumes that pool — point `CLAUDE_BIN` at a wrapper that sets
`ANTHROPIC_API_KEY` if you would rather meter it as pay-per-token API usage instead.
