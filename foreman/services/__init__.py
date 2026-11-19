"""What a person can read and do in Foreman, for every surface (ADR-0032).

The HTTP API and the CLI call the same services, so a list, a task or an
action means the same thing in both. A service reads and writes SQLite
(ADR-0002), changes state only through ``foreman.mutations``, holds no
process handles, returns plain dicts and raises the errors in ``errors``.

One service per area, each in its own module:

- ``projects``: projects, their settings and policy,
- ``engine``: a project's engine and the commands sent to it,
- ``sprints``: sprints, a sprint's board and activity,
- ``tasks``: a task's page and a person's actions on a task,
- ``backlog``: the backlog's reads and actions (ADR-0021),
- ``intake``: work filed by another system (ADR-0013),
- ``proposals``: the manager's proposals (ADR-0022),
- ``decision_gates``: questions raised for a person,
- ``worktrees``: a project's task worktrees,
- ``definitions``: roles and workflows (ADR-0024),
- ``workspace``: the reads across every project.

``task_reads`` (a task's changes, checks and runs), ``workflow_reads``,
``definition_forms`` and ``access`` are the reads and forms those use or the
API calls directly. ``Services`` puts the areas together over one store.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ..engine.control import ServeSpawner
from ..store import ForemanStore
from .backlog import BacklogService
from .decision_gates import DecisionGateService
from .definitions import DefinitionService
from .engine import EngineService
from .intake import IntakeService
from .projects import ProjectService
from .proposals import ProposalService
from .sprints import SprintService
from .tasks import TaskService
from .workspace import WorkspaceService
from .worktrees import WorktreeService

__all__ = ["Services"]


class Services:
    """Every area's service over one store, for one request or one command."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        now_factory: Callable[[], datetime] | None = None,
        serve_spawner: ServeSpawner | None = None,
    ) -> None:
        self.store = store
        clock = {"now_factory": now_factory}
        self.definitions = DefinitionService(store, **clock)
        self.projects = ProjectService(store, definitions=self.definitions, **clock)
        self.engine = EngineService(store, serve_spawner=serve_spawner, **clock)
        self.sprints = SprintService(store, **clock)
        self.tasks = TaskService(store, **clock)
        self.backlog = BacklogService(store, tasks=self.tasks, **clock)
        self.intake = IntakeService(store, tasks=self.tasks, **clock)
        self.proposals = ProposalService(store, **clock)
        self.decision_gates = DecisionGateService(store, **clock)
        self.worktrees = WorktreeService(store, **clock)
        self.workspace = WorkspaceService(store, **clock)
