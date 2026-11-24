# ADR-0038: A Step's Repository Facts Are Recorded When It Ends

- **Status:** accepted (the owner approved the mockup on 2026-11-24)
- **Date:** 2026-11-24
- **Sprint:** 62, slice 4

## Context

A step's panel on a task's Activity tab should say what the step did to the
repository: the files and lines an agent changed, and for a merge what it
brought in. Git can answer that today, but a branch is rebased, deleted or
merged later, and the answer would change or be lost. A page that asked git
when it was read would also make a read depend on a repository.

## Decision

- **Facts, recorded when the step ends (ADR-0018).** The engine reads git once,
  when the step ends, and stores the answer on the step's events. Nothing that
  shows it asks git. Git is read in `foreman/repo/git.py`, turned into
  payloads in `foreman/engine/repo_facts.py`, read back in
  `foreman/services/task_reads.py` (the run output's `session`, `changes` and
  `merge`), and drawn by the Activity tab.
- **Agent step:** the task branch's head is taken just after any branch sync
  and again when the run completes. When they differ, the run records
  `engine.step_changes` (`from_sha`, `to_sha`, `files` capped at 200 with
  `files_total`, `added`, `removed`, and `from_default_branch`, whether
  `from_sha` is on the default branch). Main's changes brought in by a sync
  are before the first head, so they are not the agent's.
- **Merge:** `engine.merge` gains `target_before`, `commits` (oldest first,
  capped at 50, with `commits_total`) and `changes` (`files`, `files_total`,
  `added`, `removed`, from `target_before` to the merge commit).
- **A failed git read leaves its field out.** It never fails the step.
- **Older steps** have no such events and show no such rows.
- **Session** is not recorded again: two runs with the same stored
  `session_id` are one session, read from the runs.
- **What a step is counted against** is read from the runs, not git: the
  attempt whose `commit_sha` is `from_sha`, else the default branch when
  `from_default_branch`, else the sha alone.

## Consequences

- The Changes tab and these facts can differ: the Changes tab compares the
  branch with the default branch as it is now; these are what one step did.
- The Changes tab cannot be opened at a file, so a changed file's path is text.
- Amends spec 2.5's event list (2026-11-24).
