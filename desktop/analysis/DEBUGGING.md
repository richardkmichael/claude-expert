# Debugging

How to attach debuggers and raise log verbosity across the main process, renderer, and native
modules.


## Electron fuses

The shipped Electron binary has its fuses set, and they decide what debugging is possible. Read them
from the fuse wire in `Contents/Frameworks/Electron Framework.framework/Electron Framework`: the
sentinel `dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX` is followed by a version byte, a count, and one ASCII
byte per fuse (`0` off, `1` on). `npx @electron/fuses read --app /Applications/Claude.app` prints
the same. This build's wire is `010011011`:

| Fuse                                    | State |
| --------------------------------------- | ----- |
| `RunAsNode`                             | off   |
| `EnableCookieEncryption`                | on    |
| `EnableNodeOptionsEnvironmentVariable`  | off   |
| `EnableNodeCliInspectArguments`         | off   |
| `EnableEmbeddedAsarIntegrityValidation` | on    |
| `OnlyLoadAppFromAsar`                   | on    |
| `LoadBrowserProcessSpecificV8Snapshot`  | off   |
| `GrantFileProtocolExtraPrivileges`      | on    |
| `EnableWasmTrapHandlers`                | on    |


## JavaScript (main process)

The shipped app has no main-process inspector. `EnableNodeCliInspectArguments` is off, so Electron
ignores `--inspect` and `--inspect-brk` and does not start the inspector on `SIGUSR1`.
`EnableNodeOptionsEnvironmentVariable` is off, so `NODE_OPTIONS=--inspect` is ignored too, and
`RunAsNode` is off, so `ELECTRON_RUN_AS_NODE` does nothing.

Chromium debugging and network-override switches are refused outright. `index.pre.js` checks argv
for `remote-debugging-port`, `remote-debugging-pipe`, `ignore-certificate-errors`,
`host-resolver-rules`, `host-rules`, `disable-web-security`, `log-net-log`, `net-log-capture-mode`,
`ssl-key-log-file` and the `*-cmd-prefix` / launcher / subprocess-path switches, matching by prefix
after stripping a leading `--`, `-` or `/`, any `=value`, and lowercasing. Unless a valid
`CLAUDE_CDP_AUTH` token is present (see below), the app writes "Claude: refusing to start — a
debugging or network-override switch is present on the command line." to stderr and exits with
status 1. Relocate with `rg -n 'refusing to start' .vite/build`.

Raise verbosity with `ELECTRON_ENABLE_LOGGING=1`, `DESKTOP_LOG_LEVEL=debug`, and
`CLAUDE_ENABLE_LOGGING=1`. See [ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md).


## JavaScript (renderer)

Create `developer_settings.json` with `{"allowDevTools": true}` in the user data directory to enable
renderer DevTools. The menu items "Show Dev Tools" (Cmd+Option+I) and "Show All Dev Tools", and the
context-menu "Inspect Element", then appear. Menu visibility is read once at launch, so restart
after creating the file. DevTools stay off even with the file when the managed key
`developerModeEnabled` is `false`, or when the install is in restricted (`coworkHipaaRestricted`)
mode. Relocate with `rg -n 'allowDevTools' .vite/build`.

The gate (`Iq`) is: the flag, and not coworkHipaa-restricted, and `developerModeEnabled !== false`.
"Enable Developer Mode…" in Help > Troubleshooting writes `allowDevTools: true` to
`developer_settings.json` after a confirmation dialog ("Enable Developer Mode?"), and the menu items
appear after a restart.

DevTools can attach to the Code-session Browser pane's page. Preview tabs are created with
`webPreferences` that do not set `devTools: false` (relocate: `rg -n 'focusOnNavigation: !1'` in the
preview class, with `session`, `sandbox`, `plugins`). With developer mode on:

- Cmd+Option+I while a preview tab has focus calls `openDevTools({mode: "undocked"})` on that tab's
  own `webContents` (the tab's `before-input-event` handler, relocate with
  `rg -n 'openDevTools\(Lq\)'`).
- The tab's `context-menu` handler builds the shared menu, whose "Inspect Element" item calls
  `inspectElement` on the tab's `webContents`. The item exists only when `allowDevTools` is true.
- "Show Dev Tools" opens DevTools for `getFocusedWebContents()`, which is the preview tab when it
  has focus. "Show All Dev Tools" opens the main window's views and the find-in-page view, plus the
  focused one.

Artifact popup windows are the exception: they use `devTools: !app.isPackaged`, so DevTools is off
there in a packaged app.

The main window renders the remote `https://claude.ai` frontend in a `WebContentsView`, so
renderer DevTools inspect that frontend — this is where web-frontend features such as the MCP Apps
host live. See [ARCHITECTURE](./ARCHITECTURE.md) and [MCP_APPS](./MCP_APPS.md).


## CDP authentication

The CDP-auth token is the only way past the argv guard above. It is validated in `index.pre.js`
(relocate with `rg -n 'CDP auth rejected' .vite/build`).

Token format:

```
<timestamp_ms>.<base64(userDataDir)>.<base64(ed25519_sig)>
```

Checks, in order:

- Both `CLAUDE_CDP_AUTH` and `CLAUDE_USER_DATA_DIR` must be set.
- The token must have three dot-separated parts.
- The middle part, base64-decoded, must equal `$CLAUDE_USER_DATA_DIR`.
- The timestamp must parse as a number, and its age must be within 300000 ms (5 minutes) and not
  negative.
- The signature over `<timestamp>.<base64-payload>` must verify against a public key embedded in
  the bundle.

The key is Ed25519, not RSA: the embedded SPKI is 44 bytes carrying OID 1.3.101.112 and a 32-byte
raw key, and verification calls `crypto.verify(null, …)` — the `null` algorithm form Ed25519
requires.

Each failure logs a specific `CDP auth rejected: <reason>` warning.

In a packaged build without a valid token, the app deletes `CLAUDE_USER_DATA_DIR` and
`SSLKEYLOGFILE` from its environment at startup, so a custom user data directory also needs the
token.

The same guard doubles as the gate for the developer dev-URL override (`CLAUDE_AI_URL` on a
`.ant.dev` host or `localhost`), for `CLAUDE_E2E_PKCE_LOG`, and for the e2e test hooks — see
[ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md).


## Native modules (.node)

`@ant/claude-native`, `@ant/claude-swift` (which includes `computer_use.node`), and `node-pty` are
compiled Mach-O shared libraries (arm64 in this install), unpacked to
`Contents/Resources/app.asar.unpacked/node_modules/`. They load into the Electron main process, so
native debugging means `lldb -p <pid>` against it. The app is signed with the hardened runtime and
without the `com.apple.security.get-task-allow` entitlement
(`codesign -d --entitlements :- /Applications/Claude.app`), so macOS refuses the attach unless
System Integrity Protection's debugging restriction is disabled or the app is re-signed. Symbols are
sparse: `claude-native-binding.node` defines only `_napi_register_module_v1` (`nm -U`), while
`swift_addon.node` keeps some Swift symbols.
