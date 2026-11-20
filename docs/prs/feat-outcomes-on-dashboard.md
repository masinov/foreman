# PR Summary: feat/outcomes-on-dashboard

## Summary

- The outcome numbers (ADR-0034) are on the dashboard, where the owner
  agreed on 2026-11-21. There is one line at the top of the project page
  ("All sprints") and one under the sprint page's summary, with the table by
  role and model behind "By role and model".
- Fix: a decision counted as waiting forever when its task was closed or
  cancelled at a gate. Foreman's project said "1 waiting" (FOR-49) while
  Needs you said none.

## Scope

- Frontend: `api/outcomes.js`, `pages/shared/Outcomes.jsx` and its test,
  `styles/outcomes.css`. The summary-line styles moved from `sprint.css` to
  `lists.css`, so the project page has them. The component is wired into
  `SprintLayout` and `ProjectLayout`.
- Backend: `foreman/domain/outcome_numbers.py` (what still waits), with a
  test.

## Files changed

- `frontend/src/api/outcomes.js` (new)
- `frontend/src/pages/shared/Outcomes.jsx`, `Outcomes.test.jsx` (new)
- `frontend/src/styles/outcomes.css` (new), `lists.css`, `sprint.css`
- `frontend/src/pages/sprint/SprintLayout.jsx`,
  `frontend/src/pages/project/ProjectLayout.jsx`
- `foreman/domain/outcome_numbers.py`, `tests/test_outcome_numbers.py`
- `docs/adr/ADR-0034-outcome-numbers.md`, `CHANGELOG.md`,
  `docs/sprints/current.md`

## Migrations

- none

## Risks

- The project page makes one more request. On a project with many runs it
  reads all of them; Foreman's own 41 tasks answer at once.

## Tests

- `ruff check foreman tests scripts`, `lint-imports`, 1592 Python tests,
  `npm run lint`, 459 frontend tests, `npm run build`. The new waiting
  test fails on the old code.
- Looked at with `scripts/dashboard_shot.mjs` on a copy of the database, at
  1440 px and at 390 px.

## Screenshots or output examples

- Sprint page, Assay sprint 2: "First time 7 of 8 · Sent back 1: review 1 ·
  You Never asked, never stepped in · Per merged task $0.36 · To merge 6.9
  min median".

## Acceptance criteria satisfied

- One line of numbers on the sprint page (that sprint) and the project page
  (all time), with the per-role and per-model detail behind a click.

## Follow-ups

- The activity views' review and proposal (owner, 2026-11-21).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
