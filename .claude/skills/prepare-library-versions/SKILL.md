---
name: prepare-library-versions
description: Download and organize multiple library versions for comparative analysis in a version-specific work directory.
---

# Prepare Library Versions

This skill sets up a clean, organized workspace for comparing multiple versions of a library by downloading them from npm and extracting relevant files.

## When to Use This Skill

- You need to compare multiple versions of a library
- You want to set up a reproducible analysis environment
- You're working on identifying which library version is bundled in minified code
- You need to establish baseline source files for pattern matching

## Key Practice: Version-Specific Work Directory

**Always work in a version-specific directory** (e.g., `work/2.0.37/` or `work/3.1.0/`) to keep investigations organized and reproducible. All downloads and extractions should go into this single directory.

## Step 1: List Available Versions

```bash
# List all available versions for a library
npm show LIBRARY_NAME versions --json

# Example: List all Ink versions
npm show ink versions --json

# Output example:
# ["4.4.1", "5.0.0", "5.0.1", ..., "6.0.0", "6.0.1", "6.1.0", ..., "6.5.0"]
```

Choose 2-5 consecutive or strategically spaced versions to download.

## Step 2: Download Library Versions

```bash
# Navigate to your version-specific work directory first
cd /path/to/work/VERSION/

# Download multiple versions
npm pack --pack-destination . LIBRARY@VERSION1 LIBRARY@VERSION2 LIBRARY@VERSION3

# Example: Download multiple Ink versions
npm pack --pack-destination . ink@6.0.0 ink@6.0.1 ink@6.1.0

# Verify downloads
ls -lh LIBRARY-*.tgz
```

**Important**: All tarballs should be in the work directory root, not in subdirectories.

## Step 3: Create Extraction Directories

```bash
# Create parallel extraction directories for source and TypeScript definitions
for version in VERSION1 VERSION2 VERSION3; do
  mkdir -p library-${version}-src
  mkdir -p library-${version}-dts
done

# Example for Ink
for v in 6.0.0 6.0.1 6.1.0; do
  mkdir -p ink-${v}-src
  mkdir -p ink-${v}-dts
done
```

## Step 4: Extract Files from Archives

Extract the key files from each version's tarball. You'll typically need:
- TypeScript definitions (`.d.ts` files) - canonical API signatures
- Source implementation files - to understand actual code differences
- Entry points and main exports

```bash
# Extract TypeScript definitions
for v in VERSION1 VERSION2 VERSION3; do
  tar xf library-${v}.tgz -C library-${v}-dts package/build/COMPONENT_PATH.d.ts
done

# Extract source files
for v in VERSION1 VERSION2 VERSION3; do
  tar xf library-${v}.tgz -C library-${v}-src package/build/COMPONENT_PATH.js
done
```

**Choosing which files to extract**:

For **UI Component Libraries** (like Ink):
```bash
# Extract main components and their TypeScript definitions
tar xf ink-6.0.0.tgz -C ink-6.0.0-src package/build/components/Box.js
tar xf ink-6.0.0.tgz -C ink-6.0.0-dts package/build/components/Box.d.ts
```

For **HTTP Clients** (like Axios):
```bash
# Extract main export and client configuration
tar xf axios-*.tgz -C axios-*-src package/lib/axios.js
tar xf axios-*.tgz -C axios-*-dts package/index.d.ts
```

For **CLI Frameworks** (like Commander):
```bash
# Extract command and option handling
tar xf commander-*.tgz -C commander-*-src package/lib/command.js
tar xf commander-*.tgz -C commander-*-dts package/index.d.ts
```

For **General approach**:
1. Start with the main entry point (`index.js`, `index.d.ts`)
2. Extract the primary implementation file that likely differs between versions
3. Extract TypeScript definitions for the same file (most reliable for API changes)

## Result Directory Structure

After completion, your work directory should look like:

```
work/2.0.37/
├── package/                           # Claude Code or target application
│   └── cli.prettier.js               # Minified code to analyze
│
├── library-6.0.0.tgz                 # Downloaded version tarballs
├── library-6.0.1.tgz
├── library-6.1.0.tgz
│
├── library-6.0.0-src/                # Extracted source files
│   └── package/build/COMPONENT.js
├── library-6.0.1-src/
│   └── package/build/COMPONENT.js
├── library-6.1.0-src/
│   └── package/build/COMPONENT.js
│
├── library-6.0.0-dts/                # Extracted TypeScript definitions
│   └── package/build/COMPONENT.d.ts
├── library-6.0.1-dts/
│   └── package/build/COMPONENT.d.ts
├── library-6.1.0-dts/
│   └── package/build/COMPONENT.d.ts
│
└── extracted-sections/               # (Optional) For extracted minified code
    └── component-minified.js
```

## Extraction Tips

**Use multiple `-C` flags to extract into different directories**:
```bash
# Extract the SAME file into different directories (cleaner)
tar xf library-6.0.0.tgz -C library-6.0.0-src package/build/Box.js
tar xf library-6.0.0.tgz -C library-6.0.0-dts package/build/Box.d.ts
# Both extract the same source, but to parallel directories for organization
```

**List archive contents to find correct paths**:
```bash
# See what's inside the tarball
tar tzf library-VERSION.tgz | head -20

# Find TypeScript definition files
tar tzf library-VERSION.tgz | grep "\.d\.ts"

# Find JavaScript source
tar tzf library-VERSION.tgz | grep "\.js" | grep -v node_modules
```

## Common Pitfalls

- ❌ Not using a version-specific work directory - causes confusion with parallel investigations
- ❌ Downloading to random locations - makes cleanup and organization difficult
- ❌ Extracting everything instead of focusing on key files - wastes space and creates noise
- ❌ Using `--preserve-dir` or wrong `tar` flags - creates nested directory structures
- ❌ Not extracting `.d.ts` files - loses the canonical API specification

## Next Steps

Once prepared, this organized structure is ready for:
1. **compare-library-signatures** - diff the TypeScript definitions to find API changes
2. **search-minified-code** - use the setup location to reference when searching minified bundles
3. **match-code-patterns** - use source files to test ast-grep patterns before applying to minified code
