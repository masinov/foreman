# ADR-0026: A Branch Is Current Before It Is Merged

- Status: accepted
- Date: 2026-11-16
- Deciders: engine team

## Context

The merge step merged the task branch into the default branch in the
integration worktree without asking whether the branch contained the default
branch's head. The supervised run of 2026-11-16 showed the consequence: the
recorded test run, the review and the merge approval were all about the
branch head, while what landed was a merge of that head with a newer default
branch. ADR-0018 ties evidence to the head commit; a merge that creates a new
tree no one tested breaks that.

## Decision

1. Before the completion guard and before `merge_branch`, `_builtin:merge`
   asks `git.commits_behind(repo, branch, default_branch)`. Above zero, it does
   not merge.
2. It brings the branch up to date with `git.sync_branch_with_base` in the
   task's own worktree, never in the operator's checkout or the integration
   worktree (ADR-0012), and returns the outcome `updated`. The
   `engine.branch_sync` event carries `step: "merge"`, the branch, the target,
   `commits_behind` and `mode: "merge_update"`.
3. If that merge conflicts, the outcome is `conflict` with the existing
   guidance, and the task goes to develop as before. A task with no worktree
   of its own that is behind is blocked rather than updated elsewhere.
4. The shipped workflows (`development`, `development_tiered`,
   `development_secure`) send `merge` + `completion:updated` to `test`. From
   there the ordinary path applies, so the reviewer and the merge approval see
   the new head.
5. A project's own workflow with no transition for `updated` at the merge step
   takes its fallback and blocks the task; the `workflow.no_transition` event
   names the step and the outcome.

## Consequences

- What is merged has been tested, reviewed and approved at the head that is
  merged, as long as the default branch does not move again in between.
  A branch that is behind again at the next merge is updated again.
- A branch that keeps falling behind costs another test, review and approval
  per round; `max_step_visits` bounds the loop.

## Out of scope

Rebasing; a shorter path that skips review after an update; testing a trial
merge in the integration worktree; the refresh before develop
(`branch_sync.py`); the dashboard's "behind" display.
