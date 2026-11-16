# PR Summary: feat/planning-requests

## Summary

- Planning is the manager's: "Plan this sprint" and "Split into smaller
  tasks", each a manager turn that ends in a proposal (ADR-0022 amendment).
  Agreed with the owner on 2026-11-16.

## Scope

- `foreman/planning.py`: the two requests, the check that a proposal does
  only what was asked, and confirmation by policy.
- Proposal operation `add_task` with `ref` and `waits_for`.
- `POST /projects/{id}/meta/message` takes `plan`; a manager turn takes
  instructions that are not stored and a hook that runs when it ends.
- Frontend: the two More-menu items with a dialog that says what will
  happen, the request handed to the manager's side bar, the card's rows for
  `add_task`, a card decided by policy shown as it now is.
- Not in this branch: removing the architect role and its workflow.

## Files changed

- `foreman/planning.py` (new), `foreman/proposals.py`, `foreman/meta_agent.py`,
  `foreman/dashboard/routers/meta.py`
- `frontend/src/app/managerRequests.js` (new), `app/App.jsx`, `api/manager.js`,
  `pages/manager/{useConversation.js,ManagerPanel.jsx,proposalWords.js}`,
  `pages/sprint/SprintHead.jsx`, `pages/task/TaskActions.jsx`
- `tests/test_planning.py`, `frontend/src/pages/manager/Planning.test.jsx` (new),
  `proposalWords.test.js`, `TaskPage.test.jsx`
- `docs/adr/ADR-0022-...md`, `docs/STATUS.md`, `docs/ARCHITECTURE.md`,
  `docs/sprints/current.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- With "Approve plans" set to Foreman, tasks enter a sprint without a person
  reading them. The check on what such a proposal may contain is strict, and
  the setting defaults to a person.
- The quality of a plan is the manager's. One real plan was read; it was
  good. One is not many.
- The manager chat is off on a network bind unless the dashboard is started
  with `--allow-remote-manager`; planning needs it on.

## Tests

- `tests/test_planning.py`, 22: the operation, the requests and their
  refusals, what Foreman may confirm, and a turn through the API with a
  faked agent under both policies.
- `Planning.test.jsx`, 3; `proposalWords.test.js` rows for `add_task`.
- One real planning turn on a database copy (39 tool calls, five tasks);
  the proposal it drafted was stored and confirmed with this code.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A sprint's goal becomes a proposal of tasks from one menu item; a task
  becomes a proposal of smaller tasks from another; the project's setting
  decides who confirms.

## Follow-ups

- Remove the architect role and `development_with_architect`.
- A terminal command for the two requests.
