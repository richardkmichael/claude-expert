# Library Boundary Detection Plan for Claude Code

## Objective
Determine exact line number ranges for each third-party NPM package bundled into the minified JavaScript file `package/cli.prettier.js` (Claude Code).

## Context
- File: `package/cli.prettier.js` (~15MB, 444,530 lines)
- Analysis files: 92 files named `cli_prettier_notes_chunk_X-Y.md`
- Goal: Find TRUE library boundaries through systematic discovery

## Discovery Method for Each Library
1. **Search for library evidence** across all chunk files using patterns/keywords
2. **Identify which chunks contain the library**
3. **Examine source code around suspected boundaries** to find transition points
4. **Look for boundary signatures**: module exports, distinctive patterns, function names
5. **Verify boundaries** by sampling content within detected range
6. **Record exact line numbers** as `Library Name, lines XXX-YYY`

### CRITICAL: Boundary Validation Methodology
When validating suspected library boundaries, **DO NOT** read the entire suspected range from the original JavaScript file. Instead:

- **For START boundary**: Read a small chunk around the suspected start line (e.g., ±10-20 lines)
- **For END boundary**: Read a small chunk around the suspected end line (e.g., ±10-20 lines)
- **Expand chunks if needed**: Increase the range around boundaries to improve validation
- **Spot-check middle**: Optionally sample a few points within the range to confirm consistency
- **NEVER read entire ranges**: Large libraries may span 10,000+ lines - this will overwhelm context

Example: If you suspect React spans lines 50,000-80,000, read lines 49,990-50,010 and 79,990-80,010 to validate the boundaries.

## Suggested Search Commands

Other commands may be used, but here are examples.  Use case-insensitive searching.

```bash
# Search all chunk files for library patterns
grep -l "pattern" cli_prettier_notes_chunk*.md

# Search for multiple patterns
grep -l "pattern1\|pattern2\|pattern3" cli_prettier_notes_chunk*.md

# Search content within files
grep -n "pattern" cli_prettier_notes_chunk*.md

# Read source around suspected boundary
Read package/cli.prettier.js offset=LINE_NUMBER limit=20
```

## Todo List: Libraries to Discover

### [ ] 8. WebSocket implementation
**Search patterns**: `WebSocket`, `ws`, `socket`, `connection`, `message`
**What to look for**: WebSocket protocol handling, connection management
**Boundary clues**: Protocol implementation, event handlers

### [ ] 9. Highlight.js
**Search patterns**: `highlight`, `hljs`, `language`, `syntax`, `grammar`
**What to look for**: Language definitions, syntax rules, highlighting engine
**Boundary clues**: Language registration, highlighting core

### [ ] 10. AWS SDK
**Search patterns**: `AWS`, `aws-sdk`, `STS`, `SSO`, `Bedrock`, `credential`
**What to look for**: AWS service clients, credential providers, protocols
**Boundary clues**: Service definitions, client constructors

### [ ] 11. Undici (HTTP client)
**Search patterns**: `undici`, `fetch`, `Request`, `Response`, `http`
**What to look for**: HTTP client implementation, request/response handling
**Boundary clues**: HTTP utilities, client setup

### [ ] 12. Lodash
**Search patterns**: `lodash`, `_`, utility functions like `map`, `filter`, `reduce`
**What to look for**: Utility function collections, data manipulation
**Boundary clues**: Utility exports, function definitions

### [ ] 13. Sharp (image processing)
**Search patterns**: `sharp`, `image`, `resize`, `format`, `buffer`
**What to look for**: Image processing functions, format conversion
**Boundary clues**: Image utilities, processing pipeline

### [ ] 14. tslib (TypeScript helpers)
**Search patterns**: `tslib`, `__extends`, `__awaiter`, `__generator`
**What to look for**: TypeScript runtime helpers, polyfills
**Boundary clues**: Helper function definitions

### [ ] 15. semver
**Search patterns**: `semver`, `version`, `satisfies`, `compare`
**What to look for**: Version comparison, semantic versioning utilities
**Boundary clues**: Version parsing functions

### [ ] 16. Zod (schema validation)
**Search patterns**: `Zod`, `schema`, `parse`, `validate`, `ZodString`
**What to look for**: Schema definitions, validation logic
**Boundary clues**: Schema constructors, validation methods

### [ ] 17. Marked.js (markdown parser)
**Search patterns**: `marked`, `markdown`, `parse`, `render`, `token`
**What to look for**: Markdown parsing, rendering functions
**Boundary clues**: Parser setup, rendering pipeline

### [ ] 18. Process management libraries
**Search patterns**: `spawn`, `graceful-fs`, `retry`, `file-lock`, `process`
**What to look for**: Process spawning, file system operations, retry logic
**Boundary clues**: Process utilities, file handling

### [ ] 19. Crypto/TLS libraries
**Search patterns**: `crypto`, `TLS`, `SSL`, `certificate`, `cipher`
**What to look for**: Cryptographic functions, TLS implementation
**Boundary clues**: Crypto utilities, protocol handling


## Libraries already discovered

Many libraries have already been discovered. They are listed in @LIBRARY_BOUNDARIES.md.  Their
boundaries may require revision based on the above analysis.  If so, report the required correction.

## Output

Append to `LIBRARY_BOUNDARIES.md` with discovered exact line ranges:

```
MIME Database (mime-db/mime-types), lines 1-4,892
Statsig SDK (v3.12.1), lines 4,893-11,204
[etc...]
```

## Notes
- Start with obvious/large libraries first
- Some libraries may be embedded within others
- Look for clear transition points in the source code
- Verify findings by sampling content within detected ranges
