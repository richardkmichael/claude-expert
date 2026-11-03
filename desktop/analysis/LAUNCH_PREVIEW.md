# Launch preview (Code-session browser pane)

Verified build: 4.4212.0. Code sessions have a Browser pane backed by a main-process "launch
preview" subsystem. Paths below are under `work/<version>/app/.vite/build/`. All code is in the
`index.chunk-*` files, so relocate by the strings given, not by chunk name.

## Starting a dev server: `.claude/launch.json`

Desktop starts the server itself. Claude calls the `preview_start` tool with `{name}`. Desktop reads
`<session cwd>/.claude/launch.json`, spawns the matching entry as a child process with
`env = { FORCE_COLOR: "1", ...entry.env, PORT: String(port) }`, buffers its stdout/stderr
(`preview_logs`), and opens a Browser tab at `http://localhost:<port>`. A server already running
under the same name is reused. Tool descriptions tell Claude to use `preview_start` instead of Bash
for servers and to create the file when it is missing.

Relocate: `rg -n 'Start a dev server by name from .claude/launch.json'` (tool definitions,
`preview_start`, `preview_stop`, `preview_list`, `preview_logs`, `preview_console_logs`,
`preview_screenshot`, `preview_snapshot`, `preview_inspect`, `preview_click`, `preview_fill`,
`preview_eval`, `preview_network`, `preview_resize`) and `rg -n '\[Preview\] Spawning process'` (the
spawn).

The template shown to Claude:

```json
{
  "version": "0.0.1",
  "configurations": [
    { "name": "<unique-name>", "runtimeExecutable": "<command>", "runtimeArgs": ["<args>"], "port": <port> }
  ]
}
```

Parsing rules (`parseLaunchJson` / `parseConfiguration`, relocate with
`rg -n 'launch.json failed to parse|must be a JSON number from 1 to 65535'`):

- The file is JSONC: comments and trailing commas are accepted.
- Top level: `version`, `configurations` (array), `autoVerify` (anything but `false` means on).
- An entry is usable when it has `runtimeExecutable` (with optional `runtimeArgs`), or `program`
  (run as `node <program> <args>`), or `url` alone (attach to an already-running server, no process
  started). VS Code `command` and `node-terminal` style entries are rejected.
- The spawn command is `runtimeExecutable`, then `runtimeArgs`, then `program`, then `args`.
- `name`: defaults to a name derived from the args. With several entries, `preview_start` must pass
  a name. A single entry is used even when the name differs.
- `port`: JSON number 1 to 65535 (a numeric string is coerced). When absent, the port comes from a
  localhost `url`, then `env.PORT`, then a scan of the command for `--port N`, `-p N`, `--port=N`,
  `localhost:N`, or `:NNNN`, then 3000.
- `cwd`: relative to the project directory, or absolute. `${workspaceFolder}` and `${workspaceRoot}`
  expand in command, args and `cwd`. Default is the project directory.
- `env`: merged into the child environment before `PORT`.
- `url`: optional. A localhost URL must be only the origin and match `port`. Non-localhost URLs go
  through the user's permission prompt and the organization browsing policy.
- `autoPort`: boolean. When the port is busy, Desktop picks another one and passes it in `PORT`,
  rewriting `--port`/`-p` arguments it recognizes. `false` pins the port and the start fails if it
  is taken. A script that ignores `PORT` and hardcodes a port needs `"autoPort": false`.
- `type: "framebuffer"` entries (`vncUrl`) feed the `framebuffer_*` tools, not the preview.

Sessions whose files are on another machine deny `preview_start` with "can't be started in this
session: the desktop app runs on the user's computer and can't read files on your machine". The
check is the `not_available_here` branch next to `launch_cwd_missing`; the session types it covers
were not enumerated.

Readiness is probed by a TCP connect to both `127.0.0.1` and `::1`, so a server bound to only one of
them is detected.

## Selecting page elements

The Browser pane has a selection mode. The user toggles it, hovers and clicks elements in the page
(Shift adds to the selection, and a pane exit gesture ends it). Relocate:
`rg -n 'enableInspectMode|captureElementContext|toggleSelectionMode'`.

Per picked element the main process reads, over the Chrome DevTools Protocol, and sends to the
claude.ai renderer through the `Launch_$_elementSelected` IPC channel (`onElementSelected(cb)` in
`mainView.js`; also `elementsDeselected`, `selectionModeEnded`):

| Field                                                     | Content                                                                                                             |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `tagName`, `id`, `classes`                                | From `DOM.describeNode`                                                                                             |
| `attributes`                                              | Subset: data-testid, data-test-id, aria-label, name, type, href, role, placeholder, title, alt, onclick, value, src |
| `action`                                                  | `navigates to: <href>` or `onclick: <first 100 chars>`                                                              |
| `computedStyles`                                          | A fixed list of CSS properties                                                                                      |
| `boundingBox`                                             | Box-model content rectangle                                                                                         |
| `innerText`                                               | First 200 characters                                                                                                |
| `parentPath`                                              | Selector-style path through up to 4 ancestors                                                                       |
| `outerHTML`, `siblingHTML`                                | `outerHTML` cut at 2000 characters, plus neighboring HTML                                                           |
| `screenshot`                                              | Base64 PNG of the element plus padding, longest side capped at 1200 px                                              |
| `reactComponent`, `reactProps`, `component`, `sourceFile` | React component name, owner chain, props, and source location when React is detected                                |

The page URL is not part of this payload. The IPC delivers it to the web frontend, which composes
the actual message to the Claude session. That frontend is served remotely and is not in this
bundle, so how the payload is rendered into the prompt (text block, image attachment, pill in the
composer) is not verifiable here. Each pick carries a `pickId`
(`<tab>:<generation>:<backendNodeId>`) so the frontend can remove a pick when it is deselected.
Separately, Claude can inspect elements itself with `preview_inspect {serverId, selector, styles}`.

An unrelated "annotate" action exists for the iOS simulator pane (`ccd_simulator_annotate`). There
is no free-form screenshot annotation in the Browser pane.

## Network and CSP behavior of the preview webview

The preview uses its own Electron session. Findings from the `launch-preview:before-request` handler
(`rg -n 'launch-preview:before-request'`):

- Desktop injects no Content-Security-Policy into dev-server pages and does not change
  `webSecurity`. Standard browser rules apply: a cross-origin `fetch` or `EventSource` needs CORS
  headers from the target server. A cross-origin `<script src>` needs none.
- A strict CSP (`default-src 'none'; script-src 'none'; connect-src 'none'`) applies only to static
  HTML that Claude renders as a "Claude page" (`isClaudePage`), not to dev servers.
- Subresource requests (`http`, `https`, `ws`, `wss`) from a page whose origin is a loopback host
  (`localhost`, `127.x`, `::1`, `*.localhost`) are classified as initiated by Desktop's own preview
  and are allowed, including to another loopback port. A loopback page therefore can load a script
  from `http://127.0.0.1:8788` and call it, provided the target sends CORS headers.
- A page on a non-loopback origin (an external site) is refused access to loopback targets, unless
  the user has allowed local network access for that HTTPS origin
  (`launchPreviewLocalNetworkAccess*` settings; telemetry
  `desktop_launch_preview_local_network_allowed`). Metadata and private-IP targets from external
  pages are cancelled.
- Sessions marked `publicHostsOnly` (Cowork and organization-governed sessions) cancel requests to
  any non-public host, loopback included.
- Main-frame navigation to a local-class host on a governed session requires a consent record.
- Organization browsing policy can block subresource origins
  (`Blocked subresource to host-policy-blocked origin`).
