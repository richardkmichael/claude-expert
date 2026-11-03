---
name: prepare-claude-desktop-source
description: Extract and format the installed Claude Desktop app's code into desktop/work/<app-version>/app, and write desktop/work/<app-version>/manifest.json recording the app build and the Claude Code version it pins. Use at the start of any Claude Desktop question, before reading desktop/work/. Safe to run when the version is already prepared.
allowed-tools: Bash(bin/prepare-claude-desktop-source.sh:*)
---

# Claude Desktop source preparation

Installed Claude Desktop version:
!`/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' /Applications/Claude.app/Contents/Info.plist`

Prepared versions:
!`ls "$(git rev-parse --show-toplevel)/desktop/work" 2>/dev/null | sort -V | tr '\n' ' '`

# Instructions

1. Run: `${CLAUDE_SKILL_DIR}/bin/prepare-claude-desktop-source.sh`

   To prepare a different app bundle, pass its path:
   `... prepare-claude-desktop-source.sh /path/to/Claude.app`. Only the installed app is normally
   available: Claude Desktop updates itself, and older builds are not downloadable.

2. Read the printed manifest:

   - `buildInfo.appVersion`, `commitHash`, `commitTimestamp`: the build to stamp findings with.
   - `claudeCode.version`: the Claude Code version this build pins. Desktop downloads that version
     at runtime into `~/Library/Application Support/Claude/claude-code/<version>/`. To research it,
     check `code/work/<version>/` and run the `prepare-claude-code-source` skill if it is missing.
   - `buildFiles`: how the main-process bundle is split into files.

3. Search the code under `desktop/work/<app-version>/app/.vite/build/`, naming that path explicitly:
   `.vite/` is hidden and `desktop/work/` is gitignored, so a recursive `rg` from elsewhere skips
   them. For the whole extracted tree, pass `rg -uu`.
