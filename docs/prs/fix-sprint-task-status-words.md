# PR Summary: fix/sprint-task-status-words

## Summary

- The owner on 2026-11-24 found that "Running, develop" in the sprint's task
  list read oddly. The column reads like "Status", not "Stage". On the
  board the columns are the stages (Queued, Develop, Test, …). In the list
  the values are statuses.
- **The column and the Overview row are named "Status".**
- **A task's Status is what it is doing, then the step it is at, when it has
  one:**
  - "Running · Develop", "Paused · Develop", "Stopped · Develop";
  - "Blocked · Test", where it used to say only "Blocked";
  - the step is named as Activity and the board name it, not as the
    lowercased workflow id;
  - "Waiting for merge approval", "Queued", "Done" and "Cancelled" are
    unchanged.
- **The same step names elsewhere:** "Stopped at Test" in the decision box
  (beside "Last run: Test"), and "· at Test" in Needs you.

## Scope

- `frontend/src/pages/sprint/taskStage.js` (`stageOf`, new `atStep`).
- `frontend/src/pages/sprint/TaskList.jsx` and
  `frontend/src/pages/task/OverviewTab.jsx`: the header and the term.
- `frontend/src/pages/task/Decision.jsx` and
  `frontend/src/pages/shared/NeedsYou.jsx`: the step's name.

## Files changed

- The frontend files above, and their tests: `SprintPage`, `TaskPage`,
  `ProjectPage` and `WorkspacePage`.
- The design:
  - `docs/design/dashboard-v7/README.md`;
  - `04-sprint-list.html`;
  - `05-task-overview.html`.
- `CHANGELOG.md` and this note.

## Migrations

None.

## Risks

None found. The change is wording only, and the column widths are
unchanged ("Waiting for merge approval" is still the longest value).

## Tests

- `npm --prefix frontend test`: 492 pass. Lint and build are clean.
- No Python suite: the change is frontend only.

## Acceptance criteria

- The list's column and the Overview's row say "Status".
- A task under way or blocked says its step as Activity names it.

## Follow-ups

None.
