# PR Summary: fix/audit-what-is-shown

## Summary

- First batch of fixes from the audit of every screen (sprint 60, slices 6
  and 7): things shown that were wrong, controls that did nothing, and
  sentences that explained the interface instead of being it.

## Scope

- A merged task: Changes and Checks are built from the commit it landed as.
- A gate decision made by a person reads "a person", not "engine".
- A finished task offers no guidance box and no overrides.
- A cancelled task has no "Not checked yet".
- "Approve plans" hint, "No tools", the shipped-definition dialog's line.
- Explanation strings removed from section headings and empty states.
- Not in this branch: acceptance criteria that are never judged, the board
  of a finished sprint, the unused worker-fleet role (questions for the
  owner).

## Files changed

- `foreman/git.py` (`landed_as`), `foreman/dashboard_task_reads.py`,
  `foreman/dashboard/task_models.py`
- `frontend/src/pages/{workspace,workspaceSettings,project,sprint,task,settings}/…`
- `tests/test_dashboard_task_reads.py`, frontend tests of the pages above
- `docs/ARCHITECTURE.md`, `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- The owner's rule on explanation strings overrides wording that came from
  `docs/design/dashboard-v7` (ADR-0020); the design files are not edited.
- A fast-forward merge has no single commit that holds the change; such a
  task shows the old empty comparison.

## Tests

- Three new tests in `tests/test_dashboard_task_reads.py` (merged, merged
  with the branch gone, not called behind); three new frontend tests.
- Both suites, ruff, lint, build.

## Screenshots or output examples

- Checked on a copy of the live database: FOR-40's Changes tab lists 51
  files "Merged into main as 86e882c"; its Checks say "Merged into main".

## Acceptance criteria satisfied

- A finished, merged task shows what it changed and nothing a person could
  type into in vain.

## Follow-ups

- The owner's answers to the audit's open questions.
