# Anthropic SDK Request Behavior

Source: `cli.prettier.js` (`work/<version>/package/cli.prettier.js`)
Verified against: cli.prettier.js 2.1.277 (2026-09-19)

What the bundled Anthropic SDK does to a request on its way out, as distinct from what Claude Code
puts into one. Claude Code's own request construction is in `ANTHROPIC_API_USAGE.md`.

This doc was previously a line-indexed listing of configuration and agent functions by minified
name. That material is covered, in landmark form, by `SETTINGS.md` (config paths and settings
merge), `FUNCTIONAL_BREAKDOWN.md` (orientation map), `MARKDOWN_FRONTMATTER.md` (agent and skill
frontmatter schema), and `SKILLS.md` (agent loading).

## Endpoint

`POST /v1/messages` against the configured base URL, which defaults to `https://api.anthropic.com`.
Grep `/v1/messages` to relocate; the hits are inside the bundled SDK, not app code.

## What the SDK adds

Three things happen in the SDK's message-create path that are not visible in Claude Code's own
request building:

A deprecation warning is printed to stderr when the requested model appears in the SDK's
end-of-life table, naming the model and its end-of-life date. A second warning covers
`thinking.type=enabled`, recommending `adaptive` instead. Both are `console.warn`, so they surface
in a terminal session without being part of the response.

A non-streaming request with no explicitly configured timeout gets one calculated from `max_tokens`
and a per-model factor. Streaming requests keep the configured timeout. Either way the fallback is
600000 ms.

The `stream` flag defaults to false when the caller omits it.

Relocate all three by grepping `calculateNonstreamingTimeout`.

## Distinguishing SDK code from app code

The SDK is bundled inline, so its code sits alongside Claude Code's in the same file. Two reliable
signals: SDK code has no `tengu_*` events and no `CLAUDE_CODE_*` env vars, and it refers to
`this._client`, a shape app code never uses.

This matters when a grep for an API concept returns hits in both. A change in SDK behavior is an
upstream dependency bump, not a Claude Code product change, and belongs in `DEPENDENCIES.md`.
