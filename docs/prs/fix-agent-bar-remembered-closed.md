# PR Summary: fix/agent-bar-remembered-closed

## Summary

- At the owner's request (2026-11-24: "Closed by default, only persist open
  if I have opened it, persist closed if I collapsed it"):
  - the Agent side bar on a task page is closed until the user opens it;
  - it no longer opens by itself on a task with a step in progress;
  - opened or closed, it stays that way on every task and on the next
    visit, remembered in the browser (`foreman.dashboard.agent.open`);
  - it is remembered apart from the manager's side bar. Opening the manager
    on a project page no longer opens the Agent bar on tasks.

## Scope

- `frontend/src/app/manager.js`: `useAgentOpen` beside `useManagerOpen`,
  both from one remembered-open hook.
- `frontend/src/app/App.jsx`: the per-task choice and the automatic opening
  are gone.

## Files changed

- The two files above.
- Tests: `frontend/src/pages/task/TaskPage.test.jsx` (the agent's side bar:
  closed until opened, remembered across visits, apart from the
  manager's) and `frontend/src/pages/manager/ManagerPanel.test.jsx`.
- Docs: ADR-0029 item 4 (amended), the design README, `docs/ARCHITECTURE.md`
  and `CHANGELOG.md`.

## Migrations

None. A browser that had the manager's bar open now finds the Agent bar
closed, until it is opened once.

## Risks

None found.

## Tests

- `npm --prefix frontend test`, lint and build.
- No Python suite: the change is frontend only.

## Acceptance criteria

- A first visit to a task page shows the Agent bar closed, with a step in
  progress or not.
- Opened, it is open on every task and after a reload. Closed, it stays
  closed.

## Follow-ups

None.
