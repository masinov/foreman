"""The project engine lock: one Foreman engine per project at a time.

`foreman run` and `foreman serve` both mutate the same checkout, the same
branches, and the same task rows. Two of them on one project is not a race the
per-task lease can settle: the task lease stops two engines from executing the
*same* task, but nothing stops a second engine from picking a *different* task
and checking out its branch underneath the first one's agent.

The engine lock closes that. It is an ordinary lease
(``resource_type="engine"``, ``resource_id=<project id>``) in the existing
``leases`` table, so it needs no schema of its own, it is visible to
``foreman lease`` inspection like every other lease, and a crashed engine
releases it by expiry rather than leaving a stale lock file behind.

The lock is renewed from a daemon thread that opens its own store connection.
It cannot ride along on agent output the way the per-task lease heartbeat does:
an agent can be silent for many minutes, and an engine that stopped renewing
because its agent went quiet would hand the whole project to a second engine.
The timer thread renews on wall-clock time regardless of what the engine is
doing.
"""

from __future__ import annotations

import _thread
import logging
import threading
from typing import Callable

from .errors import ForemanError
from .leases import generate_lease_token
from .logs import get_logger, log_event
from .models import Lease
from .store import ENGINE_RESOURCE_TYPE, ForemanStore

__all__ = [
    "DEFAULT_HEARTBEAT_SECONDS",
    "DEFAULT_LEASE_DURATION_SECONDS",
    "ENGINE_RESOURCE_TYPE",
    "EngineBusyError",
    "EngineLock",
    "EngineLockError",
    "EngineLockLostError",
    "stop_engine_on_lock_loss",
]

#: Engine lease duration. Shorter than the per-task lease default: a SIGKILLed
#: engine blocks the project for at most this long, and the timer heartbeat
#: below renews six times per lease so a slow write cannot lose it.
DEFAULT_LEASE_DURATION_SECONDS = 120.0

#: Interval between lock renewals.
DEFAULT_HEARTBEAT_SECONDS = 20.0

#: Consecutive heartbeat write failures tolerated before the lock is declared
#: lost. A single transient SQLite lock error must not stop the engine; a
#: database that stays unreachable for three intervals means it must.
HEARTBEAT_FAILURE_TOLERANCE = 3

_LOGGER = get_logger("engine_lock")


class EngineLockError(ForemanError):
    """Base error for engine-lock failures."""


class EngineBusyError(EngineLockError):
    """Raised when another live engine already holds the project lock."""

    def __init__(self, project_id: str, holder_id: str | None, expires_at: str | None) -> None:
        holder = holder_id or "unknown"
        super().__init__(
            f"Another Foreman engine is already running project {project_id!r} "
            f"(lock holder {holder}"
            + (f", lease expires {expires_at}" if expires_at else "")
            + "). Stop it, or wait for its lease to expire, before starting another."
        )
        self.project_id = project_id
        self.holder_id = holder_id
        self.expires_at = expires_at


class EngineLockLostError(EngineLockError):
    """Raised when the engine lock could no longer be renewed."""


def stop_engine_on_lock_loss(lock: "EngineLock") -> None:
    """Default lock-loss reaction: kill agent children and interrupt the engine.

    Losing the engine lock means another engine now owns this project, so the
    work in flight must be abandoned rather than finished. The main thread may
    be blocked for a long time inside an agent step, so it is interrupted the
    same way Ctrl+C would interrupt it: the orchestrator's existing guarded
    step settles the active run as ``killed`` with the task resumable at its
    persisted step, exactly as it does for a shutdown signal.
    """

    from .runner.process import terminate_all

    try:
        terminate_all(grace_seconds=2.0)
    except Exception:  # noqa: BLE001 - abandoning must not raise from a thread
        pass
    try:
        _thread.interrupt_main()
    except (RuntimeError, KeyboardInterrupt):  # pragma: no cover - platform edge
        pass


class EngineLock:
    """Hold the per-project engine lease for the duration of a ``with`` block.

    ``store`` is used from the calling thread only. The heartbeat thread gets
    its own :class:`ForemanStore` from ``store_factory`` because a SQLite
    connection must not be shared across threads.
    """

    def __init__(
        self,
        *,
        store: ForemanStore,
        project_id: str,
        holder_id: str,
        duration_seconds: float = DEFAULT_LEASE_DURATION_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
        store_factory: Callable[[], ForemanStore] | None = None,
        on_lost: Callable[["EngineLock"], None] | None = None,
        logger: object | None = None,
    ) -> None:
        self.store = store
        self.project_id = project_id
        self.holder_id = holder_id
        self.duration_seconds = float(duration_seconds)
        self.heartbeat_seconds = max(0.0, float(heartbeat_seconds))
        self._store_factory = store_factory or (lambda: ForemanStore(store.db_path))
        self._on_lost = on_lost if on_lost is not None else stop_engine_on_lock_loss
        self._logger = logger if logger is not None else _LOGGER
        self._token: str | None = None
        self._lease: Lease | None = None
        self._lost = threading.Event()
        self._lost_reason: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── state ────────────────────────────────────────────────────────────

    @property
    def held(self) -> bool:
        """True while this process holds the lock and has not lost it."""

        return self._token is not None and not self._lost.is_set()

    @property
    def lost(self) -> bool:
        """True once a renewal was refused or repeatedly failed."""

        return self._lost.is_set()

    @property
    def lost_reason(self) -> str | None:
        """Why the lock was lost, or None while it is still held."""

        return self._lost_reason

    @property
    def lease(self) -> Lease | None:
        """The acquired lease row, for reporting."""

        return self._lease

    def check(self) -> None:
        """Raise :class:`EngineLockLostError` if the lock is gone."""

        if self._lost.is_set():
            raise EngineLockLostError(self._lost_reason or "Engine lock was lost.")

    # ── lifecycle ────────────────────────────────────────────────────────

    def acquire(self) -> Lease:
        """Take the project engine lock and start the heartbeat thread."""

        token = generate_lease_token()
        lease = self.store.acquire_lease(
            project_id=self.project_id,
            resource_type=ENGINE_RESOURCE_TYPE,
            resource_id=self.project_id,
            holder_id=self.holder_id,
            lease_token=token,
            duration_seconds=self.duration_seconds,
        )
        if lease is None:
            active = self.store.get_active_lease(
                project_id=self.project_id,
                resource_type=ENGINE_RESOURCE_TYPE,
                resource_id=self.project_id,
            )
            raise EngineBusyError(
                self.project_id,
                active.holder_id if active else None,
                active.expires_at if active else None,
            )

        self._token = token
        self._lease = lease
        self._lost.clear()
        self._lost_reason = None
        self._stop.clear()
        self._start_heartbeat()
        return lease

    def release(self) -> bool:
        """Stop the heartbeat and release the lease. Safe to call twice."""

        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(5.0, self.heartbeat_seconds))

        token = self._token
        self._token = None
        if token is None or self._lost.is_set():
            # A lost lock is already held by someone else; releasing it would
            # be a no-op at best and a steal at worst.
            return False
        return self.store.release_lease(
            project_id=self.project_id,
            resource_type=ENGINE_RESOURCE_TYPE,
            resource_id=self.project_id,
            holder_id=self.holder_id,
            lease_token=token,
        )

    def __enter__(self) -> "EngineLock":
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()

    # ── heartbeat ────────────────────────────────────────────────────────

    def _start_heartbeat(self) -> None:
        if self.heartbeat_seconds <= 0:
            return
        thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"foreman-engine-lock-{self.project_id}",
            daemon=True,
        )
        self._thread = thread
        thread.start()

    def _heartbeat_loop(self) -> None:
        store: ForemanStore | None = None
        failures = 0
        try:
            store = self._store_factory()
            while not self._stop.wait(self.heartbeat_seconds):
                token = self._token
                if token is None:
                    return
                try:
                    renewed = store.renew_lease(
                        project_id=self.project_id,
                        resource_type=ENGINE_RESOURCE_TYPE,
                        resource_id=self.project_id,
                        holder_id=self.holder_id,
                        lease_token=token,
                        duration_seconds=self.duration_seconds,
                    )
                except Exception as exc:  # noqa: BLE001 - see tolerance below
                    failures += 1
                    log_event(
                        self._logger,
                        "engine_lock.heartbeat_failed",
                        level=logging.WARNING,
                        project_id=self.project_id,
                        holder_id=self.holder_id,
                        attempt=failures,
                        reason=str(exc),
                    )
                    if failures >= HEARTBEAT_FAILURE_TOLERANCE:
                        self._declare_lost(
                            f"Engine lock heartbeat failed {failures} times: {exc}"
                        )
                        return
                    continue

                if renewed is None:
                    self._declare_lost(
                        "Engine lock on project "
                        f"{self.project_id!r} was refused on renewal (expired or "
                        "taken over by another engine)."
                    )
                    return
                failures = 0
        finally:
            if store is not None:
                try:
                    store.close()
                except Exception:  # noqa: BLE001 - shutdown must not raise
                    pass

    def _declare_lost(self, reason: str) -> None:
        self._lost_reason = reason
        self._lost.set()
        log_event(
            self._logger,
            "engine_lock.lost",
            level=logging.ERROR,
            project_id=self.project_id,
            holder_id=self.holder_id,
            reason=reason,
        )
        try:
            self._on_lost(self)
        except Exception:  # noqa: BLE001 - the reaction must not kill the thread
            pass
