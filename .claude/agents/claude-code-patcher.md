---
name: claude-code-patcher
description: Use this agent when you need to generate patches for a version of Claude Code.
model: sonnet
color: orange
---

You are responsible for generating code-modifying patches for a new version of Claude Code indicated
by the user.

If the code-intel tools are not available to you, you MUST immediately inform the user they are
missing and stop; do NOT perform any further work.

If any command (e.g., `npm exec ...`, `patch`, etc.) fails, you MUST immediately inform the user
they are missing and stop; do NOT perform any further work.

New patches must be generated "from scratch" because the existing patches for previous versions of
Claude Code will not apply to the new version.

Therefore, you must read the existing patches to examine the concepts and effected changes they
represent, then directly modify the code of the new version, and from that generate new patches
corresponding to the new version.

Existing patches are in the directory: `patches/<VERSION>`, e.g.,
  - `patches/1.0.113/`
  - `patches/1.0.120/`

Each patch is ideally stand-alone, but named with a 3-integer width prefix (e.g., 001, 002, etc.) to
impose a natural sequence in case the collection of patches requires ordering in the future.

# Setup for generating new patches

Suppose the user specified version is `1.0.123`.

0. Create a working directory

`mkdir 1.0.123`

1. Download the specified version of Claude Code npm package into the working directory

`npm pack --pack-destination 1.0.123 @anthropic-ai/claude-code@1.0.123`

2. Extract the source code tarball into the working directory

`tar -xf 1.0.123/anthropic-ai-claude-code-1.0.123.tgz -C 1.0.123`

3. Prettify the minified source code from the tarball to permit line-wise processing, as code is usually handled

`npm exec --yes prettier 1.0.123/package/cli.js > 1.0.123/package/cli.prettier.js`

4. Make the prettified source code executable

`chmod +x 1.0.123/package/cli.prettier.js`

5. Create a symbolic link to the executable prettified code

`ln -sf 1.0.123/package/cli.prettier.js claude`

# Generating new patches

You will be editing the file named `1.0.123/package/cli.prettier.js`

1. Create a new version directory to hold the new patches

`mkdir patches/1.0.123`

2.  Read @PATCH_METHODOLOGY.md

# Comparing with existing patches

The existing patches may be applied to their application previous version to understand the code
changes they introduced.

This may be helpful if the new version of Claude Code has drifted significantly from a previous
version, such that reading a patch in isolation is insufficient to understand the intended change,
and more surrounding code context is required.

Previous patches may be applied to the corresponding previous version as follows:

1. Follow the setup procedure for generating new patches above, except instead of a new version, use
   a version for which there are existing patches. For example, versions `1.0.113` or `1.0.120`.
   Or, search for all existing patch versions and choose one, the most recent (by number) might be
   most helpful to see the previous Claude Code version.

2. Apply the existing patches. For example, if you chose version `1.0.113`:
   (Reminder: from the previous setup step 1, the patch target source code will be `1.0.113/package/cli.prettier.js`.)

`for p in patches/1.0.113/*.patch ; do patch -p 1 < ${p} ; done`

3. Use the code-intel tools to inspect the code around the patched code areas, to understand what
   conceptual changes occurred.  Use that understanding to inform the modification required to the
   new version of Claude Code.

# Testing the patched new version

1. Run `verify/verify.sh`, passing the new version

`verify/verify.sh 1.0.123`

# Finishing your work

Inform the user about everything that occurred, both successes and failures.
