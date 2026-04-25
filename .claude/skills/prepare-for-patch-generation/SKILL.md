---
name: prepare-for-new-patch-generation
description: Prepare the original source code for new patch generation by creating working directories, and downloading, extracting and prettifying the requested version source code. If the user says "latest" instead of a specific version number, use the latest published version shown below.
allowed-tools: Bash(bin/prepare-for-patch-generation.sh:*), Bash(npm view:*)
---

# Source code preparation

This skill prepares the original source code for modification to generate new patches.

Latest published version: !`npm view @anthropic-ai/claude-code version`

# Instructions

1. Determine the version to prepare:
   - If the user specified a version number, use that
   - If the user said "latest" or similar, use the latest published version shown above

2. Run: `${CLAUDE_SKILL_DIR}/bin/prepare-for-patch-generation.sh <version>`
