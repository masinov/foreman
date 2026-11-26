"""Which model an agent step runs on, and which rule chose it.

A role lists its models cheapest first (``model_ladder``). A step starts on
the first, or on the one a task names, and moves up to the next only after
``escalate_after`` failures of its own work on one model (ADR-0041). The
failures are counted on the task per step and model (``Task.step_failures``);
visits to the step are not what moves it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.models import Project, Task
from ..definitions.roles import RoleDefinition
from .limits import resolve_project_settings


@dataclass(slots=True)
class ModelSelection:
    """The model chosen for one agent step plus the rule that chose it."""

    model: str | None
    source: str  # "override" | "ladder" | "role" | "project_default"
    #: How many models up its ladder the step has moved from where it started.
    moves_up: int = 0
    #: The step has failed ``escalate_after`` times on the last of several
    #: models: there is no model left to move up to.
    exhausted: bool = False
    #: Failures of the step's own work on ``model`` so far.
    failures: int = 0


def ladder_start_index(task: Task, ladder: tuple[str, ...]) -> int:
    """Where on *ladder* the task's step starts.

    The task names a model of the ladder (``executor_overrides.ladder_start``;
    a number is still read as a position), else it is the first.
    """

    start = (task.executor_overrides or {}).get("ladder_start")
    if isinstance(start, str) and start in ladder:
        return ladder.index(start)
    if isinstance(start, int) and not isinstance(start, bool):
        return min(max(start, 0), len(ladder) - 1)
    if isinstance(start, str):
        # A model this role does not list: the role starts at its first.
        return 0
    return 0


def failures_on(task: Task, step_id: str, model: str | None) -> int:
    """How many failures of its own work *step_id* has had on *model*."""

    counts = (task.step_failures or {}).get(step_id) or {}
    return int(counts.get(model or "", 0) or 0)


def resolve_step_model_selection(
    *,
    task: Task,
    role: RoleDefinition,
    project: Project,
    step_id: str,
) -> ModelSelection:
    """Resolve the model for one workflow step, recording the deciding rule.

    Precedence:

    1. a model pinned for this step in the task's overrides
       (``executor_overrides.models``). It never moves up.
    2. the role ``model_ladder``: the step starts on the task's
       ``ladder_start`` model (else the first) and sits on each model until it
       has failed ``escalate_after`` times there. A role with one model never
       moves up.
    3. the role's single ``model``.
    4. the project ``default_model`` setting.
    5. ``None`` (harness default).
    """

    overrides = task.executor_overrides or {}
    ladder = tuple(role.agent.model_ladder)

    models_map = overrides.get("models")
    override_model = models_map.get(step_id) if isinstance(models_map, dict) else None
    if override_model:
        return ModelSelection(model=str(override_model), source="override")

    if ladder:
        start = ladder_start_index(task, ladder)
        last = len(ladder) - 1
        limit = role.agent.escalate_after
        index = start
        while index < last and failures_on(task, step_id, ladder[index]) >= limit:
            index += 1
        model = ladder[index]
        failures = failures_on(task, step_id, model)
        return ModelSelection(
            model=model,
            source="ladder",
            moves_up=index - start,
            exhausted=last > 0 and index == last and failures >= limit,
            failures=failures,
        )

    if role.agent.model:
        return ModelSelection(model=role.agent.model, source="role")

    default_model = resolve_project_settings(project).default_model
    if default_model:
        return ModelSelection(model=default_model, source="project_default")

    return ModelSelection(model=None, source="project_default")


def resolve_step_model(
    *,
    task: Task,
    role: RoleDefinition,
    project: Project,
    step_id: str,
) -> str | None:
    """Return only the resolved model id for one step (see ``ModelSelection``)."""

    return resolve_step_model_selection(
        task=task, role=role, project=project, step_id=step_id
    ).model
