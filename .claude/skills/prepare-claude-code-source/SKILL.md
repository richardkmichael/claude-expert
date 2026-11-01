---
name: prepare-claude-code-source
description: Download, extract and prettify a Claude Code version into code/work/<version>/package/cli.prettier.js for source analysis, and create its code/patches/<version>/ directory. Use when a question needs a Claude Code version that is not yet in code/work/. If the user says "latest" instead of a version number, use the latest published version shown below.
allowed-tools: Bash(bin/prepare-claude-code-source.sh:*), Bash(npm view:*)
---

# Source code preparation

This skill prepares a Claude Code version's source for analysis and patching.

Latest published version: !`npm view @anthropic-ai/claude-code version`

# Instructions

1. Determine the version to prepare:

   - If the user specified a version number, use that
   - If the user said "latest" or similar, use the latest published version shown above

2. Run: `${CLAUDE_SKILL_DIR}/bin/prepare-claude-code-source.sh <version>`
