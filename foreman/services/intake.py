"""Work filed by another system with a project API token (ADR-0013).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlsplit

from ..domain.api_tokens import INTAKE_SCOPE
from ..domain.models import (
    ApiToken,
    Sprint,
)
from ..mutations import MutationError, Mutations
from ..store import ForemanStore
from .base import Service
from .errors import (
    UnauthenticatedError,
    NotFoundError,
    ForbiddenError,
    InvalidRequestError,
)
from .tasks import TaskService


class IntakeService(Service):
    """Work filed by another system with a project API token (ADR-0013)."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        now_factory: Callable[[], datetime] | None = None,
        tasks: TaskService,
    ) -> None:
        super().__init__(store, now_factory=now_factory)
        self.tasks = tasks

    def authenticate_intake(self, project_id: str, secret: str | None) -> ApiToken:
        """Resolve the API token allowed to file work on this project.

        401 when no live token matches the secret, 403 when a live token
        belongs to another project or lacks the ``intake`` scope. The two are
        kept apart deliberately: a caller that gets 403 knows its credential is
        real and its configuration is wrong.
        """

        presented = (secret or "").strip()
        if not presented:
            raise UnauthenticatedError(
                "Unauthorized: send an intake API token as `Authorization: Bearer <token>`."
            )
        token = self.store.find_api_token(presented)
        if token is None:
            raise UnauthenticatedError("Unauthorized: unknown or revoked API token.")
        if token.project_id != project_id:
            raise ForbiddenError(
                "Forbidden: this API token belongs to a different project."
            )
        if not token.has_scope(INTAKE_SCOPE):
            raise ForbiddenError(
                f"Forbidden: this API token does not carry the `{INTAKE_SCOPE}` scope."
            )
        return token

    def intake_task(
        self,
        project_id: str,
        *,
        token: ApiToken,
        title: str,
        description: str | None = None,
        acceptance_criteria: str | None = None,
        task_type: str = "fix",
        priority: int = 0,
        complexity: str | None = None,
        source: dict[str, Any] | None = None,
        sprint_id: str | None = None,
    ) -> dict[str, Any]:
        """File one task handed to Foreman by another system.

        Returns the task serialized as ``GET /api/tasks/{id}`` serializes it,
        plus ``created``: False means the same ``(system, external_ref)`` was
        already filed and this call changed nothing. The transport turns that
        flag into 201 or 200.
        """

        from ..domain.models import TASK_COMPLEXITIES, TASK_TYPES

        project = self._require_project(project_id)

        clean_title = (title or "").strip()
        if not clean_title:
            raise InvalidRequestError("Task title is required.")
        if task_type not in TASK_TYPES:
            raise InvalidRequestError(
                f"Unsupported task type: {task_type}. "
                f"Expected one of: {', '.join(TASK_TYPES)}."
            )
        if complexity is not None and complexity not in TASK_COMPLEXITIES:
            raise InvalidRequestError(
                f"Unsupported complexity: {complexity}. "
                f"Expected one of: {', '.join(TASK_COMPLEXITIES)}."
            )
        try:
            priority_value = int(priority or 0)
        except (TypeError, ValueError):
            raise InvalidRequestError("'priority' must be an integer.") from None

        source_fields = self._normalize_intake_source(source)

        # Idempotency: the same incident posted twice is one task. Only a
        # caller that names both its system and its own reference for the work
        # gets this guarantee -- without a key there is nothing to match on.
        if source_fields["system"] and source_fields["external_ref"]:
            existing = self.store.find_task_by_source(
                project_id=project_id,
                source_system=source_fields["system"],
                source_ref=source_fields["external_ref"],
            )
            if existing is not None:
                payload = self.tasks.get_task(existing.id)
                payload["created"] = False
                return payload

        sprint: Sprint | None = None
        if sprint_id:
            sprint = self.store.get_sprint(sprint_id)
            if sprint is None:
                raise NotFoundError(f"Sprint not found: {sprint_id}")
            if sprint.project_id != project_id:
                raise InvalidRequestError(
                    "Sprint does not belong to this project."
                )

        # Without a sprint the work is filed into the backlog (ADR-0021); the
        # triage policy decides whether it arrives filed or accepted.
        mutations = Mutations(
            self.store, via="api", actor=f"api:{token.name}", role="api", now=self._now
        )
        try:
            filed = mutations.file_task(
                project,
                title=clean_title,
                task_type=task_type,
                description=description,
                acceptance_criteria=acceptance_criteria,
                priority=priority_value,
                complexity=complexity,
                # The audit trail names the token, never the secret.
                created_by=f"api:{token.name}",
                source=source_fields,
                into=sprint,
                event_type="intake.task_created",
                step="intake",
                event_payload={
                    "token_id": token.id,
                    "token_name": token.name,
                    # As the task payload names it: all four, or nothing.
                    "source": (
                        {
                            "system": source_fields["system"],
                            "external_ref": source_fields["external_ref"],
                            "url": source_fields["url"],
                            "reporter": source_fields["reporter"],
                        }
                        if any(source_fields.values())
                        else {}
                    ),
                },
            )
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc

        payload = self.tasks.get_task(filed.task.id)
        payload["created"] = True
        return payload

    @staticmethod
    def _normalize_intake_source(source: dict[str, Any] | None) -> dict[str, str | None]:
        """Validate the caller's ``source`` object into task columns."""

        if source is None:
            source = {}
        if not isinstance(source, dict):
            raise InvalidRequestError("'source' must be an object.")
        unknown = set(source) - {"system", "external_ref", "url", "reporter"}
        if unknown:
            raise InvalidRequestError(
                "Unknown `source` fields: "
                f"{', '.join(sorted(unknown))}. "
                "Expected: system, external_ref, url, reporter."
            )
        normalized: dict[str, str | None] = {}
        for field_name in ("system", "external_ref", "url", "reporter"):
            value = source.get(field_name)
            if value is None:
                normalized[field_name] = None
                continue
            if not isinstance(value, str):
                raise InvalidRequestError(
                    f"'source.{field_name}' must be a string."
                )
            normalized[field_name] = value.strip() or None
        url = normalized["url"]
        if url is not None and urlsplit(url).scheme.lower() not in {"http", "https"}:
            # The dashboard renders this as a link.
            raise InvalidRequestError("'source.url' must be an http or https URL.")
        return normalized
