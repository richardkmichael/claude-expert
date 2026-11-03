# `@` Mentions to Context

Verified against: cli.prettier.js 2.1.317 (2026-11-03)

How the `@` mentions in a submitted prompt become context for the model: which tokens count as
mentions, what each kind is turned into, the limits and permission checks on the way, and how each
result is rendered. Completion (what the `@` menu offers, the file index, ranking, TAB/ENTER) is in
`FILE_INCLUSION.md`. This doc follows the landmark style in `GUIDELINES.md`: anchors are literal
strings, attachment type names, `tengu_*` and outcome event names, env vars and settings keys.

## Where it runs

Mentions are turned into attachments by the per-turn attachment collector, the same pass that adds
ambient attachments (date, todo reminders, memory). Its mention producers are named, in order:
`at_mentioned_files`, `mcp_resources`, `agent_mentions`, `skill_mentions`, `peer_mentions` (grep
`"at_mentioned_files", () =>`; expect the five producer names together). They run concurrently; the
resulting attachments keep that order and precede the ambient ones. The `peer_mentions` producer
waits for the file results so it can skip names that resolved as files. A `tengu_attachments` event
records the types and token estimates of everything the pass produced.

The collector scans the prompt as submitted, after pasted-text placeholders are expanded, so an
`@path` inside pasted text is a mention too. Peer and skill mentions instead read the typed text
before expansion (`preExpansionInput`) and run only for a human-typed prompt.

No mention attachments are produced when:

- `CLAUDE_CODE_DISABLE_ATTACHMENTS` or `CLAUDE_CODE_SIMPLE` (set by `--bare`) is on. The collector
  then returns only queued commands and a few fixed items, and `@` tokens reach the model as plain
  text.
- The prompt runs in bash mode (`!`).
- The prompt starts with `/` and runs a slash command. The command processor asks for mention
  attachments only when it hands the text on as a plain prompt (`extractPromptAttachments`).
- `CLAUDE_CODE_EVAL_CONFINED` is set: file and MCP-resource mentions are skipped (an evaluation
  mode).

When a `prompt.submit` mod hook rewrites the prompt, the mention attachments of the original text
are dropped and recomputed from the rewritten text (the producers run with `inputMentionsOnly`).

## Token extraction

All mention regexes share a left boundary: start of text, whitespace, or one of the CJK punctuation
marks U+3002, U+3001, U+FF1F and U+FF01 (`。、？！`; the bundle spells them as escapes, so grep
`"\u3002\u3001\uFF1F\uFF01"`; the boundary class is built from it). An `@` inside a word, as in
`user@example.com`, is never a mention.

File mentions (grep `@"([^"]+)"` for the quoted form):

- Quoted: `@"<anything but a quote>"`. Mentions ending in ` (agent)` are excluded here; they are
  agent mentions.
- Unquoted: each whitespace-separated word whose `@` sits at the word start or after one of the CJK
  marks. The mention runs from after the `@` to the end of the word, minus any trailing run of
  characters outside `[A-Za-z0-9_]`. So `@src/` yields `src`, `@notes.md,` yields `notes.md`, and
  `@config.yaml)` yields `config.yaml`. A name that ends in a non-ASCII letter loses it (`@café`
  yields `caf`); the quoted form avoids that.
- The list is deduplicated. Agent tokens (`@agent-…`) and `server:uri` tokens are on it too; they
  fail as files and are dropped without a message.

Line ranges and fragments: the mention is parsed with `^([^#]+)(?:#L(\d+)(?:-(\d+))?)?(?:#[^#]*)?$`
(grep `#L(\d+)(?:-(\d+))?`). `@file#L10-20` reads lines 10 to 20 (offset 10, limit 11), `@file#L10`
reads line 10 alone, and any other `#fragment` is ignored (`@notes.md#intro` reads all of
`notes.md`). A reversed range (end before start) was not traced through the Read tool's validation.

MCP resource mentions use the same word scan, but need a `:` at least one character after the `@`
and at least one character after the colon. The text before the first colon is the server name; the
rest is the URI. The trailing-character trim applies here too, so a URI ending in `/` or `)` does
not match its listed form.

Agent mentions (grep `\(agent\)"` and `@(agent-[\w:.@-]+)`):

- `@"<agentType> (agent)"`, the form the completion menu inserts;
- `@agent-<agentType>`, with `agentType` from `[\w:.@-]` (plugin-scoped names such as
  `my-plugin:reviewer` work).

Peer mentions are described under "Peer and teammate mentions".

## Files

Producer: `at_mentioned_files`. For each mention, in parallel:

1. The path is resolved: `~` and `~/…` expand to the home directory, a relative path resolves
   against the session's current working directory, an absolute path is used as is.
2. Permission check. A path that a `Read` deny rule matches is dropped, as is a UNC/network path
   (`tengu_attachment_unc_read_blocked`). With `--restricted` or
   `permissions.blockReadsOutsideWorkingDirectories`, a path outside the working directories is
   dropped the same way. There is no allow check and no prompt: a mentioned file outside the project
   is read without asking unless one of those applies. Outcome events: `input_file_at_mention` with
   `denied`.
3. Symlinks. Normally the read follows links like any Read call. When the session has read deny
   rules, `--restricted`, or `permissions.blockReadsOutsideWorkingDirectories`, every spelling of
   the path through its link chain is resolved first and the mention is dropped if any spelling is
   denied or outside (`denied_at_landing`). If the chain cannot be resolved in time, the mention
   becomes an unread reference (`landing_unsettled`, `unread: "unexamined"`).
4. A directory becomes a `directory` attachment (below).
5. A file is read through the `prompt.mention` mod hook chain, then the reader below.

### The reader

Grep `tengu_at_mention_extracting_filename_success`; the reader takes it and the `_error` name as
arguments. In order:

- PDF still downloading (a file attached to a queued message): `pdf_reference` with `stillArriving`.
- Size cap: any non-PDF file over `maxSizeBytes` (262144 bytes, 256 KB) is not read
  (`tengu_attachment_file_too_large`). The cap is not overridable; only the token cap below has an
  env var. What the model then gets depends on the extension: a file with an extension that is not
  on the binary-extension list (images, audio, video, archives, office documents, fonts and so on)
  and is not a notebook becomes an `at_mention_reference` with `unread: "too_large"`. An oversized
  image, binary, `.ipynb`, or file with no extension at all (`LICENSE`, `Makefile`) is dropped with
  nothing sent to the model.
- PDF: a PDF over 10 pages (or, with no page count, over about 1 MB at 100 KB a page), or any PDF
  for a model that reads PDFs only as page images (the claude-3 models), becomes a `pdf_reference`
  with page count and size (`tengu_pdf_reference_attachment`). A smaller PDF is read whole.
- Already in context: if the session's file-read state holds a full, unchanged read of the file
  (same mtime, not a partial view, content still in the model's context), the result is
  `already_read_file`. It shows `Read <path>` in the transcript but sends nothing to the model. A
  line range does not bypass this.
- Otherwise the Read tool is called directly (no tool_use, no `PreToolUse` hooks, no permission
  prompt) with the line range if any. Text, images, notebooks and PDFs come back in the Read tool's
  own result shapes. The read records the file in the session's read state, so a later Edit needs no
  fresh Read, and it adds the path as a nested-memory trigger (below).
- Over the token cap (`CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS`, default 25000) or truncated by it:
  the file is re-read as its first 2000 lines and attached with `truncated: true`. If that read also
  fails, the mention is dropped.
- Any other read error drops the mention; only telemetry records it.

Outcome events on `input_file_at_mention`: success, `too_large`, `denied`, `denied_at_landing`,
`landing_unsettled`, `refused_at_open`.

### Nested memory

Each mentioned file read through the Read tool is pushed onto the nested-memory triggers, and the
collector's `nested_memory` producer then loads `CLAUDE.md` files from the directories between the
working directory and that file (see `MEMORY_SYSTEM.md`). `CLAUDE_CODE_DISABLE_CLAUDE_MDS` turns
this off.

### Directories

`@dir` becomes `{ type: "directory", path, content }`
(`tengu_at_mention_extracting_directory_success`, `input_dir_at_mention`). The content is one level
of `readdir` names, newline-separated, in `readdir` order with no sorting, no type markers and no
trailing slash. Hidden entries are listed. Entries the read checks refuse (a `Read` deny rule, or
outside the working directories under the read block) are left out. At most 1000 names are listed
from the first 10000 entries, then a line `… and N more entries`. A directory that a deny rule
covers is skipped (`input_dir_at_mention` `denied`); a `readdir` failure drops it
(`tengu_at_mention_extracting_directory_error`, `readdir_failed`).

## Rendering to the model

Grep `The user @-mentioned` for the reference texts and `Lists files in ` for the directory form.

- `file` (text, image, notebook, PDF): a synthetic `Read` tool_use with `file_path`, then a
  tool_result holding the Read output. With `truncated`, also
  `Note: The file … was too large and has been truncated to the first 2000 lines.`
- `already_read_file`: nothing.
- `directory`: a synthetic `Bash` tool_use, `ls <path>` with description `Lists files in <path>`,
  and a tool_result whose stdout is the listing.
- `at_mention_reference` with `unread: "too_large"`:
  `The user @-mentioned <path> (<size>). Its contents were not attached because …`, the file being
  too large to read at once, then how to read it in portions or with `allow_large`.
- `at_mention_reference` with `unread: "unexamined"`:
  `The user @-mentioned <paths>. They could not be examined and were not attached: …`
- `at_mention_reference` with no `unread`:
  `The user @-mentioned <paths>. File contents are not attached automatically in this session: …`
- `pdf_reference`: `PDF file: <path> (N pages, <size>).` and instructions to read it with `pages`
  ranges, at most 20 pages a call.
- `mcp_resource`: `Full contents of resource:` and the text, `[Binary content: <mime>]` for a blob,
  or `<mcp-resource server=… uri=…>(No content)</mcp-resource>`.
- `agent_mention`: `The user has expressed a desire to invoke the agent "<type>".`, followed by a
  request to invoke it with the required context.
- `peer_mention`: `The user @-mentioned the Claude session "…"` when resolved, or
  `The user wrote …, which matches N Claude sessions:` when ambiguous.

A `file` attachment flagged `overTokenLimit` (set only on host-supplied content, see "Disabled file
mentions") is rendered as a plain `at_mention_reference` instead when the account cannot spend
long-context credit.

The transcript shows its own lines: `Read <path>`, `Listed directory <path>/`,
`Referenced <path> (not read: too large, <size>)`,
`Referenced <paths> (not read: could not be examined)`, `Referenced PDF <path> (N pages)`.

## Disabled file mentions

With `CLAUDE_CODE_DISABLE_FILE_MENTIONS` (boolean; blocked in project and local settings) or the
host's `disableFileMentions` launch option, Claude Code does not open mentioned paths. If the host
supplied content for a mentioned file, it is attached as a `file` (subject to a 256 KB budget shared
across the prompt's mentions and the token cap, with the 2000-line fallback); otherwise the paths,
files and directories alike, go into one `at_mention_reference` with no `unread`, so the model is
told to read them with its tools. Those tool calls then pass through `PreToolUse` hooks and
permissions as usual.

## The `prompt.mention` mod hook

Each file mention's read runs through the `prompt.mention` event of the mods hook chain (grep
`"prompt.mention"`; the read helper lives in a lazily loaded chunk exporting `readThroughMention`).
The event carries `mention`, `path`, optional `offset` and `limit`, and `agentId`. A hook can deny
it (`{ deny: reason }`), pass on a different absolute `path`, `offset` or `limit`, or add context.
Added context becomes a `hook_additional_context` attachment with `hookName: "prompt.mention"` and
`hookEvent: "UserPromptSubmit"`. A read the chain does not keep is undone in the read state. A hook
may not redirect to a path a deny rule covers (`the path may not be read here`). A failing chain
attaches nothing and logs `the hooks' chain failed`. With hooks off for the session
(`settingsHooksOff`), the file is read directly. See `MODS.md` for mods in general.

## MCP resources

Producer: `mcp_resources`. For `@server:uri`, the server must be connected and its listed resources
must contain that exact URI; otherwise nothing is attached (`tengu_at_mention_mcp_resource_error`).
Some servers' resources are withheld outright, for example the Artifacts MCP server
(`Claude Code doesn't read its resources. Use its tools.`). A resource of an MCP skill that the
skill does not list is not read (log `MCP resource … not read:`). The read is a normal
`resources/read` (context `MCP @-mention resource read`); failures log
`MCP resource read failed for`. Success emits `tengu_at_mention_mcp_resource_success`.

## Agents

Producer: `agent_mentions`. Each agent token is looked up among the active agent definitions by
`agentType`, after removing the first `agent-` in the token. That suits `@agent-<type>`, but for the
quoted `@"<type> (agent)"` form it also strips an `agent-` inside the type: a type such as
`code-agent-reviewer` is looked up as `code-reviewer` and not found. Found:
`{ type: "agent_mention", agentType }` and `tengu_at_mention_agent_success`; not found:
`tengu_at_mention_agent_not_found` and nothing attached. The attachment is an instruction to the
model, not a forced dispatch. `tengu_subagent_at_mention` records whether the prompt was only the
mention (`is_subagent_only`) or started with it (`is_prefix`).

Telemetry for agent and MCP mentions stops after 100 of each per prompt; the excess is counted in
`tengu_at_mention_unreported`. The OpenTelemetry `at_mention` event carries `mention_type` `file`,
`directory`, `agent`, `mcp_resource` or `peer`, and `success`.

## Peer and teammate mentions

Peer sessions (cross-session messaging). Producer: `peer_mentions`, gated on the messaging switch:
`CLAUDE_CODE_HARBOR_KITE` when set, else the `tengu_harbor_kite` flag (default on;
`tengu_harbor_kite_win` also on Windows), and off when the host sets
`messagingBeyondOwnAgentsDisabled`. The submit regex accepts `@name` with `[\w-]{1,128}`, or
`@"name"` up to 200 characters, each optionally followed by ` [ref]` with a 6 to 12 digit hex ref.
Names containing quotes, `<`, `>`, line breaks or a bracketed hex ref, starting with `agent-` or
ending in `(agent)` are not peer names. A name that also resolved as a mentioned file or directory
is skipped. Candidates come from live sessions on this machine, cloud sessions and bridge sessions;
the session's own subagents and teammates are excluded, as are sessions known only by a default
name. Telemetry is `tengu_at_mention_peer_` plus `success`, `ask` or `not_found` (built from a
template, so grep the prefix). Results:

- with a ref that matches a candidate, or a single candidate by name: `peer_mention` with
  `status: "resolved"`; the model is told it may message that session with `SendMessage` using the
  exact `name [ref]` token, and only if asked;
- several candidates: `status: "ask"` with up to 3 listed and the total; the model is told to
  confirm with the user first;
- a ref with no match: nothing attached.

Agent-team teammates. With agent teams on (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` or
`--agent-teams`), a prompt of the form `@<teammate> <message>` (name from `[\w-]`) whose name is a
current teammate is not sent to the model: the message is written to that teammate's mailbox, the
input is cleared and `Sent to @<name>` is shown (`input_at_member_message`). An unknown name falls
through to a normal prompt.

Skill mentions (`skill_mention`) are a `/skillname` form, not `@`, and are not covered here.

## Published-docs drift

Checked against `common-workflows` ("Reference files and directories"), `interactive-mode`,
`sub-agents` ("Invoke subagents explicitly"), `cross-session-messaging`, `mcp`, `monitoring-usage`
("At mention event") and `agent-sdk/modifying-system-prompts`.

- Size limit. The docs say a text file over 256 KB isn't included and a file is included when it
  fits the Read token limit. In the source the 256 KB cap applies to every non-PDF file, images
  included, and an oversized image or binary is dropped with nothing sent; an oversized text file
  becomes a `too_large` reference telling the model how to read it. A text file over the token limit
  is not left out but attached as its first 2000 lines.
- Line ranges. `@file#L10-20` and `@file#L10` are supported; the docs do not mention them.
- Trailing punctuation. Undocumented: an unquoted mention loses trailing characters outside
  `[A-Za-z0-9_]`, including non-ASCII letters.
- Already-read files. Undocumented: a mention of a file already fully read and unchanged sends
  nothing new to the model.
- Subagent mentions. `sub-agents` says an @-mention "guarantees the subagent runs". The source adds
  a meta message asking the model to invoke the agent; it does not dispatch it. The quoted-form
  `agent-` stripping is undocumented.
- Peer typeahead. `interactive-mode` says `@` suggests "your other live sessions on this machine";
  the candidates also include cloud and bridge sessions.
- `at_mention` OTel event. `monitoring-usage` lists PDF reference attachments among the paths that
  return without logging; a `pdf_reference` from the reader logs `mention_type: "file"` with
  `success: true`. The 100-per-type cap for agents and MCP resources matches.
- Matches: `PreToolUse` hooks do not run for an `@` read; a `Read` deny rule blocks it;
  `CLAUDE_CODE_DISABLE_FILE_MENTIONS` turns mentions into paths plus a read-it-yourself note and is
  ignored in project and local settings; `CLAUDE_CODE_DISABLE_ATTACHMENTS` leaves `@` as plain text;
  mentioned files pull in their directories' `CLAUDE.md`; directory mentions list names, not
  contents; the `prompt.mention` mod event exists as described.

## Search strategy

1. `"at_mentioned_files", () =>`: the producer list and the gates above it
   (`CLAUDE_CODE_DISABLE_FILE_MENTIONS`, `CLAUDE_CODE_EVAL_CONFINED`).
2. `#L(\d+)(?:-(\d+))?`: the line-range parser; the file-token extractor sits just above it.
3. `tengu_at_mention_extracting_filename_success`: the per-mention resolver and the reader call.
4. `tengu_attachment_file_too_large` and `tengu_pdf_reference_attachment`: the reader's size and PDF
   branches; `already_read_file` follows.
5. `The user @-mentioned`: the model-facing texts; `Lists files in ` for directories.
6. `MCP @-mention resource read`: the MCP producer.
7. `The user has expressed a desire to invoke the agent`: the agent renderer.
8. `tengu_at_mention_peer_` and `The user @-mentioned the Claude session`: peer mentions.
9. `input_at_member_message`: the teammate direct-message path.
10. `readThroughMention` and `"prompt.mention"`: the mod hook chain.

Tripwires:

- [ ] mention producers are exactly the five names, in that order
- [ ] unquoted mentions trim trailing characters outside `[A-Za-z0-9_]`
- [ ] `maxSizeBytes` default 262144; token cap default 25000; fallback 2000 lines
- [ ] PDFs over 10 pages become `pdf_reference`
- [ ] directory listing caps 1000 shown of 10000 examined
- [ ] the mention reader calls the Read tool without a permission check or `PreToolUse` hooks
- [ ] agent lookup strips the first `agent-` from both mention forms
