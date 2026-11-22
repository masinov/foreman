# PR Summary: fix/task-pages-one-voice

## Summary

- A task's Overview, Checks and Activity say the same things the same
  way. The owner asked for it after the new Activity (2026-11-22).
- **Overview:**
  - The checks summary is removed.
  - Details shows everything at once, with no "More details" and no
    "Times at each step".
  - The description and the acceptance criteria are formatted.
  - The Steps table says "Approved by setting", "Merged" without a time,
    and "Attempts".
- **Checks:**
  - "Measured by Foreman".
  - The review is named by its role, without its APPROVE line.
  - Criteria are formatted and no longer repeat the review's commit.
  - "Evidence files" shows only when there are some.
- **A gate's facts** use the Details' words for who decided.

## Scope

- Frontend only.
- `Markdown` keeps a line break inside a paragraph, because acceptance
  criteria are one per line with no list mark.
- `LongText` is a block (`div`), so it can hold formatted text.
- `gateDecider` in `taskWords.js` gives both Details and a step's facts
  one wording. It names the setting's source only while the task's
  setting still says what was decided then.

## Files changed

- `frontend/src/pages/task/{OverviewTab,ChecksTab}.jsx`
- `frontend/src/pages/task/{taskWords,stepFacts}.js`
- `frontend/src/ui/{Markdown,LongText}.jsx`
- `frontend/src/styles/task.css`
- Tests: `frontend/src/pages/task/TaskPage.test.jsx`,
  `frontend/src/testing/taskFixture.js`
- Docs: `docs/design/dashboard-v7/README.md`, `CHANGELOG.md`,
  `docs/sprints/backlog.md`

## Migrations

- none

## Risks

- A description written with soft-wrapped lines (one sentence split over
  lines) now shows those breaks. Agents and the manager write one line
  per paragraph or item.

## Tests

- Frontend: 478 passed; `npm run lint`, `npm run build` clean
- Python: unchanged code; full suite run before merging
- Looked at ASS-16's Overview, Checks and the gate step on a copy of the
  live database.

## Acceptance criteria satisfied

- No checks summary on Overview; every detail shown; no "Times at each
  step".
- The same words for a gate, a review and a merge on every tab.

## Follow-ups

- The test count, which also replaces the lone "OK" in a test's detail.
