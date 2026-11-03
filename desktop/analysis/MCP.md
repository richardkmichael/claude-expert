---
verified: 4.4212.0
scope: MCP SDK/protocol, server hosting, transports, `.dxt`/`.mcpb`
---
# MCP Integration

How Claude Desktop hosts MCP servers: the SDK and protocol version, the two server-hosting paths,
transports, and Desktop Extensions (`.dxt` / `.mcpb`) one-click install. For the MCP Apps (MCP-UI)
extension, see [MCP_APPS](./MCP_APPS.md).


## SDK and protocol version

- `@modelcontextprotocol/sdk` (the MCP TypeScript SDK) is inlined into the main-process bundle by
  Vite. Its protocol-constants module appears five times: twice in the `directMcpHost.js` MCP host,
  twice in the large main-process chunk, and once in the chunk that carries the inlined Agent SDK.
  No standalone `node_modules` entry.
- Two protocol handshakes coexist. The newer one probes the server with a `server/discover`
  request and negotiates protocol revision `2026-07-28` (the SDK's "modern" era). The older one is
  the `initialize` handshake, whose negotiation list, latest first, is
  `[2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05, 2024-10-07]`.
- Desktop arms the probe for remote servers (the `addServer` config it sends `directMcpHost`) and
  for local servers, as `versionNegotiation: { mode: "auto", probe: { timeoutMs: 10000 } }`, unless
  a feature gate switches it off. A local stdio server is not probed in place: for servers run by
  the built-in Node runtime a disposable sibling process takes the probe (`Era probe` log lines),
  and other stdio servers get the `legacy` verdict. In `auto` mode a server that gives no modern answer falls back to
  `initialize`; on a failed armed connect `directMcpHost` logs `retrying the connect once with the
  older initialize handshake` and connects again without the probe. The SDK's own default, with no
  `versionNegotiation` option, is `initialize` only.

The exact SDK package version is not recoverable from the `app.asar`: `package.json` does not list
the SDK at all (its dependencies are a handful of `@ant/*` workspace packages plus `ws`,
`https-proxy-agent` and `@loc/electron-window`), the SDK embeds no version constant, and no source
maps are bundled (so the `…/sdk@X.Y.Z/…` dependency-path trick finds nothing). The determinable
fact is the protocol revisions it implements. Treat any specific SDK version as an inference, not a
read from the bundle.

To relocate the lists, anchor on the oldest version and read leftward: the formatted build has
`[<identifier>, "2025-06-18", "2025-03-26", "2024-11-05", "2024-10-07"]`, with the latest
`initialize` version hoisted into a variable just above it. The `2026-07-28` revision is a separate
literal near `server/discover` and the `versionNegotiation` error strings (`pinning is for
2026-07-28 and later`).

Do not confuse the core protocol with the MCP Apps extension version `2025-11-21` (see
[MCP_APPS](./MCP_APPS.md)) or with API-version header literals such as `2023-06-01`.

Protocol version history (selected):

| Version    | Notes                                                    |
|------------|----------------------------------------------------------|
| 2024-10-07 | early 1.x                                                |
| 2024-11-05 | ~1.1+                                                    |
| 2025-03-26 | ~1.8+                                                    |
| 2025-06-18 | ~1.12+                                                   |
| 2025-11-25 | latest `initialize` revision                             |
| 2026-07-28 | `server/discover` revision, probed first when armed      |


## Two server-hosting paths

Both are utility processes under `.vite/build/mcp-runtime/`, spawned from the main process.

`nodeHost.js` — a thin wrapper that runs a bundled Node MCP server whose entry point is passed as
argv. It imports the server module in-process, then hijacks stdout/stderr/stdin and relays them to
the parent over an Electron `MessagePort` (`{type:"stdout"|"stderr"}` out, `{type:"stdin"}` in). It
is the stdio backend for first-party / bundled Node servers, with no real OS pipes.

`directMcpHost.js` — a ~930 KB utility process that bundles the full MCP SDK and acts as the
client for remote MCP servers. It receives `addServer` messages over `parentPort`, each carrying a
per-server `MessagePort`, and builds a transport per server. Its MCP client identity is
`claude-desktop-3p`, advertising the `elicitation: { url: {} }` capability. It fetches through
Electron's `net.fetch` (the Chromium network stack), adds OAuth bearer (`Authorization: Bearer …`,
which the main process can replace on a live connection), and does not follow HTTP
redirects.

The difference: `nodeHost` launches a local server as a child and pipes its stdio; `directMcpHost`
is the client itself, connecting over the network with no server subprocess.


## Transports

| Transport       | Supported | Via                                                             |
|-----------------|-----------|-----------------------------------------------------------------|
| stdio           | yes       | `StdioClientTransport` (real subprocess spawn) + `nodeHost.js`  |
| Streamable HTTP | yes       | `directMcpHost.js` — the default for remote servers             |
| SSE             | yes       | `directMcpHost.js` — used when `config.transport === "sse"`     |
| WebSocket       | no        | no `WebSocketClientTransport`/`ServerTransport` anywhere        |


## Server configuration

User MCP servers are configured in the `mcpServers` map of `claude_desktop_config.json` (see
[CONFIGURATION](./CONFIGURATION.md)).


## Desktop Extensions (`.dxt` / `.mcpb`)

One-click MCP install: a packaged server bundle carrying an `mcpbManifest` that the app installs and
wires up as an MCP server without hand-editing JSON.

- Both `.dxt` and `.mcpb` file extensions are accepted; install-id namespaces `local.dxt`,
  `local.mcpb`, `local.unpacked`.
- An `mcpbManifest.user_config` is read and mapped to server config; a `.mcpb-cache` directory
  holds unpacked bundles.
- Admin controls exist for allowing extensions at all and for requiring a trusted-publisher
  signature (managed-config keys `isDesktopExtensionEnabled` and
  `isDesktopExtensionSignatureRequired`; allowlist plumbing: `dxt:allowlistEnabled`,
  `dxt:allowlistCache:`, `refreshAllowlistCheck`).


## Bundled MCP servers

The app ships several MCP servers in-box, in addition to user-configured ones:

| Server                          | Source                                             |
|---------------------------------|----------------------------------------------------|
| Office 365                      | `resources/office365-mcp/` (`office365-mcp-stdio.mjs`, `msal-node-runtime.node`) |
| GitHub                          | `resources/github-mcp/github-mcp-server` — a ~24 MB Go binary (arm64 Mach-O) |
| Claude in Chrome                | `@ant/claude-for-chrome-mcp`; server name `claude-in-chrome` |
| Computer Use                    | `@ant/computer-use-mcp`; server name `computer-use` |
| Visualize                       | `@ant/imagine-server`; server name `visualize` — see [MCP_APPS](./MCP_APPS.md) |

The `@ant/*` package names are read from `package.json` `dependencies`; the bundle itself inlines
those packages without naming them.

The GitHub server is a compiled Go binary rather than a Node module, so unlike the others it is not
inlined into the JS bundle and appears as a standalone executable in the archive.
