# PR Summary: feat/manager-proposes-done-and-reopen

## Summary

- Sprint 59, slice 11. The manager can propose closing a task by hand,
  reopening one, and changing a task's size and dependencies.

## Scope

- Proposal kinds `complete_task {task_id, reason}` and `reopen_task
  {task_id}`, applied through `Mutations.complete_task` and `reopen_task`.
- `edit_task` in a proposal takes `complexity` and `depends_on_task_ids`
  (a list that may be empty), through the `Mutations.edit_task` extended in
  slice 10.
- The manager's operating contract lists them.
- Proposal card: "Mark done <task> by hand, without running its remaining
  steps" with "Why"; "Reopen <task> its steps start over"; "Change <task>
  its size and dependencies".
- ADR-0022: vocabulary table and an amendment.

## Files changed

- `foreman/proposals.py`, `foreman/meta_agent.py`
- `frontend/src/pages/manager/proposalWords.js`
- `tests/test_proposals.py`,
  `frontend/src/pages/manager/proposalWords.test.js`
- `docs/adr/ADR-0022-manager-proposes-person-confirms.md`,
  `docs/STATUS.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`

## Migrations

- none

## Risks

- A manager session begun before this change does not know the new kinds
  until its operating contract is sent again (a new session). It can still
  be told in conversation.
- `complexity` cannot be cleared through a proposal (it must be a size),
  only set.

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1399 tests, 5 skipped)
- `npm --prefix frontend run lint`, `test` (383 tests), `run build`
- Not run with a real manager turn; the route a proposal takes was checked
  with one in slice 8.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Each new kind is accepted when allowed and refused with the reason when
  not; confirming applies it as a person's action with the reason recorded.

## Follow-ups

- none
