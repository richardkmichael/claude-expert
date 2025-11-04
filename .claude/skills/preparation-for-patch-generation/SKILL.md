---
name: preparation-for-new-patch-generation
description: Prepare the source code for new patch generation by creating working directories, and downloading, extracting and prettifying the requested version source code.
---

# Source code preparation

This skill prepares the original source code for modification to generate new patches.

# Instructions

1. Create the new patches output directory named `patches/{REQUESTED_VERSION}`

2. Create the working directory named `work/{REQUESTED_VERSION}`

3. Download the Claude Code source code for the requested version into the working directory

4. Extract the downloaded source code into the working directory

5. Prettify the extracted source code to generate a new file editable line-wise

## Example

Support the requested version of Claude Code to patch is `1.0.123`, here is the procedure:

1. Create the new patches output directory:

  `mkdir patches/1.0.123`

2. Create the working directory:

  `mkdir work/1.0.123`

3. Download the requested version of Claude Code npm package into the working directory

  `npm --silent pack --pack-destination work/1.0.123 @anthropic-ai/claude-code@1.0.123`

4. Extract the downloaded source code into the working directory

  `tar -xf 1.0.123/anthropic-ai-claude-code-1.0.123.tgz -C work/1.0.123`

5. Prettify the extracted source code to generate a new file editable line-wise

  `npx --yes prettier --ignore-path /dev/null work/1.0.123/package/cli.js > work/1.0.123/package/cli.prettier.js`
