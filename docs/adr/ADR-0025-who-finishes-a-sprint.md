# ADR-0025: The engine finishes a sprint only in an autonomous project

- **Status:** accepted
- **Date:** 2026-11-16
- **Sprint:** 60b

## Context

Spec section 6.3 said a sprint completes when all its tasks are `done` or
`cancelled`, and the engine did that at every autonomy level. In the supervised
run of 2026-11-16 sprint 60 closed itself the moment its only filed task was
done, although more tasks were going to be filed into it. The person had to
open a new sprint for work that belonged in the first one. The finding is
recorded in `docs/sprints/current.md` ("Found in the supervised run") and
`docs/sprints/backlog.md` ("Found in the supervised run of sprint 60").

"All filed tasks are resolved" does not mean "the sprint is finished". Only a
person, or a policy that has handed the decision to Foreman, knows whether more
work is coming.

## Decision

Decided on 2026-11-16 by Claude, who drives the finish plan; the owner has
not yet confirmed it. The engine finishes a sprint only where the
project's autonomy level is autonomous.

1. **Autonomous.** A sprint whose tasks are all `done` or `cancelled` is
   completed by the engine and the next `planned` sprint is activated, as
   before.
2. **Directed and supervised.** Such a sprint stays `active`. The engine stops,
   says once that the sprint is ready to be finished, and waits. A person
   finishes it: dashboard "Finish sprint", `foreman sprint complete`, or a
   confirmed `finish_sprint` proposal.
3. **A task added to a resolved, still active sprint is picked up on the next
   pass** and run like any other.
4. **A blocked task prevents completion at every level**, whoever finishes the
   sprint: it is unblocked or cancelled first.
5. **Section 6.4 follows the sprint being finished.** Its checkpoint actions
   run when the sprint is completed, by the engine or by a person.

## Consequences

- In a directed or supervised project a sprint is never closed behind the
  person's back; work filed after the last task finished still lands in it.
- The engine is idle but not finished in such a project: a person's action is
  needed to move to the next sprint. The "ready to be finished" notice must be
  said once, not on every pass.
- Autonomous behaviour is unchanged.
- Not decided here: reopening a completed sprint, and the checkpoint actions of
  section 6.4 themselves.
- Implemented in `SprintFlow.resolve`. `engine.sprint_ready` is emitted once
  per resolution of a directed or supervised sprint, with the resolving task
  ids, and is the dedupe key for the `sprint_resolved` attention turn.

## Amendment, 2026-11-19: "Finish sprints" is its own setting

The owner asked that autonomy let the engine run on its own for merges and
for finishing sprints, each when the person wants it. Merges already had
that ("Approve merges: A person / Foreman"). Finishing a sprint depended on
the project's autonomy level, which no page and no command set, so it could
not be chosen.

The decision is now the project setting `sprint_completion`: `human` (the
default) or `auto`. The dashboard shows it as "Finish sprints: A person /
Foreman", beside "Approve merges". The engine finishes a resolved sprint
only when it is `auto`. The autonomy level no longer decides it; its
remaining meaning is "directed", where the manager may only recommend. A
sprint is not a task, so no task override or per-type rule applies to this
setting.
