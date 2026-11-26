"""A project's engine (its worker, on the page), from any surface.

Whether the work may go on is a user's holds on it (ADR-0043,
``services.holds``), not the engine's state. What is left here is the
program: starting a worker where none holds the project (the single-machine
bootstrap, through an injectable spawner), its state, and the messages a
worker takes from the ``engine_commands`` table: ``run_task`` (Run next),
``steer_task`` and ``shutdown``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from ..domain.holds import task_hold
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
    InvalidRequestError,
    NotFoundError,
)
from .views import serialize_engine_state

#: How many engine commands the status payload carries.
ENGINE_COMMAND_LIMIT = 10


#: Engine commands a person sends to a running worker. ``run_task`` and
#: ``steer_task`` name a task and have their own routes; pausing and
#: resuming the work are holds (ADR-0043).
ENGINE_STEERING_COMMANDS: tuple[str, ...] = ("shutdown",)


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
        """Run a task next, and make sure a worker holds the project.

        With a ``task_id`` this is Run next: a ``run_task`` command puts the
        task first in line, and survives whether or not a worker is up yet.
        A task a user holds (paused, or under a block) is refused: Run next
        does not pass a hold (ADR-0043).

        Without one it is Start worker: nothing is queued, because a worker
        works on whatever is started and not held. Nothing starts a sprint
        here either; Start sprint does (ADR-0043).

        When no worker holds the project, a detached ``foreman serve`` is
        spawned, the single-machine fallback.
        """

        project = self.store.get_project(project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {project_id}")

        who = self._requester(requested_by)
        commands: list[EngineCommand] = []
        if task_id is not None:
            task = self._require_task(task_id)
            if task.project_id != project_id:
                raise InvalidRequestError(
                    f"Task {task_id} belongs to project {task.project_id}, not {project_id}."
                )
            if (
                task_hold(
                    task,
                    sprint_block=self.store.get_sprint_block(task.sprint_id),
                    workspace_block=self.store.get_workspace_block(),
                )
                is not None
            ):
                raise InvalidRequestError(
                    f"{task.task_key or task.id} is held (paused or blocked); resume or "
                    "unblock it first."
                )
            commands.append(
                self.store.enqueue_engine_command(
                    project_id=project_id,
                    command="run_task",
                    requested_by=who,
                    task_id=task_id,
                )
            )

        # Read residency after queueing: a request queued for a worker that is
        # starting right now is honoured by it, so the only case that needs a
        # spawn is "still nothing holding the lock".
        resident = self.store.get_engine_lock(project_id) is not None
        payload: dict[str, Any] = {
            "project_id": project_id,
            "started": True,
            "resident": resident,
            "spawned": False,
            "requested_by": who,
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
        """Report the worker's residency, its work, and recent orders."""

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

    def send_engine_command(
        self, project_id: str, *, command: str, requested_by: str | None = None
    ) -> dict[str, Any]:
        """Queue a ``shutdown`` for a running worker.

        Refused when none is running: a ``shutdown`` queued for nobody would
        be the first thing the next worker to start reads, and it would stop
        at once. Pausing the work is a hold (ADR-0043), not a command.
        """

        if self.store.get_project(project_id) is None:
            raise NotFoundError(f"Project not found: {project_id}")
        if command in ("pause", "resume"):
            raise InvalidRequestError(
                f"{command} is no longer an engine command: pause and resume the "
                "work itself (a task, a sprint or the workspace; ADR-0043)."
            )
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
