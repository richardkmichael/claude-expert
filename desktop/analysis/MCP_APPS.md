---
verified: 4.4212.0
scope: MCP Apps (MCP-UI) support, including `updateModelContext`
---
# MCP Apps (MCP-UI) Support

MCP Apps (the ext-apps "MCP-UI" extension) lets an MCP server ship a GUI that renders in an iframe
inside the host and talks to it over `postMessage` JSON-RPC with `ui/*` methods. This file records
what the Claude Desktop bundle supports, with the `updateModelContext` feature as the driving
question.

Spec references (local checkout):
`modelcontextprotocol/ext-apps/main/docs/patterns.md`,
`.../specification/2026-01-26/apps.mdx`.


## Headline: `updateModelContext` is not in use

`updateModelContext` — the App-to-model context channel described in `patterns.md` — is not in use
in this build. Its wire method `ui/update-model-context` appears once in the extract: in the
visualize widget's `share-edits` module, which is switched off in what Desktop serves. The camelCase
`updateModelContext`, the host-capability name, appears nowhere (`.vite/build`, `.vite/renderer`,
`node_modules`, `resources`); the widget never checks for it.

`updateModelContext` lets an App push context to the model silently: no follow-up turn, each call
overwrites the last, deferred until the next user message. At the wire level it is a view-to-host
request `ui/update-model-context`, gated by a host capability `updateModelContext` in the
`ui/initialize` result. It is distinct from `ui/message`, which sends a full user-style message that
does trigger a response.

What `share-edits` would send: the text of fields the widget marks with `data-share-edit` and the
user has edited, under a `Widget "<title>": …` header, as one `ui/update-model-context` text block
(debounced 400 ms, flushed before `window.sendPrompt`, capped at 24 000 characters and 40 fields).
It never shares password, one-time-code, card or browser-autofilled fields. The module runs only
when the resource HTML carries `<meta name="share-edits" content="on">`. The widget ships with
`content="off"`, and the server swaps in `on` only when asked to read the resource with a
`shareEdits: true` option; its resource-read handler passes no options, so the served widget keeps
`off`.

The desktop gives Apps the follow-up path (`ui/message`). Whether the host would accept the
silent-context path cannot be read from this bundle.


## Why the host side is unresolved here

The MCP Apps host — the frame that renders App iframes, advertises host capabilities, and would
accept `ui/update-model-context` — is the remotely-served `claude.ai` frontend, not this bundle. The
main window is a `WebContentsView` tagged `claude.ai-web` whose URL resolves to `https://claude.ai`
(see [ARCHITECTURE](./ARCHITECTURE.md)). The desktop ships only the App side (a built-in widget) and
the local MCP server hosts (see [MCP](./MCP.md)). Those local hosts, acting as the MCP client,
advertise MCP Apps support to servers: the `initialize` capabilities carry
`extensions: { "io.modelcontextprotocol/ui": { mimeTypes: ["text/html;profile=mcp-app"] } }`.

What the bundle does say about the host:

- The bundle's only `ui/update-model-context` sender is switched off, and nothing in it reads an
  `updateModelContext` host capability.
- The first-party App negotiates MCP Apps protocol `2025-11-21`, which predates the feature.
- `updateModelContext` entered the ext-apps spec on 2026-01-12 and first ships in the `2026-01-26`
  revision — after `2025-11-21`. A host pinned to the earlier revision cannot offer it.

A first-party App targeting `2025-11-21` strongly implies the paired host is at that same revision.
Confirming the live host's negotiated capabilities directly requires inspecting the running
claude.ai frontend (renderer DevTools, or the same frontend in a browser) — see
[DEBUGGING](./DEBUGGING.md).


## What the bundle does implement: the visualize widget

The only MCP App shipped locally is Claude Desktop's built-in artifact/visualization renderer. It is
itself an MCP App, so Anthropic dogfoods the same MCP-UI protocol a third-party server would use —
which is why it anchors the `ui/*` vocabulary and protocol version the desktop speaks.

The model calls a tool named `show_widget` with generated SVG or HTML code (required arguments
`widget_code`, `title` and `loading_messages`; the view also accepts `code` in place of
`widget_code`); the widget renders it progressively as it streams into an iframe inline in the chat.
It also handles SVG/HTML download (SVG frozen with computed styles first), clipboard copy, link
opening, host-theme application, and inline elicitation forms.

| Piece                 | Location / value                                                                                                                                                  |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Built-in MCP server   | internal name `visualize` (UI-resource namespace codename `imagine`)                                                                                              |
| Tools                 | `show_widget` (render the code); `read_me` (returns host styling context — CSS variables, colors, typography, layout rules — so the widget matches the app theme) |
| UI resource           | `ui://imagine/show-widget.html`, mimeType `text/html;profile=mcp-app` (the `profile=mcp-app` marker tells the host to render it as an MCP App)                    |
| Server registration   | `getImagineServerDef` export, from the `@ant/imagine-server` package (listed in `package.json`)                                                                   |
| Client-side view code | Embedded in the same chunk as the resource's HTML string (`<title>Visualize Widget</title>`); `appInfo` = `{ name: "visualize widget", version: "1.0.0" }`        |

The embedded view is built from source modules visible as `// src/scripts/...` banners:
`widget-main.ts` (entry), `mcp-app-helper.ts` (the `postMessage` JSON-RPC bridge),
`streaming-morph.ts` (progressive render), `elicitation.ts` (inline forms), `send-prompt.ts`,
`open-link.ts`, `clipboard-copy.ts`, `export-scrub.ts`, `host-init.ts`, `share-edits.ts`, and
several `svg-*.ts` rendering fixups. The bridge is hand-rolled, not the official `@mcp-ui` SDK — a
minimal `window.parent.postMessage` JSON-RPC client.

Its `ui/initialize` declares:

```
protocolVersion: "2025-11-21"      // MCP Apps extension version — not the core MCP 2025-11-25
appCapabilities: {}
```

That `2025-11-21` is the MCP Apps extension protocol version, intentionally distinct from the core
MCP protocol version `2025-11-25` used by the MCP client (see [MCP](./MCP.md)).


## The MCP Apps protocol version: created vs stable

MCP Apps versions its protocol by date, the same convention core MCP uses. The version string is
what `ui/initialize` carries; it is a spec-revision label, not an app or product version. Two labels
matter here, both from the ext-apps spec's own front matter for the same evolving document:

- `Created: 2025-11-21` — the initial (draft) protocol revision.
- `Status: Stable (2026-01-26)` — the stabilized revision. One commit bumped the SDK's
  `LATEST_PROTOCOL_VERSION` from `"2025-11-21"` to `"2026-01-26"` and tagged the ext-apps SDK
  `v1.0.0`, so `2026-01-26` is at once the stable revision label, the negotiated version string, and
  the date that revision was frozen.

`updateModelContext` was added 2026-01-12 — before stabilization — so it is part of the stable
`2026-01-26` revision but not the `2025-11-21` draft the widget negotiates. The `2026-01-26` spec
examples even use `hostInfo: { name: "claude-desktop" }`, so Claude is the intended host for that
revision; this build's bundled App declares `2025-11-21`.

Sourcing: the `2025-11-21` value is read from the Claude Desktop bundle (the widget's
`ui/initialize`); the `2026-01-26` stable label and the `Created` / `Status` dates are from the
ext-apps repo (`specification/2026-01-26/apps.mdx` and `LATEST_PROTOCOL_VERSION` in
`src/spec.types.ts`).


## `ui/*` methods the bundle references

Eleven methods, all used by the visualize widget — the full vocabulary present in the bundle:

| Method                                  | Role in the widget                                     |
| --------------------------------------- | ------------------------------------------------------ |
| `ui/initialize`                         | Sends handshake to the host                            |
| `ui/request-display-mode`               | Sends `{mode}` (inline / fullscreen)                   |
| `ui/message`                            | Sends a user-role message (via `window.sendPrompt`)    |
| `ui/open-link`                          | Sends `{url}` to open externally                       |
| `ui/download-file`                      | Requests a file download                               |
| `ui/update-model-context`               | Sends edited field text (`share-edits`; off as served) |
| `ui/notifications/initialized`          | Notifies the host the view is ready                    |
| `ui/notifications/size-changed`         | Notifies `{width,height}` from a `ResizeObserver`      |
| `ui/notifications/host-context-changed` | Listens; applies host theme                            |
| `ui/notifications/tool-input`           | Listens; renders finalized tool input                  |
| `ui/notifications/tool-input-partial`   | Listens; renders streaming partial input               |

Absent (relative to the current spec): resource teardown and sampling.


## Anthropic-specific postMessage extensions

The widget also uses non-standard shapes deliberately kept off the JSON-RPC transport, handled by a
raw listener host-side (the host exposes a `PostMessageTransport` plus an `AppRenderer`, named only
in a source comment in the widget):

- `anthropic:attach-files` — `postMessage({type:"anthropic:attach-files", files}, "*")`, gated on
  a real user click (user-activation enforced host-side).
- `anthropic:elicit-submit` — `{type:"anthropic:elicit-submit", text, files}`, emitted by the
  elicitation form when files are attached; without files it falls back to `window.sendPrompt`.
- `window.sendPrompt(text)` — maps "send to chat as if the user typed it" onto `ui/message`.
- Elicitation forms (`src/scripts/elicitation.ts`) drive the two paths above.
- `anthropic:copy-image` / `anthropic:copy-text` — clipboard requests to the parent frame, each
  answered by a matching `…-result` message carrying the same `requestId`.


## Bottom line

For build 4.4212.0, no MCP App in the bundle feeds context back to the model through
`updateModelContext`. The visualize widget carries a `ui/update-model-context` sender, but Desktop
serves it switched off. The desktop offers `ui/message` (a full follow-up message) as the closest
capability in use. Whether the MCP Apps host would accept `ui/update-model-context` is decided by
the remote claude.ai frontend. The bundle's own App targets the `2025-11-21` extension revision,
which is older than the revision that introduced `updateModelContext`.
