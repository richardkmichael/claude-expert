# MCP Integration

How Claude Desktop hosts MCP servers: the SDK and protocol version, the two server-hosting paths,
transports, and Desktop Extensions (`.dxt` / `.mcpb`) one-click install. For the MCP Apps (MCP-UI)
extension, see [MCP_APPS](./MCP_APPS.md).


## SDK and protocol version

- `@modelcontextprotocol/sdk` (the MCP TypeScript SDK) is inlined into the main-process bundle by
  Vite — three minified copies: the `directMcpHost.js` MCP host plus two `index.chunk-*.js`. No
  standalone `node_modules` entry.
- MCP protocol, latest negotiated: `2025-11-25`.
- Negotiation list, latest first: `[2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05, 2024-10-07]`
  (`LATEST_PROTOCOL_VERSION` / `SUPPORTED_PROTOCOL_VERSIONS` in `mcp-runtime/directMcpHost.js`, with
  duplicate minified copies in the main-process chunks).

The exact SDK package version is not recoverable from the `app.asar`: `package.json` declares it as
`"@modelcontextprotocol/sdk": "catalog:"` (resolved from a workspace catalog that is not shipped),
the SDK embeds no version constant, and no source maps are bundled (so the `…/sdk@X.Y.Z/…`
dependency-path trick finds nothing). The determinable fact is the protocol it implements
(`2025-11-25`). As a lower bound only, that protocol first shipped in the SDK around `1.24.x`, so
the bundled copy is at least that and likely newer given the build date; treat any specific version
as an inference, not a read from the bundle.

Do not confuse the core protocol with the MCP Apps extension version `2025-11-21` (see
[MCP_APPS](./MCP_APPS.md)) or with API-version header literals such as `2023-06-01`.

Protocol version history (selected):

| Version    | Notes                                              |
|------------|----------------------------------------------------|
| 2024-10-07 | early 1.x                                          |
| 2024-11-05 | ~1.1+                                              |
| 2025-03-26 | ~1.8+                                              |
| 2025-06-18 | ~1.12+                                            |
| 2025-11-25 | current default                                    |


## Two server-hosting paths

Both are utility processes under `.vite/build/mcp-runtime/`, spawned from the main process.

`nodeHost.js` — a thin wrapper that runs a bundled Node MCP server whose entry point is passed as
argv. It imports the server module in-process, then hijacks stdout/stderr/stdin and relays them to
the parent over an Electron `MessagePort` (`{type:"stdout"|"stderr"}` out, `{type:"stdin"}` in). It
is the stdio backend for first-party / bundled Node servers, with no real OS pipes.

`directMcpHost.js` — a ~690 KB utility process that bundles the full MCP SDK and acts as the
client for remote MCP servers. It receives `addServer` messages over `parentPort`, each carrying a
per-server `MessagePort`, and builds a transport per server. Its MCP client identity is
`claude-desktop-3p`, and it adds OAuth bearer (`Authorization: Bearer …`) and mutual-TLS
client-certificate handling.

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
wires up as an MCP server without hand-editing JSON. Backed by `@anthropic-ai/mcpb` and
`@ant/dxt-registry`.

- Both `.dxt` and `.mcpb` file extensions are accepted; install-id namespaces `local.dxt`,
  `local.mcpb`, `local.unpacked`.
- An `mcpbManifest.user_config` is read and mapped to server config
  (`resolveMcpbToHostConfig(...)`); a `.mcpb-cache` directory holds unpacked bundles.
- Admin controls exist for allowing extensions at all and for requiring a trusted-publisher
  signature (allowlist plumbing: `allowlistEnabled`, `allowlistCache`, `AllowlistCheck`).


## Bundled MCP servers

The app ships several MCP servers in-box, in addition to user-configured ones:

| Server                          | Source                                             |
|---------------------------------|----------------------------------------------------|
| Office 365                      | `resources/office365-mcp/` (`msal-node-runtime.node`) |
| Electron DevTools               | `@anthropic-ai/electron-devtools-mcp`              |
| Claude for Chrome               | `@ant/claude-for-chrome-mcp`                       |
| Computer Use                    | `@ant/computer-use-mcp`                            |
