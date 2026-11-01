# Claude expert MCP server

An MCP server that turns this repository into two consultable experts, one for Claude Code and one
for Claude Desktop. Each call runs a nested headless Claude session (`claude -p`) inside the
product's subtree of this repo, so the nested session loads the root `CLAUDE.md`, the subtree's
`CLAUDE.md` and the root skills, and researches the answer from the extracted sources and the
analysis docs. Only the question and the final answer cross the boundary; the exploration stays
inside the nested session.

When the research turns up something durable — a confirmed, corrected, or newly discovered behavior
— the nested session writes it back into the analysis docs following this repo's normal "Documenting
findings" loop, the same as an interactive session would. It does not commit the change itself; it
delegates that to a git-committing subagent — which subagent, and any trailer conventions it
follows, are set in this repo's own memory (a `CLAUDE.md` / `CLAUDE.local.md` the nested session
loads). The delegation runs in the foreground: the nested process exits as soon as it answers, and a
subagent spawned in the background would be cut off with it. The subagent stages the specific
file(s) by path and adds a `Consulted-by:` trailer naming the expert, so every commit made on an
expert's behalf is identifiable and revertible (`git log --grep 'Consulted-by: claude-'`,
`git revert <sha>` for a wrong one). This is why asking the same or a similar question again later
is faster and cheaper — the answer may already be sitting in the docs rather than re-derived from
source.

## The tools

    ask_claude_code_expert(question: string, session_id?: string, model?: string) -> text
    ask_claude_desktop_expert(question: string, session_id?: string, model?: string) -> text

| Tool                        | Runs in    | Researches                                                                                               | Trailer                               |
| --------------------------- | ---------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| `ask_claude_code_expert`    | `code/`    | `code/work/<version>/`, `code/analysis/`                                                                 | `Consulted-by: claude-code-expert`    |
| `ask_claude_desktop_expert` | `desktop/` | `desktop/work/<app-version>/`, `desktop/analysis/`, and `code/` for the Claude Code version Desktop pins | `Consulted-by: claude-desktop-expert` |

The desktop expert starts by preparing the installed Claude Desktop build with the
`prepare-claude-desktop-source` skill. For anything about the Claude Code that Desktop runs, it
researches the exact version the build pins, preparing it with `prepare-claude-code-source` if
needed. It gets `code/` through `--add-dir` with `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`,
so `code/CLAUDE.md` is loaded from the start.

Each reply ends with a `Research session_id:` line. Pass that value back as `session_id` on a later
call to the same tool to continue the research conversation with its context retained. A session
resumes only under the directory it started in, so a session_id from one tool does not work with the
other.

`model` is one of `opus`, `sonnet` or `haiku`, and lets the caller drop a simple lookup onto a
cheaper model. Anything else is ignored in favour of the server's own default, so a calling agent
cannot dial the cost up.

## Routing: the guide first

The server's MCP instructions tell the calling session to consult the `claude-code-guide` subagent
first for a Claude Code question, when that subagent is available, and to call
`ask_claude_code_expert` when the guide has no answer, gives too little detail, or seems wrong.
Claude Code puts server instructions in the session's context when the server connects. The
`ask_claude_code_expert` description repeats the rule for clients that do not. Claude Desktop
questions go straight to `ask_claude_desktop_expert`: there is no Desktop guide.

## What the nested sessions load

- MCP servers: only those in this repo's root `.mcp.json`, through `--strict-mcp-config`. The
  caller's user-scope servers, other projects' servers and claude.ai connectors are not loaded. Each
  expert's allowlist names the servers it may call.
- No experts of their own. Every nested session runs with `CLAUDE_EXPERT_NESTED=1`; a copy of this
  server started under that variable offers no tools, so an expert never consults itself even if
  this server is registered at user scope.

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

    claude mcp add claude-expert -s user -- \
      bun /path/to/claude-code-analysis/mcp/expert-server.mjs

Or per project, in that project's `.mcp.json`:

    {
      "mcpServers": {
        "claude-expert": {
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

    CLAUDE_CODE_ANALYSIS_DIR   Repo root the experts explore (default: parent of the script)
    CLAUDE_BIN                 Path to the claude binary (default: claude on PATH)
    EXPERT_ALLOWED_TOOLS       Comma-separated built-in tool allowlist
                               (default: Read,Grep,Glob,Bash,WebFetch,Write,Edit,Agent,Skill)
    EXPERT_TIMEOUT_MS          Per-question wall-clock budget (default: 1500000)
    EXPERT_MODEL               Model the nested session runs on (default: opus)

The default allowlist lets an expert research (`Read`/`Grep`/`Glob`/`Bash`/`WebFetch`), prepare
sources with the repo's skills (`Skill`), write or edit analysis docs directly (`Write`/`Edit`), and
delegate the commit to a subagent (`Agent`). Each expert's MCP servers are added to it. Its system
prompt forbids running `git add`/`git commit` itself even though `Bash` is allowed, and requires it
to check `git status --short` on the paths it may write first, skipping the write-back entirely if
they already hold unrelated pending changes — since this repo's checkout may be in active
interactive use at the same time a question arrives from another project. Set `EXPERT_ALLOWED_TOOLS`
to `Read,Grep,Glob,Bash,WebFetch` for strictly read-only experts.

A long call does not hold up an interactive caller. Claude Code moves an MCP tool call that has not
returned within two minutes into the background, returns the turn, and delivers a notification when
the call settles. A headless caller is the exception: auto-backgrounding is off in a non-interactive
session unless `CLAUDE_AUTO_BACKGROUND_TASKS` is set, so a `claude -p` caller blocks for the whole
question. See `code/analysis/MCP.md`, "MCP tool auto-backgrounding".

Raising `EXPERT_TIMEOUT_MS` past 1800000 also needs work at the calling end. Claude Code aborts a
stdio MCP server that has gone 30 minutes without a response or a progress notification, so a budget
above that is cut short by the client unless the caller sets a per-server `timeout` in its
`.mcp.json` or raises `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT`. The 25-minute default sits under that
bound deliberately. See `code/analysis/MCP.md`, "Tool-call timeouts and the idle watchdog".
