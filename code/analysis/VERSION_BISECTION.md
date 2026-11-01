# Version Bisection — finding when a behavior changed

Verified against: cli.prettier.js 2.1.168 (2026-06-08)

How to locate the exact release that introduced or removed a behavior, without prettifying every
candidate. This is research methodology, not a finding about any one version.

## Distribution shape: where the bundle lives

The npm package layout split at the bun migration.

- Pre-bun (`<= 2.1.116`): `@anthropic-ai/claude-code@<v>` is an ordinary npm package whose tarball
  carries the minified bundle directly at `package/cli.js`. Grep that file.
- Bun era (`>= 2.1.117`): `@anthropic-ai/claude-code@<v>` is a small wrapper (`cli-wrapper.cjs`) with no
  `cli.js`. The bundle is embedded in a platform-native package resolved through `optionalDependencies`:
  `@anthropic-ai/claude-code-<platform>-<arch>[<-musl>]@<v>`, a large (~220MB) bun-compiled binary. The
  bundle's JavaScript lives inside that binary, which the tarball stores at `package/claude`.

Platform/arch matrix (from `prepare-claude-code-source.sh`): `<platform>` is `darwin` or `linux`,
`<arch>` is `arm64` or `x64`, and a musl Linux host adds the `-musl` suffix. Example:
`@anthropic-ai/claude-code-darwin-arm64`.

## Bisecting on a stable string

You do not need to prettify, or even unpack, to date a JS-level behavior. The product's literal strings
— error messages, env var names, settings-scope identifiers, `tengu_*` event names, prompt text — are
stored as plaintext inside `package/claude` and survive minification, so `grep -a` finds them. Minified
symbol names do not survive across releases; never bisect on those.

The embedded JavaScript is identical across platforms for a given version, so any platform's native
package dates a JS-level change equally well. Pick whichever you can `npm pack`.

## Procedure

1. Pick a needle: a stable string present on one side of the change and absent on the other — an error
   message, env var, or scope name, ideally one already listed in the relevant analysis doc's landmarks.
2. List candidate versions: `npm view @anthropic-ai/claude-code versions --json`.
3. Presence-test a candidate `<v>`. Bun era:

   ```
   npm pack --pack-destination /tmp/cc @anthropic-ai/claude-code-darwin-arm64@<v>
   tar xf /tmp/cc/anthropic-ai-claude-code-darwin-arm64-<v>.tgz -C /tmp/cc
   grep -aqF 'Refusing to write through symlink' /tmp/cc/package/claude && echo present || echo absent
   ```

   Pre-bun era (`<= 2.1.116`): pack `@anthropic-ai/claude-code@<v>` and grep `package/cli.js` instead.
4. Binary-search the range until you find the adjacent (absent, present) pair. The later version of that
   pair is the release where the behavior landed.

Use presence-only grep flags: `-aqF` (exit code), `-ac` (count), or `-ao` (just the matched substring).
Bare line output dumps a multi-KB minified line or raw binary bytes — see the root `CLAUDE.md` note.

## Worked example: dating the symlink-write refusal

Needle: `Refusing to write through symlink` (the `SETTINGS.md` symlink-refusal landmark). Absent in
2.1.137, present in 2.1.138 — so the guard was introduced in 2.1.138. Cost: two `npm pack`s and two
greps, no prettify, no `tweakcc`.

## Gotchas

- Packing the meta package (`@anthropic-ai/claude-code@<v>`) in the bun era gives the wrapper stub, not
  the bundle: there is no `cli.js` and the needle is absent for every version. That false "absent" reads
  as "never present." Pack the platform-native package.
- The native tarball is large per version; extract only `package/claude` and clean up between
  candidates.
- A musl Linux host needs the `-musl` variant to run the binary, but since the embedded JS is identical
  across platforms, JS-level bisection can use a darwin or glibc variant regardless of host.

## Relationship to prepare-claude-code-source

The `prepare-claude-code-source` skill runs the full pipeline for one version — pack the native
package, `tweakcc unpack` the JS out of `package/claude`, prettify to
`work/<v>/package/cli.prettier.js`. That is what you run once you have localized the version and
want to read the code. Bisection is the cheaper presence-search that comes first: it answers "which
version?" with grep alone, so you only prettify the one or two versions you actually need to read.
