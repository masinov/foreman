# ADR-0036: A Finished Sprint Is Tagged

- **Status:** accepted
- **Date:** 2026-11-23
- **Sprint:** 62, slice 2

## Context

Spec 6.4 says a completed sprint is tagged
`checkpoint-YYYYMMDD-<sprint-slug>`. When `write_checkpoint_notes` is on, a
note listing its tasks is committed to `docs/checkpoints/<tag>.md` before
the tag, and `engine.checkpoint` is recorded.

Until now Foreman only marked the sprint completed. The setting was written
into new projects but never read.

A sprint is finished in two ways:
- by a user (`transition_sprint`: the dashboard, `foreman sprint complete`,
  a manager's proposal);
- by the engine, where the project lets Foreman finish sprints
  (`SprintFlow`, ADR-0025).

The spec does not say what happens when tagging fails, when a tag of that
name exists, or whether the tag is pushed.

## Decision

1. **One checkpoint for both ways** (`foreman/mutations/checkpoint.py`,
   `SprintCheckpoints`). `transition_sprint` calls it when a sprint becomes
   completed. A manager's proposal defers it until its changes are written,
   as it defers removing worktrees. `SprintFlow` calls it after
   `engine.sprint_completed`.
2. **The tag marks the default branch's head** and is annotated ("Sprint
   finished: <title>"). The name is the completion day (UTC) and the
   sprint's title in lower case, with every other character run made a
   hyphen, cut at 48 characters. A name already taken gets `-2`, `-3` and
   on. An existing tag is never moved.
3. **The note** is written and committed in the integration worktree, on
   the default branch, before the tag (spec 6.4).
   - It lists the goal, the tasks done and cancelled, and the follow-ups:
     the tasks agents filed (`engine.task_created`) while working on the
     sprint's tasks.
   - The project's checkout on the default branch is brought to the note's
     commit, as after a merge (ADR-0031).
4. **Pushed where merges are pushed.** When `merge_push_remote` names a
   remote, the default branch (if the note moved it) and then the tag are
   pushed, each recorded as `engine.push` or `engine.push_failed`.
5. **The sprint is finished whatever happens to its checkpoint.** A tag or
   note that cannot be made is recorded as `engine.checkpoint_failed`, with
   the reason. The sprint stays completed, and its page says "Not tagged:"
   and why.
6. **Once per completion.** `engine.checkpoint` carries the sprint's
   `completed_at`. A completion that already has one is not tagged again. A
   sprint reopened and finished again is a new completion and gets a new
   tag.
7. **Shown where the sprint is.**
   - The sprint's State says which commit the tag marks: "Finished 20 Nov
     at 6f79f4a", with the tag's name on hover. If tagging failed, it says
     "Finished 20 Nov, not tagged", with the reason on hover. The note is
     not shown: it repeats the page's goal and tasks for people who read
     the repository (owner, 2026-11-23, amended the same day from separate
     Tag and Note rows).
   - `GET /sprints/{id}` serves `checkpoint` (`tag`, `sha`, `note_path`,
     `problem`).
   - `foreman sprint complete` prints the tag and the note.
   - Settings › General › Advanced has "Checkpoint note: Write one / No
     note".

## Consequences

- A sprint can be found in git by its tag, and a project that asks for it
  keeps a record of each sprint in its own repository.
- The records are kept, like every sprint record today, on a run of the
  sprint's first task. Slice 3 stores sprint records as what they are.
- A sprint with no tasks has no task to keep its record on, so its
  checkpoint is not recorded (slice 3).
- With a push remote set, finishing a sprint from the dashboard waits for
  the push, as a merge does.
