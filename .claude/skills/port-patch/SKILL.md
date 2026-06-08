---
name: port-patch
description: Port an existing patch from a previous Claude Code version to a new version, adapting minified symbol names while preserving semantic intent.
---

# Port a patch to a new version

Ports an existing patch to a new Claude Code version. The minified source
changes completely between versions (different function/variable names,
different line numbers) but the underlying structure is preserved.

Read patches/METHODOLOGY.md first — it is the authoritative reference for the
full workflow. This skill adds operational guardrails specific to porting.

# Invocation

```
/port-patch <patch-name> to <version>
```

Examples:
- `/port-patch 001-search_all_dirs to 2.1.69`
- `/port-patch search_all_dirs to 2.1.69`

Parse the arguments to determine:
- Which patch to port — match by number or name against `patches/*/`
- Target version — the version after "to"

Find the most recent previous version of the named patch by scanning
`patches/<prev-version>/<name>.patch`. Read it and the corresponding entry
in `patches/PATCHES.md` for semantic context.

# Prerequisites

- Pristine prettified source must already exist at `work/<version>/package/cli.prettier.js`
  (use the `prepare-for-patch-generation` skill if not)
- The previous version's patch must exist in `patches/<prev-version>/`

# Workflow

## 1. Build a symbol mapping table

Before making any edits, locate every symbol used in the old patch within the
new version's source. Use persistent string literals (log messages, telemetry
event names, error strings) to find the equivalent functions and variables.

Record the mapping as a table:

| Old (X.Y.Z) | New (A.B.C) | Role                       |
|--------------|-------------|----------------------------|
| `mT()`       | `qv()`      | Additional directories     |
| `zeY()`      | `Oqz()`     | File index assembler       |

Every symbol referenced in the old patch must have a confirmed new equivalent
before proceeding.

## 2. Ensure the source file is pristine

Verify the source has no prior edits by checking for a function or variable
name introduced by a previous patch (e.g., `getAdditionalDirFiles`):

```
grep -c 'getAdditionalDirFiles' work/<version>/package/cli.prettier.js
```

A count of 0 confirms the file is unmodified.

If it has edits, re-extract:

```
tar xf work/<version>/anthropic-ai-claude-code-<version>.tgz \
    -C work/<version>/ package/cli.js
npx --yes prettier --ignore-path /dev/null work/<version>/package/cli.js \
    > work/<version>/package/cli.prettier.js
chmod +x work/<version>/package/cli.prettier.js
rm work/<version>/package/cli.js
```

Do NOT use `prettier --write` — it produces different output than the redirect
method used by `prepare-for-patch-generation.sh`.

## 3. Stage the pristine file

Run `pwd` first to confirm cwd is the repository root (not a subdirectory
like `work/<version>/`). Then stage:

```
git add -f work/<version>/package/cli.prettier.js
```

The `work/` directory is gitignored, so `-f` is required.

## 4. Apply the semantic changes

Edit the source file using the symbol mapping from step 1. Each edit should
recreate the semantic intent of the old patch using the new version's symbols.

Do NOT copy old patch text verbatim — translate it to new symbols.

## 5. Generate the patch

```
git diff -- work/<version>/package/cli.prettier.js \
    > patches/<version>/<NNN>-<name>.patch
```

Verify the patch is non-empty and contains the expected hunks.

## 6. Update patches/PATCHES.md

Add an entry for the new patch under the target version's section. Include:
- Patch filename and purpose
- What the patch changes semantically
- Key symbols/functions involved in the new version

Follow the format of existing entries in the file.

## 7. Clean up

```
git restore --staged work/<version>/package/cli.prettier.js
```

Then restore the pristine source (step 2) so the file is ready for the next
patch. Each patch is standalone — generated against the unmodified original.

# Key rules

- One patch = one independent feature. Each starts from pristine source.
- Patches are NOT cumulative. Never apply one patch before generating another.
- Always work from the repository root directory.
- Never use `prettier --write` to restore the source file.
- The `git diff` must be between staged (pristine) and working tree (edited).
- Verify the generated patch file is non-empty before cleaning up.
