"""Which runs a sprint's activity shows, and which of them are problems.

A sprint's activity is each meaningful step of each of its tasks: the work
of an agent, tests, a review, a person's decision, a merge. Some runs only
keep a record (a task filed, the step that marks a task done) and are left
out; what they record is said elsewhere. A problem is a run that sent its
task back or stopped it: a send-back, a failure, a merge conflict, a block.
"""

from __future__ import annotations

#: Roles whose runs only keep a record.
RECORD_ROLES: frozenset[str] = frozenset({"_builtin:mark_done"})

#: Steps whose runs are the engine's own records (a sprint became ready or
#: was resolved, the engine shut down), kept on whichever task was at hand.
RECORD_STEPS: frozenset[str] = frozenset({"orchestrator"})

#: Outcomes of runs that only keep a record of the task being filed.
RECORD_OUTCOMES: frozenset[str] = frozenset({"file", "created"})

#: Outcomes that send a task back or stop it.
PROBLEM_OUTCOMES: frozenset[str] = frozenset(
    {"steer", "deny", "denied", "changes_requested", "request_changes",
     "error", "failure", "failed", "conflict", "blocked", "cancel"}
)

#: Run statuses that mean the run did not finish.
PROBLEM_STATUSES: frozenset[str] = frozenset({"failed", "killed"})
