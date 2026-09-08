# PR Summary: chore/task-c68378a4e541

## Summary

Closes the two follow-ups ADR-0012 recorded when it landed one worktree per
task, plus the operator control it left missing.

- **Total worktree disk use is now bounded by an explicit policy.** New
  `max_live_worktrees` (default 4, `0` disables) caps how many task worktrees
  exist at once. `worktrees.enforce_worktree_limit` runs from the orchestrator
  immediately *before* it creates a tree, so the cap bounds peak disk use
  rather than its steady state.
- **A task's test run no longer depends on the operator's virtualenv.** New
  `worktree_setup_command` runs once inside each newly created tree to build
  that tree's own environment. This repository now uses it to create a per-tree
  venv and editable install, and `worktree_link_paths` — which symlinked the
  operator's `venv/` into every tree — is empty.
- **The dashboard can prune worktrees.** The project screen shows the live tree
  count against the cap and the worktree root, with a Prune worktrees control
  behind two new endpoints.
- ADR-0012 amended; `docs/MANUAL.md` §24 rewritten around both settings.

### The reclaim policy, and why it is not "prune the oldest paused tree"

The follow-up suggested pruning the oldest paused task's tree under pressure.
Implemented literally that would be wrong: *paused* is precisely when a tree
holds uncommitted work, so the policy would most often destroy the state
worktrees exist to preserve. The landed policy orders by age but gates on
cleanliness:

1. the integration tree and the tree of the task about to run are never
   candidates,
2. trees of done, cancelled, and deleted tasks go first,
3. then the least recently used of the rest, measured by each tree's own git
   index mtime (git rewrites it on every checkout, commit, and status in that
   tree — no schema change, and a truer signal than anything Foreman persists),
4. **a tree with uncommitted changes is never reclaimed.**

Reclaiming a *clean* tree is safe because it holds nothing its branch does not:
the task keeps its branch and workflow position, `worktree_path` is cleared,
and the next visit recreates the checkout and reprovisions its environment. The
cost of being reclaimed is one checkout and one setup run.

The consequence is that the cap is a ceiling the engine reaches for, not an
invariant it can hold. A project whose candidates are all dirty stays above its
cap and records `engine.worktree_limit_exceeded` naming the trees it refused to
take. Losing an agent's unfinished work to a disk limit is worse than exceeding
the limit and reporting it. Reclaiming also never fails a task — an error is
recorded as `engine.worktree_reclaim_failed` and the task still gets its tree.

### The setup marker

Setup runs once per tree, tracked by a marker holding a hash of the command.
The marker lives in the tree's **git admin directory**
(`<repo>/.git/worktrees/<slug>/`), not in the tree: a marker file inside the
tree would be untracked, which makes the tree dirty, which blocks
`_builtin:merge`. `git worktree remove` takes the admin directory with the
tree, so a reclaimed tree reprovisions when it comes back. Changing the setting
reprovisions every tree on its next visit; clearing it drops the marker.

A failing setup command fails `ensure` rather than running a step in an
environment that was never built. No marker is written, so the next visit
retries, and the tree is left on disk to inspect.

The shared `_integration` tree is exempt: only `_builtin:merge` works there and
it runs git and nothing else, so provisioning it would build a full environment
per project that nothing uses.

## Scope

In scope: the two settings and their validation, the reclaim policy and its
events, the setup command and its marker, the two dashboard endpoints and the
project-screen control, ADR-0012, `docs/MANUAL.md`, and this repository's own
project settings.

Out of scope: per-task containers or filesystem quotas (rejected in the ADR —
they would make Foreman own the runtime environment of every project it works
on); changing when trees are created or removed by the workflow.

## Files changed

**Backend**

- `foreman/settings.py` — `max_live_worktrees`, `worktree_setup_command`,
  `worktree_setup_timeout_seconds`, with validation.
- `foreman/worktrees.py` — `_run_setup_command` and the marker; `admin_dir`
  and `last_used_at`; `ReclaimOutcome`, `max_live_worktrees`, and
  `enforce_worktree_limit` alongside the existing store-aware
  `prune_project_worktrees`. `WorktreeManager` stays filesystem/git only.
- `foreman/orchestrator.py` — `_reclaim_worktrees_for` before `ensure`, and
  `_emit_worktree_event`.
- `foreman/dashboard_service.py` — `list_worktrees`, `prune_worktrees`,
  `_serialize_worktree`, `_require_project`.
- `foreman/dashboard_backend.py` — `GET /api/projects/{id}/worktrees`,
  `POST /api/projects/{id}/worktrees/prune`.

**Frontend**

- `frontend/src/components.jsx` — `WorktreePanel`, rendered on the project
  screen.
- `frontend/src/api.js` — `listWorktrees`, `pruneWorktrees`.
- `frontend/src/styles.css` — `.worktree-meta`, `.worktree-root`, `.btn-small`.
- `foreman/dashboard_frontend_dist/` — rebuilt.

**Tests**

- `tests/test_worktrees.py` — `WorktreeSetupCommandTests` (11),
  `WorktreeLimitTests` (8).
- `tests/test_dashboard.py` — four endpoint tests.
- `tests/test_settings.py` — `WorktreeBudgetSettingsTests` (5).
- `frontend/src/components.test.jsx` — new file, six `WorktreePanel` tests.
- `frontend/src/App.test.jsx` — the new service methods in the mock.
- `tests/test_cli.py` — comment corrected; its guard already handled both
  arrangements.

**Docs** — `docs/adr/ADR-0012-worktree-per-task.md` (amended),
`docs/MANUAL.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`,
`docs/sprints/current.md`, `CHANGELOG.md`, this file.

## Migrations

None. The reclaim policy deliberately needs no schema: last-use comes from each
tree's git index mtime, and `tasks.worktree_path` (migration 16) already
carries everything else.

## Risks

- **A project that adopts `worktree_setup_command` carelessly can dirty its
  trees.** Anything the command creates must be gitignored, or the tree is
  dirty and `_builtin:merge` refuses it. Called out in the manual and the ADR.
  For this repository, `venv/` and `*.egg-info/` were already ignored and the
  provisioned tree was verified clean.
- **A too-low `max_live_worktrees` turns into repeated setup cost**, not
  incorrect behaviour: reclaimed tasks re-provision when they resume. The
  default of 4 is a guess at a reasonable working set and is one config change
  away.
- **Reclaiming widens what the engine deletes**, so the guard matters:
  `remove_path` still refuses anything outside the worktree root, the
  integration tree and the arriving task's tree are excluded by slug, and dirty
  trees are excluded by `is_worktree_clean`. All four are covered by tests.
- **Setup runs on every `ensure` call for a tree whose marker is missing**,
  which includes trees created before this change. That is intended — those
  trees have no environment — but it means the first visit after upgrading pays
  the provisioning cost.

## Tests

- `./venv/bin/python -m unittest discover -s tests` — **831 passed**, 1 skipped.
- `npx vitest run` (frontend) — **35 passed** across 4 files.
- `npx vite build` — dist rebuilt.
- `./venv/bin/python scripts/validate_repo_memory.py` — passed.

End-to-end verification of the acceptance criterion, not just unit tests: a
worktree for this task was provisioned from scratch by the new setting
(~6 seconds), and the project's own `test_command` run inside it:

```
$ cd .foreman/worktrees/FOR-10 && ./venv/bin/python -m unittest discover -s tests
Ran 830 tests in 83.911s
OK (skipped=1)
$ git status --porcelain | wc -l
0
$ readlink -f venv/bin/python
/usr/bin/python3.12          # the tree's own venv, not the operator's
```

`foreman worktree prune foreman` then correctly kept that tree, because the
task is live.

## Acceptance criteria satisfied

| Criterion | Where |
|---|---|
| Total worktree disk use bounded by an explicit, documented policy | `max_live_worktrees` + `enforce_worktree_limit`; ADR-0012 "Bounding disk use", MANUAL §24 |
| A task's test run no longer depends on the operator's virtualenv | `worktree_setup_command`; this project reconfigured and verified above |
| The dashboard can prune worktrees | `WorktreePanel` + two endpoints |
| ADR-0012 and `docs/MANUAL.md` updated | both, plus ARCHITECTURE/CHANGELOG/STATUS/sprint |

## Follow-ups

- The cap counts trees, not bytes. A byte-based budget (`max_worktree_bytes`)
  would be a truer bound now that a tree can contain an installed environment,
  but it needs a cheap size estimate that does not stat a whole checkout on
  every task start.
- `engine.worktree_limit_exceeded` is recorded but nothing escalates it. If a
  project sits above its cap for many passes, that is a person's problem to
  hear about — a candidate for the notification policy in slice 4.
- Reclaim runs only when a task is about to get a tree. A project that goes
  idle above its cap stays there until the next task starts or someone prunes.
