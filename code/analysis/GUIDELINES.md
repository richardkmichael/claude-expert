---
verified: 2.1.154
section: Methodology (not findings)
style: methodology
scope: How to write and update analysis docs (authoritative)
---
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

6. Describe the current state only. A doc describes the version it is stamped with. When a claim no
   longer holds, rewrite or delete it rather than annotating what it used to be: no "in earlier
   versions", no Version history sections or dated appendices. Git history records how a doc
   changed.

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

## Version stamping and the index

Every doc starts with YAML frontmatter that records the bundle it was last checked against and
carries its row in the index (`README.md`):

```yaml
---
verified: 2.1.317                  # the cli.prettier.js version
verified_on: 2026-11-03
section: Hooks                     # the README section the row belongs in
style: landmark                    # landmark, legacy, generated or methodology
scope: Hook event inventory, I/O schemas, matchers
landmarks:                         # literal strings to grep for; optional for methodology
  - hook_event_name
  - fieldToMatch
---
```

The stamp covers the whole doc. Move it forward only after checking every claim in the doc against
the new version, even if no wording changed. A finding about a newer version than the stamp
therefore means re-checking the rest of the doc first; a doc that covers one topic keeps that cheap.

After changing a doc's frontmatter, or adding a doc, run `bin/analysis-index.py` from the repository
root. It rewrites the index tables from the frontmatter of every doc, and lists the docs stamped
behind the newest version in `work/`: the staleness check. `--check` changes nothing and fails if
the index is out of date or a doc's frontmatter is invalid. Never edit the index tables by hand.

A stamp only moves forward (root `CLAUDE.md`, "Documenting findings"). An older version gets checked
when a Claude Desktop question leads to the Claude Code version a Desktop build pins.

## Updating an existing doc

When source behavior has changed, or a doc trails the latest bundle:

1. Relocate the behavior in the current bundle using the doc's landmark strings (its body's recipes
   and its frontmatter `landmarks`). If a landmark string itself changed, update it to the new
   string.
2. Check every claim in the doc, and rewrite only the ones that actually changed, in landmark style.
   Leave correct evergreen prose alone; the goal is minimal, truthful drift, not a rewrite for its
   own sake.
3. If the section you touched was legacy style (line numbers, pasted minified code), retrofit it to
   landmark anchors while you are there. Don't leave a doc half-migrated with fresh line numbers.
4. Restamp the frontmatter (`verified`, `verified_on`) and run `bin/analysis-index.py`, in the same
   commit.
5. Delete claims that no longer hold, and any history the doc still carries (Version history
   sections, dated appendices, "in earlier versions" asides).
6. Commit with `(code <version>) analysis: <description>`.

The tripwire checklists (technique 4 above) make step 1 cheap: a future reader runs the checks
against a new bundle and drift surfaces as a failed check instead of silent rot.
