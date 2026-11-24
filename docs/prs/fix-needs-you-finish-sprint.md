# PR Summary: fix/needs-you-finish-sprint

## Summary

- **The owner's report, 2026-11-24:** "did we not agree to make the 'finish
  sprint' requirement clearer?" Slice 3 made the sprint page's State say
  "Ready to finish". But nothing led there: Needs you listed only task
  decisions and the sprint order, so sprint 62 sat ready with no prompt.
- **The change:** Needs you gains a sixth kind, `finish_sprint`. It covers an
  active sprint whose every task is done or cancelled, in a project where a
  user finishes sprints.
  - The row says "Finish sprint", names the sprint (a link) and its tasks,
    and has a Finish button.
  - Finish does what the sprint page's Finish sprint does: it completes the
    sprint, which tags it (ADR-0036). It confirms in the shared toast.
  - The item counts in the workspace's and the project's Needs you.
- **Where Foreman finishes sprints** (`sprint_completion = auto`), nothing
  waits, and no row is shown.

## Scope

- `foreman/services/workspace.py` (`_sprints_ready_to_finish`, the kind,
  `task_counts`)
- `foreman/store/overview.py` (`latest_sprint_record`, one statement for
  every sprint)
- `frontend/src/api/needsYou.js`
- `frontend/src/pages/shared/NeedsYou.jsx`

## Files changed

- Code as above.
- Tests:
  - `tests/test_dashboard_workspace_api.py`: listed with its tasks and
    counted; not while a task is open nor where Foreman finishes; since is
    the ready record; the query count holds over seven projects;
  - `frontend/src/pages/project/ProjectPage.test.jsx`: the row, the link,
    Finish and the toast.
- Docs: `docs/ARCHITECTURE.md`, the design README, `docs/MANUAL.md`,
  `CHANGELOG.md`.

## Migrations

None.

## Risks

- Finish from Needs you tags the repository and pushes the tag, as the
  sprint page's button does. It has no extra confirmation, also as on the
  sprint page.

## Tests

- `tests/test_dashboard_workspace_api.py` (42).
- Frontend tests, lint and build.
- The whole Python suite before the merge.

## Acceptance criteria

- A sprint ready to finish appears in Needs you and can be finished there.

## Follow-ups

None.
