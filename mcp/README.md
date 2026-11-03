# Claude expert MCP server

An MCP server that turns this repository into two consultable experts, one for Claude Code and one
for Claude Desktop. Each call runs a nested headless Claude session (`claude -p`) inside the
product's subtree of this repo, so the nested session loads the root `CLAUDE.md`, the subtree's
`CLAUDE.md` and the root skills, and researches the answer from the extracted sources and the
analysis docs. Only the question and the final answer cross the boundary; the exploration stays
inside the nested session.

When the research confirms, corrects or discovers behavior, the nested session writes it back into
the analysis docs following this repo's "Documenting findings" rules, the same as an interactive
session would.

It does not commit the change itself. It delegates the commit to a subagent: the one its
instructions name for git operations if they name one (a personal `CLAUDE.local.md` can), otherwise
the general-purpose subagent. The delegation runs in the foreground: the nested process exits as
soon as it answers, and a subagent spawned in the background would be cut off with it. The commit
includes only the files the expert changed, and carries a `Consulted-by:` trailer naming the expert,
so every commit made on an expert's behalf is identifiable and revertible
(`git log --grep 'Consulted-by: claude-'`, `git revert <sha>` for a wrong one).

This is why asking the same or a similar question again later is faster and cheaper: the answer may
already be in the docs.

## The tools

    ask_claude_code_expert(question: string, session_id?: string, model?: string, effort?: string) -> text
    ask_claude_desktop_expert(question: string, session_id?: string, model?: string, effort?: string) -> text

| Tool                        | Runs in    | Researches                                                                                               | Trailer                               |
| --------------------------- | ---------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| `ask_claude_code_expert`    | `code/`    | `code/work/<version>/`, `code/analysis/`                                                                 | `Consulted-by: claude-code-expert`    |
| `ask_claude_desktop_expert` | `desktop/` | `desktop/work/<app-version>/`, `desktop/analysis/`, and `code/` for the Claude Code version Desktop pins | `Consulted-by: claude-desktop-expert` |

The desktop expert starts by preparing the installed Claude Desktop build with the
`prepare-claude-desktop-source` skill. For anything about the Claude Code that Desktop runs, it
researches the exact version the build pins, preparing it with `prepare-claude-code-source` if
needed. It gets `code/` through `--add-dir` with `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`,
so `code/CLAUDE.md` is loaded from the start.

A successful reply ends with a `Research session_id:` line. Pass that value back as `session_id` on
a later call to the same tool to continue the research conversation with its context retained. A
session resumes only under the directory it started in, so a session_id from one tool does not work
with the other. The server accepts only a UUID here and refuses anything else, because the value
becomes a command-line argument for the nested session. The question itself reaches the nested
session on stdin, so a question that starts with `-` is not mistaken for an option.

`model` is one of `opus`, `sonnet` or `haiku`, and lets the caller drop a simple lookup onto a
cheaper model. Anything else is ignored in favour of the server's own default, so a calling agent
cannot dial the cost up.

`effort` is the effort (thinking) level, one of `low`, `medium` or `high`, passed to the nested
session as `--effort`. The default is `medium`. As with `model`, anything else falls back to the
server's default, so `xhigh` and `max` are available only through `EXPERT_EFFORT`. The server also
removes `CLAUDE_CODE_EFFORT_LEVEL` from the nested session's environment, because that variable
outranks `--effort`.

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
  expert's allowlist names the servers it may call:

  | Expert                      | MCP servers                                                                                                      |
  | --------------------------- | ---------------------------------------------------------------------------------------------------------------- |
  | `ask_claude_code_expert`    | `claude-code-docs`, `claude-platform-docs`                                                                       |
  | `ask_claude_desktop_expert` | `claude-code-docs`, `claude-platform-docs`, `mcp-specification`, `fastmcp_documentation`, `prefab_documentation` |

- No `claude-code-guide` subagent. The nested sessions run as `claude -p`, and the server clears
  `CLAUDE_CODE_ENTRYPOINT` before starting them, so Claude Code treats each as an SDK session and
  does not register the guide (see `code/analysis/CLAUDE_CODE_GUIDE.md`). The routing rule above
  applies to the calling session, not to the experts.
- No experts of their own. Every nested session runs with `CLAUDE_EXPERT_NESTED=1`; a copy of this
  server started under that variable offers no tools, so an expert never consults itself even if
  this server is registered at user scope.

## Runtime: bun

The server runs under bun. It imports the MCP SDK with the SDK version pinned in the import
specifiers, so bun auto-installs the SDK into its global cache on first run — no `package.json`, no
`node_modules`, no build step. Everything else is Node built-ins. Bump the SDK by editing the pinned
version in the three import specifiers at the top of `claude-expert.mjs`.

Install bun however you like and make sure `bun` is on PATH. One caveat if you manage bun with a
per-directory version manager (mise, asdf, and the like): the server is launched from whatever
project invokes it, not from this repo, so a bun version pinned only inside this repo does not apply
there. Either set a global default (with mise, `mise use -g bun@latest`) or register with an
absolute path to the bun binary (the path `mise which bun` prints) in place of the bare `bun` below.

## Register it

User scope makes it available in every project (recommended):

    claude mcp add claude-expert -s user -- \
      bun /path/to/claude-expert/mcp/claude-expert.mjs

Or per project, in that project's `.mcp.json`:

    {
      "mcpServers": {
        "claude-expert": {
          "command": "bun",
          "args": [
            "/path/to/claude-expert/mcp/claude-expert.mjs"
          ]
        }
      }
    }

The server resolves the repo it explores from its own location, so it always points at this
repository regardless of which project invokes it.

## Configuration

All optional, via environment variables on the server entry:

    CLAUDE_EXPERT_DIR          Repo root the experts explore (default: parent of the script;
                               a relative path resolves against the calling project's directory)
    CLAUDE_BIN                 Path to the claude binary (default: claude on PATH)
    EXPERT_ALLOWED_TOOLS       Comma-separated built-in tool allowlist
                               (default: Read,Grep,Glob,Bash,WebFetch,Write,Edit,Agent,Skill)
    EXPERT_TIMEOUT_MS          Per-question wall-clock budget (default: 1500000)
    EXPERT_MODEL               Model the nested session runs on (default: opus)
    EXPERT_EFFORT              Effort level the nested session runs at (default: medium)

The default allowlist lets an expert research (`Read`/`Grep`/`Glob`/`Bash`/`WebFetch`), prepare
sources with the repo's skills (`Skill`), write or edit analysis docs directly (`Write`/`Edit`), and
delegate the commit to a subagent (`Agent`). Each expert's MCP servers are added to it.

The server also passes a fixed `--disallowedTools` list that blocks shell commands which discard
work or rewrite history: `git push`, `reset`, `rebase`, `checkout`, `switch`, `restore`, `clean`,
`stash`, `branch -d`/`-D`, and `rm`. `git add` and `git commit` stay available because the
committing subagent runs under the same rules. The system prompt forbids the expert itself from
running any git write command. Before writing, it must find nothing staged and no pending changes in
the paths it may write (`code/` for the code expert; `desktop/` and `code/analysis/` for the Desktop
expert); otherwise it skips the write-back and says so. This repo's checkout may be in interactive
use when a question arrives from another project. Set `EXPERT_ALLOWED_TOOLS` to
`Read,Grep,Glob,Bash,WebFetch` for strictly read-only experts.

The server checks its configuration at startup and exits with a message on stderr if
`EXPERT_TIMEOUT_MS` is not a positive whole number, or if the repo root, `code/`, `desktop/` or
`.mcp.json` is missing.

Each nested session runs in its own process group. When the session exits, anything it left running
is stopped. When the server receives SIGINT or SIGTERM, which Claude Code sends when a session ends
or `/mcp` reconnects the server, it sends SIGTERM to every running nested session's group and
SIGKILL ten seconds later. A timed-out question is stopped the same way.

Concurrent calls are not serialized. Two experts that write to the same doc at the same moment can
still collide; the pending-changes check makes this unlikely but does not rule it out.

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
