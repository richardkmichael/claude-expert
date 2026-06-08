# Patch: Search All Dirs for File Completions

## Purpose

When `@` is typed in Claude Code, file completions come only from the cwd. Additional workspace
directories added via `--add-dir` or `/add-dir` are ignored by the file indexer. This patch makes
`@`-completions include files from all additional directories, and passes those directories to
the `fileSuggestion` hook so custom search scripts can also search them.

## Original Code Behavior

In unpatched Claude Code:
1. `zeY()` calls `YeY()` (git ls-files with ripgrep fallback on cwd) and `KeY()` (`.claude/`
   dir scanner) in parallel
2. The combined file list is indexed for `@`-completion
3. Directories added via `--add-dir` / `/add-dir` (returned by `mT()`) are never searched
4. Typing `@filename` for a file only in an additional dir produces no match
5. The `fileSuggestion` hook stdin receives `{ session_id, transcript_path, cwd, query }` with
   no information about additional directories, so hook scripts cannot search them either

## Patch Implementation

### Change 1: New Helper `getAdditionalDirFiles(signal, respectGitignore, dir)`

A new async helper that indexes a single additional directory, mirroring the git ls-files +
ripgrep fallback pattern used by `YeY()` / `qeY()` for the cwd:

```javascript
async function getAdditionalDirFiles(A, q, K) {
  // A = AbortSignal, q = respectGitignore, K = directory path
  try {
    let z = await Z7(eA(),
      ["-c", "core.quotepath=false", "ls-files", "--recurse-submodules"],
      { timeout: 5000, abortSignal: A, cwd: K },
    );
    if (z.code === 0) {
      // Map paths relative to cwd: join(K, relativePath) → relative(cwd, absPath)
      return z.stdout.trim().split("\n").filter(Boolean)
        .map((H) => WJ.relative(y1(), WJ.join(K, H)));
    }
    // fall through to ripgrep on non-zero exit (not a git repo, etc.)
  } catch (z) { /* fall through to ripgrep */ }

  let _ = ["--files", "--follow", "--hidden", "--glob", "!.git/"];
  if (!q) _.push("--no-ignore-vcs");
  return (await Lu(_, K, A)).map((H) => WJ.relative(y1(), H));
}
```

git ls-files is run with `cwd: K` (the additional directory). Git walks up from `K` to find its
own root, so no pre-check for a git repo is needed. On success (exit code 0), paths from stdout
are relative to the additional dir and are resolved to absolute then made relative to cwd.
On failure (non-zero exit — not a git repo, git unavailable, etc.), ripgrep is used as fallback.

### Change 2: Modified `zeY()` — Additional Dirs in the File Index

```javascript
// Before:
[w, _] = await Promise.all([YeY(A, Y), KeY(z)]),
$ = [...w, ..._],

// After:
extraDirs = mT(),
[w, _, ...extraResults] = await Promise.all([
  YeY(A, Y),
  KeY(z),
  ...extraDirs.map((dir) => getAdditionalDirFiles(A, Y, dir)),
]),
$ = [...w, ...extraResults.flat(), ..._],
```

When no additional directories are configured, `mT()` returns `[]`, the spread is empty, and
behaviour is identical to the original. The error-logging in the Fuse.js `catch` block was also
simplified (removed verbose message and `$6()` call; a plain `j = H` suffices).

### Change 3: `additional_dirs` in `fileSuggestion` Payload

```javascript
// Before:
let Y = { ...U$(), query: A };

// After:
let Y = { ...U$(), query: A, additional_dirs: mT() };
```

The `fileSuggestion` hook now receives the list of additional workspace directories so custom
search scripts can search them alongside the cwd.

## Key Variables (version 2.1.63)

| Symbol                           | Role                                                           |
|----------------------------------|----------------------------------------------------------------|
| `mT()`                           | Returns `x1.additionalDirectoriesForClaudeMd` (line ~2673)    |
| `zeY()`                          | File index assembler — modified by this patch                  |
| `YeY(signal, respectGitignore)`  | cwd file lister: git ls-files → ripgrep fallback               |
| `qeY(signal, respectGitignore)`  | git ls-files helper called by `YeY()`                          |
| `KeY(cwd)`                       | `.claude/` commands/agents/skills dir scanner                  |
| `Z7(cmd, args, opts)`            | Git subprocess runner                                          |
| `eA()`                           | Returns the git executable path                                |
| `Lu(args, cwd, signal)`          | Ripgrep wrapper                                                |
| `WJ`                             | Node `path` module alias                                       |
| `y1()`                           | Returns the current working directory                          |
| `ttY()`                          | Loads the Rust fuzzy index                                     |
| `Sg8()`                          | Generates prefix-expansion (parent dir) entries                |
| `y()`                            | Debug logger                                                   |
| `U$()`                           | Base hook payload: `{ session_id, transcript_path, cwd, ... }` |
| `w5q(query, force)`              | `@`-completion entry point — `fileSuggestion` check is here    |

## Execution Flow (patched)

```
1. zeY() starts, creates AbortSignal (10 s timeout)
2. Read respectGitignore setting (merged from project + user config)
3. extraDirs = mT()  ← additional dirs (may be empty)
4. Promise.all([
     YeY(signal, respectGitignore),              ← git ls-files (or ripgrep) on cwd
     KeY(cwd),                                   ← .claude/ dir scanner
     ...extraDirs.map(dir =>
       getAdditionalDirFiles(signal, rGI, dir)   ← git ls-files (or ripgrep) per extra dir
     ),
   ])
5. Merge: $ = [...cwdFiles, ...extraDirFiles.flat(), ...claudeFiles]
6. Build index entries: H = [...Sg8($), ...$]
7. Load Rust fuzzy index if available, else use plain list
8. Return { fileIndex, fileList }

For fileSuggestion hook path (in w5q):
  payload = { ...U$(), query, additional_dirs: mT() }
  → passed as stdin JSON to the hook command
```

## Verification

1. Run `node work/2.1.63/package/cli.prettier.js --add-dir /tmp/other-project`
2. Type `@` — file suggestions should include files from `/tmp/other-project`
3. Type a filename prefix only present in the added dir — it should appear
4. With no `--add-dir`: behaviour is unchanged (zero extra `Promise.all` entries)
5. If a `fileSuggestion` command is configured, log its stdin to verify `additional_dirs`
   is present and contains the directories passed via `--add-dir`
