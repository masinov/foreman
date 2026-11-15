# Current Sprint

## No sprint is open

Sprint 58 (frontend rebuild, Phase 4 of
`docs/reviews/2026-11-10-full-review-and-finish-plan.md`) closed on
2026-11-15: `docs/sprints/archive/sprint-58-frontend-rebuild.md`,
`docs/checkpoints/2026-11-15-sprint-58-closed.md`.

Phases 0 to 4 of the plan are done. What is left is Phase 5, "finish the
product" (two to three sprints), plus the items in `docs/sprints/backlog.md`.

### Proposed sprint 59 (not opened; the owner has not agreed its scope)

Goal: the engine can be left running again. Sprint 58 ended with the engine
stopped by the owner and a list of defects found while it ran.

| # | Slice | Source |
|---|-------|--------|
| 1 | Engine defects from sprint 58: a zero-turn corrective retry counts as a failure; a resumed session's cost is counted on every run; `run-task` waits for the next pass; merges wait behind another task's step; no push after a merge | `docs/sprints/backlog.md` |
| 2 | The reviewer must show what it read before it can approve | `docs/sprints/backlog.md` |
| 3 | Agent sandbox, first cut: per-role tool allowlists passed to the runner, read-only reviewers, the manager session limited to its read surface (FOR-42), a scrubbed environment | Phase 5 |
| 4 | Dashboard follow-ups small enough to ride along: run output in sentences, editing size, priority and dependencies after filing, Mark done and Reopen in the manager's proposals | `docs/sprints/backlog.md` |

Later Phase 5 sprints, in the plan's order: a planner step per task with a
protected acceptance test; pull requests through the remote; login, roles
and audit as a pluggable seam; manager chat through the runner;
notification seam, checkpoint tags and Codex; the database out of the
repository and a deployment guide.

A fresh agent should not start sprint 59 until this section is replaced by
an opened sprint.
