# Analysis Documentation Guidelines

How to document findings from exploring the Claude Code bundle so the docs survive version bumps
without constant rewriting.

Status: trial, expanding. The landmark style is the target for all of `analysis/`. `README.md` (the
index) marks which docs already follow it (Style `landmark`) and which still need retrofitting (Style
`legacy`); convert legacy docs as you touch them rather than maintaining a separate list here.

## The problem

`cli.prettier.js` is a minified bundle. Minified symbol names (`oR8`, `tD_`, `vG`) and line numbers
are regenerated on every release, so any doc that anchors on them is stale the moment a new version
ships. Pasting code fragments has the same failure mode: the snippet churns even when the behavior
it documents has not changed. The result is a doc that looks precise and is quietly wrong.

## What is stable vs. what churns

Anchor on the left column. Never anchor on the right.

| Stable across versions                                            | Volatile (do not anchor on)        |
|-------------------------------------------------------------------|------------------------------------|
| Literal prompt / UI strings, section headings (`# Harness`)       | Minified function/variable names   |
| Env var names (`CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS`)            | Line numbers                       |
| Config keys (`includeGitInstructions`)                            | Exact code snippets                |
| Feature-flag names (`tengu_*`)                                    | Local control-flow spelling        |
| Tool names (`Bash`), truthy/falsy token sets (`1/true/yes/on`)    | Argument order, helper-fn factoring|
| Behavioral logic, call-site relationships, invariants             |                                    |

Literal strings are the best anchors: they are the actual product, and they are what you would grep
for anyway. Minified names are the worst.

## Techniques

1. Describe behavior declaratively, at the level of intent. "The switch reads the env var — truthy
   disables, explicit-falsy enables, else falls back to the `includeGitInstructions` config (default
   on)" survives every rename. This is most of the value and ages well.

2. Replace line numbers with a re-location recipe. For each concept, give the grep that finds it in
   any version plus the shape to expect, instead of a coordinate that is stale on arrival. Example:

   > Switch: `rg -n 'CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS'`. The enclosing function is the gate; it
   > reads the env var, then a truthy helper, then a falsy helper, then `includeGitInstructions`.
   > Expect 3 call sites: git-status injection, the commit/PR workflow builder, the `# Git` block.

   That paragraph is a fingerprint. A future reader runs one command and corroborates the role
   without trusting any name or number.

3. Anchor by string, document the neighborhood. Navigate from a stable string to its behavioral
   neighbors: "grep `Committing changes with git`; the function returning it is gated by the switch
   and computes attribution via the same helper that produces the `Co-Authored-By:` trailer."

4. Encode claims as re-runnable tripwires. Turn assertions into a checklist a future reader can
   verify mechanically against a new version: `□ env var present □ exactly 3 call sites □ truthy set
   = {1,true,yes,on} □ default-on`. Drift then surfaces by failing a check, not by silent rot.

5. Structural patterns for shape, not text. When a bare string grep is not specific enough, use the
   `match-code-patterns` skill (ast-grep with metavariables) to express the logic while letting
   renamed identifiers float as metavars — rename-proof landmarking.

6. Separate evergreen from version-stamped. Keep the behavioral model version-agnostic; confine
   per-release facts to a short dated appendix where each entry is one line (e.g. "2.1.154: Bash
   description split into model-selected terse/legacy variants").

## Generated artifacts over hand-transcription

Verbatim prompt text is both the highest-signal thing to diff across versions and the most
expensive to maintain by hand. Generate it instead.

`bin/render-prompts.py` extracts rendered prompt blocks from any
`work/<version>/package/cli.prettier.js` by anchoring on stable literal strings (see the `ANCHORS`
list at the top of the script), and writes `analysis/PROMPTS_RENDERED.md`. Regenerate with:

```
python3 bin/render-prompts.py <version>      # writes PROMPTS_RENDERED.md
python3 bin/render-prompts.py <version> --stdout
```

The script is a deliberate heuristic, not a prompt evaluator: it emits the verbatim
string/template literal(s) reached from each anchor, leaves `${...}` as unevaluated placeholders,
and may include fragments from every branch of a conditional. That is fine — the goal is a wording
snapshot for diffing, not an assembled prompt. When a new version moves a section, the script
reports the anchor as `NOT FOUND`; update the anchor string (and note the change in the consuming
doc), then regenerate. Diffing two regenerated snapshots shows real wording changes instead of
rename noise.

When adding documentation that would otherwise paste a large block of generated text, prefer a
script plus a regenerated snapshot over hand-copying.

## Document roles (prompt trial)

- `PROMPTS.md` — behavioral model and landmark index: assembly/routing logic, the model-based path
  split, the section inventory keyed by stable heading strings, and the gating matrix. Each row
  carries a re-location grep and, where useful, a tripwire. No minified names or line numbers.
- `PROMPTS_RENDERED.md` — generated verbatim snapshot (see above). Never edited by hand.
- `GIT_USAGE.md` — behavioral deep-dive on git instructions; retrofit toward this style as the
  trial proceeds.

## Version stamping

Every findings doc starts with one line recording the bundle it was last checked against:

    Verified against: cli.prettier.js <version> (<YYYY-MM-DD>)

This makes the staleness check mechanical: compare the stamp to the latest local version
(`ls work/ | sort -V | tail -1`). The stamp is a per-release fact — bump it whenever you re-verify,
even if no wording changed. Mirror the version into the doc's row in `README.md`.

## Updating an existing doc

When source behavior has changed, or a doc trails the latest bundle:

1. Relocate the behavior in the current bundle using the doc's landmark strings (and the Key
   landmarks column in `README.md`). If a landmark string itself changed, that is a finding — record
   the old and new strings.
2. Rewrite only the claims that actually changed, in landmark style. Leave correct evergreen prose
   alone; the goal is minimal, truthful drift, not a rewrite for its own sake.
3. If the section you touched was legacy style (line numbers, pasted minified code), retrofit it to
   landmark anchors while you are there. Don't leave a doc half-migrated with fresh line numbers.
4. Restamp `Verified against:` and bump the Verified column in `README.md`, in the same commit.
5. Record genuinely new per-release facts in the doc's dated appendix, one line each.
6. Commit with `(code <version>) analysis: <description>`.

The tripwire checklists (technique 4 above) make step 1 cheap: a future reader runs the checks
against a new bundle and drift surfaces as a failed check instead of silent rot.
