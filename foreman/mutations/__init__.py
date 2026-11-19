"""Changes a person makes to projects, sprints and tasks, in one place.

The CLI and the dashboard both let a person accept, edit, block, unblock,
cancel and delete tasks, write guidance and decide gates, create, edit and
move sprints through their lifecycle, and file, decline, plan and unplan
backlog work (ADR-0021). Confirming a manager's proposal (ADR-0022) applies
the same operations. They used to
carry their own copies of the rules, which had drifted apart, and only some
dashboard actions left a trace. ``Mutations`` is the single implementation:
it checks the change is allowed, refuses what a running engine is in the
middle of, writes it, and records an audit event saying who did it and from
where.

Surfaces translate ``MutationError`` into their own error type and decide
how to present the result. Nothing here prints or knows about HTTP.

The rules are kept in a part per area, like the store's: ``projects``,
``tasks``, ``gates`` (a gate decision, a merge waiver), ``backlog``,
``sprints`` and ``decision_gates``, over ``base`` (who acts, the audit
event). No surface writes a project, sprint or task row itself; a test
holds that (``tests/test_layers.py``). ``Mutations`` puts them together; every part may call the
others' operations through it, as ``send_back`` unblocks a task.
"""

from __future__ import annotations

from .backlog import BacklogMutations
from .base import MutationError
from .decision_gates import DecisionGateMutations
from .gates import GateMutations
from .projects import ProjectMutations
from .sprints import SprintMutations
from .tasks import TaskMutations

__all__ = ["MutationError", "Mutations"]


class Mutations(
    ProjectMutations,
    TaskMutations,
    GateMutations,
    BacklogMutations,
    SprintMutations,
    DecisionGateMutations,
):
    """Operator changes to the tasks and sprints of one store.

    ``via`` names the surface (``"cli"``, ``"dashboard"``, ``"api"``,
    ``"engine"``) and ``actor`` who acted, when known; both are recorded on
    every audit event. ``role`` is the role recorded on the event and on the
    run it hangs from: ``"human"`` for a person, ``"api"`` for another
    system, an agent's role for work an agent files.

    ``proposal_id`` is set while a confirmed proposal is applied (ADR-0022):
    every audit event names it, and edits and gate decisions, which are
    otherwise recorded elsewhere or not at all, get an event of their own.

    ``defer_side_effects`` keeps work outside the database (removing a
    cancelled task's worktree) out of the write: it is queued on
    ``deferred`` for the caller to run once the transaction has committed,
    or to drop.
    """
