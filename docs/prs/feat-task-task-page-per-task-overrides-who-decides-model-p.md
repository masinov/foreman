# PR Summary: feat/task-task-page-per-task-overrides-who-decides-model-p

## Summary

- The task page's Overview has an "Overrides for this task" section: who
  decides at each human gate the workflow has (No override, A person decides,
  Foreman decides) and a model for each agent step (empty means no override).
- Save sends one `PATCH /tasks/{id}` with the whole `executor_overrides`
  object. Anything else the task carries (a ladder start, other policy
  decisions, models for other steps) is kept. Emptying a field clears it; a
  gate change is written to `policy` and removed from the older `gates` form
  so it cannot be shadowed.
- Details shows "(this task)" as the source once the task payload resolves the
  decision from the override. A refusal from the API is shown as its sentence.

## Scope

- Goal: set and clear per-task overrides from the task page.
- Constraints: ADR-0020, ADR-0019 error envelope; no backend change, the
  existing PATCH validates steps and values.
- Affected areas: `frontend/src/pages/task/Overrides.jsx` (new),
  `taskWords.js`, `OverviewTab.jsx`, `api/tasks.js`, `styles/task.css`,
  rebuilt `foreman/dashboard_frontend_dist`.

## Files changed

See the diff; frontend only plus docs.

## Migrations

None.

## Risks

- The model is free text, because the API offers no list of models. A wrong
  name is not refused by the PATCH; the runner reports it at the step.
- Look not checked in a browser (jsdom tests only).

## Tests

- `npm --prefix frontend test`: five new tests in `TaskPage.test.jsx`
  (offered rows, set with kept keys, clear incl. older `gates`, refusal,
  source "this task").

## Acceptance criteria satisfied

Set and clear who-decides and per-step model; Details shows "this task";
refusals shown; tested; bundle rebuilt.

## Follow-ups

- A list of known models from the API, so the field can be a choice.
