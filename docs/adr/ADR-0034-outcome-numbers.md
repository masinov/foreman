# ADR-0034: Outcome numbers

- **Status:** accepted
- **Date:** 2026-11-19
- **Sprint:** 61, slice 1 (roadmap stage 1)

## Context

The roadmap (2026-11-19) judges later work by numbers that do not exist yet:
how often an agent's work passes first time, what sends it back, how much a
person has to step in, and what a merged task costs. Routing work between
models and harnesses (stage 7) pays only if these numbers say so. `foreman
cost` gives spend per task and nothing about how the work went.

Everything needed is already recorded: the runs, and the `workflow.*`,
`engine.merge` and `human.*` events. No new state is needed.

## Decision

**Outcome numbers are computed from the records, on request, for a project
or one of its sprints.** `foreman outcomes <project> [--sprint ID] [--json]`
and `GET /api/v1/projects/{id}/outcomes?sprint=ID` return the same thing.
The computation is one pure function (`foreman/domain/outcome_numbers.py`)
over the tasks, runs and events the store hands it.

The terms, as computed:

- **A task counts** once it has started: it has a `workflow.step_started`
  event. A task filed and never run is not in the numbers.
- **Merged:** the engine merged it (an `engine.merge` event). A task closed
  by hand (`human.task_completed`) is counted as closed by hand, not merged.
- **The entry step** of a task is the step of its first `step_started`
  event. It is the step that builds the change in every shipped workflow,
  and this does not depend on step names.
- **A send-back** is a `workflow.transition` into the entry step from another
  step. Its cause is the role of the step it came from: `tests`
  (`_builtin:run_tests`), `review` (an agent role, named), `person` (a
  human gate's denial: a send-back with a note), `merge_conflict`
  (`_builtin:merge`, the branch conflicted with what had merged meanwhile),
  `other`.
- **Passed first time:** merged with no send-back. Because a merge conflict
  is usually caused by other work, a second figure leaves conflicts aside.
- **Decisions asked of a person:** each pause at a human gate
  (`workflow.paused`, reason `human_gate`), and how long it waited until it
  was decided (the next `workflow.resumed`). The median is shown.
- **Interventions not asked for:** what a person did to a task after it had
  started without a gate asking: a note (`human.message`), an edit, a block
  or unblock, a cancel, closing it by hand, reopening it, taking it out of
  the sprint. Planning, accepting and declining are not interventions.
- **Cost:** the runs' own cost (`runs.cost_usd`) and tokens kept apart
  (input, output, cache read, cache write), in total, per merged task, and
  spent on tasks that have not merged. Models are mostly used through a
  subscription, so the dollar figure is notional and the tokens are the
  measure (owner, 2026-11-10).
- **Time to merge:** from a task's first step to its merge, median. It
  includes time waiting for people, which is shown on its own.
- **By role and model:** for each agent role and model, its runs, failed
  runs, cost, tokens and time; how many send-backs it caused; and, for the
  role that ran the entry step, how many tasks it built that merged and how
  many of those passed first time. A task is credited to the model of its
  first entry-step run.

## Consequences

- The numbers cover what is kept. A project that prunes old runs or events
  (`run_retention_days`, `event_retention_days`) loses them from the
  numbers.
- Tasks run before an event existed are counted with what they have: a task
  merged before `engine.merge` was recorded does not count as merged.
- On the dashboard (owner, 2026-11-21): one line at the top of the project
  page (all sprints) and under the sprint page's summary (that sprint), with
  the per-role and per-model table behind "By role and model". The line is
  not shown while no task has started.
- No migration.

## Amendment 2026-11-21: what is still waiting

A decision still waits only when its pause is the task's last and the task
is open. A task closed or cancelled while paused at a gate was settled
without an answer there: its decision counts as asked, not as waiting, and
has no wait time. Before this, Foreman's project said one decision was
waiting while Needs you showed none (FOR-49, merged by hand at a gate).
