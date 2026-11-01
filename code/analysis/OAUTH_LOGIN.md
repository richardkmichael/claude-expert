Verified against: cli.prettier.js 2.1.289 (2026-10-07)

# OAuth login (claude.ai subscription and Console)

How `/login`, `claude auth login` and `claude setup-token` obtain first-party OAuth tokens: the
authorize URL and its parameters, the localhost and manual (copy-paste) redirects, the token
exchange, refresh, and revoke. Detailed enough to reimplement the client side. The public docs
describe only the user-facing commands.

## Endpoints and client IDs (prod)

The OAuth config object holds every URL and the client ID. Relocate it with
`rg -n 'MANUAL_REDIRECT_URL: "https' cli.prettier.js`. A sibling block returns the `local` variant
(`CLAUDE_LOCAL_OAUTH_*_BASE` env vars), and `CLAUDE_CODE_CUSTOM_OAUTH_URL` rewrites every URL onto
one base, which must be in a hard-coded allowlist (`is not an approved endpoint`).

| Key                       | Value                                                            |
| ------------------------- | ---------------------------------------------------------------- |
| `CLAUDE_AI_AUTHORIZE_URL` | `https://claude.com/cai/oauth/authorize`                         |
| `CONSOLE_AUTHORIZE_URL`   | `https://platform.claude.com/oauth/authorize`                    |
| `TOKEN_URL`               | `https://platform.claude.com/v1/oauth/token`                     |
| `MANUAL_REDIRECT_URL`     | `https://platform.claude.com/oauth/code/callback`                |
| `CLAUDEAI_SUCCESS_URL`    | `https://platform.claude.com/oauth/code/success?app=claude-code` |
| `CONSOLE_SUCCESS_URL`     | `https://platform.claude.com/buy_credits?returnUrl=…`            |
| `CLIENT_ID`               | `9d1c250a-e61b-44d9-88ed-5944d1962f5e`                           |
| `DESIGN_CLIENT_ID`        | `59637612-477b-4836-a601-b0589eda7704`                           |
| `API_KEY_URL`             | `https://api.anthropic.com/api/oauth/claude_cli/create_api_key`  |
| `ROLES_URL`               | `https://api.anthropic.com/api/oauth/claude_cli/roles`           |

`CLAUDE_CODE_OAUTH_CLIENT_ID` overrides `CLIENT_ID` and turns off the `user:plugins` scope.

Two more client IDs live outside the config object, each with its own fixed scope list:

- Keyless Console sign-in: client `41077d10-94b8-4194-be48-d251e9eb21b4`, scopes
  `user:profile user:inference`, sent to the Console authorize URL. Relocate with
  `rg -n '"41077d10-' cli.prettier.js`.
- Design (`/design-login`): `DESIGN_CLIENT_ID` (or `CLAUDE_CODE_DESIGN_OAUTH_CLIENT_ID`), scopes
  `user:design:read user:design:write`, sent to the claude.ai authorize URL.

## Scopes

Relocate the scope constants with `rg -n '"user:sessions:claude_code",' cli.prettier.js`.

- claude.ai set: `user:profile user:inference user:sessions:claude_code user:mcp_servers
  user:file_upload`, plus `user:plugins` while `PLUGINS_SCOPE_REGISTERED` is true (prod default).
- Console-only addition: `org:create_api_key`.
- Optional, refresh-only: `user:projects:read user:projects:write`, carried forward if already
  granted.

The default authorize request sends the deduplicated union of the Console list and the claude.ai
set, for both claude.ai and Console logins:

    org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers
    user:file_upload user:plugins

`setup-token` sends `user:inference` alone. A custom OAuth client (keyless Console, design) sends
its own list. No code path requests `user:profile` alone with the main `CLIENT_ID`, and the client
does not validate requested scopes. After the exchange, it classifies the token as claude.ai if
the granted `scope` contains `user:inference`, and Console otherwise. This choice selects the
success redirect.

## Authorize request

The builder appends the parameters in this order. Relocate it with
`rg -n 'searchParams.append\("code", "true"\)' cli.prettier.js`.

| Param                   | Value                                                       |
| ----------------------- | ----------------------------------------------------------- |
| `code`                  | `true`                                                      |
| `client_id`             | custom client's ID, else `CLIENT_ID`                        |
| `response_type`         | `code`                                                      |
| `redirect_uri`          | `MANUAL_REDIRECT_URL` or `http://localhost:<port>/callback` |
| `scope`                 | space-joined scope list (see Scopes)                        |
| `code_challenge`        | `base64url(sha256(code_verifier))`                          |
| `code_challenge_method` | `S256`                                                      |
| `state`                 | 32 random bytes, base64url without padding                  |
| `orgUUID`               | only when set (`forceLoginOrgUUID` managed setting)         |
| `login_hint`            | only when set (`claude auth login --email`)                 |
| `login_method`          | only when set: `sso` for `claude auth login --sso`          |

The `code_verifier` is also 32 random bytes as base64url without padding. The base64url step
replaces `+`→`-` and `/`→`_` and strips `=`.

The flow builds two URLs from the same verifier, state, and port. The manual URL
(`redirect_uri=MANUAL_REDIRECT_URL`) is the one printed or shown with "Paste code here if
prompted >". The automatic URL (`redirect_uri=http://localhost:<port>/callback`) is the one opened
in the browser.

## Redirects

Automatic (localhost):

- A Node `http` server listens on `127.0.0.1` with port `0`, so the OS picks an ephemeral port.
  The `redirect_uri` still names the host `localhost`.
- Path `/callback`. Any other path gets a 404.
- The handler reads `code`, `state`, `error`, `error_description` and `error_uri`. A state
  mismatch returns 400 `Invalid state parameter`. A missing code returns 400
  `Authorization code not found`.
- After a successful exchange, the handler 302s the browser to `CLAUDEAI_SUCCESS_URL` (granted
  scopes include `user:inference`) or `CONSOLE_SUCCESS_URL`. On failure, it 302s to
  `CLAUDEAI_SUCCESS_URL`.

Manual (copy-paste):

- The Anthropic-hosted `https://platform.claude.com/oauth/code/callback` page displays a string of
  the form `<code>#<state>`.
- Every paste site (`/login` UI, `claude auth login` stdin, the GitHub-app token setup)
  does `split("#")` and rejects input unless both halves are non-empty ("Invalid code. Please make
  sure the full code was copied").
- Only the code half is used. The pasted state is passed along but never compared with the
  generated state. The token exchange sends the state the client generated.
- If a paste arrives, the exchange uses `redirect_uri=MANUAL_REDIRECT_URL`. If the localhost
  callback won, it uses the localhost URI. The choice follows which path delivered the code.

## Token exchange

Relocate with `rg -n 'grant_type: "authorization_code"' cli.prettier.js`.

`POST TOKEN_URL`, `Content-Type: application/json`, 30 s timeout. JSON body:

| Field           | Value                                                      |
| --------------- | ---------------------------------------------------------- |
| `grant_type`    | `authorization_code`                                       |
| `code`          | the authorization code                                     |
| `redirect_uri`  | same value as the authorize request that produced the code |
| `client_id`     | custom client's ID, else `CLIENT_ID`                       |
| `code_verifier` | the PKCE verifier                                          |
| `state`         | the generated state                                        |
| `expires_in`    | only when set: `31536000` (365 days) for `setup-token`     |

A non-200 response fails the login. A 401 reports "Invalid authorization code". The client reads
`access_token`, `refresh_token`, `expires_in`, `refresh_token_expires_in` (a 30-day default
applies when it is absent), `scope` (space-separated), `account.uuid`, `account.email_address`,
`organization.uuid`, `organization.name`, `workspace.id` and `workspace.name`.

Next, the client calls `GET https://api.anthropic.com/api/oauth/profile` with
`Authorization: Bearer <access_token>` to get `organization.organization_type` (mapped to the
subscription type), `rate_limit_tier`, `seat_tier` and `billing_type`. Custom clients skip this
call.

## Refresh

Relocate with `rg -n 'grant_type: "refresh_token"' cli.prettier.js`.

`POST TOKEN_URL`, JSON body `{grant_type: "refresh_token", refresh_token, client_id, scope}`,
plus `expires_in` when set. `scope` is always sent. If the caller passes no scopes, it defaults to
the claude.ai set.

The scheduled refresh does not narrow scope. For a main-client claude.ai token (the stored scopes
include `user:inference` or a subscription type is recorded, and no custom client ID is stored),
it requests the full claude.ai set plus any already-granted `user:projects:*` scopes. This widens
a narrower token. If the server answers `invalid_scope`, the client logs
`tengu_oauth_refresh_invalid_scope_fallback` and retries with exactly the stored scopes. Other
tokens refresh with their stored scopes. The response's `refresh_token` replaces the old one
when present.

`CLAUDE_CODE_OAUTH_REFRESH_TOKEN` (`claude auth login`) refreshes with the scopes in
`CLAUDE_CODE_OAUTH_SCOPES`, which is required, and `expires_in=31536000`. That is the one caller
that refreshes with a caller-chosen scope list, which may be narrower than the original grant.

Revoke: `POST TOKEN_URL + "/revoke"` with `{token, token_type_hint: "refresh_token", client_id}`.

## `claude setup-token`

- Always uses the claude.ai authorize URL, with `scope=user:inference` only.
- Sends `expires_in=31536000` on the code exchange. The UI reports a "1-year" token. The
  `expiresInDays` option parser is a stub that always returns 365 days.
- Prints the access token for use as `CLAUDE_CODE_OAUTH_TOKEN`. It does not store it as the
  session login.
- Refused when a `forceLoginMethod` policy disallows claude.ai or when `allowedProviders`
  excludes first-party.
- The Chrome integration message notes the consequence: such tokens lack `user:profile`, so
  `/api/oauth/validate` rejects them ("env-var and setup-token sessions default to user:inference
  only").

## Accepted redirect URIs

The bundle has no server-side list of the redirect URIs accepted for `CLIENT_ID`. The client
uses only two shapes: `http://localhost:<ephemeral port>/callback` and `MANUAL_REDIRECT_URL`.
The bundled `redirect_uris` handling belongs to the MCP OAuth client (dynamic registration,
`https://claude.ai/oauth/claude-code-client-metadata`), not to this first-party login.
