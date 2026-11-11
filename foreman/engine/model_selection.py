"""Which model an agent step runs on, and which rule chose it."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Project, Task
from ..roles import RoleDefinition
from .limits import resolve_project_settings


# Complexity → ladder start index when no explicit ladder_start override is set.
_COMPLEXITY_LADDER_START: dict[str, int] = {"small": 0, "medium": 0, "large": 1}


@dataclass(slots=True)
class ModelSelection:
    """The model chosen for one agent step plus the rule that chose it."""

    model: str | None
    source: str  # "override" | "ladder" | "role" | "project_default"


def resolve_step_model_selection(
    *,
    task: Task,
    role: RoleDefinition,
    project: Project,
    step_id: str,
    visit_count: int,
) -> ModelSelection:
    """Resolve the model for one workflow step, recording the deciding rule.

    Precedence (see review.md Phase 3.3):

    1. a per-task override for this step. The ladder still escalates above an
       override that itself appears in the role ladder (resume from its index);
       an override absent from the ladder is pinned for every visit.
    2. the role ``model_ladder`` indexed by ``ladder_start + visit_count - 1``,
       where ``ladder_start`` comes from the task override, else a complexity
       map, else 0.
    3. the role's single ``model``.
    4. the project ``default_model`` setting.
    5. ``None`` (harness default).
    """

    overrides = task.executor_overrides or {}
    ladder = tuple(role.agent.model_ladder)
    step_visit_index = max(visit_count - 1, 0)

    override_model = None
    models_map = overrides.get("models")
    if isinstance(models_map, dict):
        override_model = models_map.get(step_id)

    if override_model:
        if ladder and override_model in ladder:
            base_index = ladder.index(override_model)
            index = min(base_index + step_visit_index, len(ladder) - 1)
            chosen = ladder[index]
            source = "override" if index == base_index else "ladder"
            return ModelSelection(model=chosen, source=source)
        # Pinned deliberately by the manager; keep it for every visit.
        return ModelSelection(model=str(override_model), source="override")

    if ladder:
        ladder_start = overrides.get("ladder_start")
        if not isinstance(ladder_start, int) or isinstance(ladder_start, bool):
            ladder_start = _COMPLEXITY_LADDER_START.get(task.complexity or "", 0)
        index = min(ladder_start + step_visit_index, len(ladder) - 1)
        index = max(index, 0)
        return ModelSelection(model=ladder[index], source="ladder")

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
    visit_count: int,
) -> str | None:
    """Return only the resolved model id for one step (see ``ModelSelection``)."""

    return resolve_step_model_selection(
        task=task,
        role=role,
        project=project,
        step_id=step_id,
        visit_count=visit_count,
    ).model
