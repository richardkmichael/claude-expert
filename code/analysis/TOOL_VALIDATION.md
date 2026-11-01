# Tool Validation

Behavioral model verified against 2.1.165. This document follows the landmark style in
`GUIDELINES.md`: it anchors on version-stable strings (user-facing error messages, class names,
`tengu_*` names, tool names, behavioral logic) with grep re-location recipes, not on minified symbol
names or line numbers, which churn every release. Error-message strings are the durable anchors here;
numeric `errorCode` values are a weaker contract and are shown as current 2.1.165 values. Per-release
changes are in the appendix.

## Validation architecture

Validation is tool-specific, not generic. Two tiers run per tool call:

1. Schema validation (generic). The tool's input is checked against its Zod schema. On failure the
   call short-circuits with a result carrying `is_error` and a `<tool_use_error>InputValidationError:
   ...</tool_use_error>` body. Grep `InputValidationError` and `<tool_use_error>`.

2. Input validation (per-tool). Each tool has an `async validateInput(...)` returning
   `{ result, message?, behavior?, errorCode?, meta? }`. On `result: false` the call short-circuits
   with a `<tool_use_error>${message}</tool_use_error>` body. This is where business-logic checks
   (file state, permissions, string matching) live.

There is no shared validation framework — each tool implements its own `validateInput` with its own
reasons and codes.

## Per-tool validateInput

Locate each by a distinctive message string, then read the enclosing `validateInput`. The Read, Edit,
and Write tools are distinguished by their destructured parameters: Read `{ file_path, pages }`; Edit
`{ file_path, old_string, new_string, replace_all }` with a `readFileState` context; Write
`{ file_path, content }` with `readFileState` / `agentId` context. NotebookEdit reuses several of the
same messages — disambiguate by the parameter shape.

### Read

Destructures `{ file_path, pages }`. Note: existence (`File does not exist.`) is enforced in the read
path, not in `validateInput`; size and empty-image checks also live in the read path now, not here.
A UNC path (`\\` or `//` prefix) returns success before the binary/device checks.

| Reason (message anchor)                                                      | code |
|------------------------------------------------------------------------------|------|
| `Invalid pages parameter: "…". Use formats like "1-5", "3", or "10-20".`     | 7    |
| `Page range "…" exceeds maximum of 20 pages per request.`                    | 8    |
| `File is in a directory that is denied by your permission settings.`         | 1    |
| `This tool cannot read binary files.`                                        | 4    |
| `Cannot read '…': this device file would block or produce infinite output.`  | 9    |

### Edit

Destructures `{ file_path, old_string, new_string, replace_all }`, context carries `readFileState`.
Every failure branch carries `behavior: "ask"`. Codes 6/8/9 also attach a `meta` (`isFilePathAbsolute`,
plus `actualOldString` on 9). The two dynamic-message guards (codes 12 and 0) come first.

| Reason (message anchor)                                                      | code |
|------------------------------------------------------------------------------|------|
| worktree / background-session isolation guard (dynamic message)             | 12   |
| content guard (dynamic message)                                             | 0    |
| `No changes to make: old_string and new_string are exactly the same.`        | 1    |
| `File is in a directory that is denied by your permission settings.`         | 2    |
| `File is too large to edit (…). Maximum editable file size is …` (1 GiB)      | 10   |
| `File is read-only — it has not been opened for edit in Perforce.`           | 11   |
| `File does not exist.` (+ optional ` Did you mean …?`)                        | 4    |
| `Cannot create new file - file already exists.`                              | 3    |
| `File is a Jupyter Notebook. Use the … to edit this file.`                    | 5    |
| `File has not been read yet. Read it first before writing to it.`            | 6    |
| `File has been modified since read, either by the user or by a linter. …`     | 7    |
| `String to replace not found in file.`                                       | 8    |
| `Found N matches of the string to replace, but replace_all is false. …`      | 9    |

### Write

Destructures `{ file_path, content }`, context carries `readFileState` and `agentId`. ENOENT (file
absent) returns success — Write creates new files.

| Reason (message anchor)                                                      | code |
|------------------------------------------------------------------------------|------|
| worktree / background-session isolation guard (dynamic message)             | 7    |
| `Subagents should return findings as text, not write report files. …`        | 5    |
| content guard (dynamic message)                                             | 0    |
| `File is in a directory that is denied by your permission settings.`         | 1    |
| `File is read-only — it has not been opened for edit in Perforce.`           | 6    |
| `File has not been read yet. Read it first before writing to it.`            | 2    |
| `File has been modified since read, either by the user or by a linter. …`     | 3    |

The Write subagent-report block fires only for subagents (`agentId` present) writing a file whose
basename matches `REPORT|SUMMARY|FINDINGS|ANALYSIS*.md` (case-insensitive); it also emits the
`tengu_subagent_md_report_blocked` telemetry event. The Write "modified since read" check has a
fast path: a full-file read whose content still matches is allowed through.

Re-location: grep a distinctive message, e.g. `rg -n 'No changes to make'` (Edit),
`rg -n 'Subagents should return findings'` (Write), `rg -n 'this device file would block'` (Read).
Disambiguate shared messages (`File has not been read yet`, `File has been modified since read`,
the Perforce message) by the surrounding parameter shape.

## Error handling architecture

Tools fall into two categories with different error patterns.

### Process-based tools (Bash, Grep/Search, MCP)

These spawn processes and signal failure by throwing a custom ShellError. Anchor on the constructor
message `Shell command failed` and the class name `ShellError`. The error object carries `stdout`,
`stderr`, `code`, `interrupted`, and `hadSandboxViolation`. Grep `Shell command failed`.

- Bash tool: drives the bash generator, computes an is-error verdict from the command, exit code,
  stdout, and stderr, and throws the ShellError on failure (passing the sandbox-violation flag). See
  `BASH_TOOL_EXECUTION.md` for the execution model.
- Grep/Search tool: ripgrep-backed. Description anchored on `A powerful search tool built on ripgrep`
  (wording unchanged across recent versions; it interpolates the Grep / Bash / Agent tool names).
  Binary resolution is in `FILE_INCLUSION.md` ("Ripgrep Binary Selection").
- MCP tools: flagged in telemetry via an `isMcp` field; grep `isMcp`.

### File-based tools (Read, Edit, Write, NotebookEdit)

These do direct file-system operations and do not throw during execution — their only failures are
`validateInput` returns. Consequence: a PostToolUse hook never fires on a file-tool validation
failure, because there is no execution phase to wrap.

### Error-message formatter

Errors surfaced to the user pass through a formatter that caps length at 10 KB (10000 chars). On
overflow it keeps the first 5000 and last 5000 chars joined by `... [N characters truncated] ...`.
Grep `characters truncated`.

## Hook enhancement (design notes)

These are notes on a proposed local enhancement, not current Claude Code behavior.

Core finding: validation failures and execution errors short-circuit before hooks get full context.
File-tool validation failures never reach PostToolUse (no execution phase). For process-tool
failures, the error catch historically preserved only the error message, discarding the ShellError's
`stdout` / `stderr` / `code`.

Proposed direction:
- PreToolUse: pass a validation context (schema result + input-validation result with message and
  code) so hooks can react to specific validation failures.
- PostToolUse: add a `tool_execution` property alongside `tool_response`, carrying `success`,
  `duration_ms`, and on failure `error_message` (size-limited via the formatter above), `error_type`,
  and `details` lifted from the ShellError (`stdout`, `stderr`, `exitCode`, `interrupted`). Keep
  `tool_response` clean (null on failure).

Illustrative `tool_execution` shape for a failed process tool:

```json
{
  "tool_response": null,
  "tool_execution": {
    "success": false,
    "duration_ms": 234,
    "error_message": "Shell command failed: …",
    "error_type": "ShellError",
    "details": { "stdout": "", "stderr": "…", "exitCode": 5, "interrupted": false }
  }
}
```

To implement, re-locate the join points by stable anchors rather than line numbers: the PreToolUse
and PostToolUse runners (grep `PreToolUse` / `PostToolUse` near the tool-use pipeline), the per-tool
dispatch catch (grep the `<tool_use_error>` emission), and the ShellError class (grep
`Shell command failed`).

## Tripwire checklist (re-verify on a new version)

□ two tiers: Zod schema then per-tool `validateInput`; both short-circuit via `<tool_use_error>`
□ Read validates `pages`; existence/size/empty-image are not Read `validateInput` branches
□ permission-deny message is `…denied by your permission settings.` (not "ignored by your project
  configuration")
□ Edit failures all carry `behavior: "ask"`
□ Write blocks subagent `REPORT|SUMMARY|FINDINGS|ANALYSIS*.md` writes
□ ShellError carries `stdout/stderr/code/interrupted/hadSandboxViolation`, message
  `Shell command failed`
□ error formatter caps at 10 KB with first-5000 / last-5000 truncation

## Per-release notes

- 2.1.165: behavioral model above verified. Versus earlier builds: the "ignored directory" reason
  (string `File is in a directory that is ignored by your project configuration.`) was replaced by a
  permission-deny reason; Read's `validateInput` dropped the empty-image reason (string
  `Empty image files cannot be processed.` is gone) and the in-validate size check, and added PDF
  `pages` validation (codes 7/8) and a device-file reason (code 9); Edit added too-large (1 GiB
  limit), Perforce read-only, worktree/background isolation, and content-guard reasons, and now marks
  all failures `behavior: "ask"`; Write added a subagent report-file block, Perforce read-only,
  isolation, and content-guard reasons; ShellError gained the `hadSandboxViolation` field.
