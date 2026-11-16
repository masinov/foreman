# PR Summary: feat/backlog-pull

## Summary

- Acceptance gets something that uses it: Foreman starts accepted backlog
  work on its own, and a request is work it may not start (ADR-0028). Chosen
  by the owner ("B now") after both my reading and an independent agent's
  found that Accept changed nothing that ran.

## Scope

- Engine: autonomous task selection takes backlog work after planned work,
  within a limit per sprint; the placeholder mode and `signal.task_started`
  are removed.
- Rules: a person's filing is never a request; a person planning a request
  accepts it; Foreman by policy may not plan one.
- API: the backlog says what Foreman may do with it; a sprint says how many
  tasks Foreman started; "Needs you" counts requests in one line, only
  where accepting has an effect.
- Dashboard: backlog page, the backlog task's bar on its own page, the
  settings, the sprint header.
- Spec §6.2 revised.

## Files changed

- `foreman/engine/selection.py`, `foreman/mutations.py`, `foreman/context.py`,
  `foreman/engine/{signals,workflow_runner}.py`, `foreman/runner/signals.py`,
  `foreman/roles.py`, `foreman/backlog.py`, `foreman/dashboard_overview.py`,
  `foreman/dashboard_service.py`, `foreman/data/templates/agents_md.md.j2`
- `frontend/src/pages/project/BacklogTab.jsx`, `pages/task/{BacklogDecision,TaskLayout,Decision}.jsx`,
  `pages/settings/GeneralTab.jsx`, `pages/sprint/{SprintHead.jsx,taskStage.js}`,
  `pages/shared/NeedsYou.jsx`, `api/{backlog,needsYou}.js`, tests and fixtures
- `tests/test_engine_selection.py`, `tests/test_mutations.py`, `tests/test_backlog.py`,
  `tests/test_proposals.py`, `tests/test_dashboard_workspace_api.py`,
  `tests/test_output_contract.py`; `tests/test_autonomous_mode.py` removed
- `docs/specs/engine-design-v3.md`, `docs/adr/ADR-0028-...md`, `docs/adr/README.md`,
  `docs/MANUAL.md`, `docs/ARCHITECTURE.md`, `docs/STATUS.md`,
  `docs/sprints/backlog.md`, `CHANGELOG.md`

## Migrations

- none. `triage` and `todo` keep their meaning in the data.

## Risks

- A project that was in the old autonomous mode now takes backlog work
  instead of inventing tasks. The live project is directed.
- With the setting on and requests accepted by Foreman, filed work runs with
  nobody pressing anything, bounded only by the limit per sprint and the
  spend limits.
- An engine that is already running keeps the old behaviour until restarted.

## Tests

- Engine selection, 12 new; mutations, 3 new; API, 5 new; frontend, the
  backlog page rewritten and the task bar, settings and sprint header.
- On a copy of the live database: a request accepted and another planned
  from their own pages in a browser; then the engine's selection asked
  repeatedly with the planned work marked finished: it took the three
  accepted tasks in filing order, recorded each as `engine.task_pulled` by
  `foreman` via `policy`, left the unaccepted request, and the sprint
  reported 3 of 5. Not seen: a real engine pass running a pulled task
  through its workflow.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Every control here changes something: Accept lets Foreman start the task;
  Plan moves it into a sprint; Decline keeps a no; the setting makes the
  engine take backlog work.

## Follow-ups

- Listed in `docs/sprints/backlog.md`, "After ADR-0028".
