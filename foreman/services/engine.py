"""A project's engine, from any surface.

Steering the engine is the ``engine_commands`` table's job: Run enqueues a
``resume``, Pause enqueues a ``pause``, and a task Stop enqueues a
``stop_task``. The one exception is the single-machine bootstrap: when no
engine is resident there is nothing to send a command to, so the service
spawns a detached ``foreman serve`` through an injectable spawner and then
talks to it like any other resident engine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from ..domain.models import (
    EngineCommand,
    Project,
)
from ..engine.control import (
    ServeSpawner,
    describe_engine,
    serve_command,
    serve_log_path,
    spawn_serve,
)
from ..mutations import MutationError
from ..store import ForemanStore
from .base import Service
from .errors import (
    ActionFailedError,
    NotFoundError,
    InvalidRequestError,
)
from .views import serialize_engine_state

#: How many engine commands the status payload carries.
ENGINE_COMMAND_LIMIT = 10


#: Engine commands a person sends to a running engine from the project page.
#: ``run_task`` and ``stop_task`` name a task and have their own routes.
ENGINE_STEERING_COMMANDS: tuple[str, ...] = ("pause", "resume", "shutdown")


def _serialize_engine_command(command: EngineCommand) -> dict[str, Any]:
    """Serialize one engine command row for the API."""

    return {
        "id": command.id,
        "command": command.command,
        "status": command.status,
        "task_id": command.task_id,
        "requested_by": command.requested_by,
        "requested_at": command.requested_at,
        "acknowledged_at": command.acknowledged_at,
        "completed_at": command.completed_at,
        "result_detail": command.result_detail,
    }


class EngineService(Service):
    """A project's engine: starting it, its state, and the commands sent to it."""

    def __init__(
        self,
        store: ForemanStore,
        *,
        now_factory: Callable[[], datetime] | None = None,
        serve_spawner: ServeSpawner | None = None,
    ) -> None:
        super().__init__(store, now_factory=now_factory)
        # Injected so a test — and, later, a deployment that starts engines
        # somewhere other than this host — can replace the fork without
        # replacing the decision about when to fork.
        self._spawn_serve: ServeSpawner = serve_spawner or spawn_serve

    def start_agent(
        self,
        project_id: str,
        *,
        task_id: str | None = None,
        requested_by: str | None = None,
    ) -> dict[str, Any]:
        """Ask the project's engine to start working.

        When an engine is resident the whole of "start" is a ``resume``
        command: the engine may be paused, or merely idle, and either way it
        is the engine that decides what to run next. When none is resident
        there is nobody to send that command to, so a detached ``foreman
        serve`` is spawned first — the single-machine fallback — and the
        command is queued for it to pick up on its first pass.

        A ``task_id`` becomes a ``run_task`` command rather than a CLI flag,
        so the request survives whether or not an engine is up yet.

        If no sprint is currently active and a planned sprint exists, the first
        planned sprint (by queue order) is activated before the engine starts.
        """

        project = self.store.get_project(project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {project_id}")

        if task_id is not None:
            task = self._require_task(task_id)
            if task.project_id != project_id:
                raise InvalidRequestError(
                    f"Task {task_id} belongs to project {task.project_id}, not {project_id}."
                )

        if task_id is None and self.store.get_active_sprint(project_id) is None:
            next_sprint = self.store.get_next_planned_sprint(project_id)
            if next_sprint is None:
                raise InvalidRequestError(
                    "No active or planned sprint. Add a sprint to the queue before running."
                )
            now = self._now().isoformat()
            next_sprint.status = "active"
            next_sprint.started_at = now
            self.store.save_sprint(next_sprint)

        who = self._requester(requested_by)
        commands: list[EngineCommand] = []
        if task_id is not None:
            commands.append(
                self.store.enqueue_engine_command(
                    project_id=project_id,
                    command="run_task",
                    requested_by=who,
                    task_id=task_id,
                )
            )
        resume = self.store.enqueue_engine_command(
            project_id=project_id,
            command="resume",
            requested_by=who,
        )
        commands.append(resume)

        # Read residency after queueing: a `resume` queued for an engine that
        # is starting right now is honoured by it, so the only case that needs
        # a spawn is "still nothing holding the lock".
        resident = self.store.get_engine_lock(project_id) is not None
        payload: dict[str, Any] = {
            "project_id": project_id,
            "started": True,
            "resident": resident,
            "spawned": False,
            "requested_by": who,
            "command": _serialize_engine_command(resume),
            "commands": [_serialize_engine_command(command) for command in commands],
        }
        if not resident:
            payload.update(self._spawn_local_engine(project))
        return payload

    def _spawn_local_engine(self, project: Project) -> dict[str, Any]:
        """Start a detached ``foreman serve`` for a project with no engine."""

        log_path = serve_log_path(project)
        command = serve_command(project.id, self.store.db_path)
        try:
            spawn = self._spawn_serve(command, log_path)
        except OSError as exc:
            raise ActionFailedError(
                f"Could not start a resident engine for {project.id}: {exc}"
            ) from exc
        return {
            "spawned": True,
            "pid": spawn.pid,
            "log_path": spawn.log_path,
            "serve_command": list(spawn.command),
        }

    def agent_status(self, project_id: str) -> dict[str, Any]:
        """Report the engine's residency, pause state, work, and recent orders."""

        project = self.store.get_project(project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {project_id}")
        engine = describe_engine(
            self.store,
            project_id,
            command_limit=ENGINE_COMMAND_LIMIT,
            now=self._now(),
        )
        payload = serialize_engine_state(engine)
        payload["project_id"] = project_id
        payload["commands"] = [
            _serialize_engine_command(command) for command in engine.commands
        ]
        return payload

    def list_engine_commands(
        self,
        project_id: str,
        *,
        limit: int = ENGINE_COMMAND_LIMIT,
        status: str | None = None,
    ) -> dict[str, Any]:
        """List the project's recent engine commands, newest first."""

        if self.store.get_project(project_id) is None:
            raise NotFoundError(f"Project not found: {project_id}")
        limit = max(1, min(int(limit), 200))
        commands = self.store.list_engine_commands(
            project_id, status=status, limit=limit
        )
        return {
            "project_id": project_id,
            "commands": [_serialize_engine_command(command) for command in commands],
        }

    def stop_agent(self, project_id: str, *, requested_by: str | None = None) -> dict[str, Any]:
        """Ask the project's engine to pause, and return once the order is queued.

        Pausing is about the engine, not about the work: the engine terminates
        the running agent step and leaves its task resumable at the persisted
        step. Nothing here touches task status — a dashboard that blocked every
        in-progress task on Pause was inventing a dead letter the engine never
        declared.
        """

        if self.store.get_project(project_id) is None:
            raise NotFoundError(f"Project not found: {project_id}")

        who = self._requester(requested_by)
        command = self.store.enqueue_engine_command(
            project_id=project_id,
            command="pause",
            requested_by=who,
        )
        return {
            "project_id": project_id,
            "resident": self.store.get_engine_lock(project_id) is not None,
            "requested_by": who,
            "command": _serialize_engine_command(command),
        }

    def send_engine_command(
        self, project_id: str, *, command: str, requested_by: str | None = None
    ) -> dict[str, Any]:
        """Queue a ``pause``, ``resume`` or ``shutdown`` for a running engine.

        These steer an engine that is already running, so they are refused
        when none is: a ``shutdown`` queued for nobody would be the first
        thing the next engine to start reads, and it would stop at once.
        Starting an engine that is not running is ``start_agent``'s job.
        """

        if self.store.get_project(project_id) is None:
            raise NotFoundError(f"Project not found: {project_id}")
        if command not in ENGINE_STEERING_COMMANDS:
            raise InvalidRequestError(
                f"command: unknown {command or '(none)'}; expected "
                f"{', '.join(ENGINE_STEERING_COMMANDS)}."
            )
        if self.store.get_engine_lock(project_id) is None:
            raise InvalidRequestError(
                f"The engine for {project_id} is not running, so there is nothing to "
                f"{'stop' if command == 'shutdown' else command}."
            )
        who = self._requester(requested_by)
        queued = self.store.enqueue_engine_command(
            project_id=project_id,
            command=command,
            requested_by=who,
        )
        return {
            "project_id": project_id,
            "resident": True,
            "requested_by": who,
            "command": _serialize_engine_command(queued),
        }

    def stop_task(self, task_id: str, *, requested_by: str | None = None) -> dict[str, Any]:
        """Ask the engine to stop one running task.

        The engine owns the transition: it terminates the agent step it is
        running and blocks the task with a reason naming the requester. A task
        the engine is not running is rejected on the command row rather than
        being blocked here behind the engine's back.
        """

        task = self._require_task(task_id)
        if task.status != "in_progress":
            raise InvalidRequestError(
                f"Cannot stop a task with status '{task.status}'; only in_progress tasks can be stopped."
            )

        who = self._requester(requested_by)
        command = self.store.enqueue_engine_command(
            project_id=task.project_id,
            command="stop_task",
            requested_by=who,
            task_id=task.id,
        )
        return {
            "task_id": task.id,
            "project_id": task.project_id,
            "status": task.status,
            "resident": self.store.get_engine_lock(task.project_id) is not None,
            "requested_by": who,
            "command": _serialize_engine_command(command),
        }

    def steer_task(
        self, task_id: str, *, text: str, requested_by: str | None = None
    ) -> dict[str, Any]:
        """Record guidance and have the agent step the task is running read it now.

        The note is recorded like any other. Then the engine is asked to stop
        the step in progress and start it again, which puts the note in front
        of the agent at once instead of after the step has ended. Refused
        when no agent is running on the task: then there is nothing to
        interrupt and the note should simply be saved for the next step.
        """

        task = self._require_task(task_id)
        if not text.strip():
            raise InvalidRequestError("Message text required")
        running = [
            run
            for run in self.store.list_runs(task_id=task.id, status="running")
            if not run.role_id.startswith("_builtin:")
        ]
        if task.status != "in_progress" or not running:
            raise InvalidRequestError(
                "No agent is running on this task, so there is nothing to interrupt. "
                "Save the guidance for its next step instead."
            )
        if self.store.get_engine_lock(task.project_id) is None:
            raise InvalidRequestError(
                "The engine is not running, so the step cannot be interrupted. "
                "Save the guidance for the task's next step instead."
            )
        try:
            event = self._mutations().record_guidance(task, text)
        except MutationError as exc:
            raise InvalidRequestError(str(exc)) from exc
        who = self._requester(requested_by)
        command = self.store.enqueue_engine_command(
            project_id=task.project_id,
            command="steer_task",
            requested_by=who,
            task_id=task.id,
        )
        return {
            "status": "interrupting",
            "event_id": event.id,
            "task_id": task.id,
            "step": running[-1].workflow_step,
            "command": _serialize_engine_command(command),
            "message": (
                f"Recorded. The {running[-1].workflow_step} step is being interrupted "
                "and starts again with this guidance."
            ),
        }
