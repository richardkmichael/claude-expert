# Claude Desktop Analysis

Notes on how the macOS Claude Desktop app is built and configured, worked out by reading the
Electron bundle it ships.

Anthropic publishes little about Desktop's internals: its process model, config stores, environment
variables, MCP hosting and feature codenames. The app bundle is the ground truth, and this directory
is where the answers get written down so they don't have to be re-derived each time.

## What's here

| Path        | Contents                                                         |
| ----------- | ---------------------------------------------------------------- |
| `analysis/` | The findings, one doc per topic, indexed by `analysis/README.md` |
| `bin/`      | `asar-search.py`: search `app.asar` without extracting it        |
| `work/`     | Extracted builds, one directory per app version (git-ignored)    |

## Getting the source

The app's own code ships in `/Applications/Claude.app/Contents/Resources/app.asar`. The
`prepare-claude-desktop-source` skill, in the repository root's `.claude/skills/`, extracts the
installed build into `work/<app-version>/app`. `analysis/EXTRACTION.md` covers the details:
unpacking the archive, searching it without unpacking it, and the recipes for re-checking the docs
after an update.

## How the findings are written

The document map in `analysis/README.md` records the build each doc was last verified against.
Minified identifiers change every build, so the docs anchor on string literals and behavior. When
the installed app is newer than a doc's Verified build, treat its build-specific details as suspect
and re-check them.

Claude Desktop downloads a pinned Claude Code version and runs it as a separate process. Questions
about that Claude Code are answered from `../code/`.
