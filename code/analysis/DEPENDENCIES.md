---
verified: 2.1.317
verified_on: 2026-11-03
section: Architecture and dependencies
style: landmark
scope: >-
  Third-party libraries inlined or embedded, version anchors, Bun built-ins used in their place, and
  libraries not bundled
landmarks:
  - '"ajv implementation error"'
  - X-Stainless-Package-Version
  - 'reconcilerVersion: "'
  - This runtime has no Bun.Image
---
# Inlined Third-Party Dependencies

The third-party code Claude Code ships inside `cli.prettier.js`: for each library, the string that
locates it, the string that pins its version where the bundle carries one, and what the app uses it
for. Run every `rg` below from `work/<version>/package/` against `cli.prettier.js`.

## How libraries sit in the bundle

- Libraries are inlined into the `chunk-<hash>.js` modules. A match belongs to the module named by
  the nearest `// ==== bun module:` banner above it. The one library the app requires by name at run
  time is `undici` (see Undici).
- Packages published as CommonJS keep their wrapper: a factory over an `exports` object that opens
  with `Object.defineProperty(<exports>, "__esModule", ...)`. ESM packages are flattened.
- Some libraries are inlined twice, an ESM copy and a CommonJS or UMD copy pulled in by another
  dependency or by a lazily imported module: Zod, AJV, ajv-formats and tslib. Expect two clusters of
  hits.
- Some packages embed their own `package.json` as an object literal. This lists every one, with its
  version:

      rg -n -U -o -r '$1 $2' \
        'name: "(@?[a-z0-9][a-z0-9./_@-]*)",\n(?:.*\n){0,3}?\s*version: "(\d+\.\d+\.\d+[^"]*)"' \
        cli.prettier.js

  It prints gaxios, google-auth-library, five `@aws-sdk/*` clients, openid-client and
  `@grpc/grpc-js`.
- The browser libraries injected into HTML artifact pages (mermaid, Chart.js, a highlight.js build)
  are embedded as raw files beside the modules. Only their loaders and file paths appear in
  `cli.prettier.js` (see Embedded browser bundles).
- Where Bun has a built-in, the app calls it and bundles no library (see Bun built-ins in place of
  libraries).

## Validation

### Zod

Schema validation, used for the app's schemas throughout.

- Version: 4.6.2. Zod 4 embeds its version as an object literal:
  `rg -n 'major: 4, minor: \d+, patch: \d+'` hits twice, the ESM copy and a CommonJS copy. The
  CommonJS copy sits in the lazily imported module behind `claude gateway` (see openid-client).
- Find: `rg -n -F '"$ZodError"'`.
- A Zod 3-API copy is also present: `typeName` values such as `ZodEffects`, and the error
  `rg -n 'in conjunction with custom error map'`. It carries no version constant.
- Only English error messages are bundled (`rg -n -F 'Invalid input: expected'`); Zod's locale packs
  are not.
- https://github.com/colinhacks/zod

### AJV (Another JSON Schema Validator)

JSON Schema validation. Two copies, an ESM one and a CommonJS one, both 8.18.0; each fingerprint
below hits in both copies.

- Find: `rg -n -F '"ajv implementation error"'`.
- Version: 8.18.0. AJV embeds no version constant, so it is pinned by source fingerprint:
  - Major 8, not 6: `rg -n -F 'ajv/dist/runtime/'` finds the codegen strings
    `require("ajv/dist/runtime/{equal,ucs2length,uri,validation_error}")`, the v8 `dist/runtime/*`
    layout. v6 has no `dist/runtime/`.
  - URI resolver is `fast-uri`, so at least 8.17.1 (8.17.0 was never published; 8.16 and earlier use
    `uri-js`). Module specifiers don't survive bundling, so fingerprint by absence: the punycode
    error strings `uri-js` inlines (`"not-basic"`, `"invalid-input"`) are absent.
  - At least 8.18.0: the `pattern` keyword wraps the `$data` regexp in a try/catch. Grep the codegen
    literal `rg -n -F 'code === "new RegExp"'` (8.17.1 used a plain ternary and lacks it).
  - Below 8.20.0: the `Ajv` constructor initializes `this.formats = {}`
    (`rg -n -F 'this.formats = {}'`); 8.20.0 switched to `Object.create(null)`.
  - Only 8.17.1, 8.18.0 and 8.20.0 exist in that window, so at least 8.18.0 and below 8.20.0 pins
    8.18.0.
- The `Ajv2020` draft-2020-12 class is bundled alongside the default `Ajv`.
- `ajv-formats` is fully inlined, in both copies: its `fullFormats` / `fastFormats` tables with
  `formatNames`, the `formatMaximum` / `formatMinimum` / `formatExclusiveMaximum` /
  `formatExclusiveMinimum` keywords, and the plugin that picks `fastFormats` when `mode === "fast"`.
  Find it by the formats it adds: `"iso-date-time"`, `"iso-time"`, `"uri-template"`,
  `"relative-json-pointer"`. Version 3.0.x, not pinnable further: the compiled runtime is
  byte-identical across `3.0.0-rc.0`, `3.0.0` and `3.0.1`, and no version string is embedded. npm
  `latest` is `3.0.1`, the likely resolved version.
- `ajv-errors` is not bundled; the lone `ajvErrors` string is AJV's own deprecated-options map.
- Used:
  - The MCP SDK's JSON Schema validator: an `Ajv` instance with `ajv-formats` applied, caching
    compiled validators by `$id`.
  - MCP tool input schemas, compiled with `Ajv2020` before a call. On failure it logs
    `rg -n 'Ajv could not compile it'`.
- https://github.com/ajv-validator/ajv

## HTTP and networking

### Axios

Promise-based HTTP client.

- Version: 1.15.2. `rg -n -F '"User-Agent", "axios/"'` finds the User-Agent built from a version
  variable; that variable's declaration, earlier in the same module, holds the version string.
- Find: `rg -n -F 'axios@${Math.random()}'`; `rg -n -F 'name = "AxiosError"'`.
- Bundles `follow-redirects`: `rg -n 'The follow-redirects package should be excluded'`.
- https://github.com/axios/axios

### Undici

Not inlined: `UndiciError` and undici's `debuglog("undici")` are absent. The app requires `undici`
by name through `import.meta.require` (Bun's `require`), so the runtime supplies the module.

- Find: `rg -n 'EnvHttpProxyAgent'`; `rg -n 'setGlobalDispatcher'`.
- Used: proxy support. The app builds an `EnvHttpProxyAgent` for the proxy URL, adding the mTLS
  client certificate and CA when configured, and installs it with `setGlobalDispatcher` so `fetch`
  goes through the proxy.
- https://github.com/nodejs/undici

### https-proxy-agent

HTTPS-over-proxy agent for Node's `http`/`https` clients. No version string.

- Find: `rg -n 'Creating new HttpsProxyAgent instance'`. It sits in the same module as the undici
  proxy setup, where the app subclasses it. gaxios and MSAL use it too.
- https://github.com/TooTallNate/proxy-agents

## Anthropic and MCP SDKs

### Anthropic TypeScript SDK (`@anthropic-ai/sdk`)

The Messages API client.

- Version: 0.128.0. `rg -n -F 'X-Stainless-Package-Version'` finds the request headers, whose value
  is a version variable declared just above them. The same variable builds the User-Agent
  `rg -n -F 'anthropic-sdk-typescript/'`.
- Provider clients, each lazily imported: `AnthropicBedrock`, `AnthropicBedrockMantle`,
  `AnthropicVertex`, `AnthropicFoundry`. They identify themselves with User-Agents such as
  `AnthropicBedrock/JS` and `AnthropicVertex/JS`.
- Find: `rg -n 'Streaming is required for operations that may take longer than 10 minutes'`.
- https://github.com/anthropics/anthropic-sdk-typescript

### MCP TypeScript SDK (`@modelcontextprotocol/sdk`)

MCP client and transports. The package version is not embedded.

- Protocol: `LATEST_PROTOCOL_VERSION` is `"2025-11-25"`; the supported list is 2025-11-25,
  2025-06-18, 2025-03-26, 2024-11-05, 2024-10-07. Find it in the SDK's export list:
  `rg -n ' as LATEST_PROTOCOL_VERSION'`; the declaration and the supported list are a few lines into
  that module.
- Find: `rg -n -F 'io.modelcontextprotocol/related-task'` (the tasks metadata key).
- https://github.com/modelcontextprotocol/typescript-sdk

## Cloud provider SDKs

### AWS SDK for JavaScript (v3)

- Version: 3.936.0, from the embedded `package.json` of each client:
  `rg -n 'name: "@aws-sdk/client-bedrock-runtime"'` (version two lines below).
- Clients: `client-bedrock-runtime`, `client-bedrock`, `client-sts`, `client-sso` and
  `nested-clients` (which carries SSO OIDC). Smithy's `SignatureV4` signs requests
  (`rg -n -F 'AWS4-HMAC-SHA256'`); `SignatureV4a` is registered only as a `null` placeholder, so the
  CRT signer is not bundled. `fast-xml-parser` (`XMLParser`) handles XML protocols.
- Find: `rg -n 'BedrockRuntimeClient'`.
- Used: Bedrock model access (`CountTokensCommand`, `ListInferenceProfiles`) and AWS credential
  resolution.
- https://github.com/aws/aws-sdk-js-v3

### google-auth-library and gaxios

- Version: google-auth-library 10.6.2, gaxios 7.1.4, from their embedded `package.json`:
  `rg -n 'name: "google-auth-library"'`; `rg -n 'name: "gaxios"'`.
- Used: Vertex AI authentication (`rg -n 'buildVertexGoogleAuth'`).
- https://github.com/googleapis/google-auth-library-nodejs

### Azure identity and MSAL

- Version: `@azure/msal-node` 3.8.1 and `@azure/msal-common` 15.13.1, from their license banners
  (`rg -n -F '/*! @azure/msal-node v'`). `@azure/identity` 4.10.1: `rg -n 'azsdk-js-identity/'`
  finds the User-Agent built from a version constant declared earlier in the module.
- Used: Microsoft Foundry. Without `ANTHROPIC_FOUNDRY_API_KEY` or `ANTHROPIC_FOUNDRY_AUTH_TOKEN`,
  the app gets a bearer token from `DefaultAzureCredential` for the scope
  `https://cognitiveservices.azure.com/.default`.
- https://github.com/AzureAD/microsoft-authentication-library-for-js

### openid-client and jose

- Version: openid-client 5.7.1, from its embedded `package.json` (`rg -n 'panva/openid-client'`).
  jose has no version string: `rg -n 'JWSSignatureVerificationFailed'`.
- Used: `claude gateway` (`rg -n 'Run the enterprise auth/telemetry gateway'`), whose lazily
  imported module also holds the CommonJS Zod copy.
- https://github.com/panva/openid-client

## Telemetry and feature flags

### OpenTelemetry JS

Tracing, metrics and logs, exported over OTLP or Prometheus.

- Version: `rg -n '\.VERSION = "\d+\.\d+\.\d+"'` hits four times: `1.9.0` (`@opentelemetry/api`),
  `2.7.1` (`@opentelemetry/core`, reported as `telemetry.sdk.version`), and `0.208.0` twice (the
  OTLP exporter packages, which send `OTel-OTLP-Exporter-JavaScript/<version>`).
- Find: `rg -n '@opentelemetry/api: Attempted duplicate registration'`.
- Exporters: OTLP traces, metrics and logs over `http/json`, `http/protobuf` and `grpc`, plus
  `PrometheusExporter`. Protobuf encoding is static generated code
  (`rg -n -F 'opentelemetry.proto.collector'`); no protobufjs package string is present.
- `rpc.grpc.status_code` is an OpenTelemetry semantic-convention constant, not gRPC code.
- https://github.com/open-telemetry/opentelemetry-js

### gRPC (`@grpc/grpc-js`)

- Version: 1.14.4, from its embedded `package.json` (`rg -n 'name: "@grpc/grpc-js"'`). Its build
  path also survives: `rg -n -F 'node_modules/@grpc/grpc-js/build/src'`.
- Used: the OTLP gRPC exporters.
- https://github.com/grpc/grpc-node

### GrowthBook JS SDK

Feature-flag client.

- Version: 1.6.1. The SDK class sets `this.version` from a helper that returns the version literal
  inside a `try` block; the helper sits just above the class.
- Find: `rg -n 'Cannot use remoteEval on GrowthBook Cloud'`; the SDK's default host
  `rg -n -F 'https://cdn.growthbook.io'`.
- App configuration: client key `rg -n 'sdk-zAZezfDKGoZuXXKe'`, `apiHost`
  `https://api.anthropic.com/`, `remoteEval: true`, so flags are evaluated server-side by a POST to
  `${host}/api/eval/${clientKey}`. How flags are cached, read and switched off: `FEATURE_FLAGS.md`.
- https://github.com/growthbook/growthbook

## Terminal UI

### React (reconciler)

- Version: 19.2.0, from the DevTools registration: `rg -n 'reconcilerVersion: "'`. React's own
  `version` export string is not present.
- Find: `rg -n '__REACT_DEVTOOLS_GLOBAL_HOOK__'` (the reconciler's DevTools injection; no DevTools
  bundle); the React 19 element symbol `rg -n -F 'react.transitional.element'`.
- https://github.com/facebook/react

### Ink (fork)

The terminal renderer is built on Ink but extended well past upstream.

- Find: the export list, `rg -n ' as useStdin,$'`. It exports Ink's `render`, `Box`, `Text`,
  `useApp`, `useStdin` alongside components and hooks upstream Ink lacks: `Button`, `ClickEvent`,
  `PointerEvent`, `ThemeProvider`, `useSelection`, `useTerminalViewport`.
- Host element names: `ink-root`, `ink-box`, `ink-text`, `ink-virtual-text`, and the non-upstream
  `ink-raw-ansi` (`rg -n -F '"ink-raw-ansi"'`).
- Layout: no `yoga-layout` package or wasm is bundled. A pure-JS node class exposing Yoga's node API
  (`setMeasureFunc`, `calculateLayout`, `getComputedHeight`) does the flexbox layout, and the
  renderer records timing for it (`rg -n 'lastYogaCounters'`). The source does not show whether that
  class is a third-party port or Anthropic's own.
- https://github.com/vadimdemedes/ink

### highlight.js

Syntax highlighting of code blocks in terminal output.

- Version: 11.11.1. `rg -n 'versionString = '` finds the assignment; its source is a constant
  declared near the top of the same module.
- Find: `rg -n -F 'github.com/highlightjs/highlight.js/issues/'`.
- A separate browser build is embedded for artifact pages (see Embedded browser bundles).
- https://github.com/highlightjs/highlight.js

### marked

Markdown lexer and parser. No version string.

- Find: `rg -n -F 'marked(): input parameter is undefined or null'`.
- https://github.com/markedjs/marked

## HTML and text processing

### parse5

HTML5 tokenizer and parser. No version string; the tokenizer states are a numeric enum, as in parse5
7 and later, so state names do not appear as strings.

- Find: the error codes `rg -n -F '"eof-in-comment"'`;
  `rg -n 'non-void-html-element-start-tag-with-trailing-solidus'`. A small wrapper module re-exports
  `Tokenizer`, `TokenizerMode` and `parse`.
- Used: publishing HTML artifact pages. It finds where to insert runtime blocks before `</body>`
  (`rg -n 'runtimeBlockInsertionIndex'`) and locates elements by `id`.
- https://github.com/inikulin/parse5

### Turndown and domino

HTML-to-Markdown converter and the server-side DOM it parses into (`@mixmark-io/domino`). Both live
in one lazily imported module.

- Find: `rg -n 'Turndown failed, falling back to raw HTML'`; `rg -n '__domino_frozen__'`;
  `rg -n 'turndown-root'`.
- Used: WebFetch converts fetched HTML to Markdown, after removing `style`, `script`, `noscript` and
  `iframe` elements. If conversion throws, it keeps the raw HTML.
- https://github.com/mixmark-io/turndown

### jsdiff

Text diff and patch library. No version string.

- Find: its patch-parser errors `rg -n -F 'Hunk at line'`; `rg -n -F '"Unknown line "'`.
- https://github.com/kpdecker/jsdiff

### jsonc-parser

Microsoft's JSON-with-comments scanner and parser. No version string.

- Find: `rg -n 'InvalidCommentToken'`.
- https://github.com/microsoft/node-jsonc-parser

## Utilities

### Commander.js

CLI argument parsing for `claude` and its subcommands. No version string.

- Find: `rg -n 'commander.invalidArgument'`; `rg -n 'commander.excessArguments'`.
- https://github.com/tj/commander.js

### Fuse.js

Fuzzy search.

- Version: 7.0.0. The class's static `version` is assigned on the line before
  `rg -n -F '.createIndex = '`.
- Find: the defaults object `{ location: 0, threshold: 0.6, distance: 100 }` and option names
  `includeScore`, `keys: [{ name, weight }]`.
- Used: ranking slash-command typeahead (keys `commandName`, `displayName`, `partKey`, `aliasKey`,
  `displayPartKey`; threshold 0.3) and `@`-mention suggestions for MCP resources and agents
  (threshold 0.6).
- https://github.com/krisk/Fuse

### Lodash

Utility functions, bundled as per-function modules with no `VERSION` string.

- Find: `rg -n '__lodash_hash_undefined__'` (three hits).
- https://github.com/lodash/lodash

### node-semver

- Find: `rg -n 'SEMVER_SPEC_VERSION'` (the semver spec version `2.0.0`, not the package version).
  App code also compares versions with `Bun.semver`.
- https://github.com/npm/node-semver

### lru-cache

- Find: `rg -n 'max option must be a nonnegative integer'`. No version string.
- https://github.com/isaacs/node-lru-cache

### chokidar

File watcher.

- Find: its license banner `rg -n -F '/*! chokidar - MIT License'`. No version string; the
  `fsevents` backend is absent, as in chokidar 4 and later.
- Used: watching skill files, among others (`rg -n 'tengu_skill_file_changed'` records
  `source: "chokidar"`).
- https://github.com/paulmillr/chokidar

### node-forge

Pure-JS cryptography, PKI and TLS. No version string.

- Find: `rg -n 'ByteStringBuffer'` (one module).
- Used: the sandbox runtime's TLS-terminating proxy. It loads a CA from `tlsTerminate.caCertPath` or
  generates an ephemeral one (`rg -n 'sandbox-runtime ephemeral CA'`, log prefix `[mitm-ca]`), then
  mints leaf certificates from it.
- https://github.com/digitalbazaar/forge

### tslib

TypeScript runtime helpers. Two copies: a UMD build (`rg -n -F 'define("tslib"'`) and an ESM build
exporting `__extends`, `__awaiter`, `__spreadArray`. No version string; the embedded AWS SDK
`package.json` literals require `tslib: "^2.6.2"`.

## Embedded browser bundles

These files are embedded in the binary as raw assets and are not extracted into `cli.prettier.js`. A
small module reads each one, and the HTML artifact publisher injects it into pages that need it.
Failures log the `artifact_publish` events in the last column.

| File                          | Version | Loader export         | Failure event               |
| ----------------------------- | ------- | --------------------- | --------------------------- |
| `mermaid.min.js`              | 11.16.1 | `loadMermaidBundleJs` | `mermaid_bundle_unreadable` |
| `chart.umd.min.js` (Chart.js) | unknown | `loadChartBundleJs`   | `chart_bundle_unreadable`   |
| `hljsBundle.generated.min.js` | unknown | `loadHljsBundleJs`    | `hljs_bundle_unreadable`    |

Find: `rg -n 'loadMermaidBundleJs|loadChartBundleJs|loadHljsBundleJs'`. Mermaid's version comes from
the banner its loader prepends: `rg -n -F '/*! mermaid v'`.

## Bun built-ins in place of libraries

| Built-in                                           | In place of                               |
| -------------------------------------------------- | ----------------------------------------- |
| `Bun.Image`                                        | sharp                                     |
| `Bun.YAML`                                         | a YAML library (`yaml`, `js-yaml`)        |
| `Bun.TOML`                                         | a TOML parser                             |
| `Bun.stringWidth`, `Bun.wrapAnsi`, `Bun.stripANSI` | `string-width`, `wrap-ansi`, `strip-ansi` |
| `Bun.Terminal`                                     | a PTY library such as `node-pty`          |
| `Bun.semver`                                       | app-side version comparison               |

`Bun.Image` is wrapped in an object exposing sharp's chain (`metadata`, `resize`, `rotate`, `jpeg`,
`png`, `webp`, `toBuffer`). Find it with `rg -n 'This runtime has no Bun.Image'`. The others:
`rg -n 'Bun\.(YAML|TOML|stringWidth|wrapAnsi|stripANSI|Terminal|semver)'`.

## Not bundled

| Library          | Evidence                                                                |
| ---------------- | ----------------------------------------------------------------------- |
| RxJS             | `BehaviorSubject`, `ReplaySubject`, `ObjectUnsubscribedError` absent    |
| Sharp            | `@img/sharp-` absent; images go through `Bun.Image`                     |
| Undici (code)    | `UndiciError` absent; `undici` is required at run time                  |
| ws               | `WebSocket was closed before the connection was established` absent     |
| yaml, js-yaml    | `YAMLParseError`, `YAMLException` absent; YAML goes through `Bun.YAML`  |
| Sentry SDK       | `@sentry`, `sentry_key` absent                                          |
| Statsig SDK      | `StatsigUser`, `statsig.com` absent                                     |
| Datadog SDK      | `dd-trace` absent; the app posts logs to the Datadog HTTP intake itself |
| MIME database    | `mime-db` absent                                                        |
| Zod locale packs | non-English Zod messages absent                                         |

- Errors reach telemetry without Sentry: process handlers emit `tengu_uncaught_exception` and
  `tengu_unhandled_rejection` events. `SentryErrorBoundary` appears only as an app log string.
- `statsig` survives only as the legacy `~/.claude/statsig` directory name, in cleanup lists and a
  `Read(~/.claude/statsig/**)` permission rule.
- Datadog logs go to `rg -n -F 'http-intake.logs.us5.datadoghq.com/api/v2/logs'`.

## Quick reference

| Library             | Version | Anchor (fixed string)                                   |
| ------------------- | ------- | ------------------------------------------------------- |
| Zod                 | 4.6.2   | `"$ZodError"`                                           |
| AJV                 | 8.18.0  | `"ajv implementation error"`                            |
| ajv-formats         | 3.0.x   | `"relative-json-pointer"`                               |
| Axios               | 1.15.2  | `"User-Agent", "axios/"`                                |
| https-proxy-agent   | unknown | `Creating new HttpsProxyAgent instance`                 |
| Anthropic SDK       | 0.128.0 | `X-Stainless-Package-Version`                           |
| MCP TypeScript SDK  | unknown | ` as LATEST_PROTOCOL_VERSION`                           |
| AWS SDK v3          | 3.936.0 | `name: "@aws-sdk/client-bedrock-runtime"`               |
| google-auth-library | 10.6.2  | `name: "google-auth-library"`                           |
| @azure/msal-node    | 3.8.1   | `/*! @azure/msal-node v`                                |
| @azure/identity     | 4.10.1  | `azsdk-js-identity/`                                    |
| openid-client       | 5.7.1   | `panva/openid-client`                                   |
| OpenTelemetry API   | 1.9.0   | `@opentelemetry/api: Attempted duplicate registration`  |
| @grpc/grpc-js       | 1.14.4  | `name: "@grpc/grpc-js"`                                 |
| GrowthBook SDK      | 1.6.1   | `Cannot use remoteEval on GrowthBook Cloud`             |
| React reconciler    | 19.2.0  | `reconcilerVersion: "`                                  |
| Ink (fork)          | n/a     | `"ink-raw-ansi"`                                        |
| highlight.js        | 11.11.1 | `github.com/highlightjs/highlight.js/issues/`           |
| marked              | unknown | `marked(): input parameter is undefined or null`        |
| parse5              | 7+      | `non-void-html-element-start-tag-with-trailing-solidus` |
| Turndown + domino   | unknown | `__domino_frozen__`                                     |
| jsdiff              | unknown | `Hunk at line`                                          |
| jsonc-parser        | unknown | `InvalidCommentToken`                                   |
| Commander.js        | unknown | `commander.invalidArgument`                             |
| Fuse.js             | 7.0.0   | `.createIndex = `                                       |
| Lodash              | unknown | `__lodash_hash_undefined__`                             |
| lru-cache           | unknown | `max option must be a nonnegative integer`              |
| chokidar            | 4+      | `/*! chokidar - MIT License`                            |
| node-forge          | unknown | `ByteStringBuffer`                                      |
| tslib               | unknown | `define("tslib"`                                        |
