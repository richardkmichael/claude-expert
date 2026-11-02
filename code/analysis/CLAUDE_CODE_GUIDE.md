# Claude Code's Self-Help: the Guide Agent and the claude-code-docs Skill

Verified against: cli.prettier.js 2.1.316 (2026-11-02)

Claude Code ships two ways for the model to answer questions about Claude Code itself: the built-in
`claude-code-guide` subagent, and a bundled `claude-code-docs` skill that is off by default. Both
draw on reference documents compiled into the binary, which never appear in `cli.prettier.js`. For
the Agent tool and the other built-in agents, see `TASK_TOOL_AND_SUBAGENTS.md`; for skill
registration and visibility, see `SKILLS_AND_SUBAGENTS.md`.

## The claude-code-guide subagent

Relocate with `rg -n 'You are the Claude guide agent.'`; the definition and its doc-source URL
constants are just around it.

Availability. Registered unless `CLAUDE_CODE_ENTRYPOINT` is an SDK entrypoint (`sdk-ts`, `sdk-py`,
`sdk-cli`). A non-interactive launch sets the entrypoint to `sdk-cli` unless the caller already set
one (grep `"sdk-cli" : "cli"`), so a plain `claude -p` session has no `claude-code-guide`. It is
also absent in coordinator mode and when built-in agents are disabled, like every built-in. Its
`whenToUse` lists five domains and ends "Before spawning a new agent, check if there is already a
running or recently completed claude-code-guide agent that you can continue via SendMessage."

Definition. `model: "haiku"`, `permissionMode: "dontAsk"` (a tool call that needs approval is
denied, not prompted), no `maxTurns`, no `omitClaudeMd`, no `mcpServers`.

Tools. An explicit list, chosen when the definition is read:

- `Glob`, `Grep`, `Read`, `WebFetch`, `WebSearch` by default.
- `Bash`, `Read`, `WebFetch`, `WebSearch` when the embedded search tools are active (the build ships
  them, the host has not opted back into the search tools, and the entrypoint is not `local-agent`)
  and Bash is usable (not Windows, or Windows with Git Bash). The prompt then says to use `find` and
  `grep` through Bash.

It has no Skill tool and no MCP tools: the explicit list names none and `mcpServers` is unset, so
the resolver keeps none of the session's MCP tools, docs servers included. MCP server instructions
still reach it mid-turn through `mcp_instructions_delta`, which the agent's tool set does not
filter.

How it gets documentation. Only by fetching over the web with `WebFetch`, falling back to
`WebSearch` "if docs don't cover the topic". The prompt's "Documentation sources" name:

| Source                    | URL                                                       |
| ------------------------- | --------------------------------------------------------- |
| Claude Code and Agent SDK | `https://code.claude.com/docs/en/claude_code_docs_map.md` |
| Claude API                | `https://platform.claude.com/llms.txt`                    |
| Claude Tag (Slack) index  | `https://claude.com/docs/llms.txt`                        |
| Claude Tag overview       | `https://claude.com/docs/claude-tag/overview.md`          |

The Agent SDK pages live in the Claude Code docs map, and the prompt says the platform.claude.com
index does not list them. Its approach: pick the domain, fetch the map, pick URLs, fetch pages,
answer from them, and read local `CLAUDE.md` / `.claude/` with the read tool. If the docs cannot be
reached it must say so and flag that its answer may be out of date, linking
`https://code.claude.com/docs`.

The published docs are also served by two MCP servers, `https://code.claude.com/docs/mcp` (Claude
Code) and `https://platform.claude.com/docs/mcp` (Claude Platform and API). The guide does not use
them.

Prompt content beyond the docs:

- Five domains: Claude Code; the Claude Agent SDK (its built-in tools, self-hosted, distinct from
  the API's Tool Runner and from Managed Agents); the Claude API (Messages API, Tool Runner
  `client.beta.messages.tool_runner`, manual tool-use loops, Managed Agents); Claude Tag (Claude in
  Slack, `/install-slack-app`, Admin settings or `@Claude connect`); and `claude plugin eval` plus
  the `/skill-doctor` report.
- Plugin eval and `/skill-doctor` have no public docs page. After a `---` separator the prompt
  embeds the bundled quick reference (below), headed "# Plugin eval and /skill-doctor (embedded
  offline reference)", preceded by whether each is available in this session (`/skill-doctor`
  follows the gate `tengu_lantern_prism` or `CLAUDE_CODE_LANTERN_PRISM`).
- A feedback line: "/feedback" on the first-party API when product feedback is allowed, otherwise
  the GitHub issues URL.
- A "# User's Current Configuration" section, when any apply: prompt-type commands ("Available
  custom skills in this project", which includes bundled skills), non-built-in agents, configured
  MCP server names, plugin skills, and settings keys with values omitted.

## The claude-code-docs skill

A bundled skill that answers the same questions in the main thread. Relocate the registration with
`rg -n 'tengu_claude_code_skill_loaded'`.

Gate. `isEnabled()` is `tengu_birch_kettle` (default `false`), and
`CLAUDE_CODE_DISABLE_CLAUDE_CODE_SKILL` turns it off regardless. A skill whose `isEnabled()` is
false is dropped from the one loaded command list that feeds both the user's slash menu and the
model's skill listing, so while the flag is off neither the user nor the model can invoke it: `/`
gives an unknown-command error and the Skill tool returns `Unknown skill`. The flag's value comes
from the account's feature flags (see `FEATURE_FLAGS.md`); there is no local override.

When enabled it is invocable by both: `userInvocable: !0` and no model-invocation restriction.

| Field             | Value                                                                                              |
| ----------------- | -------------------------------------------------------------------------------------------------- |
| `name`            | `claude-code-docs`                                                                                 |
| `menuDescription` | `Answer questions about Claude Code features and settings`                                         |
| `allowedTools`    | `Read`, `Grep`, `Glob`, `WebFetch(domain:code.claude.com)`, `WebFetch(domain:platform.claude.com)` |
| `argumentHint`    | `[question]`                                                                                       |
| telemetry         | `tengu_claude_code_skill_loaded` with `has_args`                                                   |

Its description scopes it to Claude Code itself and says to skip Claude API and SDK questions in
favor of `/claude-api`.

The prompt is the skill's `SKILL.md`, then a "# Current Build" section "Generated from the running
Claude Code binary at invocation time", which the prompt calls ground truth that overrides training
data and documentation. That section lists every visible command with its aliases, the
`claude plugin` CLI subcommands available in this session, custom agents, MCP servers, and a
provider note when the session does not use Anthropic's first-party API. The user's question follows
under "## User Request".

The skill ships five reference files, extracted to the skill's base directory on first use:

| Path in the skill                    | Content                                             |
| ------------------------------------ | --------------------------------------------------- |
| `references/plugin-eval-quickref.md` | The plugin eval and `/skill-doctor` quick reference |
| `references/plugin-eval.md`          | The full plugin eval and `/skill-doctor` reference  |
| `references/live-sources.md`         | WebFetch URLs for current Claude Code documentation |
| `references/claude-tag.md`           | Claude Tag (Claude in Slack) reference              |
| `references/recent-changes.md`       | Recent changes                                      |

Relocate the map with `rg -n '"references/plugin-eval.md"'`; it is exported as `SKILL_FILES` beside
`SKILL_PROMPT`.

## The bundled reference documents

The plugin eval references exist because, in their own words, these features "have no public docs
page yet":

- `plugin-eval-quickref.md` (about 10 KB): availability and the kill switch, what plugin eval does,
  the suite layout, graders, mocks, and the run options in brief. The guide agent embeds it whole.
- `plugin-eval.md` (about 80 KB): the full reference, with sections on the case file format,
  graders, mocking MCP servers, every option, exit codes, the results JSON (v1), the HTML report,
  how the sandbox works, CI use, troubleshooting, and `/skill-doctor`.

`cli.prettier.js` holds only the binary's JavaScript modules, so these files are not in it. The
bundle names them as assets: `rg -n '\.md\.zst"'` lists the zstd-compressed Markdown assets
(`plugin-eval-quickref-<hash>.md.zst` and `plugin-eval-<hash>.md.zst` among them), and the skill's
uncompressed files are loaded by path (`claude-tag-<hash>.md`, `live-sources-<hash>.md`,
`recent-changes-<hash>.md`, `SKILL-<hash>.md`).

To read a compressed asset, decompress zstd frames from the native binary and keep the one whose
text matches. Each frame starts with the magic bytes `28 b5 2f fd`:

```bash
python3 -I - ~/.local/share/claude/versions/<version> <out-dir> <<'EOF'
import mmap, re, subprocess, sys
path, out = sys.argv[1:]
with open(path, 'rb') as f:
    m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    starts = [x.start() for x in re.finditer(rb'\x28\xb5\x2f\xfd', m)] + [len(m)]
    for a, b in zip(starts, starts[1:]):
        r = subprocess.run(['zstd', '-dcq'], input=m[a:min(b, a + 5_000_000)],
                           capture_output=True)
        if r.stdout.lstrip().startswith(b'# Plugin eval'):
            open(f'{out}/frame_{a}.md', 'wb').write(r.stdout)
EOF
```

The uncompressed files sit in the binary as plain text; search for a heading such as
`# Live Documentation Sources` or `# Claude Tag (Claude in Slack)`.

## Re-verify

- `□` The SDK entrypoint exclusion is still in the default agent list, and `-p` still maps to
  `sdk-cli`.
- `□` The guide's model is still `haiku`, its mode `dontAsk`, and its tool list has no MCP or Skill
  entries.
- `□` The four doc URLs are unchanged.
- `□` The embedded plugin eval reference is still present in the guide's prompt.
- `□` `claude-code-docs` is still gated by `tengu_birch_kettle`, default `false`.
- `□` The skill's `SKILL_FILES` map still has the five reference paths.
