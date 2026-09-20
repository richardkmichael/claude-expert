# Claude Code Analysis

Notes on how Claude Code actually behaves, worked out by reading the shipped bundle, plus the
tooling used to get at it.

The published documentation lags the product, and the product ships often. When a question comes up
that the docs don't answer, such as what gates a given prompt block, which env var turns it off, or
what a hook actually receives, the bundle is the only ground truth. This repository is where the
answers get written down so they don't have to be re-derived each time.

## What's here

| Path                | Contents                                                                   |
| ------------------- | -------------------------------------------------------------------------- |
| `analysis/`         | The findings, one doc per topic, indexed by `analysis/README.md`           |
| `analysis/schemas/` | JSON Schemas for Claude Code's own files: frontmatter, session transcripts |
| `.claude/skills/`   | Skills for fetching a version, matching code patterns, porting patches     |
| `bin/`              | Generators: rendered prompt text, transcript schema, transcript stripping  |
| `patches/`          | Out-of-tree patches to the bundle, with a catalog and a porting method     |
| `mcp/`              | An MCP server that makes this repo consultable from another project        |
| `verify/`           | Scripts for checking that a patched build behaves as intended              |
| `work/`             | Where extracted sources land. Git-ignored; you generate it yourself        |

## Getting a bundle

The `prepare-for-patch-generation` skill downloads a given version, extracts it, and prettifies it
into `work/<version>/package/cli.prettier.js`. It handles both distribution eras: the earlier
minified npm package, and the later bun-compiled native binary whose embedded JavaScript modules
have to be pulled out and concatenated.

Everything else assumes that file exists. Nothing in this repo fetches it implicitly.

## How the findings are written

Each doc anchors on things that survive a release: literal prompt and UI strings, telemetry event
names, environment variables, config keys, tool names, and the behavioral logic itself. Never on
minified symbol names, line numbers, or pasted implementation.

In place of a line number, a doc gives a relocation recipe: the grep that finds the behavior in any
version, and the shape to expect when you get there. Claims worth re-checking are written as
tripwires, a short checklist a future reader can run against a newer bundle, so drift surfaces as a
failed check rather than as silent rot.

Every doc records the version it was last verified against. When that stamp falls behind the bundle
you have, treat its version-specific details as suspect and re-check them. Re-verifying and
restamping is routine work here, not an exception.

`analysis/README.md` is the index. It maps each doc to its scope, its verified version, its
anchoring style, and the strings to grep to find the behavior again.

## Using it from another project: Expert MCP server

`mcp/expert-server.mjs` exposes this repository as a single MCP tool, so another project's session
can ask a question about Claude Code without adding this repo to its context. The call runs a nested
headless session rooted here; only the question and the answer cross the boundary. See
`mcp/README.md` for registration.

Complements the `@claude-code-guide` agent native to Claude Code.

## Patching the bundle

`patches/` holds changes that make the client do something the shipped product doesn't expose, such
as giving hooks the validation context they otherwise never see. A patch never applies across
versions, since the identifiers it touches are regenerated each release, so each version gets its
own set and `patches/METHODOLOGY.md` covers porting them forward.
