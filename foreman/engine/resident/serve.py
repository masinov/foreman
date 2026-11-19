"""``serve_project``: what ``foreman serve`` runs.
"""

from __future__ import annotations

import logging

from ...history.logs import log_event
from ...store import ForemanStore
from ..lock import EngineBusyError, EngineLock
from ..orchestrator import ForemanOrchestrator
from . import ResidentEngine
from .base import _LOGGER, DEFAULT_POLL_SECONDS, ServeResult


def serve_project(
    *,
    store: ForemanStore,
    project_id: str,
    orchestrator: ForemanOrchestrator | None = None,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    once: bool = False,
    lock: EngineLock | None = None,
    logger: logging.Logger | None = None,
    **engine_kwargs: object,
) -> ServeResult:
    """Acquire the project engine lock and run the resident engine under it.

    Raises :class:`~foreman.engine.lock.EngineBusyError` when another engine
    holds the lock; the lock is released on every other exit path, including an
    unhandled error.
    """

    engine_logger = logger if logger is not None else _LOGGER
    orchestrator = orchestrator or ForemanOrchestrator(store)
    engine_lock = lock or EngineLock(
        store=store,
        project_id=project_id,
        holder_id=orchestrator.holder_id,
    )

    try:
        engine_lock.acquire()
    except EngineBusyError as exc:
        # A supervisor reading only the process log must be able to tell a
        # refused start from a crash, so the refusal is logged before it is
        # raised for the CLI to print.
        log_event(
            engine_logger,
            "serve.lock_busy",
            level=logging.ERROR,
            project_id=project_id,
            holder_id=exc.holder_id,
            expires_at=exc.expires_at,
            reason=str(exc),
        )
        raise
    log_event(
        engine_logger,
        "serve.lock_acquired",
        project_id=project_id,
        holder_id=orchestrator.holder_id,
        lease_id=engine_lock.lease.id if engine_lock.lease else None,
        expires_at=engine_lock.lease.expires_at if engine_lock.lease else None,
    )
    try:
        engine = ResidentEngine(
            store=store,
            project_id=project_id,
            orchestrator=orchestrator,
            lock=engine_lock,
            poll_seconds=poll_seconds,
            logger=engine_logger,
            **engine_kwargs,  # type: ignore[arg-type]
        )
        return engine.run(once=once)
    finally:
        engine_lock.release()
        log_event(
            engine_logger,
            "serve.lock_released",
            project_id=project_id,
            holder_id=orchestrator.holder_id,
        )
