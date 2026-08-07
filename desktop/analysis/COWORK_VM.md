# Cowork VM Bundle On Disk

What `vm_bundles/` actually contains, why `du` disagrees with `ls`, how the images are versioned and
updated, and what that means for relocating or profiling the user data directory.

For the gating that decides whether the bundle is downloaded at all (`yukonSilver`,
`secureVmFeaturesEnabled`, `autoDownloadInBackground`), see [FEATURES](./FEATURES.md).

VM bundle manifest sha `6d1538ba…`, published 2026-06-10 — independent of the app build in the
[README](./README.md) banner, which pins which manifest sha is wanted.


## Bundle layout

`$userData/vm_bundles/` holds two things: `claudevm.bundle/` (the live VM) and `warm/<sha>/` (a
prefetch cache for a future version).

| File                            | Apparent |   On disk | Role                                       |
|---------------------------------|---------:|----------:|--------------------------------------------|
| `rootfs.img`                    | 10.00 GiB| 5.14 GiB  | GPT disk, guest `/` — read-write            |
| `sessiondata.img`               | 10.00 GiB| 6.95 MiB  | ext4, guest `/sessions` — read-write        |
| `rootfs.img.zst`                |  1.19 GiB| 1.19 GiB  | download cache and binary-delta base        |
| `initrd`                        | 77.5 MiB | 77.5 MiB  | boot                                        |
| `initrd.zst`                    | 76.8 MiB | 76.8 MiB  | download cache / delta base                 |
| `vmlinuz`                       | 56.3 MiB | 56.3 MiB  | boot                                        |
| `vmlinuz.zst`                   | 14.3 MiB | 14.3 MiB  | download cache / delta base                 |
| `efivars.fd`                    |  128 KiB |  128 KiB  | EFI NVRAM — per-VM, mutable                 |
| `.<file>.origin`                |  40 B    |           | bundle sha the local `<file>` came from     |
| `.<file>.zst.origin`            |  40 B    |           | bundle sha the local `<file>.zst` came from |
| `.cowork-adopted`               |  40 B    |           | bundle sha marker                           |
| `machineIdentifier`             |   70 B   |           | per-VM identity                             |
| `gvisorMacAddress`              |   17 B   |           | per-VM MAC                                  |
| `vmIP`                          |   11 B   |           | last guest IP                               |

Apparent total 21.41 GiB; `du` total ~6.6 GiB.

`warm/<sha>/` holds `<file>.zst` for a version other than the current one. Stale sha directories are
swept, but the keep-list is `[nextSha, currentSha]`, so a directory can survive as the current sha
after an app update.


## Sparse files, and reading them on macOS

Both `.img` files are sparse: the logical size is fixed but only written blocks are allocated. `du`
reports allocated blocks, `ls` reports `st_size`, hence the ~15 GiB gap.

The fixed logical size is a guest requirement, not a host reservation. `mkfs.ext4` laid out group
descriptors, bitmaps, inode tables and journal for a 10 GiB device, and `rootfs.img`'s GPT puts its
backup header at the last LBA — neither can be grown without `resize2fs`/GPT repair. Nothing is
reserved on the host, so a long-running VM can still fill the disk. The app compensates with
`statfs` prechecks before download and before warm promotion, and classifies `ENOSPC` as
`failure_reason: disk_full`, but that is a check, not a guarantee.

Sparseness is maintained at runtime, not just at creation. `rootfs.img` has 7,725 scattered holes
totalling 4.86 GiB with no hole reaching EOF — the signature of guest discard/TRIM being punched
into the host file. The native addon imports both `ftruncate` and `fcntl` (`F_PUNCHHOLE`).

The shipped artifact is compressed, not sparse: `rootfs.img.zst` is what downloads, and is
zstd-decompressed locally. Sparseness is a local runtime property.

Gotcha when mapping extents: macOS defines `SEEK_HOLE = 3` and `SEEK_DATA = 4`, the inverse of
Linux. Using the Linux constants silently returns the hole map instead of the data map. Cross-check
the total against `stat -f %b` × 512:

```python
import os
SEEK_HOLE, SEEK_DATA = 3, 4          # macOS ordering
fd = os.open(path, os.O_RDONLY); size = os.fstat(fd).st_size
pos = total = 0
while pos < size:
    d = os.lseek(fd, pos, SEEK_DATA)
    if d >= size: break
    h = os.lseek(fd, d, SEEK_HOLE)
    total += h - d; pos = h
```


## rootfs.img

GPT, 10 GiB addressable:

| Partition | Type                   | Size       | Contents                        |
|-----------|------------------------|-----------:|----------------------------------|
| 1         | Linux filesystem       | 10139 MiB  | ext4, label `cloudimg-rootfs`    |
| 15        | EFI System Partition   |    99 MiB  | ESP                              |

An Ubuntu cloud-image layout. Kernel cmdline is
`root=LABEL=cloudimg-rootfs ro console=hvc0 console=hvc1 fsck.repair=yes console=tty1
console=ttyAMA0` — the `ro` is only the initial mount. The partition superblock shows
`last_mounted /`, mount count 10, and a write timestamp matching the last VM run, with 5.13 GiB used
against 5.14 GiB allocated on the host.

So `rootfs.img` is a live read-write disk, not a read-only golden image. There is no separate
writable partition and no overlay. Two VMs cannot share one.


## sessiondata.img

ext4, label `sessions`, `last_mounted /sessions`. Created locally on first VM setup and never
downloaded — it is absent from the bundle manifest, and the reinstall path logs "Reinstall files
deleted (sessiondata.img and compressed cache preserved)". It therefore survives VM version bumps
and reinstalls.

It holds one Linux home directory per Cowork session, named with a docker-style
adjective-adjective-noun and owned by a per-session uid (1001, 1002, …):

```
/<session-name>/
  .bashrc .profile .bash_logout          Ubuntu skel
  tmp/node-compile-cache/v22.22.0-arm64-<hash>-<uid>/
  tmp/claude-<uid>/-sessions-<session-name>/<session-uuid>/tasks/
  .npm/_logs/
  .cache/claude-cli-nodejs/-sessions-<session-name>/mcp-logs-<server>/*.jsonl
  mnt/{uploads,outputs,.claude/{projects,skills},.auto-memory,.remote-plugins/plugin_<id>}
```

Host-mounted folders appear by name under `mnt/`. The native addon exposes
`vmGetSessionsDiskInfo` / `SessionsDiskInfo` and has `prunedSessions` / `skippedSessions` counters,
so there is a pruning path over this disk.


## Versioning and updates

The wanted VM version is a build constant compiled into the app, not fetched. From the bundle
manifest chunk:

```js
versions[0] = { sha: `6d1538ba6fecc4e5c5583993c4b30bb1875f0f5a`, publishedAt: `2026-06-10`,
                files: { unix: { arm64: [ {name:`rootfs.img`, checksum:`f40e54e8…`},
                                          {name:`vmlinuz`,    checksum:`588bfd1d…`},
                                          {name:`initrd`,     checksum:`cb36d011…`} ] … },
                         win32: { … rootfs.vhdx … } } }
```

The manifest's own `$comment` says older `versions[]` entries are retained "so the publish workflow
can generate binary deltas from them". `sessiondata.img` and `efivars.fd` are not in it.

Local state is the 40-byte `.<file>.origin` markers. The readiness check compares that string to the
baked sha and yields `ready` / `missing` / `origin_missing` / `version_mismatch`. There is no "is my
VM stale" network poll — updating the app is what updates the VM.

On mismatch, per file, in order:

1. Warm-bundle promotion from `warm/<sha>/<file>.zst` (decompress, verify, rename into place).
2. Decompress the local `<file>.zst` cache.
3. Binary delta.
4. Full download from `https://downloads.claude.ai/vms/linux/<arch>/<sha>/<file>.zst`.

Integrity is the manifest's per-file sha256 (`checksum`, and `rawChecksum` where the hash is over
the decompressed stream), verified before the staged `<file>.tmp` is renamed into place.

The delta path needs both `<file>.zst` and `.<file>.zst.origin` present, plus a native
`applyVmImageDelta` and a feature flag; it renames `<file>.zst` to `<file>.zst.deltabase` while
working. It is skipped when a warm source is available. Deleting the `.zst` caches therefore forces
a full re-download on the next bump rather than a delta.

The only genuine network version lookup is the warm prefetch:
`GET https://downloads.claude.ai/releases/darwin/universal/<appVersion>/vm_hash`, which returns the
40-hex VM sha for that app version and is staged into `warm/<sha>/`. It only runs for a sha
different from the current one, and requires `autoDownloadInBackground`.


## Path resolution, CLAUDE_USER_DATA_DIR, and profiles

The bundle path is built lexically from `userData` and never canonicalized:

```js
function vmBundlesDir() { return path.resolve(app.getPath(`userData`), `vm_bundles`) }
function bundlePath()   { return path.resolve(vmBundlesDir(), `claudevm.bundle`) }
```

`CLAUDE_USER_DATA_DIR` relocates `userData` before anything else runs (see
[DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md)), so the VM bundle moves with it:

```js
if (process.env.CLAUDE_USER_DATA_DIR) {
  app.setPath(`userData`, process.env.CLAUDE_USER_DATA_DIR);
  app.setPath(`logs`, path.resolve(process.env.CLAUDE_USER_DATA_DIR, `Logs`));
}
```

Using the env var for personal/work profiles therefore gives each profile its own VM bundle, and
they cannot be shared. Not only because `sessiondata.img` carries session state, but because
`rootfs.img` is itself a read-write disk, and `efivars.fd` / `machineIdentifier` /
`gvisorMacAddress` are per-VM identity — sharing the last would give two VMs the same MAC.

Marginal cost of an additional profile is ~6.6 GiB at current sizes, of which ~1.42 GiB is
byte-identical cache and ~5.14 GiB is a rootfs that starts identical and diverges. Both images grow
with use, trending toward ~11 GiB actual per profile. Both profiles run the same binary, so both
always want the identical rootfs and each will independently pull ~1.3 GB on every VM bump.


## Relocating vm_bundles with a symlink

Supported in practice. The path is never `realpath`'d, and the app is not sandboxed: it declares 12
entitlements and `com.apple.security.app-sandbox` is not among them, so there is no container
boundary. (`com.apple.security.virtualization` is present — see [entitlements](#entitlements).)
Everything downstream is ordinary `fs` (`mkdir` recursive, `createWriteStream`, `rename`, `statfs`,
`readdir`) plus the Virtualization.framework attachment, all of which follow symlinks.

The bundle's private-file module does contain symlink hardening, but none of it reaches here:

| Guard                             | Applies to `vm_bundles`?                                     |
|-----------------------------------|---------------------------------------------------------------|
| Pre-traversal probe               | No — gated on `process.platform === 'win32'`                  |
| Below-boundary symlink refusal    | No — scoped to `CLAUDE_CONFIG_DIR`, a registered root, or a literal `.claude` path component |
| `O_NOFOLLOW` on private write     | Leaf file only, never parent directories                      |

That second guard's own error text names "symlink the whole config root" as a supported relocation.

Practical notes:

- Symlink the whole `vm_bundles` directory, not files inside it — `O_NOFOLLOW` will refuse a
  symlinked `.origin` leaf, and `rename` replaces a symlinked target rather than following it, so
  symlinked `.zst` files are silently converted to real files on the next update.
- Keep `warm/` and `claudevm.bundle/` together; the free-space precheck `statfs`s the bundle dir and
  will then report the correct volume.
- Quit the app first. `EBUSY`/`EACCES`/`EPERM` on the images is treated as "locked by running VM",
  and stale files are kept silently rather than erroring.
- Use `mv` on the same volume — it is a rename, so it preserves the holes exactly. Plain `cp`
  inflates a sparse image to full size; use `cp -c` (clonefile) or `rsync --sparse` if you must
  copy.
- No recursive delete of the `vm_bundles` root appears anywhere in the bundle — only per-file
  `unlink` and per-entry cleanup inside `warm/`.


## Entitlements

Cowork needs `com.apple.security.virtualization`. The shipped app declares 12 entitlements under
hardened runtime (`flags=0x10000(runtime)`), signed by Anthropic PBC, Team ID `Q6L2SF6YDW`:

```
com.apple.application-identifier              com.apple.security.device.print
com.apple.developer.team-identifier           com.apple.security.device.usb
com.apple.security.cs.allow-jit               com.apple.security.personal-information.location
com.apple.security.device.audio-input         com.apple.security.personal-information.photos-library
com.apple.security.device.bluetooth           com.apple.security.virtualization
com.apple.security.device.camera              keychain-access-groups
```

Notable absences: no `com.apple.security.app-sandbox` (hence no container boundary on file paths),
and no `com.apple.security.cs.disable-library-validation` — so library validation is enforced.

Three are scoped to the Team ID and cannot be claimed by an ad-hoc signature:
`com.apple.application-identifier`, `com.apple.developer.team-identifier`, and
`keychain-access-groups` (whose five groups — `…claude.webauthn`, `…claude.hwkey`, and three
`…microsoft.identity`/`workplacejoin` groups — back passkey, hardware-key, and Entra sign-in).

`com.apple.security.virtualization` is not team-scoped, so a re-signed or cloned bundle can keep it.
That matters if you relocate profiles by cloning the app rather than by setting the env var: a clone
is not categorically barred from Cowork the way it is from passkey sign-in. Whether the VM actually
boots in a clone is untested here — the entitlement is only the first gate, with
`secureVmFeaturesEnabled` and the server-side flags still ahead of it (see
[FEATURES](./FEATURES.md)). Note also that library validation being enforced means an ad-hoc outer
signature needs `com.apple.security.cs.disable-library-validation` added, or it cannot load the
team-signed `Electron Framework.framework`.


## Reclaiming space

Ordered best to worst.

| Action                                        | Saves                     | Cost                        |
|-----------------------------------------------|--------------------------:|------------------------------|
| Per-profile `secureVmFeaturesEnabled: false`   | ~6.6 GiB for that profile | no Cowork in that profile    |
| Delete orphaned `warm/<sha>/*.tmp`             | 187 MiB observed          | none                         |
| Delete `<file>.zst` caches                     | ~1.28 GiB/profile         | full re-download, not a delta, on the next bump |
| `cp -c` clone of `rootfs.img` between profiles | ~5 GiB, decaying          | not recommended — see below  |

The per-profile disable is the real lever when running personal/work profiles: the preference lives
in each profile's own `claude_desktop_config.json`, so Cowork can be on in one and off in the other.
See [FEATURES](./FEATURES.md) for the key and [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md) for the
profile mechanism.

The warm `.tmp` orphan is safe to remove: warm downloads resume through `.partial`, not `.tmp`; the
promote path unlinks `<target>.tmp` on entry but only runs when the file is not already ready; and
warm prefetch only runs for a sha different from the current one. A `.tmp` left under a directory
whose sha has since become current is unreachable.

Clonefile between profiles is documented here so nobody re-derives it and assumes it is a good idea.
The mechanics work — `clonefile` is copy-on-write, so a cloned `rootfs.img` starts free and
diverges per block — but the economics do not:

- The saving decays. Both guests write to their own root filesystem continuously, so the shared
  block count falls from day one toward zero.
- It breaks on every VM version bump. The update path renames a fresh `.tmp` over `rootfs.img`,
  which severs the clone, silently leaving two full copies — exactly the state the work was meant
  to avoid.
- `du` double-counts clones while the volume does not, so there is no easy way to check whether it
  is still working.
- Getting the exclusion list wrong (`efivars.fd`, `machineIdentifier`, `gvisorMacAddress`,
  `sessiondata.img`, `.cowork-adopted`) yields two VMs sharing an identity or a MAC.
- It is inference from reading minified code, not something verified by running it.

Recurring manual work whose payoff shrinks, that fails silently, on a read-write VM disk. Prefer
the disable.


## Re-verification recipes

```bash
EX=/tmp/claude-asar-extract
B=~/Library/Application\ Support/Claude/vm_bundles/claudevm.bundle

# Apparent vs allocated, per file
for f in "$B"/*; do printf '%-20s %12s %12s\n' "$(basename "$f")" \
  "$(stat -f %z "$f")" "$(( $(stat -f %b "$f") * 512 ))"; done

# Which bundle sha the local files came from
for f in "$B"/.*.origin; do printf '%-26s %s\n' "$(basename "$f")" "$(cat "$f")"; done

# Chunk holding the baked-in manifest (sha, publishedAt, per-file sha256)
grep -l 'rootfs.vhdx' "$EX/.vite/build/"*.js

# Bundle path construction and the env-var override
grep -rn 'vm_bundles' "$EX/.vite/build/"*.js
grep -rn 'CLAUDE_USER_DATA_DIR' "$EX/.vite/build/index.pre.js"

# ext4 label of a guest image, without mounting it. The superblock starts 1024 bytes into
# the filesystem; s_volume_name is at +0x78 within it, so 1144 from the partition start.
# Pass the partition offset as $2 (0 for sessiondata.img; 206848*512 for rootfs.img part 1).
python3 -c 'import sys; f=open(sys.argv[1],"rb"); f.seek(int(sys.argv[2])+1144)
print(f.read(16).rstrip(b"\0").decode())' "$B/sessiondata.img" 0
```

Do not use `grep -E` with bounded-repetition context windows (`.{0,120}foo.{0,120}`) against
`app.asar` or the minified chunks. Lines are hundreds of KB long and the regex engine backtracks
effectively forever — two such greps ran for over 40 minutes here without output. Use `grep -F`
or `grep -l` to locate the chunk, then slice context in Python. See
[EXTRACTION](./EXTRACTION.md) for the ASAR reader.
