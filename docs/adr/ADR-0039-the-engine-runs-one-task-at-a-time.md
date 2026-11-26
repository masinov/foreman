# ADR-0039: The Engine Runs One Task at a Time

- **Status:** accepted (owner, 2026-11-24: "Either sequential or parallel but
  this faux parallelism makes no sense", then "Yes, do it by hand")
- **Date:** 2026-11-24
- **Sprint:** 62
- **Amends:** ADR-0011 (its 2026-11-15 amendment is withdrawn)
- **Amended by:** ADR-0043 (2026-11-26): a task a user paused or blocked does
  not hold the queue, and a request to run a task does not pass a hold

## Context

A project's engine runs one step at a time: one agent or one built-in step,
of one task. But it did not run one task at a time.

- **It moved on at a gate.** When a task stopped at a gate for a user's
  decision (merge approval), the engine parked it and started the next task
  from the default branch as it was at that moment. Several tasks were then
  under way at once, their branches overlapping in time, with only one ever
  being worked on.
- **It had a side door.** While an agent step ran, the engine looked every
  ten seconds for other tasks whose merge a user had approved and merged
  them inside that step (ADR-0011 amendment of 2026-11-15). A built-in step
  such as the tests made no such checks, so the same approval was carried
  out at once or waited ten minutes, depending on what was running.

Sprint 62 (2026-11-24) showed the cost:
- **Collisions:** every task that merged second collided with the one
  before it on the files both edit (`CHANGELOG.md`,
  `docs/sprints/current.md`). FOR-52's change took one minute; the task
  stayed open for more than two hours, through four develop passes, four
  test runs and three approvals.
- **Waiting:** a task sent back after its approval waited behind the next
  task's whole cycle.
- **A puzzle for the owner:** they could not tell what the engine was doing.

It was neither sequential nor parallel. The spec's main loop (§6.1) already
says "at most one task can be paused (sequential execution)". The code had
drifted from it.

## Decision

1. **A task waiting for a decision holds the queue.** While a task of the
   active sprint is stopped at a gate (a `_builtin:human_gate` step), the
   engine starts no other task. The pass ends with the stop reason
   `waiting_for_decision`, and a resident engine waits.
2. **The decided task comes first.** A decision is a database write, which
   wakes a resident engine. Its next pass takes the decided task first,
   since a task part-way through is always chosen before a new one, and
   carries it through its merge and done steps. Only then does the next task
   start, from the default branch that the merge left.
3. **The side door is removed:** `_carry_out_approved_merges`, the
   `only_roles` option of a task run, `MERGE_STEP_ROLES` and
   `APPROVED_MERGE_CHECK_SECONDS`. Nothing else runs while a decision is
   pending, so nothing waits behind another task's step for it.
4. **A task blocked by a failure does not hold the queue.** A loop limit, a
   failed step or a branch violation needs fixing, not a decision, and may
   wait for days. The engine goes on with the next task, as before. That
   task's branch can fall behind and collide when it is unblocked. That is
   the exception, and the workflow already handles it.
5. **A request to run a named task** (`foreman engine run-task`, "Run next")
   still runs that task, even while another waits for a decision. A user
   asked for it.

## Consequences

- **No collisions between tasks run by the engine.** Each task's branch
  starts after the previous task merged, so tasks no longer collide with
  each other on shared files. A user's own merges to the default branch,
  made while a task is under way, still can.
- **The engine waits while a user decides.** On 2026-11-24 approvals came
  within seconds to a few minutes. A project whose merges Foreman approves
  (`merge_approval = auto`) never stops at that gate, and does not wait.
- **Several tasks at once stays a separate decision.** Several agents
  working together, each in its own working copy, would be real
  parallelism, with its own rule for shared files (owner direction 7). It is
  recorded in the backlog.
- **The run result changes.** A one-shot `foreman run` that stops at a gate
  now reports `waiting_for_decision`, not `blocked`.
