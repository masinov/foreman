# ADR-0037: A Record Belongs To A Run, A Sprint Or The Project

- **Status:** accepted (owner, 2026-11-24: "Go. I like it.")
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
engine commands that name no task (pause, resume, shutdown). They sit on 22
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
   - to the project: `engine.run_pruned`, `engine.event_pruned`,
     `engine.command_applied`/`engine.command_rejected` for a command that
     names no task, and (amended 2026-11-24) the worktree clean-ups:
     `engine.worktrees_reclaimed`, `engine.worktree_limit_exceeded` and
     `engine.worktree_reclaim_failed`. To stay under `max_live_worktrees`
     the engine removes other tasks' worktrees; that is about the
     project's worktrees, not about the task that needed the room, which
     the payload names as `for_task_id`. The live database held none, so
     the migration has nothing of these to move.

   What stays on a task's run is what is about that task: a recovered
   run, a block, a gate decision, a branch violation, a command that names
   the task.
3. **One writer.** `RunRecords` gains `emit_sprint_event` and
   `emit_project_event`, which save the event and offer it to the notifier
   as `emit_event` does. No run is made for them, and
   `select_project_system_task` is removed.
4. **Reads:**
   - A sprint's events are its tasks' events and its own records, in one
     order. This covers the sprint's event stream and the checkpoint the
     sprint page reads.
   - The project's records are read by project.
   - A task's Activity lists every record the engine kept on the task
     (amended 2026-11-24). It used to leave out those whose text did not
     quote the task's id, to hide records pinned to it from elsewhere.
     That also hid blocks the sprint's Activity listed, such as FOR-14's
     "Default branch 'main' HEAD changed". A task's Activity now lists at
     least what its sprint's Activity lists about it.
   - The sprint's Activity no longer leaves out runs at the `orchestrator`
     step. What is left there is about a task: a run recovered, a block
     before any step.

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
   - Its State then reads "Ready to finish", with "Every task is done or
     cancelled." on hover; the Tasks row beside it already says so. "Finish
     sprint" stays the action beside the title.
   - The state is read from the tasks, not from the `engine.sprint_ready`
     record, so it is true even when no engine is running.
8. **The project's Activity shows the tag.** Its rows say what happened in
   a short phrase, and the rest on hover (the owner's rule for activity).
   - A finished sprint's row says "Finished". On hover it says "3 tasks
     merged, tagged checkpoint-20261120-sprint-2 at 6f79f4a".
   - If tagging failed, the row says "Finished, not tagged" in the failure
     colour. On hover it says "3 tasks merged, not tagged:" and the reason.
   - A sprint finished before tagging existed keeps "3 tasks merged".
   - This stays one row, because finishing and tagging are one moment.
   - The tag is the one of that completion. A sprint reopened and finished
     again shows its new tag.

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

## Decided after (owner, 2026-11-24)

- **The sprint's Activity does not list the sprint's own records.** On
  every page the Activity tab lists what happened to what the level holds,
  and the level's own state is in its head:
  - the project's Activity lists its sprints and its engine;
  - a sprint's lists its tasks;
  - a task's lists its steps.

  A sprint's finish and tag are in its State and in the project's
  Activity.
