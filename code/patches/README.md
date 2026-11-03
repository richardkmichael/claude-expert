# Patches Index

Out-of-tree patches that modify the Claude Code bundle to add hook and behavior enhancements the
shipped product doesn't expose. Minified identifiers change every release, so a patch never applies
across versions — each version gets its own regenerated set under `patches/<version>/`.

Start here, then:

- `PATCHES.md` — the catalog: what each patch does, original vs patched behavior, design decisions,
  and execution flow.
- `METHODOLOGY.md` — how to recreate the patches for a new version: locate the equivalent code by
  stable strings, recreate the semantic change against the new identifiers, regenerate standalone
  `.patch` files.

## The patches

| #   | Name                                         | Purpose                                                                                      |
| --- | -------------------------------------------- | -------------------------------------------------------------------------------------------- |
| 1   | PreToolUse Hook Validation Context           | PreToolUse hooks receive schema/input validation context and run even on invalid input       |
| 2   | PostToolUse Hook Execution Context           | PostToolUse hooks receive execution context and run even when the tool errored               |
| 3   | Piped Command Environment Variable Expansion | Piped bash commands expand env vars instead of getting empty stdin                           |
| 4   | Agent and Skill File Content Interpolation   | Agent and skill `.md` files interpolate variables in their content                           |
| 5   | Additional Workspace Directory File Indexing | Files in `additionalDirectories` are indexed for `@`-file completion                         |
| 6   | CLAUDE_SKILL_DIR in Hook Commands            | Skill-defined hook commands can use `${CLAUDE_SKILL_DIR}`                                    |
| 7   | Gate Git Tips with DISABLE_GIT_INSTRUCTIONS  | The Bash git-tips section respects `CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS`                    |
| 8   | Allow Symlinked Local Settings Writes        | The settings writer writes through a symlinked `.claude/settings.local.json` (`2.1.168/001`) |

Full detail for each — and per-version updates — is in `PATCHES.md`.

## Corpus layout

- `patches/<version>/NNN-name.patch` — the per-version patch files, numbered and applied in order.
- Validate with the harness in `../verify/`: it symlinks the bundle, applies a version's patches,
  and drives the patched CLI headless to confirm the enhanced hooks fire.

## Maintaining

When recreating patches for a new version, follow `METHODOLOGY.md`, add the version's `.patch` files
under `patches/<version>/`, and update `PATCHES.md` where a patch's semantics changed. Keep the patch
table above in sync when patches are added or removed.
