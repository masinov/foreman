"""The engine command table: reading, applying and finishing commands (ADR-0011).
"""

from __future__ import annotations

import logging

from ...domain.errors import EngineCommandInterrupt
from ...domain.models import (
    ENGINE_COMMANDS_NEEDING_A_RESIDENT_ENGINE,
    EngineCommand,
)
from ...runner import process
from .base import ResidentEngineBase, _runnable_on_request

#: Recorded on commands a starting engine refuses because they were addressed
#: to a resident engine that is no longer there.
STALE_COMMAND_DETAIL = "no engine was resident"


#: Why a command an earlier engine had picked up, but not finished, is closed.
UNFINISHED_COMMAND_DETAIL = "the engine stopped before it finished applying this command"


#: How long a terminated agent process group is given to die before the engine
#: stops waiting for it.
COMMAND_TERMINATE_GRACE_SECONDS = 2.0


class CommandHandling(ResidentEngineBase):
    """Applying engine commands."""

    def _reject_stale_commands(self) -> None:
        """Settle commands left over from an engine that is gone.

        A pending `pause`, `stop_task`, or `shutdown` describes an intent
        about a process that is no longer running: applying them to *this*
        engine would pause a service nobody asked to pause, or block a task
        nobody is working on. A `resume` and a `run_task` describe work rather
        than a process, and work outlives the engine, so both are left pending
        for the first pass to pick up.

        A command the previous engine had acknowledged but not finished (it
        stopped in between) gets the same treatment: a `run_task` is queued
        again, anything else is closed with the reason.
        """

        for command in self.store.list_engine_commands(
            self.project_id, status="pending", limit=1000
        ):
            if command.command not in ENGINE_COMMANDS_NEEDING_A_RESIDENT_ENGINE:
                continue
            self._finish_command(command, "rejected", STALE_COMMAND_DETAIL)
        unfinished = self.store.list_engine_commands(
            self.project_id, status="acknowledged", limit=1000
        )
        for command in reversed(unfinished):  # oldest first
            if command.command in {"run_task", "resume"}:
                self._apply_idle_command(command)
            else:
                self._finish_command(command, "rejected", UNFINISHED_COMMAND_DETAIL)

    def _drain_commands(self) -> None:
        """Apply every pending command, oldest first, before the next pass."""

        while True:
            command = self.store.next_pending_engine_command(self.project_id)
            if command is None:
                return
            self._acknowledge(command)
            self._apply_idle_command(command)

    def _poll_commands(self, running_task_id: str) -> None:
        """Command hook the orchestrator calls before a step and on every tick.

        Returns normally to let the step continue. Raises
        :class:`~foreman.domain.errors.EngineCommandInterrupt` when the command needs
        the running step stopped; the orchestrator settles the run as
        ``killed`` on the way out and :meth:`_settle_interrupt` finishes the
        command once the stack has unwound.
        """

        self._complete_started_run_request(running_task_id)
        while True:
            command = self.store.next_pending_engine_command(self.project_id)
            if command is None:
                return
            self._acknowledge(command)

            if command.command in {"pause", "shutdown"} or (
                command.command in {"stop_task", "steer_task"}
                and command.task_id == running_task_id
            ):
                # Kill the agent's whole process group first: the run must be
                # settled against a child that is already gone, not one still
                # writing to the repository.
                process.terminate_all(grace_seconds=COMMAND_TERMINATE_GRACE_SECONDS)
                self._log(
                    "serve.command_interrupting",
                    command_id=command.id,
                    command=command.command,
                    task_id=running_task_id,
                    requested_by=command.requested_by,
                )
                raise EngineCommandInterrupt(command, task_id=running_task_id)

            self._apply_idle_command(command, running_task_id=running_task_id)

    def _apply_idle_command(
        self,
        command: EngineCommand,
        *,
        running_task_id: str | None = None,
    ) -> None:
        """Apply one command that does not need the running step stopped."""

        name = command.command
        if name == "pause":
            self._paused = True
            self._finish_command(command, "completed", "Engine paused; no task was running.")
        elif name == "shutdown":
            self._paused = True
            self._stopping = True
            self._finish_command(
                command, "completed", "Engine shutting down; no task was running."
            )
        elif name == "resume":
            was_paused = self._paused
            self._paused = False
            self._finish_command(
                command,
                "completed",
                "Engine resumed." if was_paused else "Engine was already running.",
            )
        elif name == "run_task":
            self._apply_run_task(command)
        elif name == "stop_task":
            self._finish_command(
                command,
                "rejected",
                self._stop_task_rejection(command, running_task_id),
            )
        elif name == "steer_task":
            # Nothing to interrupt. The guidance is recorded and the task's
            # next agent step reads it, as it would have without the command.
            self._finish_command(
                command,
                "completed",
                f"Task {command.task_id!r} was not running a step, so nothing was "
                "interrupted; its next agent step reads the guidance.",
            )
        else:  # pragma: no cover - the schema CHECK constraint prevents this
            self._finish_command(
                command, "rejected", f"Unknown engine command {name!r}."
            )

    def _apply_run_task(self, command: EngineCommand) -> None:
        """Queue a `run_task` for the next pass, or reject it with a reason.

        A queued request stays ``acknowledged``; it is ``completed`` when the
        pass that ran the task has ended, with what happened as its detail.
        """

        if not self._accepts_run_requests:
            self._finish_command(
                command,
                "rejected",
                "A one-shot `foreman run` holds this project and ends after its "
                "pass, so it cannot take a run request. Ask again when it has "
                "finished, or start `foreman serve`.",
            )
            return
        task_id = command.task_id
        if not task_id:
            self._finish_command(
                command, "rejected", "run_task needs a task id."
            )
            return
        task = self.store.get_task(task_id)
        if task is None:
            self._finish_command(
                command, "rejected", f"Unknown task {task_id!r}."
            )
            return
        if task.project_id != self.project_id:
            self._finish_command(
                command,
                "rejected",
                f"Task {task_id!r} belongs to project {task.project_id!r}, "
                f"not {self.project_id!r}.",
            )
            return
        if not _runnable_on_request(task):
            self._finish_command(
                command,
                "rejected",
                f"Task {task_id!r} is {task.status!r} and not runnable. Only a "
                "todo task, or an in_progress task with a persisted resume "
                "point, can be run on request.",
            )
            return
        self._run_requests.append((task_id, command))
        position = len(self._run_requests)
        self.store.mark_engine_command(
            command.id,
            "acknowledged",
            detail=(
                f"Task {task_id!r} will run next."
                if position == 1
                else f"Task {task_id!r} is queued to run ({position} requests ahead of the sprint)."
            ),
        )

    def _stop_task_rejection(
        self, command: EngineCommand, running_task_id: str | None
    ) -> str:
        """Explain why a `stop_task` could not be applied."""

        if not command.task_id:
            return "stop_task needs a task id."
        if running_task_id is None:
            return (
                f"Task {command.task_id!r} is not running: the engine is idle. "
                "Use `foreman task block` to park a task that is not running."
            )
        return (
            f"Task {command.task_id!r} is not the task this engine is running "
            f"({running_task_id!r})."
        )

    def _settle_interrupt(self, interrupt: EngineCommandInterrupt) -> None:
        """Finish the command whose interrupt just unwound the stack.

        By now the orchestrator has settled the agent run as ``killed`` and the
        task is resumable at its persisted step. What remains is the difference
        between the two stops: a `pause` leaves the task exactly as it is, a
        `stop_task` parks it as ``blocked`` naming who stopped it.
        """

        command = interrupt.command
        assert isinstance(command, EngineCommand)  # only this module raises it
        task_id = interrupt.task_id

        if command.command == "stop_task":
            reason = f"Stopped by {command.requested_by}"
            self.orchestrator.stop_task(command.task_id or task_id, reason=reason)
            detail = (
                f"Stopped task {command.task_id!r}: the agent process group was "
                f"terminated, its run settled as killed, and the task is blocked "
                f"({reason})."
            )
        elif command.command == "steer_task":
            # The task stays exactly where it was, in progress at the step
            # that was interrupted, and the engine keeps going: its next pass
            # starts that step again, with the guidance in the prompt and, for
            # a role that keeps its session, in the conversation it had. The
            # interrupted visit did not finish, so it is not counted against
            # the step's limit.
            if task_id:
                self.orchestrator.forgive_step_visit(task_id)
                self.orchestrator.release_task(task_id)
            detail = (
                f"Interrupted task {task_id!r} to read guidance: the agent process "
                "group was terminated, its run settled as killed, and the step "
                "starts again."
            )
        else:
            # `pause` and `shutdown` both leave the task resumable. The lease
            # goes back so the task is not pinned to an engine that has stopped
            # working on it; the guarded step usually released it already, and
            # releasing twice is a no-op.
            if task_id:
                self.orchestrator.release_task(task_id)
            self._paused = True
            if command.command == "shutdown":
                self._stopping = True
            detail = (
                f"{'Shut down' if command.command == 'shutdown' else 'Paused'} "
                f"during task {task_id!r}: the agent process group was terminated, "
                "its run settled as killed, and the task is resumable."
            )
        self._finish_command(command, "completed", detail, task_id=task_id)

    def _acknowledge(self, command: EngineCommand) -> None:
        """Record that this engine has picked a command up."""

        self.store.mark_engine_command(command.id, "acknowledged")
        self._log(
            "serve.command_acknowledged",
            command_id=command.id,
            command=command.command,
            task_id=command.task_id,
            requested_by=command.requested_by,
        )

    def _finish_command(
        self,
        command: EngineCommand,
        status: str,
        detail: str,
        *,
        task_id: str | None = None,
    ) -> None:
        """Close a command out and leave a durable trace of what happened."""

        self.store.mark_engine_command(command.id, status, detail=detail)
        event_type = (
            "engine.command_applied" if status == "completed" else "engine.command_rejected"
        )
        self._log(
            f"serve.command_{status}",
            level=logging.INFO if status == "completed" else logging.WARNING,
            command_id=command.id,
            command=command.command,
            task_id=command.task_id or task_id,
            requested_by=command.requested_by,
            detail=detail,
        )
        try:
            self.orchestrator.record_engine_event(
                project_id=self.project_id,
                event_type=event_type,
                task_id=command.task_id or task_id,
                detail=detail,
                payload={
                    "command_id": command.id,
                    "command": command.command,
                    "requested_by": command.requested_by,
                    "task_id": command.task_id,
                    "detail": detail,
                },
            )
        except Exception as exc:  # noqa: BLE001 - a lost trace must not stop the engine
            self._log(
                "serve.command_event_failed",
                level=logging.ERROR,
                command_id=command.id,
                reason=str(exc),
            )

    def _take_run_request(self) -> tuple[str, EngineCommand] | None:
        """Consume the next queued `run_task` request, if one is waiting."""

        if not self._run_requests:
            return None
        return self._run_requests.pop(0)

    def _complete_started_run_request(self, running_task_id: str) -> None:
        """Close the `run_task` command as soon as the engine is on its task.

        The request is pending only until the engine starts the task; a pass
        can run for hours, and a command left ``acknowledged`` for all of it
        would tell the page the request is still waiting.
        """

        request = self._active_run_request
        if request is None or request[0] != running_task_id:
            return
        self._active_run_request = None
        self._started_run_requests.add(request[1].id)
        self._finish_command(
            request[1], "completed", f"Task {running_task_id!r} was started."
        )

    def _finish_run_request(
        self,
        request: tuple[str, EngineCommand] | None,
        status: str,
        detail: str,
    ) -> None:
        """Close a `run_task` command once its pass has ended.

        A request already closed when its task started is left as it is.
        """

        if request is None:
            return
        if self._active_run_request is request:
            self._active_run_request = None
        if request[1].id in self._started_run_requests:
            self._started_run_requests.discard(request[1].id)
            return
        self._finish_command(request[1], status, detail)

    def _has_pending_command(self) -> bool:
        """True when a command is waiting for this engine to pick it up."""

        return self.store.next_pending_engine_command(self.project_id) is not None
