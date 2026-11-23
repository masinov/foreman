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

from dataclasses import dataclass

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

#: Who did a row, as the activity's By filter names them: ``user`` for what
#: a person did (by hand, at a gate, through a channel), ``foreman`` for the
#: engine's own steps (tests, a merge, a gate decided by setting), and an
#: agent's role id for its work.
BY_USER = "user"
BY_FOREMAN = "foreman"

#: Backends and roles through which a person acts.
USER_BACKENDS: frozenset[str] = frozenset({"human", "dashboard", "cli", "api"})
USER_ROLES: frozenset[str] = frozenset({"human"})

#: Backends of the engine's own steps, and the prefix of its built-in roles.
ENGINE_BACKENDS: frozenset[str] = frozenset({"builtin", "orchestrator", "engine"})
BUILTIN_PREFIX = "_builtin:"


@dataclass(frozen=True)
class WhoRule:
    """How a row's ``who`` is told: the words for a person and the engine, and what marks each."""

    user: str
    foreman: str
    user_backends: tuple[str, ...]
    user_roles: tuple[str, ...]
    engine_backends: tuple[str, ...]
    builtin_prefix: str


#: The rule the sprint's activity uses.
WHO = WhoRule(
    user=BY_USER,
    foreman=BY_FOREMAN,
    user_backends=tuple(sorted(USER_BACKENDS)),
    user_roles=tuple(sorted(USER_ROLES)),
    engine_backends=tuple(sorted(ENGINE_BACKENDS)),
    builtin_prefix=BUILTIN_PREFIX,
)


# A task's own steps (its Activity table): every run of the task but those
# that are not a step of it. The step that marks a task done only closes
# it after the merge; the engine's records (its role) are kept on
# whichever task and step were at hand, and only one that names the task
# (a step stopped or paused during it) is about it.

#: Roles whose runs are not one of the task's steps.
NOT_STEP_ROLES: frozenset[str] = frozenset({"_builtin:mark_done"})

#: The role of the engine's own records.
ENGINE_RECORD_ROLE = "_builtin:orchestrator"

#: Where a step that made no commit of its own says which commit it was
#: about: the event, and the field of it that holds the commit.
STEP_COMMIT_EVENTS: tuple[tuple[str, str], ...] = (
    ("engine.test_run", "head_sha"),
    ("engine.merge", "sha"),
)

#: Where a test step says how many tests ran: the event, and its field.
STEP_REPORT_EVENT: tuple[str, str] = ("engine.test_run", "report")
