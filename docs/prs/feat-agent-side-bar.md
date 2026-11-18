# PR Summary: feat/agent-side-bar

## Summary

- On a task page the side bar is the conversation with the task's agents,
  where the manager's was (ADR-0029, asked for by the owner).

## Scope

- Dashboard frontend only. No API, engine or schema change.

## Files changed

- `frontend/src/pages/task/AgentPanel.jsx` (new), `RunStory.jsx` (new, moved
  out of `ActivityTab.jsx`), `useTaskPulse.js` (new), `TellAgent.jsx`,
  `ActivityTab.jsx`, `TaskActions.jsx`
- `frontend/src/app/App.jsx`, `ManagerToggle.jsx`, `Shell.jsx`, `manager.js`,
  `useLiveData.js`, `projectEvents.js` (new)
- `frontend/src/styles/shell.css`, `manager.css`, `task.css`
- tests: `TaskPage.test.jsx`, `ManagerPanel.test.jsx`, `Planning.test.jsx`
- `docs/adr/ADR-0029-...md`, `docs/adr/README.md`, `docs/adr/ADR-0011-...md`,
  `docs/design/dashboard-v7/README.md`, `docs/ARCHITECTURE.md`,
  `docs/STATUS.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- The manager can no longer be asked about a task from the task's page.
- A step with very long output is read again once a second while it prints;
  the read is capped at 200,000 characters on the server.

## Tests

- Frontend lint, 428 tests, build. Python untouched.
- In a browser on a copy of the live database: the bar closed and opened on
  a task waiting for approval; a finished task (steps, no box); a task with
  a running step faked in the copy opened the bar by itself, and a real
  develop run replayed into it event by event was followed to its last line
  with the page left alone; a note saved for the next step appeared once, in
  place; the step's end changed the header and the box; Split landed on the
  backlog with the manager asked; a narrow window did not open the bar by
  itself; the bar's last button measured inside the window at the top of the
  page and scrolled, for the manager too.
- Not seen: a real agent interrupted from the bar.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- One place to see and steer a task's agent, where the output is in view.

## Follow-ups

- Whether a person's note should reach every later step (owner undecided).
