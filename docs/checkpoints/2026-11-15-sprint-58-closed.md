# Checkpoint: sprint 58 closed (2026-11-15)

Phase 4 of the finish plan (frontend rebuild) is complete on `main`.

## What works

- The dashboard is the one in `docs/design/dashboard-v7/` (ADR-0020):
  workspace, project, sprint and task pages; the backlog as a page; the
  manager as a side bar that proposes and a person confirms (ADR-0022);
  project and workspace settings; sign in when the server has a token. The
  old frontend and `/dashboard/legacy` are gone.
- Everything the old dashboard could do has a place or was dropped on
  purpose: `docs/design/dashboard-v7/legacy-capabilities.md`.
- A task can be closed and reopened by hand (`foreman task done`,
  `foreman task reopen`, the task's More menu).
- Slices and who executed each (Foreman or by hand):
  `docs/sprints/archive/sprint-58-frontend-rebuild.md`.
- Validation at close: 1342 Python tests (5 skipped), 367 frontend tests,
  ESLint and `ruff check` clean, repository validator passing, CI green.

## What is incomplete

- From Phase 4 of the plan: no browser acceptance pack, no types in the
  frontend, descriptions and manager replies are not rendered as markdown,
  and a task's run output is raw JSON.
- The engine has been stopped since 2026-11-13. Nothing built after that
  date has been seen against a running engine. Between steps a running
  engine may report no current task, so a task could read "Stopped at ..."
  for a moment; not observed, only reasoned.
- The engine defects found while Foreman ran the sprint are open
  (`docs/sprints/backlog.md`).
- FOR-42 and FOR-43 wait in the backlog of Foreman's own project for the
  owner to accept or decline.

## Known regressions

- None known. One frontend test ("never sends a host-level setting") failed
  once on CI at `a963ac4`; the likely cause was fixed in
  `fix/forms-keep-an-early-edit` but the failure was never reproduced.

## Schema or migration notes

- Migrations 21 (backlog, ADR-0021), 22 (manager proposals, ADR-0022) and 23
  (the commit each run left). Schema version 23.

## Safe branch points

- `main` at the merge of `docs/sprint-58-close`.

Next: Phase 5. A proposed sprint 59 is in `docs/sprints/current.md`; it is
not opened until the owner agrees its scope.
