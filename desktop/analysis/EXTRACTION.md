# Extraction, Modification, and Re-verification

How to unpack the app for inspection, repack a modified copy, and re-check the facts in this doc set
after an update.


## Extracting the app code

App-specific code lives in an ASAR archive (Atom Shell Archive — a tar-like Electron format):

```
/Applications/Claude.app/Contents/Resources/app.asar
```

Extract it:

```bash
npx --yes asar extract "/Applications/Claude.app/Contents/Resources/app.asar" /tmp/claude-asar-extract
```

The Electron runtime, Chromium, and native frameworks under `Claude.app/Contents/Frameworks/` are
generic Electron, not app-specific.

To search the archive without extracting it — useful for finding which of the ~90 chunks holds a
string — the format is an 8-byte pickle header, a JSON directory, then concatenated file bodies:

```python
import json, struct
f = open('/Applications/Claude.app/Contents/Resources/app.asar', 'rb')
hsz = struct.unpack('<II', f.read(8))[1]     # bytes 0-7:  pickle size word, then header size
jsz = struct.unpack('<II', f.read(8))[1]     # bytes 8-15: string framing, then JSON length
hdr = json.loads(f.read(jsz).decode())
base = 8 + hsz                               # file bodies start here

def walk(node, path=''):
    for k, v in node.get('files', {}).items():
        q = f'{path}/{k}'
        if 'files' in v: yield from walk(v, q)
        else: yield q, v

needle = b'vm_bundles'
for q, v in walk(hdr):
    if not v.get('size') or 'offset' not in v: continue   # 'unpacked' entries have no body here
    f.seek(base + int(v['offset'])); body = f.read(int(v['size']))
    if needle in body:
        print(q, v['size'], body.count(needle))
```

Entries flagged `unpacked` appear in the header with a size but no `offset` — their bodies live
beside the archive in `app.asar.unpacked/` (the native `.node` modules and bundled MCP binaries).
Skip them or read them from that directory.

`hsz` is measured from offset 8, so bodies start at `8 + hsz` — which is also `16 + jsz` plus the
pickle's alignment padding. Using `16 + hsz` reads garbage.


## Modifying the app (ASAR repack)

```bash
# Extract
npx --yes asar extract "/Applications/Claude.app/Contents/Resources/app.asar" /tmp/claude-asar-extract

# Edit files in /tmp/claude-asar-extract/...

# Repack
npx asar pack /tmp/claude-asar-extract "/Applications/Claude.app/Contents/Resources/app.asar"

# Re-sign (repacking invalidates the code signature)
codesign --force --deep --sign - /Applications/Claude.app
```

Caveats:

- Repacking invalidates the app signature. The ad-hoc re-sign above satisfies macOS, but Gatekeeper
  may quarantine the result.
- The next app update overwrites `app.asar` with a fresh copy, losing the changes.
- Prefer config-file edits or env vars over asar patching where possible — those survive updates.
  See [CONFIGURATION](./CONFIGURATION.md) and [ENVIRONMENT_VARIABLES](./ENVIRONMENT_VARIABLES.md).


## Re-verification recipes

Run these against a fresh extract after an update, then refresh the [README](./README.md) banner and
any drifted details across the doc set. The main-process code is code-split, so search the whole
`.vite/build/` directory rather than a single file.

```bash
EX=/tmp/claude-asar-extract

# Build metadata (version, commit, timestamp, build type)
grep -rhoE '"appVersion":"[^"]*"|"commitHash":"[^"]*"|"commitTimestamp":"[^"]*"|"buildType":"[^"]*"' \
  "$EX/.vite/build/"*.js | sort -u

# All process.env.* references (deduped)
find "$EX" -name "*.js" -not -path "*/node_modules/*" \
  | xargs grep -ohE 'process\.env\.[A-Z][A-Z0-9_]+' \
  | sed 's/process.env.//' | sort -u

# Env vars accessed through the lazy-getter accessor map (misses the grep above)
grep -rhoE '(CLAUDE|ANTHROPIC|COWORK|OFFICE|OAUTH|API)_[A-Z0-9_]+:\(\)=>' "$EX/.vite/build/"*.js \
  | sed -E 's/:\(\)=>.*//' | sort -u

# MCP core protocol negotiation list (latest first). The latest version is hoisted into a variable
# and the array's first element is that identifier, not a literal — so anchor on the OLDEST version
# and read leftward. Literals are backtick-quoted; a double-quote pattern finds nothing.
grep -rhoE '.{110}`2024-10-07`' "$EX/.vite/build/"*.js | sort -u

# MCP Apps (ui/*) method vocabulary referenced anywhere
grep -rhoE '"ui/[a-z/-]+"' "$EX/.vite/build/"*.js "$EX/.vite/renderer/"**/*.js 2>/dev/null | sort -u

# Preference schema keys. The zod object and the defaults object live in different chunks; the
# defaults object is the easier read. Brace-match rather than using a fixed-width window — the
# schema outgrew any constant .{N}, and the zod helper names are re-minified every build.
grep -rl 'menuBarEnabled' "$EX/.vite/build/"*.js        # then brace-match in Python

# -3p suffix logic (Claude-3p directory mechanism). Backtick-quoted since the minifier switched
# to template literals; the '"-3p"' form matches nothing.
grep -rn -- '`-3p`' "$EX/.vite/build/"*.js

# Remote managed-settings / org-policy fetcher
grep -rn 'loadRemoteManagedSettings\|/api/claude_code/settings' "$EX/.vite/build/"*.js

# One-line context for a single variable or identifier
grep -rhoE '.{45}NAME_HERE.{55}' "$EX/.vite/build/"*.js | head -1
```

Minified identifiers (`_9()`-style function names, single-letter vars) change every build — treat
any that appear in this doc set as snapshot illustrations, not stable names. The behaviors and
string literals they anchor to are the durable facts.

String quoting is not durable either. This build's minifier emits template literals, so `` `-3p` ``
and `` `2025-11-25` `` rather than `"-3p"` and `"2025-11-25"`. A recipe that pins the quote
character will silently return nothing after a toolchain change, which reads identically to the
feature having been removed. When a recipe comes back empty, re-check the quoting before concluding
anything is gone.


## A search trap: bounded repetition on minified lines

The context-window recipes above use fixed-length `.{N}` deliberately. Do not reach for the
bounded-range form when adapting them:

```bash
grep -aoE '.{0,80}(foo|bar)[^a-z].{0,200}' app.asar      # hangs
grep -aoE '.{100}realpath(Sync)?\(.{120}' app.asar       # hangs
```

Minified chunks are single lines of hundreds of KB, and `app.asar` is one ~40 MB line as far as
`grep` is concerned. Combining `.{0,N}` ranges with alternation or an optional group makes the
regex engine backtrack essentially without bound — two such greps ran for over 40 minutes here
without producing output. Fixed-length `.{N}` with no alternation is far safer but still slow on the
whole archive.

The reliable pattern is to locate with a fixed string, then slice context in Python:

```bash
grep -l 'someStringLiteral' "$EX/.vite/build/"*.js      # which chunk
```

```python
s = open(chunk, errors='replace').read()
i = s.find('someStringLiteral')
print(s[max(0, i-400):i+400])
```

Re-indenting a chunk first (`re.sub(r';(?=[A-Za-z$_\[(])', ';\n', s)`) makes it greppable by line
without changing semantics, which is worth doing once per chunk under investigation.
