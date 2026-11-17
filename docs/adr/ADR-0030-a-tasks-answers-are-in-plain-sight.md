# ADR-0030: A task's answers are in plain sight, and More holds what is rare

- **Status:** accepted
- **Date:** 2026-11-17
- **Sprint:** 60

## Context

Two things the owner asked about on 2026-11-17, which turned out to be one
question: where the answers to "what do I do with this task" live.

1. In "Needs you", only an approve-merge row (and a proposed sprint order)
   had a button. A blocked task's row had none and showed the sprint's name,
   not why the task was blocked. No decision said so: design v7 drew only
   approve-merge rows, and the build gave a button to what was drawn. The
   reason offered for it afterwards (unblocking is one of several answers)
   is equally true of approving, and the task page already offered Unblock
   as a single press.
2. The task page's "More" menu held everything that was not the decision:
   Stop (the only way to stop a running task), Run next, Reopen (the only
   thing a finished task can have done to it), Mark done, Cancel, Block,
   Split, Delete, and Unblock a second and third time. The owner: a menu
   called More reads as "less important, additional actions", not as the
   place crucial ones were put together.

Found on the way: on a task the engine is running, Mark done, Cancel and
Delete were offered and the API refuses all three until the step stops.

## Decision

1. **An action that depends on the task's state is a button where that
   state is shown.** With a question open that is the decision (approve,
   unblock, accept, send back; unchanged). Without one it is a button beside
   the title: Run next (queued, or left part-way with no engine on it), Stop
   (the engine is running it), Reopen (done or cancelled).
2. **Ending a task by hand is the same in every open state, so it has one
   fixed button beside the title: Close.** Its dialog asks how the task
   ends, "Not needed" (cancel) or "Already done" (mark done, with the reason,
   which is the only trace that Foreman checked nothing). Neither is chosen
   for the person. Close is not offered while the engine is running the
   task, nor for a task in the backlog, which cannot be marked done and is
   declined from its decision.
3. **More holds what is rare:** Block, Split into smaller tasks, Delete, and
   Cancel for a backlog task. Unblock is no longer in it. Delete is not
   offered while the engine is running the task.
4. **A "Needs you" row carries the main button of its task's decision when
   the row can show what that decision weighs.** A merge shows tests, review
   and commit, and has Approve. A blocked task shows why it is blocked and
   the step it stopped at, and has Unblock. A proposed sprint order shows
   the order and has Accept and Reject. A plan has to be read and requests
   are several, so those rows link to where they are decided. The other
   answers to a row's question are one click away, on the task.
5. The blocked row's kind reads "Blocked" (the button says Unblock).
   `GET /needs-you` items of kind `unblock` carry `blocked`: `reason` and
   `step`.

## Consequences

- Design v7 draws Edit and More beside a task's title and no row button for
  a blocked task; it names the kind "unblock". Recorded in `docs/STATUS.md`.
- The order beside the title is Edit, the state's button, Close, More. Edit
  and More do not move between states.
- Block on a running task overlaps with Stop (Stop ends the step now, Block
  waits for the step to end). Left as it is; the owner has not decided.
- In the backlog, Decline (in the decision) and Cancel (in More) both say
  "not this". Left as it is.
