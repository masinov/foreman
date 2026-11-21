"""What a sprint's activity lists, and which of it is a problem.

A sprint's activity is what happened to each of its tasks: each run that did
work (an agent's step, tests, a review, a person's decision at a gate, a
merge, a block) and what a person did to a task by hand (closed it,
cancelled it, unblocked it). Left out: runs that only keep a record (a task
filed or cancelled, the step that marks a task done, the engine's own
records) and gate runs a person did not decide (Foreman approving by the
project's setting, or a gate asking a person, whose answer is listed).

A problem is what sent a task back or stopped it: a send-back, a failure, a
merge conflict, a block, a cancel.
"""

from __future__ import annotations

#: Roles whose runs only keep a record.
RECORD_ROLES: frozenset[str] = frozenset({"_builtin:mark_done"})

#: Steps whose runs are the engine's own records (a sprint became ready or
#: was resolved, the engine shut down), kept on whichever task was at hand.
RECORD_STEPS: frozenset[str] = frozenset({"orchestrator"})

#: Outcomes of runs that only keep a record: a task filed or cancelled (the
#: cancel is listed from the person's own event, with who and why).
RECORD_OUTCOMES: frozenset[str] = frozenset({"file", "created", "cancel"})

#: The gate role: listed only when a person decided at it.
GATE_ROLE = "_builtin:human_gate"

#: What a person does to a task by hand, as the sprint's activity calls it.
HAND_EVENTS: dict[str, str] = {
    "human.task_completed": "closed",
    "human.task_cancelled": "cancelled",
    "human.task_unblocked": "unblocked",
}

#: Outcomes that send a task back or stop it.
PROBLEM_OUTCOMES: frozenset[str] = frozenset(
    {"steer", "deny", "denied", "changes_requested", "request_changes",
     "error", "failure", "failed", "conflict", "blocked", "cancelled"}
)

#: Run statuses that mean the run did not finish.
PROBLEM_STATUSES: frozenset[str] = frozenset({"failed", "killed"})
