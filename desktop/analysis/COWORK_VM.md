---
verified: 4.4212.0
scope: Where Cowork runs (device or cloud); the local VM's `vm_bundles/`, images, updates
---
# Cowork VM Bundle On Disk

Where a Cowork task can run, what `vm_bundles/` contains for the local placement, why `du` disagrees
with `ls`, how the images are versioned and updated, and what that means for relocating or profiling
the user data directory.

For the gating that decides whether the bundle is downloaded at all (`yukonSilver`,
`secureVmFeaturesEnabled`, `autoDownloadInBackground`), see [FEATURES](./FEATURES.md).

VM bundle manifest sha `072b6cbf…`, published 2026-10-22, independent of the app build in the
[README](./README.md) banner, which pins which manifest sha is wanted.


## Where Cowork runs

The main process carries a placement table per surface. `cowork` and `coworkRoutines` can each run
on `device` (the local VM described below) or in `cloud`, with the cloud host `anthropic` or
`self-hosted`. The table's own labels for the result are `local-only`, `cloud-only`, `hybrid` and
`nowhere`. Locate it with `rg -n 'cowork-local-tasks-off'`.

- The device placement is denied for both Cowork surfaces by the `cowork-local-tasks-off` rule,
  logged as "the organization's local tasks switch is off". Its input is a GrowthBook gate latched
  into the `coworkLocalTasksOffLatched` setting and logged as
  `[cowork] local tasks turned off (GrowthBook gate)`. The user then sees "Your organization doesn't
  allow Cowork tasks on this computer." Third-party (`3p`) deployments are exempt from this rule.
- `secureVmFeaturesEnabled: false` makes the local workspace unsupported ("Enable the
  secureVmFeaturesEnabled preference to use this feature.").
- A cloud Cowork task is a Claude Code remote session. The main process looks it up at
  `/v1/code/sessions/<id>` with `anthropic-beta: ccr-byoc-2025-07-29` and treats it as Cowork when
  the session carries the tag `config:cowork-remote`. Its environment kind is `anthropic_cloud` or
  `byoc`, and its telemetry `session_type` is `cowork-remote`. Inside such a session Claude Code
  runs with `CLAUDE_CODE_ENTRYPOINT` `remote_cowork` or `remote_cowork_trigger`.
- A `[RemoteMigrationSweep]` moves local scheduled Cowork tasks to server-side triggers (`trig_…`
  ids; events `cowork_scheduled_tasks_auto_migrated` and
  `cowork_scheduled_task_migration_reverted`). It is driven by a server config whose `enabled` field
  defaults to false.

`app.asar` holds these rules but no picker for a new task's placement, which points to the remotely
served claude.ai frontend making that choice. The following comes from the user's report and was not
checked in the bundle: Cowork is a mode picked in the Home tab when sending a message, and Home and
Code are the two top-level tabs.

The local VM path is complete in this build, and the app keeps the bundle current whether or not
tasks run locally. On the machine checked, the images were restaged on the 4.4212.0 update
(2026-10-29) while the last `[VM:start]` in `~/Library/Logs/Claude/cowork_vm_node.log` and the last
`sessiondata.img` write were 2026-09-26.

The guest's Claude Code is staged separately from the bundle, under
`$userData/claude-code-vm/<version>/`: a Linux `claude` binary for the pinned version, plus
`.payload` (sha256 and size), `.verified`, and a `.sdk-version` file one level up. VM start prepares
it in the same step as the bundle download (`download_and_sdk_prepare`).


## Bundle layout

`$userData/vm_bundles/` holds two things: `claudevm.bundle/` (the live VM) and `warm/<sha>/` (a
prefetch cache for a future version).

| File                 |  Apparent |   On disk | Role                                                 |
| -------------------- | --------: | --------: | ---------------------------------------------------- |
| `rootfs.img`         | 10.00 GiB | 10.00 GiB | GPT disk, guest `/`, read-write                      |
| `sessiondata.img`    | 10.00 GiB |  12.4 MiB | ext4, guest `/sessions`, read-write                  |
| `rootfs.img.zst`     |  1.16 GiB |  1.16 GiB | download cache and binary-delta base                 |
| `vmlinuz`            |  56.3 MiB |  56.3 MiB | direct kernel boot                                   |
| `vmlinuz.zst`        |  14.4 MiB |  14.4 MiB | download cache / delta base                          |
| `initrd`             |  27.0 MiB |  27.0 MiB | direct kernel boot                                   |
| `initrd.zst`         |  26.7 MiB |  26.7 MiB | download cache / delta base                          |
| `initrd-micro`       |   4.3 MiB |   4.3 MiB | direct kernel boot ("direct kernel (micro-initrd)")  |
| `initrd-micro.zst`   |   1.6 MiB |   1.6 MiB | download cache / delta base                          |
| `efivars.fd`         |   128 KiB |   128 KiB | EFI variable store, used on the EFI (GRUB) boot path |
| `.<file>.origin`     |      40 B |           | bundle sha the local `<file>` came from              |
| `.<file>.zst.origin` |      40 B |           | bundle sha the local `<file>.zst` came from          |
| `.cowork-adopted`    |      40 B |           | wanted bundle sha, rewritten on each download check  |
| `machineIdentifier`  |      70 B |           | per-VM identity                                      |
| `gvisorMacAddress`   |      17 B |           | per-VM MAC                                           |
| `vmIP`               |      11 B |           | last guest IP                                        |

Apparent total 21.29 GiB; `du` total 11.30 GiB, measured right after a full download.

The Swift addon also attaches `Contents/Resources/smol-bin.arm64.img` from the app bundle as a
read-only virtio-blk device ("Added smol-bin.img as read-only virtio-blk device"). On macOS it is
not copied into `claudevm.bundle/`; it is 26 MiB apparent, 52 KiB allocated.

`warm/<sha>/` holds `<file>.zst`, or a `<file>.delta-<fromSha>.zst`, for a version other than the
current one.


## Sparse files, and reading them on macOS

`sessiondata.img` is sparse: the logical size is fixed but only written blocks are allocated. `du`
reports allocated blocks and `ls` reports `st_size`, hence the gap.

`rootfs.img` is not sparse as staged. Decompression writes every block of the 10 GiB image, so after
a full download it is fully allocated (10.00 GiB on disk on the machine checked). The shipped
artifact is compressed, not sparse: `rootfs.img.zst` is what downloads.

The fixed logical size is a guest requirement, not a host reservation. `mkfs.ext4` laid out group
descriptors, bitmaps, inode tables and journal for a 10 GiB device, and `rootfs.img`'s GPT puts its
backup header at the last LBA. Neither can be grown without `resize2fs`/GPT repair. Nothing is
reserved on the host, so a long-running VM can still fill the disk. The app compensates with
`statfs` prechecks before download, before a delta and before warm promotion, and classifies
`ENOSPC`/`EDQUOT` as `failure_reason: disk_full`, but that is a check, not a guarantee.

Guest discard/TRIM can punch holes into the host file at runtime: the Swift addon imports both
`ftruncate` and `fcntl` (`F_PUNCHHOLE`). That is not observable on a freshly staged image that has
not booted yet.

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

| Partition | Type                 |      Size | Contents                      |
| --------- | -------------------- | --------: | ----------------------------- |
| 1         | Linux filesystem     | 10139 MiB | ext4, label `cloudimg-rootfs` |
| 15        | EFI System Partition |    99 MiB | ESP                           |

An Ubuntu cloud-image layout. The Swift addon boots it one of two ways. With `vmlinuz` and an initrd
present in the bundle it uses direct kernel boot ("Using direct kernel boot: kernel=…"), otherwise
it logs "Direct-boot artifacts not present in bundle; using EFI (GRUB) boot". The kernel cmdline is
`root=LABEL=cloudimg-rootfs ro console=hvc0 console=hvc1 fsck.repair=yes console=tty1 console=ttyAMA0`.
The `ro` is only the initial mount.

As published (before first boot), the partition superblock shows `last_mounted /`, mount count 4,
and 4.80 GiB used.

`rootfs.img` is a live read-write disk, not a read-only golden image. There is no separate writable
partition and no overlay. The update path never uses the local `rootfs.img` as a delta base; it
rebuilds from the pristine `.zst` cache. Two VMs cannot share one.


## sessiondata.img

ext4, label `sessions`, `last_mounted /sessions`. Created locally on first VM setup ("Creating new
session data disk (10GB) at …") and never downloaded. It is absent from the bundle manifest, and the
reinstall path logs "Reinstall files deleted (sessiondata.img and compressed cache preserved)". It
therefore survives VM version bumps and reinstalls.

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

Host-mounted folders appear by name under `mnt/`. The Swift addon exposes `vmGetSessionsDiskInfo` /
`SessionsDiskInfo` and has `prunedSessions` / `skippedSessions` counters, so there is a pruning path
over this disk.


## Versioning and updates

The wanted VM version is a build constant compiled into the app, not fetched. From the bundle
manifest chunk:

```js
versions[0] = { sha: `072b6cbfe74f428a98bd86035f83b322b369d1f1`, publishedAt: `2026-10-22`,
                files: { unix: { arm64: [
                  { name: `rootfs.img`, checksum: `40818968…`, size, rawChecksum, rawSize,
                    progressStart, progressEnd,
                    deltas: [ { fromSha: `6db63bc6…`, checksum, size }, … ] },
                  { name: `vmlinuz`, … }, { name: `initrd`, … }, { name: `initrd-micro`, … } ],
                  x64: [ … ] },
                  win32: { … rootfs.vhdx, vmlinuz, initrd … } } }
```

The manifest's own `$comment` says the other `versions[]` entries are "the recently shipped bundles
kept so the publish workflow can generate binary deltas from them". Each current `rootfs.img` entry
lists the published deltas by `fromSha`, five in this build. `sessiondata.img`, `efivars.fd` and
`smol-bin` are not in it.

Local state is the 40-byte `.<file>.origin` markers. The readiness check compares that string to the
baked sha and yields `ready` / `missing` / `origin_missing` / `version_mismatch` (logged as
`[Bundle:status] <file> version mismatch: have=…, want=…`). There is no "is my VM stale" network
poll: updating the app is what updates the VM.

Before any file is staged, the download checks for 15 GiB free on the bundle volume, less any
resumable partials and the allocated size of the old `rootfs.img`, and otherwise fails with
"Insufficient disk space for Cowork VM install".

On mismatch, per file, in order:

1. Delete the old `<file>` to free disk space ("Deleting old `<file>` to free disk space"), then its
   `.origin`. A file that fails with `EBUSY`/`EACCES`/`EPERM` is logged as "locked by running VM,
   keeping stale bundle" and skipped.
2. Plan a binary delta (conditions below). Without one, a `<file>.zst` whose `.<file>.zst.origin` is
   missing or names another sha is deleted ("Dropping stale `<file>` cache").
3. Package preseed: stage `Contents/Resources/preseed/vm_bundle/<file>.zst` as the compressed cache,
   when the app ships one.
4. Warm-bundle promotion from `warm/<sha>/<file>.zst` (decompress, verify, rename into place).
5. Decompress the local `<file>.zst` cache, if its `.zst.origin` already names the wanted sha.
6. Binary delta.
7. Full download from `https://downloads.claude.ai/vms/linux/<arch>/<sha>/<file>.zst`, streamed to a
   resumable `<file>.zst.<checksum-prefix>.partial` while decompressing into `<file>.tmp`.

Integrity is the manifest's per-file sha256 (`checksum` over the compressed file, and `rawChecksum`
over the decompressed stream), verified before the staged `<file>.tmp` is renamed into place.

The delta path needs a GrowthBook flag and the native `applyVmImageDelta` (in
`claude-native-binding.node`). It also needs `rawChecksum`/`rawSize` in the manifest entry, an
existing `<file>.zst` whose `.<file>.zst.origin` holds a different 40-hex sha, and a manifest delta
`fromSha` matching that sha. It is skipped when a warm source is available ("local source available,
preferring it over a delta"). It fetches `<file>.delta-<fromSha>.zst` from the same base URL, or
uses a prefetched one from `warm/`, and renames `<file>.zst` to `<file>.zst.deltabase` while
working. The native applier writes `<file>.tmp`, checks it against `rawChecksum`, and tees a fresh
`<file>.zst` cache for the next bump. Any failure is reported as `lam_vm_bundle_delta_failed` and
falls back to the full download. Deleting the `.zst` caches, or losing their `.zst.origin` markers,
therefore forces a full re-download on the next bump rather than a delta.

The bundle directory is also swept 90 s after startup (unless `disableStartupBundleSweep` is set, or
a download or VM start is in flight) and at the start of each download. The sweep removes leftover
`<file>.tmp`, `<file>.zst.tmp`, delta temporaries, `*.preseed.tmp` and `.wvm-tmp-*` entries, plus
`.partial` downloads not for a file still needed. It logs `[Bundle:sweep] Removed …`.

The only genuine network version lookup is the warm prefetch:
`GET https://downloads.claude.ai/<releases folder>/darwin/universal/<appVersion>/vm_hash`. The
releases folder is taken from the update's download address (`releases` by default), or the request
goes to the update proxy when one is configured. It returns the 40-hex VM sha for that app version,
and the files are staged into `warm/<sha>/`, as a delta from the current sha where one is published,
otherwise the full `.zst`. It only runs for a sha different from the current one ("VM SHA matches
current version, skipping"), and requires `autoDownloadInBackground`.

Stale `warm/` entries are swept only on the way into a prefetch, with the keep-list
`[nextSha, currentSha]`. With `autoDownloadInBackground` off, or no bundle present, the keep-list is
`[currentSha]`. When the workspace VM is unsupported, every entry is removed. While each update's
`vm_hash` equals the bundled sha, the sweep never runs and old (possibly empty) `warm/<sha>/`
directories stay.


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
`gvisorMacAddress` are per-VM identity. Sharing the last would give two VMs the same MAC.

Marginal cost of an additional profile is ~11.3 GiB right after a full download: ~1.20 GiB of
compressed cache, a fully allocated 10 GiB `rootfs.img`, and the small boot files. Both profiles run
the same binary, so both always want the identical rootfs. Each pulls its own update on every VM
bump: ~1.29 GB in full, or a published `rootfs.img` delta (52–480 MB in this build, depending on the
starting sha) when the delta conditions hold.


## Relocating vm_bundles with a symlink

Supported in practice. The path is never `realpath`'d, and the app is not sandboxed: it declares 13
entitlements and `com.apple.security.app-sandbox` is not among them, so there is no container
boundary. (`com.apple.security.virtualization` is present; see [entitlements](#entitlements).)
Everything downstream is ordinary `fs` (`mkdir` recursive, `createWriteStream`, `rename`, `statfs`,
`readdir`) plus the Virtualization.framework attachment, all of which follow symlinks.

The bundle's private-file module does contain symlink hardening, but none of it reaches here:

| Guard                          | Applies to `vm_bundles`?                                                                    |
| ------------------------------ | ------------------------------------------------------------------------------------------- |
| Pre-traversal probe            | No: gated on Windows                                                                        |
| Below-boundary symlink refusal | No: scoped to `CLAUDE_CONFIG_DIR`, a registered root, or a literal `.claude` path component |
| `O_NOFOLLOW` on private write  | Leaf file only, never parent directories                                                    |

That second guard's own error text names relocating the root itself as the supported route: "to
relocate Claude Code's config directory, symlink ~/.claude itself or set CLAUDE_CONFIG_DIR in
Desktop Settings."

Practical notes:

- Symlink the whole `vm_bundles` directory, not files inside it. `O_NOFOLLOW` will refuse a
  symlinked `.origin` leaf, and the update path deletes the old file and renames a fresh one into
  place, so symlinked image or `.zst` files are silently converted to real files on the next update.
- Keep `warm/` and `claudevm.bundle/` together; the free-space precheck `statfs`s the bundle dir and
  will then report the correct volume.
- Quit the app first. `EBUSY`/`EACCES`/`EPERM` on the images is treated as "locked by running VM",
  and stale files are kept silently rather than erroring.
- Use `mv` on the same volume. It is a rename, so it preserves the holes exactly. Plain `cp`
  inflates a sparse image to full size; use `cp -c` (clonefile) or `rsync --sparse` if you must
  copy.
- No recursive delete of the `vm_bundles` root appears anywhere in the bundle, only per-entry
  deletes inside `claudevm.bundle/` (the sweeps, reinstall) and inside `warm/`.


## Entitlements

Cowork needs `com.apple.security.virtualization`. The shipped app declares 13 entitlements under
hardened runtime (`flags=0x10000(runtime)`), signed by Anthropic PBC, Team ID `Q6L2SF6YDW`:

```
com.apple.application-identifier              com.apple.security.device.print
com.apple.developer.team-identifier           com.apple.security.device.usb
com.apple.security.automation.apple-events    com.apple.security.personal-information.location
com.apple.security.cs.allow-jit               com.apple.security.personal-information.photos-library
com.apple.security.device.audio-input         com.apple.security.virtualization
com.apple.security.device.bluetooth           keychain-access-groups
com.apple.security.device.camera
```

Notable absences: no `com.apple.security.app-sandbox` (hence no container boundary on file paths),
and no `com.apple.security.cs.disable-library-validation`, so library validation is enforced.

Three are scoped to the Team ID and cannot be claimed by an ad-hoc signature:
`com.apple.application-identifier`, `com.apple.developer.team-identifier`, and
`keychain-access-groups`. The last holds five groups: `…claude.webauthn`, `…claude.hwkey`, and three
`…microsoft.identity`/`workplacejoin` groups, which back passkey, hardware-key, and Entra sign-in.

`com.apple.security.virtualization` is not team-scoped, so a re-signed or cloned bundle can keep it.
That matters if you relocate profiles by cloning the app rather than by setting the env var: a clone
is not categorically barred from Cowork the way it is from passkey sign-in. Whether the VM actually
boots in a clone is untested here. The entitlement is only the first gate, with
`secureVmFeaturesEnabled` and the server-side flags still ahead of it (see
[FEATURES](./FEATURES.md)). Note also that library validation being enforced means an ad-hoc outer
signature needs `com.apple.security.cs.disable-library-validation` added, or it cannot load the
team-signed `Electron Framework.framework`.


## Reclaiming space

Ordered best to worst.

| Action                                         |                      Saves | Cost                                            |
| ---------------------------------------------- | -------------------------: | ----------------------------------------------- |
| Per-profile `secureVmFeaturesEnabled: false`   | ~11.3 GiB for that profile | no local Cowork in that profile                 |
| Delete orphaned `warm/<sha>/*.tmp`             |       whatever is orphaned | none                                            |
| Delete `<file>.zst` caches                     |          ~1.20 GiB/profile | full re-download, not a delta, on the next bump |
| `cp -c` clone of `rootfs.img` between profiles |    up to ~10 GiB, decaying | not recommended (see below)                     |

The per-profile disable is the real lever when running personal/work profiles: the preference lives
in each profile's own `claude_desktop_config.json`, so Cowork's local VM can be on in one and off in
the other. See [FEATURES](./FEATURES.md) for the key and [DEPLOYMENT_MODES](./DEPLOYMENT_MODES.md)
for the profile mechanism.

A warm `.tmp` orphan is safe to remove: warm downloads resume through `.partial`, not `.tmp`. A warm
download unlinks `<file>.zst.tmp` in its sha directory on entry, and the promote path unlinks
`<target>.tmp` on entry but only runs when the file is not already ready. Warm prefetch only runs
for a sha different from the current one, so a `.tmp` left under a directory whose sha has since
become current is unreachable.

Clonefile between profiles is documented here so nobody re-derives it and assumes it is a good idea.
The mechanics work: `clonefile` is copy-on-write, so a cloned `rootfs.img` starts free and diverges
per block. The economics do not:

- The saving decays. Both guests write to their own root filesystem continuously, so the shared
  block count falls from day one toward zero.
- It breaks on every VM version bump. The update path deletes `rootfs.img` and renames a fresh
  `.tmp` into place, which severs the clone, silently leaving two full copies: exactly the state the
  work was meant to avoid.
- `du` double-counts clones while the volume does not, so there is no easy way to check whether it
  is still working.
- Getting the exclusion list wrong (`efivars.fd`, `machineIdentifier`, `gvisorMacAddress`,
  `sessiondata.img`, `.cowork-adopted`) yields two VMs sharing an identity or a MAC.
- It is inference from reading minified code, not something verified by running it.

Recurring manual work whose payoff shrinks, that fails silently, on a read-write VM disk. Prefer
the disable.


## Re-verification recipes

```bash
EX=desktop/work/<app-version>/app
B=~/Library/Application\ Support/Claude/vm_bundles/claudevm.bundle

# Apparent vs allocated, per file
for f in "$B"/* "$B"/.*; do [ -f "$f" ] && printf '%-26s %12s %12s\n' "$(basename "$f")" \
  "$(stat -f %z "$f")" "$(( $(stat -f %b "$f") * 512 ))"; done

# Which bundle sha the local files came from
for f in "$B"/.*.origin "$B"/.cowork-adopted; do printf '%-26s %s\n' "$(basename "$f")" "$(cat "$f")"; done

# Chunk holding the baked-in manifest (sha, publishedAt, per-file sha256, deltas)
rg -l 'rootfs.vhdx' "$EX/.vite/build/"

# Update sequence, delta, warm prefetch and sweep log lines
rg -n -F -e '[downloadVM]' -e '[delta]' -e '[warm]' -e '[Bundle:sweep]' "$EX/.vite/build/"

# Placement rules (device / cloud) and the local-tasks gate
rg -n -e 'cowork-local-tasks-off' -e 'coworkLocalTasksOffLatched' "$EX/.vite/build/"

# Bundle path construction and the env-var override
rg -n '"vm_bundles"' "$EX/.vite/build/"
rg -n 'CLAUDE_USER_DATA_DIR' "$EX/.vite/build/index.pre.js"

# Boot and disk messages in the Swift addon
strings -n 6 /Applications/Claude.app/Contents/Resources/app.asar.unpacked/node_modules/@ant/claude-swift/build/Release/swift_addon.node \
  | rg -e 'smol-bin' -e 'direct kernel' -e 'session data disk' -e 'cloudimg-rootfs'

# What the update did last time
rg -n -F -e '[downloadVM]' -e '[VM:start]' ~/Library/Logs/Claude/cowork_vm_node.log

# ext4 label of a guest image, without mounting it. The superblock starts 1024 bytes into
# the filesystem; s_volume_name is at +0x78 within it, so 1144 from the partition start.
# Pass the partition offset as $2 (0 for sessiondata.img; 206848*512 for rootfs.img part 1).
python3 -c 'import sys; f=open(sys.argv[1],"rb"); f.seek(int(sys.argv[2])+1144)
print(f.read(16).rstrip(b"\0").decode())' "$B/sessiondata.img" 0
```

Search the bundle with `rg`, not `grep`. In this environment `grep` is a ugrep build that backtracks
effectively forever on bounded-repetition context windows (`.{0,120}foo.{0,120}`) over lines
hundreds of KB long. See [EXTRACTION](./EXTRACTION.md) for the ASAR reader.
