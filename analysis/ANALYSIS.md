# Analysis of package/cli.prettier.js

Source: `cli.prettier.js` 2.1.76 (`work/2.1.76/package/cli.prettier.js`)

## Objectives

### Ultimate Goal: Runtime Debugging and Modification
Enable debugger attachment and custom modifications to the minified application by creating version-resilient documentation that identifies functional patterns and debugging entry points.

### Primary Goal: Version-Resilient Functional Mapping
Create comprehensive annotations that survive minification changes across versions:
- **Functional patterns** and **behavior signatures** over specific variable names
- **Runtime debugging landmarks** (unique strings, error messages, console patterns)
- **Hook execution entry points** with distinctive call patterns
- **Architectural boundaries** between persistent functional modules

### Secondary Goal: Comprehensive Program Documentation
Create "companion documentation" for understanding overall program operation:
- **Core application functionality areas** (UI rendering, I/O handling, etc.)
- **Native vs. third-party code boundaries** with clear delineation
- **Major functional modules** and their interactions
- **Data flow patterns** and state management approaches
- **Program architecture** and component relationships

### Tertiary Goal: Hook Modification Strategy
Identify debugger-friendly approaches to `PreToolUse` and `PostToolUse` hooks:
- **Breakpoint target locations** with stable signatures
- **Stack trace patterns** leading to hook execution
- **Call sequence analysis** for runtime interception
- **Configuration object structures** for hook behavior modification

## Methodology

### Analysis Approach (Simplified)
- **Chunk size:** 5,000 lines per analysis file
- **Follow the Decision Tree above** - this determines your approach for each section of code
- **Output:** Separate file per chunk (`cli_prettier_notes_chunk_[start]-[end].md`)
- **Hook findings:** Add to main `cli_prettier_notes.md` with precise debugging details

### Phase 3: Runtime Modification Playbook (FUTURE)
- **Scope:** Debugger attachment strategies for identified hook sections
- **Deliverables:**
  - **Breakpoint placement guide** for hook interception
  - **Variable modification strategies** for behavior changes
  - **Fallback patterns** when minification changes break initial approaches

## File Structure

```
cli_prettier_notes_chunk_1-3000.md      # Completed chunk
cli_prettier_notes_chunk_3001-4000.md   # Completed chunk
cli_prettier_notes_chunk_4001-5000.md
...
```

## Core Principles (Apply After Decision Tree)

- **Follow the Decision Tree first** - it overrides these principles when conflicts arise
- **Debugging-first mindset:** Every annotation should consider "how would I find this with a debugger?"
- **Version resilience:** Document functional relationships that persist across code reorganization
- **Library interaction focus:** Emphasize how native code uses libraries rather than library internals
- **Context management:** Clear progress tracking for resuming after context limits

## CRITICAL: Analysis Decision Tree

Follow this decision tree in order - each step overrides previous steps:

### 1. FIRST: Is this hook-related code?
If you see `PreToolUse`, `PostToolUse`, or hook execution patterns:
- **RECORD EVERYTHING PRECISELY**: Exact function names, variable names, line ranges
- **EXAMPLE**: `PreToolUse Hook: Function XJ9.executePreToolHook() at lines 42150-42200, config object hookConfig.PreToolUse, calls validatePermission(tool, context)`
- This overrides all other rules

### 2. SECOND: Is this a large library block?
If you see 1000+ lines of pure third-party library code (React, Ink, Axios, Sentry, or ANY other large library):
- **SKIP AND DOCUMENT**: `Lines 15000-65000: React library (50,000 lines) - Core component system, hooks, reconciler`
- **NOTE**: React/Ink/Axios/Sentry are examples - expect other unknown libraries too
- **NOTE**: All line numbers in examples are illustrative - use actual line numbers from your analysis
- Exception: Still analyze any native integration code within the library block

### 3. THIRD: For all other code (native application code):
- **USE PATTERNS ONLY**: Focus on stable identifiers, API calls, error messages
- **AVOID**: Minified function names, specific line numbers
- **EXAMPLE**: `Highlight.js Pattern: Compiled regex rules with test/compile/exec methods and error strings containing "regex" or "compile"`

## Important Notes for LLM Analysts

- **All line numbers in these instructions are examples only** - use the actual line numbers from your analysis
- **When instructions conflict, follow the decision tree above in order**
- **If unsure whether code is hook-related, err on the side of recording precise details**
- **Large library blocks are typically 1000+ consecutive lines of the same library**

## Library Block Strategy

### Identifying Large Library Sections
Look for these patterns to identify massive third-party library blocks that can be skipped. These are EXAMPLES - expect other unknown libraries with similar patterns:

**React Library Indicators:**
- Component definition patterns: `function Component()`, `React.createElement`
- Hook patterns: `useState`, `useEffect`, `useContext`
- Reconciler/renderer code: Virtual DOM manipulation, fiber architecture
- JSX transformation utilities

**Ink Library Indicators:**
- Terminal UI components: `Box`, `Text`, `Input` components
- ANSI escape sequences and terminal control codes
- Yoga layout engine integration

**Axios Library Indicators:**
- HTTP client patterns: `XMLHttpRequest`, `fetch` wrappers
- Request/response interceptors
- Configuration objects with `baseURL`, `timeout`, `headers`

**Sentry Library Indicators:**
- Error capture patterns: `captureException`, `captureMessage`
- Breadcrumb tracking, performance monitoring
- DSN configuration and transport mechanisms

**General Library Indicators (for unknown libraries):**
- Large blocks of consistent, complex code with minimal native app integration
- Repeated patterns of similar function definitions or data structures
- Self-contained modules with their own internal logic and minimal external dependencies
- Code that appears to implement generic functionality (networking, UI frameworks, data processing, etc.)
- Distinctive naming patterns or consistent code style different from native app code

### Skipping Strategy
When you encounter a large library block (>1000 lines of pure library code):

1. **Document the boundary**: `Lines 15000-65000: React library (50,000 lines) - Core component system, hooks, reconciler`
2. **Note integration points**: Look for where native code imports/configures the library
3. **Skip internal implementation**: Don't analyze React's internal reconciler or Axios's HTTP handling
4. **Resume at library end**: Continue detailed analysis when native code resumes

### Critical: Don't Skip These Areas
**Always analyze** even within library sections:
- **Configuration objects** where native code customizes library behavior
- **Custom hooks/plugins** that extend library functionality
- **Error handling wrappers** around library calls
- **Monkey-patching** or library modification code
- **Integration glue code** between native app and libraries

### Library Block Documentation Format
```
Lines 15000-65000: React Library Block (50,000 lines)
- Core functionality: Component system, hooks, reconciler, DOM rendering
- Integration points:
  * Line 14950: Native app imports React components
  * Line 65100: Custom hook definitions for app-specific logic
- Skip reason: Pure library internals, no native code interspersed
- Resume analysis: Line 65001
```
