# PR Summary: fix/sandbox-git-and-prune

## Summary

Faults found by an independent review of FOR-64 (the reviewer's sandbox)
before its code went live:
- **Every git command failed in a sandbox on git before 2.31.** The push
  block wrote `GIT_CONFIG_PARAMETERS` entries as `'key'='value'`, which git
  2.25 (this machine) refuses outright. It is now written `'key=value'`,
  which every version reads and which still blocks the push.
- **Prune deleted a running review's sandbox.** `_sandbox-<slug>` never
  matched a live task, so `foreman worktree prune` and the dashboard's prune
  removed it. A live task's sandbox is now kept.
- **The reviewer could not take screenshots, and that would have blocked
  every frontend task.**
  - No Playwright browser is installed on this machine, and Playwright sat
    in the `e2e` extra, not `dev`.
  - The prompt also gave no way to serve the app.
  - A criterion the reviewer could not check had to be `not_verified`, and
    FOR-62's rule refuses an approval with one.
  - Now:
    - the shipped prompt points to the project's own preview recipe in its
      `AGENTS.md`;
    - when the reviewer cannot see a page, it judges from the code and adds
      an S3 finding, "not seen in a browser";
    - Foreman's recipe is `scripts/review_screenshots.py`: it builds,
      serves a read-only copy of the database on a free localhost port, and
      screenshots at 1440 and 390 px with any Chromium on the PATH;
    - Foreman's `worktree_setup_command` (a project setting) installs
      `.[dev,e2e]`.
- `docs/ARCHITECTURE.md` no longer claims the old format works everywhere,
  and says the push block is a deterrent, not a wall.

## Scope

The sandbox's git environment, prune, the code reviewer's prompt, a preview
script, AGENTS.md, ARCHITECTURE.md, the sprint file.

## Files changed

- `foreman/repo/worktrees.py`
- `foreman/data/roles/code_reviewer.toml`
- `scripts/review_screenshots.py` (new)
- `AGENTS.md`, `docs/ARCHITECTURE.md`, `.gitignore`, `docs/sprints/current.md`
- `tests/test_sandbox.py`, `tests/test_worktrees.py`
- this note.

## Migrations

None.

## Risks

- The preview script needs a Chromium-family browser; this machine has
  Google Chrome. Without one the reviewer falls back to judging the code,
  with an S3 finding.

## Tests

- New: git status, log and diff work in a sandbox of a repository with a
  remote, and the push URL is still blocked. Prune keeps a live task's
  sandbox. Both fail without the fix.
- Sandbox, worktree, role and agent-sandbox tests: 175 passed.
- The preview script, run end to end: four screenshots of the project and
  task pages.
- Full suite before merge.

## Acceptance criteria

- A reviewer in a sandbox can run git and the project's tests on this
  machine.
- Prune keeps a running review's working copy.
- A frontend task can be approved when the page could not be seen, with
  that recorded as an S3 finding.

## Follow-ups (backlog)

- `run_scope = "none"` is not enforced.
- Pushes are deterred, not prevented or detected.
- Sandboxes left behind by a hard-killed engine are cleaned up only by prune.
