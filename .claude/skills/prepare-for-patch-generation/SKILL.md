---
name: prepare-for-new-patch-generation
description: Prepare the original source code for new patch generation by creating working directories, and downloading, extracting and prettifying the requested version source code.
---

# Source code preparation

This skill prepares the original source code for modification to generate new patches.

# Instructions

1. Use the `bin/prepare-for-patch-generation.sh` script, providing the user requested version.

## Example

If the user requested version of Claude Code to patch is `1.0.123`, here is the procedure:

1. Run the script with the version:

  `bin/prepare-for-patch-generation.sh 1.0.123`
