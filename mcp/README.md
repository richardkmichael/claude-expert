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
change itself; it delegates that to a git-committing subagent — which subagent, and any trailer
conventions it follows, are set in this repo's own memory (a `CLAUDE.md` / `CLAUDE.local.md` the
nested session loads). The subagent stages the specific file(s) by path and adds a
`Consulted-by: claude-code-expert` trailer, so every commit made on the expert's behalf is
identifiable and revertible (`git log --grep 'Consulted-by: claude-code-expert'`, `git revert <sha>`
for a wrong one). This is why asking the same or a similar question again later is faster and
cheaper — the answer may already be sitting in `analysis/` rather than re-derived from source.

## The tool

    ask_claude_code_expert(question: string, session_id?: string, model?: string) -> text

The reply ends with a `Research session_id:` line. Pass that value back as `session_id` on a later
call to continue the same research conversation with its context retained — the calling Claude does
this automatically when it wants a follow-up.

`model` is one of `opus`, `sonnet` or `haiku`, and lets the caller drop a simple lookup onto a
cheaper model. Anything else is ignored in favour of the server's own default, so a calling agent
cannot dial the cost up.

## Runtime: bun

The server runs under bun. It imports the MCP SDK with the SDK version pinned in the import
specifiers, so bun auto-installs the SDK into its global cache on first run — no `package.json`,
no `node_modules`, no build step. Everything else is Node built-ins. Bump the SDK by editing the
pinned version in the three import specifiers at the top of `expert-server.mjs`.

Install bun however you like and make sure `bun` is on PATH. One caveat if you manage bun with a
per-directory version manager (mise, asdf, and the like): the server is launched from whatever
project invokes it, not from this repo, so a bun version pinned only inside this repo does not apply
there. Either set a global default (with mise, `mise use -g bun@latest`) or register with an
absolute path to the bun binary (the path `mise which bun` prints) in place of the bare `bun` below.

## Register it

User scope makes it available in every project (recommended):

    claude mcp add claude-code-expert -s user -- \
      bun /path/to/claude-code-analysis/mcp/expert-server.mjs

Or per project, in that project's `.mcp.json`:

    {
      "mcpServers": {
        "claude-code-expert": {
          "command": "bun",
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
    EXPERT_TIMEOUT_MS          Per-question wall-clock budget (default: 1500000)
    EXPERT_MODEL               Model the nested session runs on (default: opus)

The default allowlist lets the expert research (`Read`/`Grep`/`Glob`/`Bash`/`WebFetch`), write or
edit `analysis/` docs directly (`Write`/`Edit`), and delegate the commit to a subagent (`Agent`).
Its system prompt forbids running `git add`/`git commit` itself even though `Bash` is allowed, and
requires it to check `git status --short` first and skip the write-back entirely if the working
tree already has unrelated pending changes — since this repo's checkout may be in active interactive
use at the same time a question arrives from another project. Set `EXPERT_ALLOWED_TOOLS` back to
the original `Read,Grep,Glob,Bash,WebFetch` to restore a strictly read-only expert.

A long call does not hold up an interactive caller. Claude Code moves an MCP tool call that has not
returned within two minutes into the background, returns the turn, and delivers a notification when
the call settles. A headless caller is the exception: auto-backgrounding is off in a non-interactive
session unless `CLAUDE_AUTO_BACKGROUND_TASKS` is set, so a `claude -p` caller blocks for the whole
question. See `analysis/MCP.md`, "MCP tool auto-backgrounding".

Raising `EXPERT_TIMEOUT_MS` past 1800000 also needs work at the calling end. Claude Code aborts a
stdio MCP server that has gone 30 minutes without a response or a progress notification, so a budget
above that is cut short by the client unless the caller sets a per-server `timeout` in its
`.mcp.json` or raises `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT`. The 25-minute default sits under that
bound deliberately. See `analysis/MCP.md`, "Tool-call timeouts and the idle watchdog".
