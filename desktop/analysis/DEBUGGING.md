# Debugging

How to attach debuggers and raise log verbosity across the main process, renderer, and native
modules.


## JavaScript (main process)

Launch Electron with `--inspect=9229` or `--inspect-brk=9229` and connect via `chrome://inspect`.

With `--remote-debugging-port` or `--remote-debugging-pipe`, the app additionally requires a valid
`CLAUDE_CDP_AUTH` token (see below). Normal launches do not need it.

Raise verbosity with `ELECTRON_ENABLE_LOGGING=1`, `DESKTOP_LOG_LEVEL=debug`, and
`CLAUDE_ENABLE_LOGGING=1`. See [ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md).


## JavaScript (renderer)

Renderer DevTools work in the app window (Cmd+Option+I, or the View menu) once enabled. Create
`developer_settings.json` with `{"allowDevTools": true}` in the user data directory to enable them.

The main window renders the remote `https://claude.ai/new` frontend in a `WebContentsView`, so
renderer DevTools inspect that frontend — this is where web-frontend features such as the MCP Apps
host live. See [ARCHITECTURE](./ARCHITECTURE.md) and [MCP_APPS](./MCP_APPS.md).


## CDP authentication

The CDP-auth guard protects against unauthorized debugger attaches. It fires only when argv contains
`--remote-debugging-port` or `--remote-debugging-pipe`, and is validated in `index.pre.js` (function
`Dm()` in this build).

Token format:

```
<timestamp_ms>.<base64(userDataDir)>.<base64(rsa_sig)>
```

Checks, in order:

- Both `CLAUDE_CDP_AUTH` and `CLAUDE_USER_DATA_DIR` must be set.
- The token must have three dot-separated parts.
- The middle part, base64-decoded, must equal `$CLAUDE_USER_DATA_DIR`.
- The timestamp must be a valid number and within 5 minutes of now.
- The RSA signature over `<timestamp>.<base64-payload>` must verify against a public key embedded in
  the bundle.

Each failure logs a specific `CDP auth rejected: <reason>` warning.


## Native modules (.node)

`@ant/claude-native`, `@ant/claude-swift` (which includes `computer_use.node`), and `node-pty` are
compiled Mach-O shared libraries. Debug with `lldb -p <pid>` against the running Electron process;
they are likely stripped of symbols.

`SIGUSR1` to the Electron process enables the Node.js inspector (JS side), not native debugging.
