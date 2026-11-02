# Limit Resets

How Settings > Usage reads the usage-limit resets granted to an account, and the request the `Use`
button sends to apply one. Resets are a claude.ai web feature: the desktop app shows them because
its main window loads the claude.ai frontend, not because of code in `app.asar`.

## Where the code lives

The desktop app's tray usage menu opens the page by navigating its main window to
`<main window URL>/settings/usage`; that is the only reference to the page in `app.asar`. The page,
the reset UI and the claim request are all in the remotely served claude.ai frontend, so they are
absent from the extracted `app.asar` and change on the web deploy schedule rather than with desktop
releases.

The internal name of the feature is `cedar_ember`. It appears as a query flag, a response key, the
`program` value of the claim request, and the analytics events `claudeai.cedar_ember.*`. It is an
internal code name, so it can be renamed or removed with any frontend deploy. Code that depends on
it should detect the response by shape (an object whose `grants[]` entries carry `resets_left` and
`ends_at`) and treat a missing block as unknown rather than as zero resets.

## Reading the resets

```
GET https://claude.ai/api/organizations/{org_uuid}/usage?cedar_ember=1&skip_spend=1
```

- Authentication is the claude.ai session cookie. The desktop main process reads the active org UUID
  from the `lastActiveOrg` cookie.
- The `cedar_ember=1` flag requests the reset block. A variant used at a limit sends `at_wall=1` in
  its place.
- The same response carries the usual limit windows (`five_hour`, `seven_day`, `seven_day_sonnet`
  and so on, each `{utilization, resets_at}`), `limits[]` and `extra_usage`.

The reset status is the top-level `cedar_ember` object:

| Field               | Meaning                                                           |
| ------------------- | ----------------------------------------------------------------- |
| `eligible`          | Whether the account can hold resets                               |
| `ineligible_reason` | Why not, when `eligible` is false                                 |
| `at_limit`          | Whether a limit is hit right now                                  |
| `exhausted[]`       | The limit kinds currently hit                                     |
| `grants[]`          | One entry per grant, described below                              |
| `next_grant_id`     | The grant the `Use` button claims; null when nothing is claimable |
| `weekly_resets_at`  | The next weekly reset                                             |
| `cooldown_until`    | End of a claim cooldown, or null                                  |
| `event_props`       | Analytics context: tier, tenure bucket, billing path, surface     |
| `paused_held`       | Not read by the frontend                                          |

Each grant:

| Field                | Meaning                                                            |
| -------------------- | ------------------------------------------------------------------ |
| `id`                 | Grant identifier, a readable slug naming the promotion             |
| `label`              | Human-readable description of the grant                            |
| `resets_total`       | Resets the grant provides                                          |
| `resets_left`        | Resets not yet used                                                |
| `starts_at`          | Start of the grant's validity                                      |
| `ends_at`            | Expiry, shown in the UI as the grant's expiry date                 |
| `clears[]`           | The limit windows a reset clears, such as `five_hour`, `seven_day` |
| `gives_back_weekly`  | Whether a reset restores weekly allowance                          |
| `paused`             | Whether the grant is paused                                        |
| `usable_now`         | Whether the grant can be claimed right now                         |
| `use_requires_limit` | Whether a limit must be hit before the grant can be used           |
| `percent_used`       | Current utilization of each cleared window                         |
| `blocking[]`         | Limits that prevent use right now                                  |
| `type`               | Grant kind (`full` observed); not read by the frontend             |
| `arm`                | Experiment arm; not read by the frontend                           |
| `unavailable_reason` | Why `usable_now` is false; not read by the frontend                |

The page counts available resets as the sum of `resets_left` over grants that are not paused. A used
grant stays in `grants[]` with `resets_left: 0` at least until its `ends_at`, and the page hides it,
so a fully used set of grants renders as "No resets right now".

## Applying a reset

The `Use` button sends:

```
POST https://claude.ai/api/organizations/{org_uuid}/reset_rate_limits
Content-Type: application/json

{"program": "cedar_ember", "grant_id": "<grants[].id>", "request_id": "<client-generated id>"}
```

- Authentication is the claude.ai session cookie.
- `grant_id` is normally `next_grant_id` from the reset status.
- `request_id` is generated per click. A retry of an attempt with an unknown outcome resends the
  same `request_id`, so the server can treat it as the same claim.
- The same route without a grant in the body is a dev tool that internal test accounts use to reset
  their limits. Its availability is gated by the `can_reset_rate_limits` capability.

The response fields are `result`, `reason`, `reset` (bool), `grant_id`, `resets_left`, `cleared[]`,
`weekly_resets_at` and `cooldown_until`.

| `result`       | Meaning                                                  |
| -------------- | -------------------------------------------------------- |
| `reset`        | The reset was applied                                    |
| `already_used` | The grant has no resets left                             |
| `not_limited`  | No limit needs clearing                                  |
| `cooldown`     | A claim cooldown is in effect                            |
| `ineligible`   | The account or grant is not eligible                     |
| `unavailable`  | The reset cannot be applied right now; `reason` says why |

The client adds two outcomes of its own: `rate_limited` for an HTTP 429 and `error` for any other
failure. `reason` is one of `config_off`, `tier`, `seat`, `mobile`, `surface`, `cli_version`,
`no_grant`, `tenure`, `other_experiment`, `control`, `not_enrolled`, `plan_changed`, `unavailable`,
`paused`, `expired`, `unknown_grant`, `not_next_grant`, `blocked_by_other_limit`,
`grant_id_required`, `not_limited` or `already_used`.

After an error, `already_used` or `cooldown`, the page fetches the reset status again and compares
the grant's `resets_left` and `percent_used` with their values before the claim. This determines
whether the reset was applied even when the response was lost.

## Other usage endpoints

Neither of these carries reset grants:

- `GET https://claude.ai/api/organizations/{org_uuid}/usage`, called by the desktop main process for
  the tray usage menu with the session cookie.
- `GET https://api.anthropic.com/api/oauth/usage`, called by the desktop Claude Code integration
  with the OAuth bearer token and `anthropic-beta: oauth-2025-04-20`.

The desktop main process polls the first one without `cedar_ember=1`, adding `?skip_spend=1` to
background polls except about once an hour. It keeps the result in a `plan-usage` store and appends
samples to `plan-usage-history.json` in the app's data directory. It reads `five_hour`, `seven_day`,
`seven_day_opus`, `seven_day_oauth_apps`, `seven_day_cowork`, `seven_day_omelette`,
`omelette_promotional` (shown in the tray as "Claude Design grant"), `seven_day_sonnet`, `limits[]`
and `extra_usage` from it. The second returns the same limit windows, and the desktop app reads only
`five_hour`, `seven_day`, `seven_day_sonnet`, `seven_day_opus`, `limits[]` and `extra_usage` from
it.

## Other code-named blocks in the usage response

The `/usage` response carries further top-level blocks under code names. On an account with no
active promotions they are all `null`. The frontend groups them as follows:

- Extra limit windows, each `{utilization, resets_at}` and grouped with `omelette_promotional`:
  `iguana_necktie`, `nimbus_quill`, `cinder_cove`, `amber_ladder`, `copper_kite`, `harbor_lantern`,
  `wattle_ember` and `granite_teacup`.
- `tangelo` is a limit window included when computing the next reset. It has its own
  `tangelo_credit_grant` endpoint.
- `starry_waterfall` is a credit or discount offer, requested with `starry_waterfall=<value>` in the
  query.
- `brass_thimble` and `juniper_tide` are feature and experiment flags elsewhere in the frontend.
- `amber_cistern` and `amber_gauge` are not read by the frontend.

## Inspecting it locally

The main window's Chromium HTTP cache keeps the last response of each request, including the
`/usage` call the Usage page makes. The server sends no `Cache-Control` header, so the copy is never
reused as fresh, but it stays on disk under
`~/Library/Application Support/Claude/Cache/Cache_Data/`. Reading it shows the reset status without
sending a request.

Each entry is a Chromium simple-cache file: a 24-byte header whose bytes 12-15 hold the key length,
the key (the URL), the body, then an end-of-stream marker followed by the response headers. Bodies
keep their `content-encoding`, usually `zstd`:

```python
import json, struct, subprocess, sys

data = open(sys.argv[1], 'rb').read()
key_len = struct.unpack_from('<I', data, 12)[0]
eof = data.find(struct.pack('<Q', 0xf4fa6f45970d41d8), 24 + key_len)
body, headers = data[24 + key_len:eof], data[eof:].lower().replace(b' ', b'')
for encoding, cmd in ((b'zstd', ['zstd', '-dc', '-q']), (b'br', ['brotli', '-dc']),
                      (b'gzip', ['gzip', '-dc'])):
    if b'content-encoding:' + encoding in headers:
        body = subprocess.run(cmd, input=body, capture_output=True).stdout
        break
print(json.dumps(json.loads(body).get('cedar_ember'), indent=2))
```

Find the entry with `rg -l -a -F 'cedar_ember=1' Cache_Data`. The same decoding applies to the
cached frontend JS from `assets-proxy.anthropic.com`. Format the chunks with `oxfmt` before reading
them, and search for string literals such as `resets_left`, `reset_rate_limits` and `cedar_ember`,
because minified names change on every deploy.
