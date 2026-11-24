# ADR-0037: A Record Belongs To A Run, A Sprint Or The Project

- **Status:** proposed (for the owner to read before code is written)
- **Date:** 2026-11-24
- **Sprint:** 62, slice 3

## Context

Spec 2.5 gives every event a `run_id` and a `task_id`, both `NOT NULL`.
Most events are about a run of a task: an agent's step, a test run, a
merge. Some are not:
- **about a sprint:** it started, it finished, it is ready to finish (and
  the one attention turn that says so), its tag or why there is none, and
  the push and checkout that go with the tag;
- **about the project and its engine:** a command it applied or refused
  with no task named, old runs and events pruned.

To keep these, the engine makes up a run (role `_builtin:orchestrator`,
backend `orchestrator`) on whichever task is at hand. For a sprint that is its first
task. For the project it is the first task in progress or blocked, else the
active sprint's first task, else any task (`select_project_system_task`).
This has four effects:
- the record appears to belong to a task it has nothing to do with;
- every activity read has to know these runs are fake and leave them out
  (`RECORD_STEPS`, `ENGINE_RECORD_ROLE`);
- a sprint's records follow its first task if that task is moved to
  another sprint. The sprint then loses its tag, and the other sprint gains
  it;
- a project with no task cannot keep them at all, so they are dropped.

The live database has 23 records kept this way: 11 about a sprint, and 12
engine commands that name no task (pause, resume, shutdown). They sit on 25
made-up runs that hold nothing else.

## Decision

1. **Three owners.** An event belongs to exactly one of:
   - a run, as now (`run_id` and `task_id` set);
   - a sprint (`sprint_id` set, no run, no task);
   - the project (none of the three).

   `events` gains `sprint_id` (references `sprints`). `run_id` and
   `task_id` may be empty. A check holds the rule: `run_id` and `task_id`
   are both set or both empty, and an event with a run has no `sprint_id`.
   An event of a task's run does not carry the task's sprint, because a
   task can move between sprints.
2. **What moves:**
   - to the sprint: `engine.sprint_started`, `engine.sprint_completed`,
     `engine.sprint_ready`, the `sprint_resolved` attention turn (its
     payload gains `sprint_id`), `engine.checkpoint`,
     `engine.checkpoint_failed`, and the `engine.push`/`engine.push_failed`
     and `engine.checkout_updated`/`engine.checkout_behind` a checkpoint
     makes;
   - to the project: `engine.run_pruned`, `engine.event_pruned`, and
     `engine.command_applied`/`engine.command_rejected` for a command that
     names no task.

   What stays on a task's run is what is about that task: its worktree
   made or removed, a recovered run, a block, a gate decision, a branch
   violation. Those runs are steps of the task.
3. **One writer.** `RunRecords` gains `emit_sprint_event` and
   `emit_project_event`, which save the event and offer it to the notifier
   as `emit_event` does. No run is made for them, and
   `select_project_system_task` is removed.
4. **Reads:**
   - A sprint's events are its tasks' events and its own records, in one
     order. This covers the sprint's event stream and the checkpoint the
     sprint page reads.
   - The project's records are read by project.
   - `RECORD_STEPS` and the "engine's record role" exceptions in the
     activity reads go, as nothing is pinned to a task any more.
5. **Old records are moved by the migration that adds the column.** On the
   made-up runs (role `_builtin:orchestrator`, backend `orchestrator`):
   - an event of a sprint type takes the sprint from its payload's
     `sprint_id`, or for a `sprint_resolved` turn the sprint of the task it
     was pinned to;
   - a project type loses its run and task (a command counts only when its
     payload names no task);
   - a made-up run left with no events is deleted;
   - events keep their ids, so notifications already sent still point at
     them.

   The migration runs on the live database the next time Foreman starts.
6. **Kept and deleted with what owns them.**
   - Pruning removes old events of finished tasks, as now, and old project
     records.
   - It never removes a sprint's records. They are few, and the sprint
     page reads its tag from them.
   - Deleting a sprint deletes its records.
7. **The sprint says it is ready to finish.**
   - The trigger is the rule the engine uses: the sprint is active, has
     tasks, and every one is done or cancelled.
   - Its State then reads "Ready to finish, every task done or cancelled".
     "Finish sprint" stays the action beside the title.
   - The state is read from the tasks, not from the `engine.sprint_ready`
     record, so it is true even when no engine is running.
8. **The project's Activity shows the tag.** The "Finished" row for a
   sprint says "3 tasks merged, tagged at 6f79f4a", with the tag's name on
   hover. If tagging failed, it says "3 tasks merged, not tagged", with the
   reason on hover. A sprint finished before tagging existed keeps "3 tasks
   merged". This stays one row, because it is one moment.

## Consequences

- Spec 2.5 is amended: `run_id` and `task_id` may be empty, and `sprint_id`
  is added, with the rule in item 1.
- Every reader of `Event.run_id` and `Event.task_id` must allow them to be
  empty. Most already go through a task or a run and never see a sprint or
  project record. The ones that read all of a project's events
  (notifications, the manager's digest, the CLI's watch) are checked one by
  one.
- `events` is rebuilt to drop `NOT NULL` (SQLite 3.31 cannot alter a
  column). That copies 26,000 rows once.
- The sprint's first task no longer shows records that were never about
  it.

## Not decided here

- Whether the sprint's Activity tab lists its own records ("Finished,
  tagged …") beside its tasks' work. Today it lists task work only. The
  project's Activity is where the sprint's own changes are listed.
