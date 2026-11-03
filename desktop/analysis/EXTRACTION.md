---
verified: 4.4212.0
scope: Unpacking, repacking/re-signing, re-verification recipes
---
# Extraction, Modification, and Re-verification

How to unpack the app for inspection, repack a modified copy, and re-check the facts in this doc set
after an update.


## Extracting the app code

App-specific code lives in an ASAR archive (Atom Shell Archive — a tar-like Electron format):

```
/Applications/Claude.app/Contents/Resources/app.asar
```

Prepare it with the `prepare-claude-desktop-source` skill, or run its script directly:

```bash
.claude/skills/prepare-claude-desktop-source/bin/prepare-claude-desktop-source.sh [/path/to/Claude.app]
```

It extracts `app.asar` with a pinned `@electron/asar` into `desktop/work/<app-version>/app`, formats
every `.js` file under `.vite/build/` with the same pinned oxfmt the Claude Code pipeline uses, and
writes `desktop/work/<app-version>/manifest.json`. The manifest records the app's build info
(version, commit, commit timestamp, build type), the Claude Code version the build pins, and how the
main-process bundle is split into files. A version already prepared is reported and left alone.
`.vite/renderer/` and `resources/` are extracted but not formatted.

A second archive sits beside it: `Contents/Resources/ion-dist.asar` (~190 MB), the bundled web
frontend that custom third-party mode serves (see [ARCHITECTURE](./ARCHITECTURE.md)). The skill does
not extract it; `desktop/bin/asar-search.py <needle> .../ion-dist.asar` searches it in place.

The Electron runtime, Chromium, and native frameworks under `Claude.app/Contents/Frameworks/` are
generic Electron, not app-specific.

To search the archive without extracting it, which is useful for finding which of the several
hundred chunks holds a string, run `desktop/bin/asar-search.py <needle> [app.asar]`. It prints each
matching file's path inside the archive, its size and the match count. The format it reads is an
8-byte pickle header, a JSON directory, then concatenated file bodies.

Entries flagged `unpacked` appear in the header with a size but no `offset` — their bodies live
beside the archive in `app.asar.unpacked/` (the native `.node` modules and bundled MCP binaries).
The search skips them; read them from that directory.

The header size is measured from offset 8, so bodies start at `8 + header size`, which is also
`16 + JSON length` plus the pickle's alignment padding. Using `16 + header size` reads garbage.

Each file entry also carries an `integrity` record (SHA-256 of the whole file plus per-4 MiB block
hashes), and the app's `Info.plist` key `ElectronAsarIntegrity` holds a SHA-256 of the header JSON
for both `app.asar` and `ion-dist.asar`.


## Modifying the app (ASAR repack)

The shipped Electron has the `EnableEmbeddedAsarIntegrityValidation` and `OnlyLoadAppFromAsar` fuses
on (see [DEBUGGING](./DEBUGGING.md#electron-fuses)). Electron checks `app.asar`'s header against the
`ElectronAsarIntegrity` hash in `Info.plist` at launch, so a repacked archive needs that hash
updated too, and editing `Info.plist` in turn breaks the code signature. Work on a copy of the app,
never on `/Applications/Claude.app`:

```bash
APP=~/claude-patched/Claude.app            # a copy: cp -R /Applications/Claude.app ~/claude-patched/
EX=$(mktemp -d)/app

# Extract
npx --yes @electron/asar extract "$APP/Contents/Resources/app.asar" "$EX"

# Edit files in "$EX"/... (native modules stay in app.asar.unpacked/ and must stay unpacked)

# Repack, keeping the same entries unpacked
npx @electron/asar pack "$EX" "$APP/Contents/Resources/app.asar" \
  --unpack '{*.node,*.dylib,spawn-helper,github-mcp-server}'

# Update the integrity hash: SHA-256 of the new header JSON
NEW_HASH=$(python3 -I -c '
import hashlib, struct, sys
f = open(sys.argv[1], "rb"); f.read(12); n = struct.unpack("<I", f.read(4))[0]
print(hashlib.sha256(f.read(n)).hexdigest())' "$APP/Contents/Resources/app.asar")
/usr/libexec/PlistBuddy -c "Set :ElectronAsarIntegrity:Resources/app.asar:hash $NEW_HASH" \
  "$APP/Contents/Info.plist"

# Re-sign (repacking and the plist edit invalidate the code signature)
codesign --force --deep --sign - "$APP"
```

Caveats:

- The ad-hoc re-sign drops Anthropic's Team ID and entitlements, so keychain-backed sign-in and
  entitlement-gated features (the Cowork VM needs `com.apple.security.virtualization`) may fail;
  Gatekeeper may also quarantine the result.
- The next app update overwrites `app.asar` with a fresh copy, losing the changes.
- Prefer config-file edits or env vars over asar patching where possible — those survive updates.
  See [CONFIGURATION](./CONFIGURATION.md) and [ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md).


## Re-verification recipes

Run these against a fresh extract after an update, then refresh the [README](./README.md) banner and
any drifted details across the doc set. The main-process code is code-split, so search the whole
`.vite/build/` directory rather than a single file. Use `rg` (see the root `CLAUDE.md`). The
prepared source is formatted one statement per line, so print matching lines rather than fixed-width
context windows. `Q` is a quote class that matches `"`, `'` or a backtick, so the recipes do not
depend on the quote character.

`rg` can skip the code without saying so. The code sits under `.vite/`, a hidden directory, which
`rg` skips unless `--hidden` is set (a `~/.ripgreprc` may set it). `desktop/work/` is gitignored, so
a search that recurses into it from `desktop/` or the repository root skips it entirely. Name
`$EX/.vite/build` explicitly, as below, or pass `-uu`.

```bash
EX=desktop/work/<app-version>/app
Q="[\"'\`]"

# Build metadata (version, commit, timestamp, build type): read desktop/work/<app-version>/manifest.json

# All process.env.* references (deduped)
rg -uu -oN --no-filename -g '*.js' -g '!node_modules' 'process\.env\.[A-Z][A-Z0-9_]+' "$EX" \
  | sed 's/process.env.//' | sort -u

# Upper-case names in the chunks' lazy-getter export maps (misses the search above). The formatted
# source writes these as `NAME: () =>`.
rg -oN --no-filename '(CLAUDE|ANTHROPIC|COWORK|OFFICE|OAUTH|API)_[A-Z0-9_]+: \(\) =>' "$EX/.vite/build" \
  | sed -E 's/: \(\) =>.*//' | sort -u

# MCP core protocol negotiation list (latest first). The latest version is hoisted into a variable
# and the array's first element is that identifier, not a literal, so anchor on the OLDEST version.
# The formatted array sits on one line; read the hoisted variable one line above it.
rg -N --no-filename -B1 "${Q}2024-10-07${Q}" "$EX/.vite/build"

# MCP Apps (ui/*) method vocabulary referenced anywhere. The quote class also matches an escaped
# \"ui/...\" inside a template literal.
rg -oN --no-filename "${Q}ui/[a-z][a-z/-]*" "$EX/.vite/build" "$EX/.vite/renderer" | cut -c2- | sort -u

# Preference schema keys. The zod object and the defaults object live in different chunks; the
# defaults object is the easier read. In the formatted source both are one key per line.
rg -l 'menuBarEnabled' "$EX/.vite/build"

# -3p suffix logic (Claude-3p directory mechanism)
rg -n -- "${Q}-3p${Q}" "$EX/.vite/build"

# Remote managed-settings / org-policy fetcher
rg -n 'loadRemoteManagedSettings|/api/claude_code/settings' "$EX/.vite/build"

# Context for a single variable or identifier: the line, plus neighbors
rg -n -C3 'NAME_HERE' "$EX/.vite/build" | head -20
```

Minified identifiers (single-letter and short mangled names) change every build — treat any that
appear in this doc set as snapshot illustrations, not stable names. The behaviors and string
literals they anchor to are the durable facts.

String quoting is not durable either. oxfmt normalizes string literals to double quotes in the
formatted extract, but literals that are part of a template literal stay backtick-quoted, and
strings nested inside one keep their escapes (`\"…\"`). The shipped `app.asar` is matched byte for
byte by `asar-search.py`, so a needle there must match the minifier's choice: this build ships
`"-3p"` and `"2024-10-07"`, with no backtick forms. When a recipe comes back empty, re-check the
quoting before concluding anything is gone.


## A search trap: bounded repetition on minified lines

The formatted extract is one statement per line, so line-oriented `rg` works on it directly. The raw
`app.asar` is not: its chunks are minified single lines of up to several MB, and the archive is one
~58 MB blob as far as a line-oriented tool is concerned.

On raw files, do not use the bundled `grep` with bounded ranges:

```bash
grep -aoE '.{0,80}(foo|bar)[^a-z].{0,200}' app.asar      # hangs
grep -aoE '.{100}realpath(Sync)?\(.{120}' app.asar       # hangs
```

Combining `.{0,N}` ranges with alternation or an optional group makes that regex engine backtrack
essentially without bound. `rg` does not have this problem. For raw files, locate with a fixed
string, then slice context in Python:

```bash
desktop/bin/asar-search.py 'someStringLiteral'           # which file inside app.asar
```

```python
s = open(chunk, errors='replace').read()
i = s.find('someStringLiteral')
print(s[max(0, i-400):i+400])
```
