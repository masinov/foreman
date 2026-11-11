# feat/guidance-delivery

## Summary

Sprint 56 slice 9 (review finding E13). Guidance written for a task was saved
as a `human.message` event that nothing read, while the UI said "sent". It is
now delivered to the task's next agent step and the UI says where it stands.

## Scope

- `foreman/guidance.py`: notes and their delivery state derived from events;
  `prompt_with_guidance` appends undelivered notes to an agent prompt.
- Orchestrator: every agent step collects the task's undelivered notes,
  appends them to the prompt, and emits `human.message_delivered`
  (`message_event_ids`, `role`, `step`) on the run that carries them. A note
  is delivered once.
- Service: `POST /api/tasks/{id}/messages` returns `status: recorded`,
  `will_deliver` and a sentence; the task payload has `guidance` with each
  note's state.
- UI: the composer button reads "Add guidance", the reply sentence is shown,
  the drawer has a Guidance section, the feed summarises the delivery event.

Two states only, recorded and delivered. "Acknowledged" is not claimed:
nothing in an agent's output proves it acted on a note.

## Files changed

`foreman/guidance.py` (new), `foreman/orchestrator.py`,
`foreman/dashboard_service.py`, `frontend/src/App.jsx`, `components.jsx`,
`format.js`, `styles.css`, rebuilt bundle, tests, changelog, sprint.

## Migrations

None.

## Risks

A note is read by whichever agent step comes next, which may be a reviewer.
The prompt tells that step to pass on work that is not its own. Guidance
written while a step is running waits for the next step; it does not
interrupt the running one.

## Tests

Full Python suite, `ruff check`, frontend `vitest` and build.

## Acceptance criteria satisfied

Slice 9 as written in `docs/sprints/current.md`.

## Follow-ups

Interrupting a running step to deliver guidance at once (needs the session
resume work in slice 10).
