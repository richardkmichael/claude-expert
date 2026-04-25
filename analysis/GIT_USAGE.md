# Claude Code Git Usage in System Prompts

Source: `cli.prettier.js` 2.1.104 (`work/2.1.104/package/cli.prettier.js`)

## Key Finding

The heavy git behavioral instructions -- the Git Safety Protocol, commit workflow, PR workflow, and attribution -- are carried by the Bash tool's `description` field, not the main system prompt. A shorter "For git commands:" block sits higher up in the same Bash description, and this shorter block is NOT affected by the disable-instructions switch.

This means git instructions are invisible if you only examine the system prompt text; they are embedded in the tool definition passed via the `tools` API parameter.

## The Disable Switch -- `oR8()`

Several of the fragments below are conditional on `oR8()` (line 255725). It reads an env var and a config key:

```js
[source fragment removed]
```

Each section below states explicitly whether its fragment is gated by this switch. When a section says "When `oR8()` returns false", that means one of:

- `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` is set to a truthy value in the environment, OR
- `includeGitInstructions: false` is set in the user config.

## Where Git Appears in Prompt-Relevant Code

### 1. Bash Tool Description -- `Dr4()` / `Wr4()`

The Bash tool description function `Dr4()` (line 360267) builds the full tool description. It composes a main body and, at the end, optionally appends the output of `Wr4()` (line 360089):

```js
[source fragment removed]
```

`Wr4()` contains three sections:

- "Committing changes with git" -- step-by-step commit workflow with the Git Safety Protocol
- "Creating pull requests" -- step-by-step PR workflow using `gh`
- "Other common operations" -- one-liner for viewing PR comments

Full rendered text: see `PROMPTS_RENDERED.md`, section "Bash Tool Description".
Analysis and source references: see `PROMPTS.md`, section "Prompt Content in Tool Descriptions".

When `oR8()` returns false: `Wr4()` returns an empty string at its first line, so nothing is appended. The Git Safety Protocol, commit workflow, PR workflow, and the `gh pr create` template are all removed from the model's view. The `Co-Authored-By:` trailer computation (via `GS6()` -- see "Commit Attribution" below) is unreachable.

### 2. Git Status Context Injection -- `xU1()`

At conversation start, the current git status is captured and injected into the first user message as a `<system-reminder>` block. This is informational context only -- it tells the model what branch it's on and what files are changed, but contains no behavioral instructions.

`xU1()` is defined at line 255751 (cached via `$1(async () => { ... })`). It produces lines like:

```
gitStatus: This is the git status at the start of the conversation. Note that this status is a snapshot in time, and will not update during the conversation.
Current branch: [BRANCH]

Main branch (you will usually use this for PRs): [MAIN_BRANCH]

Git user: [USER]

Status:
[git status --short output]

Recent commits:
[git log --oneline -n 5]
```

The invocation that gates the injection is at line 255823:

```js
[source fragment removed]
```

When `oR8()` returns false: `xU1()` is not called and no `gitStatus:` block appears in the first user message. Also skipped for remote sessions when `CLAUDE_CODE_REMOTE` is set. When included, truncated at 40k characters.

See `PROMPTS.md`, section "Context Injection" and `PROMPTS_RENDERED.md`, section "Context Injection".

### 3. Plan Mode Agent Restrictions

Agents spawned with restricted Bash use (Explore agent `f6z()` at line 248970, Plan agent `v6z()` at line 249061) receive system prompts that enumerate safe vs forbidden Bash commands. Lines 249001-249002 (Explore) and 249088-249089 (Plan) are nearly identical:

```
- Use Bash ONLY for read-only operations (ls, git status, git log, git diff, find, cat, head, tail)
- NEVER use Bash for: mkdir, touch, rm, cp, mv, git add, git commit, npm install, pip install, or any file creation/modification
```

These are in the subagent system prompts, not the main system prompt.

When `oR8()` returns false: no effect. The subagent prompts are independent of `oR8()` and still mention these git commands as examples.

### 4. Bash Tool Description -- Inline Git Example

Inside `Dr4()` at line 360285, as part of the multi-command guidance (array `z`, rendered under a "When issuing multiple commands:" header):

```
If the commands are independent and can run in parallel, make multiple Bash tool calls in a single message. Example: if you need to run "git status" and "git diff", send a single message with two Bash tool calls in parallel.
```

This is about command chaining patterns, not git-specific behavior.

When `oR8()` returns false: no effect. This line is in the main body of `Dr4()`, which is not gated.

### 5. Bash Tool Description -- "For git commands:" Short Block

Inside `Dr4()` at lines 360290-360293, array `Y`, rendered under the header `"For git commands:"` at line 360327. The bullets are defined as:

```js
[source fragment removed]
```

Four lines total once rendered: the header plus three bullets.

When `oR8()` returns false: no effect. This block is in the main body of `Dr4()`, above the `Wr4()` append point, and is not gated. It is the primary piece of git guidance the model retains when the disable switch is set -- three rules (prefer new commits, avoid destructive ops, don't bypass hooks) survive even with the large workflow block removed.

### 6. PowerShell Tool Description -- Git References

On Windows, the Bash-equivalent tool description is built by `vc4()` at line 346923. It mirrors the short "For git commands:" block at lines 347000-347003 and additionally contains PowerShell-specific git examples:

- Line 346957: prohibition on `git rebase -i`, `git add -i` (interactive editors).
- Lines 346962-346966: here-string commit-message example (`git commit -m @'...'@`).
- Line 346968: stop-parsing-token example (`git log --% --format=%H`).

When `oR8()` returns false: no effect. `vc4()` is not gated, so Windows users retain both the "For git commands:" mirror and the PowerShell-specific examples even with the switch set. (The bigger `Wr4()` commit/PR workflow text does not have a PowerShell counterpart -- Windows users never receive it.)

### 7. Sandbox / Deny-Rules Prompt

The sandbox prompt and user-deny rules (around line 363018) classify `git add && git commit` / `git push` as analogous to code execution for risk analysis, and list `git push --force` and remote branch deletion under "Git Destructive".

When `oR8()` returns false: no effect. The sandbox prompt is not gated.

### 8. Auto-Memory Prompt

The auto-memory system prompt (lines 478122, 478147) tells the model that `git log` / `git blame` are authoritative for history and recent changes -- part of the "what NOT to save in memory" guidance.

When `oR8()` returns false: no effect. The auto-memory prompt is not gated.

## Git Safety Protocol (inside `Wr4()`)

The full protocol, from `Wr4()` starting at line 360098:

- NEVER update the git config
- NEVER run destructive git commands (push --force, reset --hard, checkout ., restore ., clean -f, branch -D) unless the user explicitly requests
- NEVER skip hooks (--no-verify, --no-gpg-sign, etc) unless the user explicitly requests
- NEVER run force push to main/master, warn the user if they request it
- CRITICAL: Always create NEW commits rather than amending, unless explicitly requested. Pre-commit hook failure means the commit didn't happen, so --amend would modify the wrong commit
- When staging files, prefer specific files by name rather than "git add -A" or "git add ."
- NEVER commit changes unless the user explicitly asks

When `oR8()` returns false: the entire protocol disappears along with the rest of `Wr4()` (section 1). The short block in section 5 still survives and covers destructive ops, hook-skipping, and amend-vs-new-commit in condensed form.

## Commit Attribution

The commit and PR attribution text is generated by `GS6()` (line 359283), called from within `Wr4()`. The attribution is surface-dependent and configurable.

### Default (CLI and most surfaces)

Commit: `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
PR footer: `[robot emoji] Generated with [Claude Code](https://claude.com/claude-code)`

The model name in the commit trailer is resolved dynamically in `GS6()`:

- `uK()` (line 118870) returns the current model ID
- `N76()` (line 118957) maps model IDs to display names (e.g., "Opus 4.6", "Sonnet 4.5", "Haiku 4.5")
- `Vf1()` (line 118991) prefixes with "Claude " to produce e.g. "Claude Opus 4.6"
- If working in an internal Anthropic repo (`BI4()` at line 309705, which checks an `X68` variable populated by the internal-repo detection), `GS6()` uses the actual model name via `Vf1(uK())`
- Otherwise `GS6()` falls back to the literal `"Claude Opus 4.6"` (line 359297)

### Remote sessions (claude.ai/code)

If `CLAUDE_CODE_REMOTE_SESSION_ID` and `SESSION_INGRESS_URL` are available (and not localhost), `GS6()` uses a session URL for both commit and PR attribution: `https://[ingress]/code/[session_id]` (lines 359284-359293).

If no session URL is available: empty strings (no attribution).

### User configuration overrides

Inside `GS6()` at lines 359300-359303:

- `config.attribution.commit` -- custom commit trailer string
- `config.attribution.pr` -- custom PR footer string
- `config.includeCoAuthoredBy === false` -- disables all attribution

When `oR8()` returns false: `GS6()` is unreachable from the Bash tool description path because its only caller is `Wr4()`, which returns empty. Attribution trailers are neither computed nor shown in the prompt.

## Implications

### For reproducing the system prompt

The git instructions are only available if you include a Bash tool with the `Wr4()` content (and the short "For git commands:" block from `Dr4()`) in its description. If you're reproducing the Claude Code experience outside of it (e.g., using the Anthropic API directly), you need to either:

1. Embed the git instructions in your Bash tool description (matching how Claude Code does it), or
2. Move them into your system prompt text (which Claude Code does not do)

### For subagents

Subagents spawned via the Task tool do not receive the Bash tool with the full `Wr4()` content; they get a more restricted system prompt (section 3). The main agent's git instructions explicitly prohibit using TodoWrite or Task tools during commit and PR operations: "NEVER use the TodoWrite or Task tools". This prevents the main agent from delegating git operations to subagents.

### Entanglement

The Bash tool description is a single dynamically-generated string. The git sections (`Wr4()`) are concatenated to the end of the core Bash usage instructions (`Dr4()`), gated by `oR8()`. The commit attribution (`GS6()`) is computed inside `Wr4()`, making the description vary based on:

- Current model ID (affects Co-Authored-By name)
- Execution surface (`remote` vs others -- affects attribution format)
- Whether the repo is an internal Anthropic repo (affects model name resolution)
- User config (`attribution`, `includeCoAuthoredBy`, `includeGitInstructions` settings)
- `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS` env var

There is no mechanism to include the full workflow git instructions without the Bash tool, or to include the Bash tool without the short "For git commands:" block.
