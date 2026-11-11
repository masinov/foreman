"""Running Foreman: run, serve, the engine commands, and the dashboard."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from ..dashboard_runtime import DEFAULT_FRONTEND_DEV_URL, run_dashboard_server
from ..engine_control import (
    default_command_requester,
    describe_engine,
)
from ..engine_lock import EngineBusyError, EngineLock
from ..errors import EngineCommandInterrupt
from ..logs import configure_json_logging
from ..models import EngineCommand
from ..orchestrator import ForemanOrchestrator, OrchestratorError
from ..runner.process import EngineShutdown, install_shutdown_handlers
from ..serve import DEFAULT_POLL_SECONDS, ResidentEngine, serve_project
from ..notifications import (
    NotificationDeliveryWorker,
)
from ..store import ForemanStore

from .common import (
    DB_OPTION_NOTE,
    EXIT_QUOTA_EXHAUSTED,
    add_db_option,
    add_json_option,
    print_json,
    print_lines,
    resolve_db_path_or_print,
    resolve_project_or_print,
    resolve_task_or_print,
    set_handler,
)


def handle_run(args: argparse.Namespace) -> int:
    """Handle ``foreman run``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    if getattr(args, "json_logs", False):
        configure_json_logging()

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        orchestrator = ForemanOrchestrator(store)
        # One engine per project: a one-shot run and a resident `foreman serve`
        # would otherwise pick different tasks in the same checkout.
        lock = EngineLock(
            store=store,
            project_id=project.id,
            holder_id=orchestrator.holder_id,
        )
        try:
            lock.acquire()
        except EngineBusyError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        install_shutdown_handlers()
        # While this run holds the project it is the only process that can act
        # on a `pause` or a `stop_task`, so it answers engine commands the way
        # a resident engine does. It ends after its pass, so it takes no run
        # requests, and running it is itself the instruction to work, so a
        # standing pause does not hold it back.
        commands = ResidentEngine(
            store=store,
            project_id=project.id,
            orchestrator=orchestrator,
            lock=lock,
            accepts_run_requests=False,
            honour_standing_pause=False,
        )
        try:
            commands.attach()
            result = orchestrator.run_project(project.id, task_id=args.task)
        except EngineCommandInterrupt as exc:
            commands.settle_interrupt(exc)
            command = exc.command
            print(
                f"Run stopped by engine command `{command.command}` from "
                f"{command.requested_by}. The agent process was terminated and its "
                "run settled as killed.",
                file=sys.stderr,
            )
            return 130
        except (EngineShutdown, KeyboardInterrupt) as exc:
            if lock.lost:
                print(
                    f"Run stopped: {lock.lost_reason}",
                    file=sys.stderr,
                )
                return 1
            reason = str(exc) or "interrupted"
            print(
                f"Run stopped: {reason} Agent processes were terminated; the active "
                "task keeps its resume point and its lease was released.",
                file=sys.stderr,
            )
            return 130
        except OrchestratorError as exc:
            print(f"Failed to run project: {exc}", file=sys.stderr)
            return 1
        finally:
            lock.release()
        # A one-shot run has no later pass to send from, so it drains once
        # here. Anything a destination refuses is left queued with its backoff
        # intact for the next `foreman run` or a resident `foreman serve`; a
        # notification is never worth failing a completed run over, so this
        # sits after the lock is released and outside the run's exit paths.
        delivered = NotificationDeliveryWorker(store).drain(project.id)
        db_path = store.db_path

    print_lines(
        "Run",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        (f"Scope: task {args.task}" if args.task is not None else "Scope: project"),
        (
            "Executed tasks: " + ", ".join(result.executed_task_ids)
            if result.executed_task_ids
            else "Executed tasks: none"
        ),
        (
            "Blocked tasks: " + ", ".join(result.blocked_task_ids)
            if result.blocked_task_ids
            else "Blocked tasks: none"
        ),
        f"Stop reason: {result.stop_reason}",
        *(
            [
                f"Notifications: {delivered.delivered} delivered, "
                f"{delivered.retrying} retrying, {delivered.failed} failed"
            ]
            if delivered.did_work
            else []
        ),
        *(
            [
                f"Retry after: {result.retry_after or 'unknown'}",
                "The paused task keeps its resume point; run again once the backend quota resets.",
            ]
            if result.stop_reason == "quota_exhausted"
            else []
        ),
    )
    if result.stop_reason == "quota_exhausted":
        return EXIT_QUOTA_EXHAUSTED
    return 0


def handle_serve(args: argparse.Namespace) -> int:
    """Handle ``foreman serve``.

    Thin by design: everything about the loop, the lock, and the waiting lives
    in ``foreman.serve``. This function resolves arguments, turns on JSON
    logging (the resident engine has no terminal to print to), and maps the
    result to an exit code.
    """

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    if args.poll_seconds <= 0:
        print("--poll-seconds must be greater than zero.", file=sys.stderr)
        return 1

    configure_json_logging()

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1

        install_shutdown_handlers()
        try:
            result = serve_project(
                store=store,
                project_id=project.id,
                poll_seconds=args.poll_seconds,
                once=args.once,
            )
        except EngineBusyError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    return result.exit_code


def handle_dashboard(args: argparse.Namespace) -> int:
    """Handle ``foreman dashboard``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    token = args.token
    if args.token_file:
        try:
            token = Path(args.token_file).expanduser().read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(f"Failed to read --token-file: {exc}", file=sys.stderr)
            return 1
    try:
        run_dashboard_server(
            db_path=db_path,
            host=args.host,
            port=args.port,
            frontend_mode=args.frontend_mode,
            frontend_dev_url=args.frontend_dev_url,
            reload=args.reload,
            auth_token=token or None,
            allowed_origins=tuple(args.allowed_origins),
            allow_insecure_network=args.allow_insecure_network,
            allow_remote_manager=args.allow_remote_manager,
        )
    except (OSError, RuntimeError) as exc:
        print(f"Failed to start dashboard: {exc}", file=sys.stderr)
        return 1
    return 0


def _format_command_row(command: EngineCommand) -> str:
    parts = [
        f"- [{command.status}] {command.command}",
        f"id={command.id}",
        f"by={command.requested_by}",
        f"at={command.requested_at}",
    ]
    if command.task_id:
        parts.insert(2, f"task={command.task_id}")
    line = " | ".join(parts)
    if command.result_detail:
        line = f"{line}\n    {command.result_detail}"
    return line


def handle_engine_status(args: argparse.Namespace) -> int:
    """Handle ``foreman engine status``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        # A `pause` that has been applied but not yet resumed is the engine's
        # current state, so the most recent applied pause/resume is what makes
        # "paused" visible to an operator who did not queue it themselves.
        engine = describe_engine(store, project.id, command_limit=args.limit)
        lock = engine.lock
        commands = engine.commands
        running = store.list_tasks(project_id=project.id, statuses=("in_progress",))
        paused = engine.paused
        db_path = store.db_path

    if getattr(args, "as_json", False):
        now = datetime.now(timezone.utc)
        print_json(
            {
                "database": str(db_path),
                "project_id": project.id,
                "state": engine.state,
                "resident": lock is not None,
                "paused": paused,
                "holder_id": lock.holder_id if lock is not None else None,
                "heartbeat_at": lock.heartbeat_at if lock is not None else None,
                "heartbeat_age_seconds": (
                    lock.heartbeat_age_seconds(now) if lock is not None else None
                ),
                "lease_expires_at": lock.expires_at if lock is not None else None,
                "lease_expired": lock.is_expired(now) if lock is not None else False,
                "running_task_ids": [task.id for task in running],
                "commands": [
                    {
                        "id": command.id,
                        "command": command.command,
                        "task_id": command.task_id,
                        "status": command.status,
                        "requested_by": command.requested_by,
                        "requested_at": command.requested_at,
                        "result_detail": command.result_detail,
                    }
                    for command in commands
                ],
            }
        )
        return 0

    lines = [
        "Engine status",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
    ]
    if lock is None:
        lines.append("Resident engine: none (no engine holds this project)")
    else:
        now = datetime.now(timezone.utc)
        age = lock.heartbeat_age_seconds(now)
        age_text = "unknown" if age is None else f"{age:.0f}s ago"
        state = "paused" if paused else "running"
        if lock.is_expired(now):
            state = "stale lease (no heartbeat since it expired)"
        lines.extend(
            [
                f"Resident engine: {lock.holder_id}",
                f"State: {state}",
                f"Heartbeat: {age_text} (at {lock.heartbeat_at})",
                f"Acquired: {lock.acquired_at} | Lease expires: {lock.expires_at}",
            ]
        )
    if running:
        lines.append(
            "Current task: "
            + ", ".join(f"{task.id} | {task.title}" for task in running)
        )
    else:
        lines.append("Current task: none")

    lines.append(f"Recent commands ({len(commands)}):")
    if not commands:
        lines.append("- none")
    else:
        lines.extend(_format_command_row(command) for command in commands)
    print_lines(*lines)
    return 0


def handle_engine_command(args: argparse.Namespace) -> int:
    """Handle every ``foreman engine`` verb that enqueues a command."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    task_id = getattr(args, "task_id", None)
    requested_by = args.by or default_command_requester()
    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        if task_id is not None:
            task = resolve_task_or_print(store, task_id)
            if task is None:
                return 1
            if task.project_id != project.id:
                print(
                    f"Task {task_id} belongs to project {task.project_id}, "
                    f"not {project.id}.",
                    file=sys.stderr,
                )
                return 1
        resident = store.get_engine_lock(project.id)
        command = store.enqueue_engine_command(
            project_id=project.id,
            command=args.engine_command_name,
            requested_by=requested_by,
            task_id=task_id,
        )
        db_path = store.db_path

    lines = [
        f"Queued engine command: {command.command}",
        f"Database: {db_path}",
        f"Project: {project.id} | {project.name}",
        f"Command id: {command.id}",
        f"Requested by: {command.requested_by}",
    ]
    if command.task_id:
        lines.append(f"Task: {command.task_id}")
    if resident is None:
        # Not an error: `resume` and `run_task` are honoured by the next engine
        # to start. The others will be rejected as stale, and saying so now is
        # kinder than letting the operator discover it in the command log.
        lines.append(
            "No engine is resident on this project. "
            + (
                "The next `foreman serve` will apply it."
                if command.command in {"resume", "run_task"}
                else "It will be rejected when an engine next starts."
            )
        )
    else:
        lines.append(f"Resident engine: {resident.holder_id}")
    print_lines(*lines)
    return 0


def register_run(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman run` to the parser."""

    run_parser = subparsers.add_parser("run", help="Run Foreman against a project.")
    run_parser.add_argument("project_id", help="Project identifier.")
    run_parser.add_argument("--task", help="Single task identifier to run.")
    add_db_option(
        run_parser,
        help_text=f"Path to the SQLite store containing the project workflow state. {DB_OPTION_NOTE}",
    )
    run_parser.add_argument(
        "--json-logs",
        action="store_true",
        help="Emit structured JSON-lines logs on stderr instead of staying quiet.",
    )
    set_handler(run_parser, handle_run, "run")



def register_serve(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman serve` to the parser."""

    serve_parser = subparsers.add_parser(
        "serve",
        help="Run Foreman as a resident engine for one project.",
    )
    serve_parser.add_argument("project_id", help="Project identifier.")
    serve_parser.add_argument(
        "--poll-seconds",
        type=float,
        default=DEFAULT_POLL_SECONDS,
        help=(
            "Seconds an idle engine waits before running another pass. It also "
            "wakes immediately when another process writes to the database. "
            f"Default: {DEFAULT_POLL_SECONDS}."
        ),
    )
    serve_parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one pass and exit (cron-style deployment, and tests).",
    )
    add_db_option(
        serve_parser,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(serve_parser, handle_serve, "serve")



def register_engine(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman engine` to the parser."""

    engine_parser = subparsers.add_parser(
        "engine",
        help="Inspect and steer the resident engine for one project.",
    )
    engine_commands_parser = engine_parser.add_subparsers(
        dest="engine_command",
        metavar="engine_command",
        required=True,
    )

    engine_status = engine_commands_parser.add_parser(
        "status",
        help="Show the resident engine and its recent commands.",
    )
    engine_status.add_argument("project_id", help="Project identifier.")
    engine_status.add_argument(
        "--limit",
        type=int,
        default=10,
        help="How many recent commands to show (default: 10).",
    )
    add_db_option(
        engine_status,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    add_json_option(engine_status)
    set_handler(engine_status, handle_engine_status, "engine status")

    def _add_engine_command(
        name: str, *, command_name: str, help_text: str, needs_task: bool = False
    ) -> None:
        sub = engine_commands_parser.add_parser(name, help=help_text)
        sub.add_argument("project_id", help="Project identifier.")
        if needs_task:
            sub.add_argument("task_id", help="Task identifier.")
        sub.add_argument(
            "--by",
            default=None,
            help=(
                "Who is asking, recorded on the command. "
                "Defaults to the OS user name."
            ),
        )
        add_db_option(
            sub,
            help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
        )
        sub.set_defaults(engine_command_name=command_name)
        set_handler(sub, handle_engine_command, f"engine {name}")

    _add_engine_command(
        "pause",
        command_name="pause",
        help_text=(
            "Stop the engine picking up new work and stop the running agent "
            "step, leaving its task resumable."
        ),
    )
    _add_engine_command(
        "resume",
        command_name="resume",
        help_text="Let a paused engine start picking up work again.",
    )
    _add_engine_command(
        "shutdown",
        command_name="shutdown",
        help_text="Stop the running step, release the engine lock, and exit.",
    )
    _add_engine_command(
        "run-task",
        command_name="run_task",
        help_text="Run one task next, regardless of sprint order.",
        needs_task=True,
    )
    _add_engine_command(
        "stop-task",
        command_name="stop_task",
        help_text="Stop the task the engine is running and block it.",
        needs_task=True,
    )



def register_dashboard(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman dashboard` to the parser."""

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Start the web dashboard.",
    )
    add_db_option(
        dashboard_parser,
        help_text=f"Path to the SQLite store for dashboard data. {DB_OPTION_NOTE}",
    )
    dashboard_parser.add_argument(
        "--host",
        default="localhost",
        help="Host to bind to (default: localhost).",
    )
    dashboard_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080).",
    )
    dashboard_parser.add_argument(
        "--frontend-mode",
        choices=("dist", "dev"),
        default="dist",
        help=(
            "Frontend delivery mode. Use `dist` for the shipped built React app "
            "and `dev` when a Vite dev server will serve the frontend shell."
        ),
    )
    dashboard_parser.add_argument(
        "--frontend-dev-url",
        default=DEFAULT_FRONTEND_DEV_URL,
        help=(
            "Origin for the frontend dev server when `--frontend-mode dev` is used "
            f"(default: {DEFAULT_FRONTEND_DEV_URL})."
        ),
    )
    dashboard_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn reload support for local dashboard backend development.",
    )
    dashboard_parser.add_argument(
        "--token",
        default=os.environ.get("FOREMAN_DASHBOARD_TOKEN"),
        help=(
            "Shared access token required on every /api request "
            "(default: FOREMAN_DASHBOARD_TOKEN). Required for non-loopback binds."
        ),
    )
    dashboard_parser.add_argument(
        "--token-file",
        dest="token_file",
        help="Read the access token from a file instead of the command line.",
    )
    dashboard_parser.add_argument(
        "--allowed-origin",
        dest="allowed_origins",
        action="append",
        default=[],
        metavar="ORIGIN",
        help="Allow cross-origin browser requests from ORIGIN (repeatable). Off by default.",
    )
    dashboard_parser.add_argument(
        "--allow-insecure-network",
        dest="allow_insecure_network",
        action="store_true",
        help="Permit a non-loopback bind without a token (trusted networks only).",
    )
    dashboard_parser.add_argument(
        "--allow-remote-manager",
        dest="allow_remote_manager",
        action="store_true",
        help=(
            "Keep the manager chat enabled on a non-loopback bind. It runs a "
            "full-access agent session on this host; off by default off-loopback."
        ),
    )
    set_handler(dashboard_parser, handle_dashboard, "dashboard")

