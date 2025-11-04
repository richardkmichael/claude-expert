# Library Block Documentation Instructions

## Problem Identified

The current analysis is providing excessive detail for large third-party libraries (RxJS, Lodash, Sentry, etc.), documenting dozens of individual functions and operators. This creates enormous analysis files when what's needed is high-level library identification and boundaries.

## Required Approach: High-Level Library Blocks

**Replace detailed library analysis with concise block identification:**

### Template Format:
```
Lines [start]-[end]: [Library Name] ([size] lines)
Identified by: [Stable identifying traits]
Integration points: [Where native code connects to library]
```

### Example Transformations:

**BEFORE (Current - Too Much Detail):**
```
### 1. RxJS Library Components
A significant portion of this chunk is dedicated to RxJS, indicating a reactive programming paradigm.
*   **Observables:**
    *   `K7().Observable` (line 28400) - The base Observable class.
    *   `hw().EMPTY` (line 31000) - Represents an Observable that immediately completes.
    [... 70+ more detailed function descriptions ...]
```

**AFTER (Concise Block Format):**
```
Lines 28000-33000: RxJS Library (5,000 lines)
Identified by:
  - String literals: "Observable", "Subject", "Subscriber" at lines 28400, 30000, 28200
  - Class patterns: Observable/Subject/Scheduler hierarchies
  - Method signatures: subscribe(), pipe(), map(), filter()
  - Error messages: "Cannot subscribe to closed observable"
Integration points:
  - Line 27900: Native code imports RxJS operators
  - Line 33100: App-specific error handling wrapper around RxJS
```

## Library Identification Guidelines

### What to Document (Keep Brief):

**1. Boundary Lines**
- Start and end line numbers of the library block
- Total line count for the library

**2. Stable Identifying Traits**
- **String literals**: Unique error messages, console logs, library-specific terms
- **Class/function patterns**: Distinctive API structures (Observable.subscribe, $.ajax, etc.)
- **Configuration objects**: Library-specific property names and structures
- **Method signatures**: Characteristic parameter patterns

**3. Integration Points Only**
- Where native application code imports/initializes the library
- Where native code wraps or extends library functionality
- Configuration objects where native code customizes library behavior

### What NOT to Document (Skip Completely):

**1. Internal Library Implementation**
- Individual library functions and their purposes
- Library's internal class hierarchies
- Detailed operator/method descriptions
- Library-specific algorithms and data structures

**2. Library Documentation**
- How the library works internally
- Library API explanations
- Educational content about library usage

## Specific Library Patterns

### RxJS (Reactive Programming)
```
Identified by: "Observable", "Subject", "pipe", "subscribe" strings
Pattern: Class hierarchies with .subscribe(), .pipe() methods
Integration: Look for native code creating Observables or using operators
```

### Lodash (Utility Functions)
```
Identified by: "_." prefix patterns, utility function names
Pattern: Collection of utility functions with consistent naming
Integration: Look for native code calling _.map(), _.filter(), etc.
```

### Sentry (Error Reporting)
```
Identified by: "Sentry", "captureException", DSN configuration
Pattern: Error handling wrappers, breadcrumb tracking
Integration: Look for native error handling that calls Sentry methods
```

### React/Ink (UI Framework)
```
Identified by: Component patterns, "React", "createElement", JSX transforms
Pattern: Component lifecycle methods, hooks, virtual DOM
Integration: Look for native component definitions and app initialization
```

### Axios (HTTP Client)
```
Identified by: HTTP method names, "axios", request/response patterns
Pattern: Promise-based HTTP client with interceptors
Integration: Look for native API calls and HTTP configuration
```

## Implementation Instructions

### Step 1: Identify Library Boundaries
- Scan for consistent patterns indicating start/end of library blocks
- Note line ranges where the library appears to be self-contained

### Step 2: Find Stable Identifiers
- Look for unique string literals that won't change across versions
- Note distinctive API patterns and class structures
- Identify error messages and console output specific to the library

### Step 3: Locate Integration Points
- Find where native code imports or initializes the library
- Look for configuration objects where native code customizes the library
- Note wrapper functions or extensions created by the application

### Step 4: Replace Detailed Analysis
- Remove all detailed function-by-function documentation
- Replace with concise block format using template above
- Focus on what makes this library identifiable across versions

## Success Criteria

After revision, each large library should be:
1. **Documented in 5-10 lines maximum** (not 50-100 lines)
2. **Identifiable in future versions** using stable patterns
3. **Focused on integration points** rather than library internals
4. **Useful for debugging** native code interactions with the library

The goal is efficiency and version-resilience, not comprehensive library documentation.