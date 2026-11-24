# PR Summary: fix/sprint-62-loose-ends

## Summary

- **Sprint 62's loose ends, done once its queue was empty.** That way no
  queued task would collide on the shared files.
- **A review step reads as approved, not committed,** in a task's Steps
  table. On FOR-52 the merge step had brought the branch up to date, so the
  next review recorded a new head, and the table said "Committed 299cc5e".
  A step now counts as having committed only when it writes code (an
  agent's step that ended done), as the Activity tab already says it.
- **The finished sprints list's Spend title is set to the right** with its
  figures, as the active sprints' list is.
- **The docs held back while tasks ran:**
  - CHANGELOG lines for the engine's one task at a time, the reviewer's
    current evidence, and these fixes;
  - the sprint file, with slices 4 to 9 done through Foreman, slice 10 the
    engine fixes, and the sprint ready to finish;
  - the backlog, with what running sprint 62 through Foreman found, and the
    out-of-date "who finishes a sprint" line;
  - STATUS test counts.

## Scope

- `frontend/src/pages/task/taskWords.js` (`stepRows`)
- `frontend/src/pages/project/FinishedSprints.jsx`
- `CHANGELOG.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `docs/STATUS.md`

## Files changed

- The files above, and `frontend/src/pages/task/TaskPage.test.jsx`: a review
  whose recorded commit moved reads "Approved". The test fails without the
  fix.

## Migrations

None.

## Risks

None found.

## Tests

- `npm --prefix frontend test`, lint and build.
- `scripts/validate_repo_memory.py`.
- No Python change.

## Acceptance criteria

- No review step reads "Committed".
- Sprint 62's records are current.

## Follow-ups

- Finishing sprint 62, which tags the repository, is the owner's call.
