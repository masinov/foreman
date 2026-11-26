# PR Summary: feat/holds-pause-and-block

## Summary

- Builds ADR-0043, parts 1 and 2 (part 3, the supervisor and a Workers
  view, is left for later). A user holds the work, not the engine:
  - **Pause** lets a running step finish, then nothing after it starts;
    **Stop** cuts the step (it runs again on Resume, the cut visit not
    counted); **Resume** lifts pauses. On a sprint or the workspace they
    act on each unfinished task there.
  - **Block** holds a task, a sprint or the workspace, with a reason, until
    Unblock where it was set. A blocked sprint is in Needs you.
  - A hold holds what comes after: a held task is parked before its next
    step (built-ins included), so it never merges or becomes done, and a
    blocked sprint or workspace is neither finished nor followed by the next
    sprint. A held task does not hold the queue; Run next does not pass a
    hold.
- The engine leaves the dashboard. A sprint's work has one status line
  (`services/work_status.py`), the same on the project's Work row, the
  sprint's Details, the top bar's work menu and the workspace's projects
  table. "Start worker" appears only when no worker runs a project with
  work. "Activate sprint" is "Start sprint"; starting a worker no longer
  starts a sprint.
- The engine's `pause`, `resume` and `stop_task` commands are retired
  (rejected with where they went).

## Scope

- Store: migration 31 (task pause columns, `holds`), `store/holds.py`
  (only these methods write a pause, so neither the engine nor a stale task
  object can lift one).
- Domain: `domain/holds.py` (`task_hold`), `TaskStoppedInterrupt`.
- Mutations: `mutations/holds.py`; Block of a running task waits for its
  step (`block_requested`); holds cleared on move, close, reopen, decline,
  sprint finish, cancel and delete; work joining an all-paused sprint joins
  paused.
- Engine: selection skips held tasks; the step loop parks a held task and
  applies a waiting Block; the command poll cuts a stopped step (agent steps
  every 5 s while printing, test runs every 2 s; merges never); sprint finish
  and advance check blocks; the resident engine drops its in-memory pause.
- Services and API: `services/holds.py`, `api/routers/holds.py`; task and
  sprint payloads carry `hold`, `step_running`, `waits_for`, `needed_by`,
  `block`, `work`; the workspace carries `block` and each project's `work`;
  approvals say when a held task goes on.
- CLI: `foreman pause|resume|block|unblock`; `foreman engine` keeps
  `status`, `run-task`, `shutdown`.
- Dashboard: Work row, work menu, sprint and workspace controls, task
  actions and stage words, Needs you row, Activity milestones and filters.
- Docs: ARCHITECTURE, MANUAL §23, README, design README and drawings 02 and
  05, CHANGELOG, STATUS, ADR-0011 and ADR-0039 pointers.

## Files changed

- Backend: `foreman/store/{migrations,holds,tasks,rows,sprints,overview,__init__}.py`,
  `foreman/domain/{holds,models,errors}.py`,
  `foreman/mutations/{holds,tasks,backlog,sprints,base,__init__}.py`,
  `foreman/engine/{holds,selection,sprints,agent_step,control}.py`,
  `foreman/engine/orchestrator/{passes,tasks,base}.py`,
  `foreman/engine/workflow_runner/{base,builtin_steps}.py`,
  `foreman/engine/builtins/{base,run_tests}.py`,
  `foreman/engine/resident/{base,commands,__init__}.py`,
  `foreman/services/{holds,work_status,views,tasks,sprints,workspace,engine,reports,__init__}.py`,
  `foreman/api/{app,schemas}.py`, `foreman/api/routers/{holds,engine,tasks}.py`,
  `foreman/cli/{holds,engine,parser}.py`, `foreman/definitions/gate_steps.py`.
- Frontend: `api/{holds,engine,tasks,workspace,milestones,needsYou}.js`,
  `pages/project/{WorkRow,ProjectLayout,ActivityTab}.jsx`,
  `pages/shared/{WorkStatus,WorkMenu,SprintHoldControls,StartWorker}.jsx`,
  `pages/shared/{workWords,useHoldAction,words,decisionWords,useProjectEngine}.js`,
  `pages/shared/{NeedsYou,milestones}.jsx`, `pages/sprint/{SprintHead.jsx,taskStage.js}`,
  `pages/task/{TaskActions,OverviewTab}.jsx`, `pages/task/{taskWords,runWords}.js`,
  `pages/workspace/{WorkspacePage,ProjectsTable,WorkspaceHoldControls}.jsx`,
  `app/App.jsx`, `ui/Button.jsx`, styles; removed `EngineRow.jsx`,
  `EngineMenu.jsx`, `engineControl.js`.
- Tests: `tests/test_holds.py` (new), and the engine, dashboard, CLI,
  workspace, proposal, mutation and serve tests rewritten for holds; the
  frontend tests likewise.

## Migrations

- 31: `tasks.paused_at`, `paused_by`, `pause_mode`, `block_requested`;
  table `holds`. Carries a standing engine pause or stop over as paused
  tasks of the active sprint, and "Stopped by …" tasks over as paused
  tasks. On the live database (2026-11-26) neither applies: no sprint is
  active and no task is "Stopped by".

## Risks

- A sprint's Pause, Stop and Resume act on each task; Resume on a sprint
  also resumes tasks paused one by one (by design: Block is the long park).
- A paused task's branch can fall behind while the sprint goes on; the
  refresh before its next step merges the default branch in.
- A paused task at a gate releases the queue, so the collisions ADR-0039
  removed are possible for that task, as for a blocked one.
- The workspace's own block is not a Needs you row (the ADR said it would
  be): it is lifted from "Unblock all" above the projects, which is where
  it shows.

## Tests

- `./venv/bin/python -m pytest tests -n auto -q`: see the merge note.
- `npm test` (vitest) and `npm run lint` in `frontend/`.
- `ruff check foreman tests scripts`, `lint-imports`,
  `scripts/validate_repo_memory.py`.
- Migration 31 run on a copy of the live database.
- Screenshots at 1440 and 390 of the workspace, project, sprint and task
  pages on a demo copy (paused, stopped-by-test, blocked sprint, waiting on
  a dependency); every page fits a phone's width.

## Screenshots or output examples

- Taken under `.review/` in the worktree (not committed).

## Acceptance criteria satisfied

- ADR-0043 §1–§8 as built, except part 3 (supervisor, Workers view) and the
  workspace block in Needs you (above).

## Follow-ups

- ADR-0043 part 3: a test that a worker killed hard leaves no agent process,
  then a supervisor (systemd user unit) and the Workers view.
- A daily spend limit that pauses a project's work, if wanted.
