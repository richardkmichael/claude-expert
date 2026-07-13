# Inlined Third-Party Dependencies

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

Libraries bundled (inlined) into `cli.prettier.js` by the build toolchain.
Line numbers are approximate first-occurrence anchors for discovery, not precise boundary ranges.
The file is an ES module (`import { createRequire }` at line 1).

---

## Libraries

### Zod
Schema validation library (TypeScript-first).
- Anchor: `$ZodError` near line 4815; i18n error message blocks in ~30 languages
  from line ~1 through ~15,000 (Arabic, Vietnamese, etc.)
- Used: settings/config schema validation throughout the application
- https://github.com/colinhacks/zod

### AJV (Another JSON Schema Validator)
JSON schema validation.
- Anchor: `"ajv implementation error"` string literal (present ~9x).
- Plugins: `ajv-formats` is fully inlined (not merely referenced by its codegen
  `require("ajv-formats/dist/formats")` string) — its `dist/formats.js` (the `fullFormats` /
  `fastFormats` tables and `formatNames = Object.keys(fullFormats)`), `dist/limit.js` (the
  `formatMaximum` / `formatMinimum` / `formatExclusiveMaximum` / `formatExclusiveMinimum` keywords),
  and the plugin function that selects `fastFormats` vs `fullFormats` by `mode === "fast"`. Grep the
  format names it adds: `"iso-date-time"`, `"iso-time"`, `"uri-template"`, `"relative-json-pointer"`.
  Version 3.0.x, not pinnable further from the bundle: the compiled runtime (`dist/*.js`) is
  byte-identical across `3.0.0-rc.0` (2021), `3.0.0`, and `3.0.1` (2024) — only the `.d.ts` files and
  the version field differ, and neither reaches the bundle. No SHA/version string is embedded and the
  code matches the published npm tarballs verbatim, so it is a normal semver install (npm `latest` =
  `3.0.1`, the most likely resolved version). `ajv-errors` is not bundled (the lone `ajvErrors` string
  is ajv core's own deprecated-options map).
- Version: 8.18.0 (confirmed against 2.1.207). AJV embeds no version constant, so pin it by source
  fingerprint, not a string. Each step is a grep against `cli.prettier.js`:
  - Major 8, not 6: the `require("ajv/dist/runtime/{equal,ucs2length,uri,validation}")` codegen
    strings — the v8 `dist/runtime/*` layout. v6 has no `dist/runtime/`.
  - URI resolver is `fast-uri`, so >= 8.17.1 (8.17.0 was never published; 8.16 and earlier use
    `uri-js`). Module specifiers don't survive bundling, so fingerprint by absence: the punycode
    error strings that `uri-js` inlines (`"not-basic"`, `"invalid-input"`) are gone.
  - >= 8.18.0: the `pattern` vocabulary wraps the `$data` regexp in a try/catch — grep the codegen
    literal `code === "new RegExp"` (introduced with `gen.let("valid")` + `gen.try(...)` in 8.18.0;
    8.17.1 used a plain ternary and has neither).
  - < 8.20.0: the `Ajv` constructor initializes `this.formats = {}` (8.20.0 switched it to
    `Object.create(null)`).
  - Only 8.17.1 / 8.18.0 / 8.20.0 exist in that window, so `>= 8.18.0` and `< 8.20.0` pins 8.18.0.
- Used: likely MCP/tool schema validation
- https://github.com/ajv-validator/ajv

### tslib
TypeScript runtime helpers emitted by the compiler (`__spreadArray`, `__awaiter`, etc.).
- Anchor: `__spreadArray` near line 30984
- Not a standalone library block — helpers are distributed through the bundle

### RxJS
Reactive programming library (Observables, Subjects, operators).
- Anchor: `BehaviorSubject` near line 32262; `ReplaySubject` near line 32345
- Used: reactive state management, stream processing
- https://github.com/ReactiveX/rxjs

### Axios
Promise-based HTTP client.
- Anchor: `AxiosError` class definition near line 45061; `"axios@"` string near line 44990
- Used: HTTP communication (likely for API calls or proxy handling)
- https://github.com/axios/axios

### OpenTelemetry API
Observability framework (tracing, metrics, logging).
- Anchor: `setTracerProvider` export near line 1989; `"@opentelemetry/api: Attempted duplicate
  registration"` string near line 62605
- Used: internal telemetry and tracing
- https://github.com/open-telemetry/opentelemetry-js

### gRPC / Protocol Buffers
gRPC core library and Protobuf schema support.
- Anchor: `"rpc.grpc.status_code"` near line 64833; `opentelemetry.proto.common.v1` references
  near line 355027
- Used: OpenTelemetry OTLP export over gRPC
- https://github.com/grpc/grpc-node

### Undici
Modern Node.js HTTP/1.1 and HTTP/2 client (with WebSocket support).
- Anchor: `UndiciError` class near line 70213; `debuglog("undici")` near line 71107
- Used: HTTP communication (lower-level than Axios; likely the Anthropic API client)
- https://github.com/nodejs/undici

### AWS SDK for JavaScript (v3)
AWS service clients: Bedrock Runtime, STS, SSO, SSOOIDC; Signature V4 request signing.
- Anchor: `SignatureV4` / `SignatureV4a` near line 93665
- Used: AWS Bedrock model access, IAM credential resolution
- https://github.com/aws/aws-sdk-js-v3

### React + React DOM / Reconciler
React core and reconciler (fiber architecture). Used as the rendering foundation for Ink.
- Anchor: `__REACT_DEVTOOLS_GLOBAL_HOOK__` check near line 140287
- Note: reconciler-specific names (`workInProgress`, `createFiber`) are minified; identify
  by DevTools hook check and `P6()` / `K6(P6(), 1)` pattern used throughout app code
- https://github.com/facebook/react

### Ink
React-based UI framework for terminal/CLI interfaces. Renders React component trees to the
terminal using its own layout engine.
- Anchor: named export block `{ useInput, render, useApp, useStdin, Text, ... }` near line 152068
- Used: all interactive terminal UI (prompt, suggestions, output rendering)
- Note: `yoga-layout` (Ink's flexbox engine) does not appear as a separate string —
  it is either fully inlined or replaced by a wasm module
- https://github.com/vadimdemedes/ink

### Sharp
High-performance image processing library (resize, format conversion, EXIF, etc.).
- Anchor: `@img/sharp-${platform}/versions` require near line 177867;
  `@img/sharp-libvips-*/versions` fallback nearby
- Used: image manipulation for vision/multimodal input processing
- https://github.com/lovell/sharp

### node-forge
Cryptographic library (TLS, PKI, ASN.1, AES, RSA, SHA).
- Anchor: `ByteStringBuffer` export near line 252046
- Used: certificate handling, cryptographic operations (likely for TLS or OAuth flows)
- https://github.com/digitalbazaar/forge

### Highlight.js
Syntax highlighting library with language auto-detection.
- Anchor: GitHub issue URLs `github.com/highlightjs/highlight.js/issues/...` near line 298817
- Used: syntax highlighting in terminal output (code blocks in responses)
- https://github.com/highlightjs/highlight.js

### parse5 (HTML5 tokenizer/parser)
HTML5-conformant tokenizer and tree builder.
- Anchor: state-machine method pattern like `["DOCTYPE_STATE"](A)`,
  `["COMMENT_END_DASH_STATE"](A)` near line 327900; error constants object `ZA` with fields
  like `eofInComment`, `nestedComment` used in tokenizer state handlers
- Used: parsing HTML in model responses or tool output
- https://github.com/inikulin/parse5

### Commander.js
CLI argument parsing framework.
- Anchor: `"commander.invalidArgument"` error code near line 539710
- Used: parsing `claude` command-line arguments and subcommands
- https://github.com/tj/commander.js

### Fuse.js
Lightweight fuzzy-search library (bitap algorithm, scored results, weighted keys).
- Anchor: class with constructor accepting `(collection, { includeScore, threshold, keys:[{name,weight}] })`
  and `.search(query, {limit})` method, near line 454237
- Used: fallback file-name fuzzy matching for `@` completion when Rust FileIndex is unavailable
- Note: fully inlined; identified by characteristic option shape, not by name
- https://github.com/krisk/Fuse  |  https://fusejs.io

### Lodash
General-purpose utility library.
- Anchor: `"__lodash_hash_undefined__"` internal sentinel string near line 313
- Used: deep clone, type checking, array/object utilities scattered through the bundle
- https://github.com/lodash/lodash

### GrowthBook
Feature flag and A/B testing SDK. Replaces Statsig (see below).
- Anchor: class `L81` near line 61726; client key string `"sdk-zAZezfDKGoZuXXKe"` near line 62394
- Initialization: `new L81({ apiHost: "https://api.anthropic.com/", clientKey: OGA, remoteEval: true, ... })`
  near line 534138; `remoteEval: true` means gate evaluation is server-side at the Anthropic API
- Used: feature gate evaluation via `Ow(gateName)` (line 534007); result cached in
  `cachedGrowthBookFeatures` in app state
- `Ow()` checks `cachedGrowthBookFeatures[name]` first, then falls back to `cachedStatsigGates[name]`
  (legacy property still present in app state at line 535744 but no longer populated by a live SDK)
- Disabled entirely when `DISABLE_TELEMETRY` or `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` env vars are set
- User attributes sent for targeting: `id` (deviceId), `sessionId`, `organizationUUID`, `accountUUID`,
  `userType`, `subscriptionType`, `rateLimitTier`, `email`, `appVersion`
- https://github.com/growthbook/growthbook

---

## Absent Libraries

The following libraries are absent:

| Library            | Old role                     | Status         |
|--------------------|------------------------------|----------------|
| Sentry SDK         | Remote error tracking        | Removed, but replaced by two mechanisms: (1) Local file logging — `DXz()` appends error stack/message to `~/.claude/logs/{ts}.jsonl`; the `jXz()` call inside `DXz()` is a no-op. (2) Remote error telemetry via the `n()` telemetry pipeline — `uncaughtException` and `unhandledRejection` process handlers emit `tengu_uncaught_exception` / `tengu_unhandled_rejection` events (with error name and up to 2000 chars of message) plus 50+ other categorized `tengu_*_error` events at specific failure sites. Stack traces are NOT sent remotely. Telemetry likely goes to `https://api.anthropic.com/api/claude_code/metrics`. |
| Statsig SDK        | Feature flags / A/B testing  | Replaced by GrowthBook (see above). `cachedStatsigGates` property still exists in app state (line 535744) as a legacy fallback in `Ow()`, but the Statsig SDK itself is absent. `statsig.com`, `StatsigUser`, `featureGates` strings — not found. |
| MIME Database      | MIME type lookup             | Removed. `mime-db`, IANA source entries — not found. |
| React DevTools     | React debug hook bundle      | Removed as a separate section. `__REACT_DEVTOOLS_GLOBAL_HOOK__` check remains (line 140287) but is a guard in the React bundle, not a DevTools bundle. |
| DOM Implementation | DOM node/tree API            | Removed. `DOMImplementation`, `NodeFilter.SHOW` — not found. Likely replaced by a custom terminal renderer rewrite. |

---

## How to Find Libraries in a New Version

When the version changes and all names are re-minified, use these stable anchors in order:

| Library       | Stable search anchor |
|---------------|----------------------|
| Zod           | `$ZodError` or i18n error message strings (Arabic/Vietnamese/etc.) |
| AJV           | `"ajv implementation error"` |
| RxJS          | `BehaviorSubject`, `ReplaySubject`, `combineLatest` |
| Axios         | `AxiosError`, `"axios@"` random string in Axios internals |
| OpenTelemetry | `"@opentelemetry/api: Attempted duplicate registration"` |
| gRPC          | `"rpc.grpc.status_code"` |
| Undici        | `UndiciError`, `debuglog("undici")` |
| AWS SDK       | `SignatureV4`, `SignatureV4a`, `BedrockRuntime` |
| React         | `__REACT_DEVTOOLS_GLOBAL_HOOK__` |
| Ink           | Named export block with `useInput`, `render`, `useApp`, `useStdin` together |
| Sharp         | `@img/sharp-` require string |
| node-forge    | `ByteStringBuffer` |
| Highlight.js  | `github.com/highlightjs/highlight.js/issues/` in error strings |
| parse5        | State method names: `"DOCTYPE_STATE"`, `"COMMENT_END_DASH_STATE"` as computed keys |
| Commander.js  | `"commander.invalidArgument"` |
| Fuse.js       | Constructor with `{ includeScore, threshold, keys: [{name, weight}] }` + `.search(q,{limit})` |
| Lodash        | `"__lodash_hash_undefined__"` |
| GrowthBook    | Client key string `"sdk-zAZezfDKGoZuXXKe"`; class `L81`; `remoteEval: true` in init options |
