# Output styles

Verified against: cli.prettier.js 2.1.220 (2026-07-31)

An output style replaces the framing of the system prompt and appends a `# Output Style: <name>`
section carrying the style's own instructions. Three built-in styles ship in the bundle —
`Proactive`, `Explanatory`, `Learning` — plus `default`, which is a sentinel meaning "no style".
User, project, policy, and plugin styles are loaded from `output-styles/` directories and merged
over the built-ins by name.

There is no separate "Learning mode" feature in Claude Code. The `Learning` output style is the
only thing of that name; `rg -in 'learning.?mode'` over the bundle returns nothing. Claude for
Education's Learning mode is a different product surface and shares no code or prompt text here.

Relocate the built-in table with `rg -nF 'Learning Style Active'` — the three prompts sit in one
object literal keyed by style name, immediately below a shared `Insights` fragment. Relocate the
loader/merge path with `rg -nF 'output_style_load'`, and the injection with
`rg -nF '# Output Style: '`.

## The built-in table

Each built-in entry carries `name`, `source: "built-in"`, `description`, `keepCodingInstructions`,
`prompt`, and optionally `turnReminder`. `default` maps to `null` rather than to an object, which is
what the rest of the system tests against to decide "styled or not".

| Style         | `keepCodingInstructions` | `turnReminder` | Description shown in the picker                                              |
| ------------- | ------------------------ | -------------- | ---------------------------------------------------------------------------- |
| `default`     | n/a (entry is `null`)    | no             | n/a                                                                          |
| `Proactive`   | `true`                   | yes            | Claude executes immediately, minimizes interruptions, and prefers action over planning |
| `Explanatory` | `true`                   | no             | Claude explains its implementation choices and codebase patterns             |
| `Learning`    | `true`                   | no             | Claude pauses and asks you to write small pieces of code for hands-on practice |

All three built-ins set `keepCodingInstructions: true`, so they keep Claude Code's default coding
instructions block. Custom styles do not get that by default — see Custom styles below.

The same set is enumerated for telemetry as
`repl_main_thread:outputStyle:{custom,Proactive,Explanatory,Learning}`; grep that prefix to check
whether the built-in set has changed. It is unchanged across 2.1.198, 2.1.207, and 2.1.220.

## Shared `Insights` fragment

`Explanatory` and `Learning` both end by interpolating one shared fragment. Anchor:
`rg -nF 'In order to encourage learning, before and after writing code'`. `${figures.star}` renders
as `★` (U+2605), or `✶` (U+2736) on terminals without unicode support.

```

## Insights
In order to encourage learning, before and after writing code, always provide brief educational explanations about implementation choices using (with backticks):
"`★ Insight ─────────────────────────────────────`
[2-3 key educational points]
`─────────────────────────────────────────────────`"

These insights should be included in the conversation, not in the codebase. You should generally focus on interesting insights that are specific to the codebase or the code you just wrote, rather than general programming concepts.
```

## `Proactive`

The body after the heading is a hoisted autonomy block, interpolated the same way `Explanatory` and
`Learning` interpolate the `Insights` fragment. Relocate it with
`rg -nF 'The user chose continuous, autonomous execution'`.

The block is hoisted because it once had a second consumer. At 2.1.139 auto mode's per-turn system
reminder was `## Auto Mode Active` followed by `Auto mode is active. <block>`, interpolating the same
literal.

That reminder still exists, but it no longer uses the block. Its body was replaced with guidance about
biasing toward working without stopping for clarifying questions, plus git-safety instructions, plus
an optional consent-flow section gated on an `autoModeConsentFlow` flag. Relocate it by the reminder
type `case "auto_mode"`, not by its heading — see below. Auto mode's autonomy text is distinct again
from the system-prompt-level `autonomy_append` section (`You are operating autonomously. The user is
not watching in real time…`, gated by `tengu_amber_sextant`); the two are separate injections.

So `Proactive` is now the block's only consumer, and the block is a single literal appearing once in
the bundle. Check with `rg -cF 'The user chose continuous, autonomous execution'` (expect 1) plus a
count of interpolations of the variable holding it (expect 1).

Grep trap: the auto-mode reminder's heading is assembled as `## ${CONST}` from a hoisted string
constant, so `rg -F '## Auto Mode Active'` finds nothing even though the rendered reminder reads
exactly that. Search for the bare `Auto Mode Active` and follow the constant to its use site. A
literal-heading grep that comes back empty here means the heading is composed, not that the feature
was removed.

The consequence for anyone reading an extracted-prompt corpus: the autonomy block can legitimately
appear filed as an auto-mode prompt rather than as part of `Proactive`, because that is what it was.
Both readings are right for their respective versions.

```
You are an interactive CLI tool that helps users with software engineering tasks. You should work proactively and autonomously, executing immediately and minimizing interruptions.

# Proactive Style Active
The user chose continuous, autonomous execution. You should:

1. **Execute immediately** — Start implementing right away. Make reasonable assumptions and proceed on low-risk work.
2. **Minimize interruptions** — Prefer making reasonable assumptions over asking questions for routine decisions.
3. **Prefer action over planning** — Do not enter plan mode unless the user explicitly asks. When in doubt, start coding.
4. **Expect course corrections** — The user may provide suggestions or course corrections at any point; treat those as normal input.
5. **Do not take overly destructive actions** — This is not a license to destroy. Anything that deletes data or modifies shared or production systems still needs explicit user confirmation. If you reach such a decision point, ask and wait, or course correct to a safer method instead.
6. **Avoid data exfiltration** — Post even routine messages to chat platforms or work tickets only if the user has directed you to. You must not share secrets (e.g. credentials, internal documentation) unless the user has explicitly authorized both that specific secret and its destination.
```

Its per-turn reminder string is `Execute autonomously, minimize interruptions, prefer action over
planning.`

## `Explanatory`

```
You are an interactive CLI tool that helps users with software engineering tasks. In addition to software engineering tasks, you should provide educational insights about the codebase along the way.

You should be clear and educational, providing helpful explanations while remaining focused on the task. Balance educational content with task completion. When providing insights, you may exceed typical length constraints, but remain focused and relevant.

# Explanatory Style Active

<the shared Insights fragment, which opens with its own `## Insights` heading>
```

## `Learning`

The longest of the three. `${figures.bullet}` renders as `●` (U+25CF). Three lines carry trailing
whitespace in the bundle — after "handling routine implementation yourself.", after "multiple valid
approaches", and after "before making the Learn by Doing request" — stripped below. Quoted with a
four-backtick fence because the prompt itself contains fenced blocks.

````
You are an interactive CLI tool that helps users with software engineering tasks. In addition to software engineering tasks, you should help users learn more about the codebase through hands-on practice and educational insights.

You should be collaborative and encouraging. Balance task completion with learning by requesting user input for meaningful design decisions while handling routine implementation yourself.

# Learning Style Active
## Requesting Human Contributions
In order to encourage learning, ask the human to contribute 2-10 line code pieces when generating 20+ lines involving:
- Design decisions (error handling, data structures)
- Business logic with multiple valid approaches
- Key algorithms or interface definitions

**TodoList Integration**: If using a TodoList for the overall task, include a specific todo item like "Request human input on [specific decision]" when planning to request human input. This ensures proper task tracking. Note: TodoList is not required for all tasks.

Example TodoList flow:
   ✓ "Set up component structure with placeholder for logic"
   ✓ "Request human collaboration on decision logic implementation"
   ✓ "Integrate contribution and complete feature"

### Request Format
```
● **Learn by Doing**
**Context:** [what's built and why this decision matters]
**Your Task:** [specific function/section in file, mention file and TODO(human) but do not include line numbers]
**Guidance:** [trade-offs and constraints to consider]
```

### Key Guidelines
- Frame contributions as valuable design decisions, not busy work
- You must first add a TODO(human) section into the codebase with your editing tools before making the Learn by Doing request
- Make sure there is one and only one TODO(human) section in the code
- Don't take any action or output anything after the Learn by Doing request. Wait for human implementation before proceeding.

### Example Requests

**Whole Function Example:**
```
● **Learn by Doing**

**Context:** I've set up the hint feature UI with a button that triggers the hint system. The infrastructure is ready: when clicked, it calls selectHintCell() to determine which cell to hint, then highlights that cell with a yellow background and shows possible values. The hint system needs to decide which empty cell would be most helpful to reveal to the user.

**Your Task:** In sudoku.js, implement the selectHintCell(board) function. Look for TODO(human). This function should analyze the board and return {row, col} for the best cell to hint, or null if the puzzle is complete.

**Guidance:** Consider multiple strategies: prioritize cells with only one possible value (naked singles), or cells that appear in rows/columns/boxes with many filled cells. You could also consider a balanced approach that helps without making it too easy. The board parameter is a 9x9 array where 0 represents empty cells.
```

**Partial Function Example:**
```
● **Learn by Doing**

**Context:** I've built a file upload component that validates files before accepting them. The main validation logic is complete, but it needs specific handling for different file type categories in the switch statement.

**Your Task:** In upload.js, inside the validateFile() function's switch statement, implement the 'case "document":' branch. Look for TODO(human). This should validate document files (pdf, doc, docx).

**Guidance:** Consider checking file size limits (maybe 10MB for documents?), validating the file extension matches the MIME type, and returning {valid: boolean, error?: string}. The file object has properties: name, size, type.
```

**Debugging Example:**
```
● **Learn by Doing**

**Context:** The user reported that number inputs aren't working correctly in the calculator. I've identified the handleInput() function as the likely source, but need to understand what values are being processed.

**Your Task:** In calculator.js, inside the handleInput() function, add 2-3 console.log statements after the TODO(human) comment to help debug why number inputs fail.

**Guidance:** Consider logging: the raw input value, the parsed result, and any validation state. This will help us understand where the conversion breaks.
```

### After Contributions
Share one insight connecting their code to broader patterns or system effects. Avoid praise or repetition.

## Insights

<the shared Insights fragment, which repeats the `## Insights` heading — see below>
````

The heading is duplicated in the rendered `Learning` prompt. The style's own body ends with a
`## Insights` heading and then interpolates the shared fragment, which opens with a `## Insights`
heading of its own, so the assembled prompt contains:

```
## Insights

## Insights
In order to encourage learning, before and after writing code, …
```

`Explanatory` is unaffected: it interpolates the fragment directly under `# Explanatory Style
Active` and so emits the heading once.

`TODO(human)` is prompt-level only. The marker appears nowhere outside these prompt strings — no
parser, scanner, or UI affordance looks for it, so nothing detects or validates the placeholder, and
nothing enforces "one and only one".

## Injection into the system prompt

The style contributes two things to a prompt build.

The intro paragraph changes wording. The base intro is built from the resolved style and branches on
whether it is `null`:

```
You are an interactive agent that helps users ${style !== null ? 'according to your "Output Style" below, which describes how you should respond to user queries.' : "with software engineering tasks."} Use the instructions below and the tools available to you to assist the user.
```

The style body is appended as its own dynamic section, `# Output Style: <name>` followed by the
style's `prompt`, registered under the section key `output_style`. It returns `null` for `default`,
so the section is absent entirely. See `PROMPTS.md` for where this sits in the section inventory.

The coding instructions block is conditional on the same object:
`style === null || style.keepCodingInstructions === true` includes it. So `default` keeps it, all
three built-ins keep it, and a custom style keeps it only by opting in.

## Per-turn reminder

A non-default style also injects a per-turn `system-reminder`. The builder returns nothing when the
configured style is `default`; otherwise it emits `{type: "output_style", style: <name>,
turnReminder: <resolved style's turnReminder>}`, rendered as:

```
<name> output style is active. <turnReminder, or "Remember to follow the specific guidelines for this style.">
```

Only `Proactive` defines a `turnReminder`, so `Explanatory` and `Learning` get the generic fallback
sentence.

The renderer looks the style name up in the built-in table, not the merged table, and returns no
reminder when the lookup misses. Custom styles therefore never produce a per-turn reminder — their
instructions live only in the one-time `# Output Style:` section. Anchor:
`rg -nF 'output style is active.'` and check whether the lookup is still against the built-in
literal.

## Resolution and precedence

The configured style name comes from the `outputStyle` setting ("Controls the output style for
assistant responses"), defaulting to `default`.

A plugin style with `force-for-plugin: true` overrides the setting entirely: the resolver scans for
plugin-sourced styles with that flag and returns the first one, logging
`Using forced plugin output style: <name>`. With more than one, it warns
`Multiple plugins have forced output styles: <names>. Using: <name>` and takes the first.

Absent a forced plugin style, the configured name is looked up in the merged table. Styles are
merged over the built-ins in this order, each overwriting by name:

1. built-ins
2. plugin styles
3. user settings (`~/.claude/output-styles/`)
4. project settings (`.claude/output-styles/`)
5. policy settings

Policy wins last, so an admin-managed style shadows a same-named user or project one. A custom style
named `Learning` replaces the built-in.

Safe mode (`CLAUDE_CODE_SAFE_MODE=1`, `--safe-mode`) short-circuits the loader: it returns the
built-in table only, skipping every custom source. Relocate with `rg -nF 'outputStyles'` at the
loader's first line.

Custom style files are parsed as markdown with frontmatter: `name` (default: filename without
`.md`), `description` (default: derived from the body, else `Custom <name> output style`), and
`keep-coding-instructions`. The body is the prompt. `force-for-plugin` in a user or project file is
rejected with `Output style "<name>" has force-for-plugin set, but this option only applies to
plugin output styles. Ignoring.` Field types and coercion rules: `MARKDOWN_FRONTMATTER.md`.

## Surfaces

- `/config` → the entry labelled `Output style` — the picker.
- `/output-style` — a redirect stub, not a picker. It prints
  `/output-style moved → Output style in /config` and opens the config dialog on its Config tab. The
  redirect shares one label map with `/vim` (`{vim: "Editor mode", "output-style": "Output style"}`)
  and falls back to the `vim` entry for an unrecognized name. Relocate with
  `rg -nF 'in /config'`.
- `outputStyle` in settings — the persisted name.
- `tengu_output_style_changed` — telemetry on change.
- `output_style_load` / `output_style_load_failed` — loader telemetry. A load failure logs
  `Failed to load output styles: <message>` and yields an empty custom set.
- Plugin manifests can point at a styles path instead of auto-loading `output-styles/`: "Path to an
  output-styles directory or file, relative to the plugin root. When set, the output-styles/
  directory is not auto-loaded — list its files here if you want both."

## Drift from the published docs

- The docs give the no-style value as `Default`; the bundle's sentinel is lowercase `default`. The
  merged table is indexed by a plain object lookup, so `"Default"` misses every entry and resolves
  to `null` — the same outcome as `default`, which is why the mismatch is invisible.
- The docs describe `/output-style` as the way to switch styles. It is a redirect stub; the picker
  is the `Output style` entry in `/config`.
- The docs do not publish any of the built-in prompt bodies, only one-line summaries of what each
  style does.
- Published changelog history (not verifiable from a single bundle): output styles were deprecated
  in 2.0.30 and un-deprecated in 2.0.32; the `/output-style` command was deprecated around 2.1.73
  and reduced to the `/config` redirect around 2.1.91.

## Tripwire

Re-run against a new version:

- □ built-in set is exactly `default`, `Proactive`, `Explanatory`, `Learning`
- □ `default` is a `null` entry, not an object
- □ all three built-ins set `keepCodingInstructions: true`
- □ `Proactive` is the only built-in with a `turnReminder`
- □ `Explanatory` and `Learning` share one `Insights` fragment
- □ `Learning` still renders `## Insights` twice (fragment heading plus its own)
- □ the autonomy block still has exactly one consumer (`Proactive`), not two
- □ the auto-mode reminder still composes its heading from a constant (so a literal grep for
  `## Auto Mode Active` still fails, and its absence proves nothing)
- □ the `★ Insight` rule is 37 box-drawing chars, the closing rule 49
- □ no `TODO(human)` handling outside the `Learning` prompt text
- □ per-turn reminder still resolves against the built-in table (custom styles get none)
- □ `rg -in 'learning.?mode'` still returns nothing
