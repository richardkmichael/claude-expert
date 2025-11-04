# Revision Instructions: Focus on Native App Code with Efficient Library Handling

## Problem Identified

The current analysis has two main issues:
1. **Third-party libraries** (RxJS, Lodash, Sentry, etc.) are documented in excessive detail when we only need high-level identification
2. **Debugging landmarks** contain minified function names that will become useless after re-minification

## Required Approach: Two-Tier Analysis

### Tier 1: Native Claude Code Application (DETAILED ANALYSIS)
For native application code, provide comprehensive debugging information with version-resilient patterns.

### Tier 2: Third-Party Libraries (CONCISE IDENTIFICATION)
For large library blocks, provide minimal identification information only.

## CRITICAL: Decision Tree

Follow this hierarchy when revising your analysis:

### 1. FIRST: Is this a large third-party library block?
If you see 1000+ lines of pure library code (RxJS, Lodash, Sentry, React, Ink, Axios, etc.):

**Use Library Block Format:**
```
Lines [start]-[end]: [Library Name] ([size] lines)
Identified by: [Stable identifying traits - strings, patterns, APIs]
Integration points: [Where native Claude Code connects to this library]
```

**Example:**
```
Lines 28000-33000: RxJS Library (5,000 lines)
Identified by:
  - String literals: "Observable", "Subject", "Subscriber" at lines 28400, 30000, 28200
  - API patterns: .subscribe(), .pipe(), .map(), .filter() methods
  - Error messages: "Cannot subscribe to closed observable"
Integration points:
  - Line 27900: Claude Code imports RxJS operators for event handling
  - Line 33100: App-specific error wrapper around RxJS streams
```

### 2. SECOND: Is this hook-related native code?
If you see `PreToolUse`, `PostToolUse`, or hook execution in native Claude Code:

**Use Precise Documentation (keep current minified names + add patterns):**
```
**Hook Function Name**: [Current minified name] - [Functional description]
- **Pattern**: [How to identify in future versions]
- **Parameters**: [Expected parameter patterns]
- **String markers**: [Unique strings to search for]
- **Context**: [When/where called in app flow]
- **Current name**: [Minified name] (will change in next version)
```

### 3. THIRD: All other native Claude Code
For native application code that's not hooks:

**Use Pattern-Based Documentation (replace minified names with patterns):**
```
**[Functional Description]**:
- **Pattern**: [How to identify this in future versions]
- **Parameters**: [Expected parameter patterns]
- **Behavior**: [What this function does in Claude Code]
- **String markers**: [Unique error messages, console logs]
- **Context**: [When/where this executes in app lifecycle]
- **Current names**: [List current minified names for reference]
```

## Library Identification Patterns

### Common Third-Party Libraries:

**RxJS (Reactive Programming):**
- Identifiers: "Observable", "Subject", "pipe", "subscribe" strings
- Patterns: .subscribe(), .pipe() method chains
- Typical size: 5,000-15,000 lines

**Lodash (Utility Functions):**
- Identifiers: "_." prefix patterns, utility function collections
- Patterns: _.map(), _.filter(), _.forEach() style functions
- Typical size: 10,000-20,000 lines

**Sentry (Error Reporting):**
- Identifiers: "Sentry", "captureException", DSN configurations
- Patterns: Error handling wrappers, breadcrumb tracking
- Typical size: 15,000-30,000 lines

**React (UI Framework):**
- Identifiers: "React", "createElement", component patterns
- Patterns: Component lifecycle, hooks, virtual DOM
- Typical size: 30,000-50,000 lines

**Ink (Terminal UI):**
- Identifiers: Terminal UI components, ANSI escape sequences
- Patterns: Box, Text, Input components
- Typical size: 5,000-10,000 lines

**Axios (HTTP Client):**
- Identifiers: HTTP method names, request/response patterns
- Patterns: Promise-based HTTP with interceptors
- Typical size: 3,000-8,000 lines

## Native Code Enhancement Instructions

### For Claude Code Application Code:

#### Step 1: Cross-Reference Implementation
- Use line numbers to find exact code in `package/cli.prettier.js`
- Read actual implementation to understand functionality
- Identify what this code does specifically in Claude Code

#### Step 2: Find Version-Resilient Patterns
**String Patterns:**
- Error messages: "Failed to execute tool", "Invalid configuration"
- Console logs: console.warn("Claude Code: ..."), console.error("...")
- API endpoints, configuration keys, command names

**Behavioral Patterns:**
- Parameter structures specific to Claude Code operations
- Return value patterns for tool execution, user interaction
- Exception handling specific to Claude Code functionality

**Contextual Patterns:**
- Tool execution lifecycle, user input handling, output rendering
- Configuration loading, plugin management, session handling

#### Step 3: Document Integration Points
For library integrations, focus on:
- How Claude Code initializes/configures the library
- Custom wrappers or extensions Claude Code adds
- Error handling specific to Claude Code's usage

## Revision Priority

### High Priority (Revise First):
1. **Hook-related code** - Critical for your debugging needs
2. **Tool execution and management** - Core Claude Code functionality
3. **User interaction and UI rendering** - Essential app behavior
4. **Configuration and session management** - App initialization

### Medium Priority:
1. **Error handling and logging** - Important for debugging
2. **Plugin and extension management** - App architecture
3. **File system and process management** - Core utilities

### Low Priority (Library Blocks):
1. **Large library sections** - Convert to concise identification only
2. **Utility function collections** - Minimal documentation needed

## Success Criteria

After revision:

**For Native Claude Code:**
- Detailed, pattern-based documentation that survives re-minification
- Clear debugging information for tool execution and hooks
- Understanding of app architecture and functionality

**For Third-Party Libraries:**
- Concise identification (5-10 lines maximum per library)
- Stable identifiers for finding libraries in future versions
- Integration points where Claude Code connects to libraries

**Overall:**
- Dramatically reduced file sizes
- Focus on actionable debugging information
- Version-resilient analysis that remains useful after re-minification

## Files to Revise

Focus on files with extensive library documentation or debugging landmarks:
- cli_prettier_notes_chunk_28001-33000.md (RxJS heavy)
- cli_prettier_notes_chunk_73001-78000.md (React heavy)
- All files with "Debugging Landmarks" sections
- Any files with 50+ lines of library function documentation

Convert library sections to concise blocks, enhance native code sections with version-resilient patterns.