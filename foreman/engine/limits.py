"""Validated project settings and the ceilings derived from them."""

from __future__ import annotations

from ..models import Project
from ..settings import ProjectSettings, SettingsError, settings_of
from .errors import OrchestratorError


def resolve_project_settings(project: Project) -> ProjectSettings:
    """Validate a project's raw settings blob, or fail fast with a clear error.

    An unattended engine must not run a misconfigured project on silent
    defaults; invalid settings stop the run before any task is touched.
    """

    try:
        return settings_of(project)
    except SettingsError as exc:
        raise OrchestratorError(
            f"Project {project.id!r} has invalid settings: {exc}"
        ) from exc


def run_cost_ceiling(project: Project, role_max_cost_usd: float) -> float:
    """Return the cost ceiling for one agent run; 0 means no ceiling.

    The role sets a ceiling and the project's ``runner_max_cost_usd`` may
    lower it. Neither can raise the other.
    """

    ceilings = [
        value
        for value in (
            max(float(role_max_cost_usd or 0.0), 0.0),
            resolve_project_settings(project).runner_max_cost_usd,
        )
        if value > 0
    ]
    return min(ceilings) if ceilings else 0.0


def project_timeout_seconds(
    project: Project,
    *,
    role_timeout_minutes: int | None = None,
) -> int:
    """Return the effective timeout window for native runs and stale-run recovery."""

    setting = resolve_project_settings(project).time_limit_per_run_minutes
    if setting > 0:
        return setting * 60
    if role_timeout_minutes is not None and role_timeout_minutes > 0:
        return role_timeout_minutes * 60
    return 0


def active_run_recovery_timeout_seconds(project: Project) -> int:
    """Return the stale-run ownership window used for crash recovery."""

    setting = resolve_project_settings(project).active_run_recovery_timeout_minutes
    if setting > 0:
        return setting * 60

    project_timeout = project_timeout_seconds(project)
    default_timeout = 5 * 60
    if project_timeout <= 0:
        return default_timeout
    return min(project_timeout, default_timeout)
