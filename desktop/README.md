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

## Getting the source

The app's own code ships in `/Applications/Claude.app/Contents/Resources/app.asar`.
`analysis/EXTRACTION.md` covers unpacking it, searching the archive without unpacking it, and the
recipes for re-checking the docs after an update.

## How the findings are written

`analysis/README.md` records the app version, build commit and build time the docs were last checked
against. Minified identifiers change every build, so the docs anchor on string literals and
behavior. When the installed app is newer than the recorded build, treat build-specific details as
suspect and re-check them.

Claude Desktop bundles Claude Code and runs it as a separate process. Questions about that bundled
Claude Code are answered from `../code/`.
