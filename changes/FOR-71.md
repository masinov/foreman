# A step moves up its role's models only after failures of its own work, as each role sets

- A role's models, cheapest first (`[agent] model_ladder`), and how many failures on one model before the next (`escalate_after`, at least 1, default 2) are set in the role's TOML and in the role editor (Settings › Roles, for the workspace and for a project's own). One model never moves up; none is the project's default.
- A step moves up only after failures of its own work: its run ended without a result, the review sent it back, or the tests failed after it. Not a restart, a Stop, a conflict send-back, a usage wait or an infrastructure error. The count is kept on the task per step and model.
- Every move up is a line in the task's Activity with its reason ("Develop moves up to claude-opus-5-5 · the review sent it back twice"); the step's details say which model ran and why.
- After `escalate_after` failures on the last model, the task blocks for a person ("Develop failed twice on claude-opus-5-5, the last of its models.").
- A model pinned for a step never moves up. The task page's overrides and `foreman task override --ladder-start MODEL` name the model a task starts on, by the model.
- `foreman outcomes` shows, per role and model, the failures of its own work, the send-backs and the moves up beside the runs and the cost.
