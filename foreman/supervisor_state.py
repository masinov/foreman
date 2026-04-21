"""Shared supervisor-to-SQLite finalization helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .orchestrator import ForemanOrchestrator
from .store import ForemanStore


@dataclass(slots=True)
class SupervisorMergeResult:
    """Summary of one supervisor merge finalization."""

    project_id: str
    task_id: str
    sprint_id: str
    task_status: str
    sprint_status: str
    stop_reason: str | None


def finalize_supervisor_merge(
    store: ForemanStore,
    *,
    repo_path: str | Path,
    branch_name: str,
    task_id: str | None = None,
    utc_now: Callable[[], datetime] | None = None,
) -> SupervisorMergeResult | None:
    """Persist task and sprint state after a supervisor merges an approved branch."""

    orchestrator = ForemanOrchestrator(store, utc_now=utc_now)
    return orchestrator.finalize_supervisor_merge(
        repo_path=str(Path(repo_path)),
        branch_name=branch_name,
        task_id=task_id,
    )
