---
verified: 2.1.316
verified_on: 2026-10-31
section: Architecture and dependencies
style: landmark
scope: >-
  `githubRepoPaths` in ~/.claude.json: when it is written, teleport and deep-link readers, stale
  entries
landmarks:
  - githubRepoPaths
  - Teleport to Repo
  - No local clone found for repo
---
# githubRepoPaths in ~/.claude.json

`githubRepoPaths` is a key in the global config file (`~/.claude.json`). It maps a lowercase
`owner/repo` to an ordered array of absolute local checkout paths, most recently used first. It
exists to find a local clone of a GitHub repository when a feature starts from the repository name
and not from a directory.

## Re-location recipes

| Behavior                  | Grep                                                               |
| ------------------------- | ------------------------------------------------------------------ |
| Writer, reader, remover   | `githubRepoPaths` (one module holds all of them)                   |
| Write log line            | `Added ${i} to tracked paths for repo`                             |
| Skip log line             | `Not in a GitHub repository, skipping path mapping update`         |
| Remove log line           | `Removed ${o} from tracked paths for repo`                         |
| Teleport path picker      | `Teleport to Repo` and `no longer contains the correct repository` |
| Teleport mismatch message | `You must run claude --teleport`                                   |
| Deep link repo lookup     | `Resolved repo` beside `No local clone found for repo`             |

## Writing

The writer is called once per interactive launch, in the step list that follows the trust dialog and
onboarding (the setup-screens function, whose steps include `TrustDialog`). It does not run in print
mode, in the SDK, in background-session workers, or when the setup screens are skipped.

Steps:

1. Read the current directory's git remote and take `owner/name` from it, only when the host is
   exactly `github.com`. GitHub Enterprise hosts and non-GitHub remotes are skipped, with the log
   line `Not in a GitHub repository, skipping path mapping update`.
2. Take the git root of the session's original working directory (the directory itself when no
   root is found), then resolve it with `realpath`.
3. Lowercase the repository name and use it as the key.
4. If the first array element already equals the path, do nothing. Otherwise write the array with
   the path moved or added at the front and every other path kept.

Nothing is ever expired by age or count on the write side. Paths from earlier launches stay until a
removal (below) or a manual edit.

## Reading

Three read sites, all through one lookup that lowercases the key:

- Teleport (`claude --teleport <session>` and the resume flow). When the session's repository does
  not match the current directory (`mismatch` or `not_in_repo`), the stored paths are filtered to
  those that still exist (`stat` succeeds). If any remain, a "Teleport to Repo" picker offers them.
  If none remain, the command stops with
  `You must run claude --teleport <id> from a checkout of <repo>`.
- The teleport picker verifies the choice before using it: it reads the git remote of the chosen
  path and compares `owner/name` case-insensitively with the target repository. A mismatch removes
  that path from the array and shows
  `<path> no longer contains the correct repository. Select another path.`
- The deep-link handler. A launch with a repository parameter (`--deep-link-repo`) opens in the
  first stored path that still exists, falling back to the home directory with the log line
  `No local clone found for repo`. This path does no remote check.

Remote Control, `--resume` across worktrees, PR status and plain `--resume` do not read the key.

## Stale entries

| Stale case                                         | Effect                                                                                 |
| -------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Directory deleted                                  | Filtered out at read time, never offered. Left in the file.                            |
| Directory exists, now a different repo (teleport)  | Caught by the remote check, removed, user told to pick again.                          |
| Directory exists, now a different repo (deep link) | Used as the working directory. No remote check.                                        |
| GitHub repo renamed, remote URL updated            | A new key is written on the next launch. The old key is unused.                        |
| GitHub repo renamed, remote URL not updated        | The old key keeps being written. Teleport looks up the new name, so it finds no paths. |
| GitHub repo deleted                                | Entry is inert.                                                                        |

No stale entry causes an error. Deleting the key, or any path in it, is safe: the next launch inside
a GitHub checkout adds the current path back.

## Version history

- 2.1.316: first written.
