"""Sleeping until the database changes, a command arrives, or the poll interval ends.
"""

from __future__ import annotations

from .base import ResidentEngineBase


class Waiting(ResidentEngineBase):
    """Waiting between passes."""

    def _has_something_waiting(self) -> bool:
        """Whether the pass should end between tasks so the loop can act.

        True when a task was asked for by name, or a command arrived that no
        step was running to hear. The loop drains commands at its top and its
        next pass runs the requested task first.
        """

        return bool(self._run_requests) or (
            self.store.next_pending_engine_command(self.project_id) is not None
        )

    def _wait(self, seconds: float) -> None:
        """Sleep for ``seconds`` in ticks, returning early if the lock is lost
        or a command is waiting.

        These waits are the long ones: a failure backoff reaches five minutes,
        and a quota wait reaches six hours. An engine that ignored `shutdown`
        for six hours would not be controllable, so a queued command cuts the
        wait short and the loop drains it on the next pass.

        ``data_version`` is checked first because it is a pragma rather than a
        table read, so the common case — nothing committed since the last tick
        — costs nothing beyond it. Only an actual commit by another connection
        is worth a lookup in ``engine_commands``.
        """

        deadline = self._monotonic() + seconds
        baseline = self.store.data_version()
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0 or self._lock_is_lost():
                return
            self._sleep(min(self._tick_seconds, remaining))
            version = self.store.data_version()
            if version != baseline:
                baseline = version
                if self._has_pending_command():
                    return

    def _wait_for_change(self, timeout: float) -> bool:
        """Block until another process commits, or ``timeout`` elapses.

        ``PRAGMA data_version`` only moves when a *different* connection
        commits, so this detects a task queued by the dashboard, the CLI, or
        the intake API without polling any table. The baseline is re-read on
        every wait.

        A commit is not necessarily about this project: lock heartbeats,
        another project's engine and a running agent's event stream all move
        ``data_version``. Only a change to this project's own settings,
        sprints, tasks, commands or queued notifications ends the wait; the
        rest cost one small read each instead of a full pass.
        """

        baseline = self.store.data_version()
        activity = self.store.project_activity_token(self.project_id)
        deadline = self._monotonic() + timeout
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                return False
            self._sleep(min(self._tick_seconds, remaining))
            if self._lock_is_lost():
                return False
            version = self.store.data_version()
            if version == baseline:
                continue
            baseline = version
            if self.store.project_activity_token(self.project_id) != activity:
                return True
