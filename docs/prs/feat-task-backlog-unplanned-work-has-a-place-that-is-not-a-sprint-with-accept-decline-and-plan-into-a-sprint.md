# PR Summary: feat/task-backlog-unplanned-work-has-a-place-that-is-not-a-sprint-with-accept-decline-and-plan-into-a-sprint

## Summary

- Sprint 58 slice 3. Each project now has one backlog. Work goes there
  filed, gets accepted, and is then planned into a sprint. The engine runs
  only the active sprint and never a backlog task. The model is in
  `docs/adr/ADR-0021-backlog.md`.
- The backlog is a `sprints` row with the new `kind = 'backlog'`. Sprint
  reads filter `kind = 'sprint'`, so it is never listed, counted, activated
  or advanced into. A trigger keeps it `planned` no matter who writes. A
  backlog task's status is `triage` (filed), `todo` (accepted) or the new
  `declined`.
- File, accept, decline, plan (into a planned or active sprint, or a new
  planned sprint created in the same transaction) and unplan all live in
  `foreman/mutations.py`. Each one writes an audit event that names `via`
  and `by`.
- The intake queue is replaced. Intake files into the backlog, and
  migration 21 moves each `<project>-intake` queue's waiting work there.
- A task an agent creates with the `task_created` signal is filed into the
  backlog under the triage policy. It no longer joins the running sprint.
- New API routes under `/api/v1`. New CLI command `foreman backlog
  list|add|accept|decline|plan|unplan`.

## Scope

- Python only: models, migration, store, mutation service, engine signal
  handling, dashboard service and routes, CLI, tests, docs.
- No frontend files changed. The workflow runner and the lease code are
  untouched (`foreman/engine/selection.py` and `foreman/engine/sprints.py`
  are unchanged too; they already go through `get_active_sprint` and
  `get_next_planned_sprint`, which now exclude the backlog).
- Beyond the listed surfaces, this branch also adds `unplan` (CLI and
  `POST /tasks/{id}/unplan`). Without it, "move a not-started task back to
  the backlog" would have been an operation with no way to call it. It also
  adds `accept` on filing (`--accept`, `"accept": true`), so a person can
  file their own work already accepted. That is the design's "New task"
  under "Accepted, not planned".

## Files changed

- `docs/adr/ADR-0021-backlog.md` (new), `docs/adr/README.md`; ADR-0013 §4
  is marked superseded.
- `foreman/models.py`: `Sprint.kind`, `SPRINT_KINDS`, `BACKLOG_STATES`, the
  `declined` status.
- `foreman/migrations.py`: migration 21.
- `foreman/store/sprints.py`: kind-aware reads, `get_backlog`,
  `ensure_backlog`, `move_tasks_to_sprint` (all or none, guarded on each
  row's current sprint and status).
- `foreman/store/overview.py`: the milestone, active-sprint, paged-sprint
  and backlog-count reads use `kind` instead of the `-intake` id suffix.
  Adds `page_backlog_tasks`.
- `foreman/store/rows.py`: reads `kind`.
- `foreman/mutations.py`: `file_task`, `decline_task`, `plan_tasks`,
  `unplan_task`; refuses to transition, delete or block in the backlog;
  `role` on audit runs and events; unique audit ids.
- `foreman/backlog.py` (new): the one backlog read, shared by the API and
  `foreman backlog list --json`.
- `foreman/engine/signals.py`: `task_created` files through `file_task`.
- `foreman/dashboard_service.py`: intake goes through `file_task`, plus the
  backlog methods. Sprint endpoints answer 404 for the backlog. The task
  payload gains `sprint_id` and `in_backlog`.
- `foreman/dashboard/routers/backlog.py` (new), `foreman/dashboard/app.py`,
  `foreman/dashboard/schemas.py`.
- `foreman/cli/backlog.py` (new), `foreman/cli/parser.py`,
  `foreman/cli/tasks.py` (`task add --sprint <backlog>` is refused).
- Tests: `tests/test_backlog.py` (new), `tests/test_mutations.py`,
  `tests/test_migrations.py`, `tests/test_engine_selection.py`,
  `tests/test_engine_signals.py`, plus updates listed under Risks.
- Docs: `README.md`, `docs/ARCHITECTURE.md`, `docs/MANUAL.md`,
  `docs/STATUS.md`.

## Migrations

- Migration 21; the schema version goes from 20 to 21.
  - Adds `sprints.kind` (`sprint` or `backlog`) with a vocabulary trigger,
    a unique index of one backlog per project, and a trigger that refuses
    a backlog that is not `planned`.
  - Replaces the `tasks.status` vocabulary triggers so they accept
    `declined`.
  - For each project with a `<project>-intake` sprint: creates
    `<project>-backlog`, moves the queue's `triage` and `todo` tasks into
    it, deletes the queue if nothing is left in it and no decision gate
    points at it, and marks it completed if it is planned and holds only
    finished work. Started or finished intake tasks keep their sprint.
    Each step is guarded, so a replay changes nothing (tested).

## Risks

- **Behavior change.** Accepted intake work and agent follow-up tasks no
  longer run on their own. They wait in the backlog until a person plans
  them. The design asks for this, but a project that relied on `triage=auto`
  intake running unattended now needs someone to plan the work.
- **Tests changed because the behavior they pinned was replaced:**
  - `tests/test_intake.py`, `IntakeServiceTests`: three service-level
    tests asserted that the intake queue sprint was created active, stayed
    planned, and was reactivated. These are now three tests saying filed
    work goes to the backlog, leaves the active sprint alone, and never
    activates. Every intake endpoint (HTTP) test, the idempotency tests,
    the triage tests and `test_the_engine_never_selects_a_triaged_task`
    pass unmodified.
  - `tests/test_engine_signals.py`, `tests/test_output_contract.py`: agent
    follow-ups are now looked for in the backlog, not the active sprint.
  - `tests/test_dashboard_workspace_api.py`: the fixtures modelled the
    intake queue as a sprint with id `p1-intake`. They now use a real
    backlog row. The asserted numbers are unchanged.
  - `tests/test_store.py`: `task_counts` gains `declined: 0`.
  - `tests/test_cli_package.py` and `tests/test_dashboard_api.py`: the new
    command and router are registered.
- `task_counts` in API payloads gains a `declined` key (additive).
- `foreman task list` lists by sprint, so it no longer shows backlog tasks.
  `foreman backlog list` does.
- The shipped (pre-rebuild) frontend no longer sees the intake queue as a
  sprint, and it has no backlog screen yet. The rebuilt frontend will read
  `GET /projects/{id}/backlog`.
- Any new code that reads `sprints` directly must filter `kind = 'sprint'`.
  The database prevents a backlog from running, but nothing prevents it
  from being displayed as a sprint.

## Tests

- `./venv/bin/python -m unittest discover -s tests`: 1206 tests, OK (1
  skipped).
- `./venv/bin/ruff check .`: all checks passed.
- `./venv/bin/python scripts/validate_repo_memory.py`
- New coverage:
  - `tests/test_mutations.py::BacklogMutationsTests`: every operation and
    its audit event, plus the refusals (planning a filed task, planning
    into a completed or cancelled sprint, declining a planned task,
    unplanning started work, a stale task in a multi-task plan moving
    nothing, the backlog's own lifecycle).
  - `tests/test_migrations.py::BacklogMigrationTests`: a version-20
    database with four intake shapes, upgraded once and replayed.
  - `tests/test_engine_selection.py::BacklogIsNeverRunTests`.
  - `tests/test_engine_signals.py::AgentFiledTaskTriageTests`: triage
    `human`, `auto` and per-type rules.
  - `tests/test_backlog.py`: the API and the CLI.

## Screenshots or output examples

```
$ foreman backlog list foreman
Backlog: foreman | Foreman
Filed work is accepted by a person. Filed 1, accepted 2, declined 0.
Filed, not accepted (1)
  FOR-31 | fix | Check the lease fencing token on writes | filed by api:pagerduty | task-check-the-lease-fencing-token-on-writes
Accepted, not planned (2)
  FOR-29 | feature | JSON output on the remaining read commands | filed by alice | task-json-output-on-the-remaining-read-commands
  ...
```

`GET /api/v1/projects/{id}/backlog` returns `project_id`, `backlog_id`,
`triage`, `counts` (`filed`, `accepted`, `declined`), `tasks` (id, key,
title, state, status, type, priority, complexity, description, criteria,
created_by, created_at, source) and `total`.

## Acceptance criteria satisfied

- ADR-0021 states the model, what happens to the intake queue, and the
  migration. It is listed in `docs/adr/README.md`.
- A database created before this change opens with its intake queue's
  tasks in the backlog (`BacklogMigrationTests`). The schema version is
  bumped once, to 21.
- The engine never selects a backlog task and never treats the backlog as
  a sprint to run (`BacklogIsNeverRunTests`).
- Each operation (file, accept, decline, plan into an existing sprint,
  plan into a new sprint, move back) is covered in `tests/test_mutations.py`,
  with the refusals and the audit event.
- An agent-created follow-up task lands in the backlog and follows the
  triage policy (`AgentFiledTaskTriageTests`).
- The API endpoints and CLI commands exist and are tested. The intake
  endpoint's tests pass unmodified. Three service-level tests of the
  replaced queue activation were rewritten (see Risks).
- The whole Python suite and ruff pass. No frontend file changes. This
  file exists.

## Merge with main (frontend foundation)

- `main` gained the frontend foundation (sprint 58 slice 1). The only
  conflict was in `docs/STATUS.md`, in the "conflicts" list. Both sides were
  kept: main's notes on the partly rebuilt dashboard and the Needs you kinds,
  and this branch's "Resolved (ADR-0021)" entry in place of the open backlog
  question. The entry now also says the rebuilt frontend has no backlog
  screen yet.
- No code conflicted. The new frontend reads `task_counts` and the
  workspace payload by key, so the additive `declined` count does not affect
  it. After the merge, the Python suite (1206 tests), ruff, and
  `npm --prefix frontend test` (134 tests, including the committed-bundle
  check) all pass. No frontend file is changed by this branch.

## Follow-ups

- The design's "Filed by" column shows "carried from sprint N" for work
  moved back. The data exists (`human.task_unplanned` events carry
  `from_sprint_title`), but the backlog payload does not expose it yet.
- The manager (meta-agent) context lists sprints but not the backlog, so it
  cannot yet propose planning backlog work.
- Reopening a declined task is not supported.
- Identity: `requested_by` is recorded as given until a provider exists
  (design README, "Identity").
