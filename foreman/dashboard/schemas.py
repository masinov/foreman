"""The request bodies the API accepts, as types.

A route that names one of these gets a validated object, and a body with a
field of the wrong type is refused with a sentence naming the field. The
routes used to coerce with ``str(...)``, which turned ``null`` into the text
``"None"`` and a number into a title.

Fields that are required by the service (a title, a repository path) default
to empty here on purpose: the service owns the rule and its message, and
these models own only the types. Unknown fields are ignored, as before.

Settings, task-field and role updates stay free-form dicts: their keys are
open-ended and the service validates them one by one.
"""

from __future__ import annotations

from typing import Any, TypeVar

from fastapi import Request
from pydantic import BaseModel, ConfigDict, ValidationError

from ..dashboard_service import DashboardValidationError
from .context import read_json_body

_M = TypeVar("_M", bound=BaseModel)


class _Body(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class ProjectCreate(_Body):
    name: str = ""
    repo_path: str = ""
    workflow_id: str = "development"


class SprintMove(_Body):
    direction: str = ""


class SprintCreate(_Body):
    title: str = ""
    goal: str | None = None
    initial_tasks: list[dict[str, Any]] | None = None


class TaskCreate(_Body):
    title: str = ""
    task_type: str = "feature"
    acceptance_criteria: str | None = None
    description: str | None = None
    complexity: str | None = None
    depends_on: list[str] | None = None


class RequestedBy(_Body):
    """Who asked, for actions that are recorded against a person."""

    requested_by: str | None = None


class EngineCommandBody(RequestedBy):
    command: str = ""


class AgentStart(RequestedBy):
    task_id: str | None = None


class BacklogFile(_Body):
    """A task a person files into the backlog (ADR-0021)."""

    title: str = ""
    task_type: str = "feature"
    description: str | None = None
    acceptance_criteria: str | None = None
    priority: int = 0
    complexity: str | None = None
    #: File it already accepted: the person filing it is the one deciding.
    accept: bool = False
    requested_by: str | None = None


class TaskDecline(_Body):
    reason: str | None = None
    requested_by: str | None = None


class NewSprint(_Body):
    title: str = ""
    goal: str | None = None


class BacklogPlan(_Body):
    """Accepted backlog tasks, and the sprint, existing or new, to plan them into."""

    task_ids: list[str] = []
    sprint_id: str | None = None
    new_sprint: NewSprint | None = None
    requested_by: str | None = None


class TaskDenial(_Body):
    note: str | None = None


class TaskBlock(_Body):
    reason: str = ""
    requested_by: str | None = None


class TaskUnblock(_Body):
    #: Guidance for the next agent step, recorded with the unblock.
    note: str | None = None
    requested_by: str | None = None


class GuidanceNote(_Body):
    text: str = ""


class GateCreate(_Body):
    sprint_id: str = ""
    conflict_description: str = ""
    suggested_order: list[str] | None = None
    suggested_reason: str = ""


class GateResolution(_Body):
    resolution: str = ""
    resolved_by: str = "human"


def body_as(model: type[_M]):
    """Return a dependency that reads the JSON body and validates it as ``model``.

    The body is read by ``read_json_body``, so the JSON content type is still
    required (see ``foreman/dashboard_guard.py``).
    """

    async def dependency(request: Request) -> _M:
        data = await read_json_body(request)
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            first = exc.errors()[0]
            field = ".".join(str(part) for part in first["loc"]) or "body"
            raise DashboardValidationError(f"'{field}': {first['msg']}.") from exc

    return dependency


class TokenCreate(_Body):
    name: str = ""
    scopes: list[str] = []


class ChannelCreate(_Body):
    name: str = ""
    url: str = ""
    kind: str | None = None
    secret_env: str | None = None
