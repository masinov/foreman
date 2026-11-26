# The size label goes, and a step moves up its role's models only after failures of its own work

- Date: decided with the owner, 2026-11-25
- Moved from the hand-written `docs/sprints/backlog.md` on 2026-11-26 (FOR-70). The words below are as they were written; only a reference to another section is now a link.
- Built as FOR-71 and FOR-72 (sprint 65); the decision is kept here as it was taken.

- **Large tasks ran on the default model.** FOR-61, FOR-62 and FOR-64 were
  marked large, but no role has a model ladder, so `complexity` changed
  nothing. **Decided with the owner, 2026-11-25** (a sprint 64 candidate;
  the rule goes into ADR-0041 with it):
  - **The size label goes.** `complexity` only chose the ladder's first
    rung, and it is a guess ("a bit... ambiguous"). It leaves model choice,
    the task forms, the planner's output and the dashboard.
  - **A person or the manager pins a model per task and step** with the
    override that already exists (`executor_overrides.models`, the task
    page's overrides).
  - **A step moves up a rung only after failures of its own work:** the
    review sent it back with an S1 or S2 finding, the tests failed after
    it, or the agent could not finish. Not on an engine restart, a branch
    brought up to date after a conflict, a wait for usage limits, or an
    infrastructure error. Today every visit to the step counts
    (`workflow_runner/base.py`), so a conflict send-back climbs the
    ladder too.
  - **A role says how many failures on one rung before moving up**
    (`escalate_after`, default 2), so the cheaper model gets one more pass
    with the review's findings. Past the top rung, the task blocks for a
    person (later, ADR-0041's question to a person).
  - **Every move up is in the Activity with its reason**, and `foreman
    outcomes` compares cost and send-backs per model.
