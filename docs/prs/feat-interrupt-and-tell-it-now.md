# PR Summary: feat/interrupt-and-tell-it-now

## Summary

- A person can interrupt the agent step a task is running and have it read
  a note at once, from under that step's live output. Agreed with the owner.

## Scope

- Engine command `steer_task`: interrupt the step, leave the task where it
  was, carry on (ADR-0011 amendment). Migration 28.
- Guidance handed to a killed run is handed over again on restart.
- `POST /tasks/{id}/steer`; the "Tell the agent" box on the Activity tab.

## Files changed

- `foreman/models.py`, `foreman/migrations.py`, `foreman/serve.py`,
  `foreman/orchestrator.py`, `foreman/guidance.py`,
  `foreman/engine/workflow_runner.py`, `foreman/dashboard_service.py`,
  `foreman/dashboard/routers/tasks.py`
- `frontend/src/api/tasks.js`, `pages/task/ActivityTab.jsx`,
  `styles/task.css`, `TaskPage.test.jsx`
- `tests/test_serve.py`, `tests/test_dashboard_engine_commands_api.py`,
  `tests/test_engine_commands.py`
- `docs/adr/ADR-0011-...md`, `docs/STATUS.md`, `CHANGELOG.md`

## Migrations

- 28: `engine_commands` rebuilt so its CHECK allows `steer_task`.

## Risks

- Interrupting kills the agent mid-turn; work it had not written is redone.
- Whether a real agent continues its conversation after the restart was not
  yet seen when this was written (see Tests).

## Tests

- Engine: a step interrupted by `steer_task` leaves the task in progress at
  that step, uncounted, with no lease; the next pass runs the step with the
  guidance in its prompt. API: the note and the command, and each refusal.
  Frontend: the box, both buttons, the refusals.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A note can reach the agent that is working now, from where its work shows.

## Follow-ups

- A supervised run against a real agent.
- The same from a terminal.
