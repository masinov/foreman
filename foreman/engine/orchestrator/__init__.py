"""Task orchestration for Foreman workflow execution.

``ForemanOrchestrator`` is the engine's entry point, in one part per concern:

- ``base``: what it is built from, the project's definitions, recovery,
  evidence and the engine's own events,
- ``passes``: a project pass (the next task, approved merges, the commands
  read between tasks),
- ``tasks``: one task under a lease, and blocking, releasing or stopping one,
- ``gates``: a person's decision at a human gate, and running on from it.
"""

from __future__ import annotations

from .gates import HumanGateResume
from .passes import ProjectPass
from .tasks import TaskRun

__all__ = ["ForemanOrchestrator"]


class ForemanOrchestrator(
    ProjectPass,
    TaskRun,
    HumanGateResume,
):
    """Run a project's tasks through their workflows."""
