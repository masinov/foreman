# What an operator can count on from the engine

Behaviour that changed what a person running Foreman sees, from sprint 56 and
from the step facts of sprint 62 (ADR-0038). Moved from `docs/STATUS.md` on
2026-11-26.

## What sprint 56 changed

- A cancelled task is never written to or merged by the engine; a blocker
  signal stops the workflow; a crash between steps costs one step.
- Completion evidence states facts tied to the branch head (tests, review,
  and the criteria an approving review covers) and has no score (ADR-0018).
  The criteria judge was removed on 2026-11-19.
- Guidance written for a task reaches its next agent step and shows as
  waiting or read.
- Retries continue the interrupted session; a quota stop needs the CLI's
  own notice or wording; a pause survives an engine restart; `foreman run`
  answers engine commands; a crash of `foreman serve` exits non-zero.
- Autonomous mode works inside a per-task worktree and degrades, not
  blocks, when the agent does not name its task.
- The database refuses statuses and types outside the vocabulary.

## Step facts from the repository (2026-11-24)

- A step's panel says what it did to the repository (ADR-0038, sprint 62
  slice 4). Only steps run after this change have Changed, Main before and
  Brought in; Session works for every run. A path in Changed is text: the
  Changes tab cannot be opened at a file.
