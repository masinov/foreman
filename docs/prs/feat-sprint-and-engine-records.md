# PR Summary: feat/sprint-and-engine-records

## Summary

- Sprint 62, slice 3 (ADR-0037, which the owner read before the code was
  written: "Go. I like it.").
- **The change:** an event belongs to a run of a task, to a sprint, or to
  the project. Records that are not about a task are no longer pinned to
  one through a made-up run:
  - **the sprint's:** it started, finished, is ready to finish (and its
    `sprint_resolved` attention turn), its tag or why there is none, and
    what the checkpoint pushed and checked out;
  - **the project's:** a command that names no task, a pruning.
- **Old records:** schema 29 moves them. On the live database that is 11
  sprint records and 12 commands, and the 22 made-up runs that held only
  them are deleted.
- **What a user sees:**
  - the sprint's State says "Ready to finish" when an active sprint's
    every task is done or cancelled;
  - the project's Activity says a finished sprint's tag on hover, or
    "Finished, not tagged" and why;
  - a sprint keeps its tag when its first task moves to another sprint.

## Scope

- **Schema:** `foreman/store/migrations.py`, migration 29.
  - `events` is rebuilt: `run_id` and `task_id` may be empty, and
    `sprint_id` is added (cascading on the sprint's delete).
  - Two checks hold the rule: a run and its task are set together, and an
    event of a run has no sprint.
  - The old records are moved, and the made-up runs left empty are
    deleted.
- **Model and store:**
  - `foreman/domain/models.py`: `Event.sprint_id`, `FINISHED_TASK_STATUSES`,
    `sprint_ready_to_finish`;
  - `foreman/store/{rows,events,sprints,overview}.py`. A sprint's events
    are its tasks' and its own, in one order with cursors. Pruning keeps a
    sprint's own records. Deleting a sprint deletes them. A finished
    sprint's milestone carries its `checkpoint`.
- **Writer:** `foreman/history/records.py` gains `emit_sprint_event`,
  `emit_project_event` and `emit_sprint_attention`, and
  `select_project_system_task` is removed.
- **Callers:** `foreman/engine/sprints.py`, `foreman/mutations/checkpoint.py`,
  `foreman/engine/retention.py`,
  `foreman/engine/orchestrator/base.py` (`record_engine_event`).
- **Reads:**
  - `foreman/services/sprints.py`: `ready_to_finish`;
  - `foreman/services/workspace.py`: the milestone's `checkpoint`;
  - `foreman/services/{base,reports}.py`: `sprint_id` on an event;
  - `foreman/domain/outcome_numbers.py`: skips events of no task.
- **Frontend:** `pages/sprint/SprintHead.jsx` (State) and
  `pages/shared/milestones.jsx` (the Finished row).

## Files changed

- Code as above, with `foreman/domain/activity.py`,
  `foreman/notifications/delivery.py` and `foreman/engine/task_worktrees.py`
  (comments only).
- Tests:
  - `tests/test_sprint_and_project_records.py` (new, 13 tests);
  - `frontend/src/pages/sprint/SprintPage.test.jsx`;
  - `frontend/src/pages/project/ProjectPage.test.jsx`.
- Docs:
  - ADR-0037 and `docs/adr/README.md`;
  - spec 2.5 (amended);
  - `docs/ARCHITECTURE.md`, `docs/MANUAL.md`, the design README;
  - `CHANGELOG.md`, `docs/STATUS.md`;
  - `docs/sprints/current.md`, `docs/sprints/backlog.md`.

## Migrations

- **Migration 29:**
  - rebuilds `events` (26,010 rows on the live database, about 3 s);
  - moves the records pinned to a task;
  - deletes the made-up runs left empty.
- **Checked on a copy of the live database:**
  - 11 sprint records and 12 project records moved;
  - runs went from 573 to 551;
  - `PRAGMA foreign_key_check` is clean.
- It runs on the live database the next time Foreman starts.

## Risks

- **Readers that assume every event has a task or a run.** The readers of
  all a project's events were checked: notifications, the manager's
  context, the project stream, outcome numbers and pulled tasks. Every
  other reader goes through a task or a run, so it never sees these
  records.
- **Task Activity is unchanged.** It still hides the engine's own records
  about a task (its worktree made, for instance) unless they name the
  task.

## Tests

- `./venv/bin/python -m unittest discover -s tests`: 1635 pass.
- `npm --prefix frontend test`: 491 pass. Lint and build are clean.
- `./venv/bin/ruff check foreman tests` and `lint-imports`: clean.

## Acceptance criteria

- No sprint or project record is written on a made-up run of a task.
- Old records are moved, and their ids are kept.
- The sprint says it is ready to finish.
- The project's Activity shows the tag.

## Follow-ups

- Whether the sprint's own Activity tab lists its own records ("Finished,
  tagged …") beside its tasks' work (ADR-0037, not decided).
