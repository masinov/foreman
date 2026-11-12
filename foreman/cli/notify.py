"""Where a project is told what the engine is doing."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence
from uuid import uuid4

from ..models import Event, NotificationDelivery, NotificationDestination, Project
from ..notifications import (
    ATTENTION,
    DESTINATION_KINDS,
    NotificationError,
    TransportError,
    add_destination,
    build_payload,
    build_transport,
    resolve_notification_policy,
)
from ..store import ForemanStore

from .common import (
    DB_OPTION_NOTE,
    add_db_option,
    print_lines,
    resolve_db_path_or_print,
    resolve_project_or_print,
    set_handler,
)


def handle_notify_add(args: argparse.Namespace) -> int:
    """Handle ``foreman notify add``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        try:
            destination = add_destination(
                store,
                project.id,
                name=args.name,
                url=args.url,
                kind=args.kind,
                headers=_parse_header_arguments(args.header),
                secret_env=args.secret_env,
            )
        except (NotificationError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        config = destination.config
        policy = resolve_notification_policy(project)

    print_lines(
        "Notification destination added",
        f"Project: {project.id} | {project.name}",
        f"Destination: {destination.id} | {destination.name} ({destination.kind})",
        f"Target: {destination.target}",
        f"Signed: {config.get('secret_env') or 'no'}",
        f"Policy: notification={policy}",
        (
            "This project's policy delivers nothing. Set `notification` to "
            "'attention' or 'all' in its settings to start delivering."
            if policy == "none"
            else "Deliveries are queued by the engine and sent by `foreman serve` "
            "or at the end of `foreman run`."
        ),
    )
    return 0


def handle_notify_list(args: argparse.Namespace) -> int:
    """Handle ``foreman notify list``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        destinations = store.list_notification_destinations(project.id)
        counts = store.count_notification_deliveries(project.id)
        policy = resolve_notification_policy(project)

    lines = [
        "Notification destinations",
        f"Project: {project.id} | {project.name}",
        f"Policy: notification={policy}",
    ]
    if not destinations:
        lines.append("- none")
    else:
        for destination in destinations:
            state = "enabled" if destination.enabled else "disabled"
            lines.append(
                f"- {destination.id} | {destination.name} | {destination.kind} | {state}"
            )
            lines.append(
                f"  target={destination.target}"
                f" | signed={'yes' if destination.config.get('secret_env') else 'no'}"
            )
    lines.append(
        f"Deliveries: {counts['pending']} pending | {counts['delivered']} delivered"
        f" | {counts['failed']} failed"
    )
    print_lines(*lines)
    return 0


def handle_notify_remove(args: argparse.Namespace) -> int:
    """Handle ``foreman notify remove``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        destination = _resolve_destination_or_print(store, project, args.destination)
        if destination is None:
            return 1
        store.delete_notification_destination(destination.id)

    print_lines(
        "Notification destination removed",
        f"Project: {project.id} | {project.name}",
        f"Destination: {destination.id} | {destination.name}",
        "Its queued and recorded deliveries were removed with it.",
    )
    return 0


def handle_notify_test(args: argparse.Namespace) -> int:
    """Handle ``foreman notify test``.

    Sends immediately and synchronously, unlike the engine, because the whole
    point is to find out right now whether the URL works.
    """

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        destination = _resolve_destination_or_print(store, project, args.destination)
        if destination is None:
            return 1
        event = Event(
            id=f"event-{uuid4().hex[:12]}",
            run_id="",
            task_id="",
            project_id=project.id,
            event_type="notification.test",
            payload={"detail": "Test delivery from `foreman notify test`."},
        )
        delivery = NotificationDelivery(
            id=f"ntf-test-{uuid4().hex[:8]}",
            project_id=project.id,
            destination_id=destination.id,
            kind=ATTENTION,
            payload=build_payload(
                kind=ATTENTION, event=event, project=project, task=None
            ),
        )
        try:
            detail = build_transport(destination).send(destination, delivery)
        except (NotificationError, TransportError) as exc:
            print(
                f"Test delivery to {destination.name} failed: {exc}",
                file=sys.stderr,
            )
            return 1

    print_lines(
        "Test notification delivered",
        f"Project: {project.id} | {project.name}",
        f"Destination: {destination.id} | {destination.name}",
        f"Response: {detail}",
    )
    return 0


def handle_notify_deliveries(args: argparse.Namespace) -> int:
    """Handle ``foreman notify deliveries``."""

    db_path = resolve_db_path_or_print(args.db)
    if db_path is None:
        return 1

    with ForemanStore(db_path) as store:
        store.initialize()
        project = resolve_project_or_print(store, args.project_id)
        if project is None:
            return 1
        deliveries = store.list_notification_deliveries(
            project.id, status=args.status, limit=args.limit
        )
        names = {
            destination.id: destination.name
            for destination in store.list_notification_destinations(project.id)
        }

    lines = [
        "Notification deliveries",
        f"Project: {project.id} | {project.name}",
    ]
    if not deliveries:
        lines.append("- none")
    for delivery in deliveries:
        lines.append(
            f"- {delivery.id} | {delivery.kind} | {delivery.status}"
            f" | {names.get(delivery.destination_id, delivery.destination_id)}"
        )
        detail = f"  attempts={delivery.attempts}/{delivery.max_attempts}"
        if delivery.status == "pending":
            detail += f" | next={delivery.next_attempt_at}"
        if delivery.status == "delivered":
            detail += f" | delivered={delivery.delivered_at}"
        lines.append(detail)
        if delivery.last_error:
            lines.append(f"  error={delivery.last_error}")
    print_lines(*lines)
    return 0


def _resolve_destination_or_print(
    store: ForemanStore, project: Project, reference: str
) -> NotificationDestination | None:
    """Resolve a destination by id or by name, scoped to one project."""

    destination = store.get_notification_destination(reference)
    if destination is None:
        destination = store.find_notification_destination(project.id, reference)
    # Scoped to the named project so a mistyped id cannot touch another
    # project's destination.
    if destination is None or destination.project_id != project.id:
        print(
            f"Unknown notification destination for project {project.id}: {reference}",
            file=sys.stderr,
        )
        return None
    return destination


def _parse_header_arguments(values: Sequence[str] | None) -> dict[str, str]:
    """Parse repeated ``--header Name: value`` arguments into an object."""

    headers: dict[str, str] = {}
    for entry in values or ():
        name, separator, value = str(entry).partition(":")
        if not separator or not name.strip():
            raise NotificationError(
                f"Header must be given as 'Name: value', got {entry!r}."
            )
        headers[name.strip()] = value.strip()
    return headers


def register_notify(subparsers: argparse._SubParsersAction) -> None:
    """Add `foreman notify` to the parser."""

    notify_parser = subparsers.add_parser(
        "notify",
        help="Manage where a project is told what the engine is doing.",
    )
    notify_commands = notify_parser.add_subparsers(dest="notify_command")
    notify_parser.set_defaults(handler=None, command_path="notify")

    notify_add = notify_commands.add_parser(
        "add",
        help="Add a notification destination.",
    )
    notify_add.add_argument("project_id", help="Project identifier.")
    notify_add.add_argument(
        "--name",
        required=True,
        help="What to call this destination, e.g. `ops-channel`. Unique per project.",
    )
    notify_add.add_argument(
        "--url",
        required=True,
        help="Where deliveries are POSTed as JSON.",
    )
    notify_add.add_argument(
        "--kind",
        choices=sorted(DESTINATION_KINDS),
        default="webhook",
        help="Transport to deliver through. Defaults to `webhook`.",
    )
    notify_add.add_argument(
        "--header",
        action="append",
        metavar="'Name: value'",
        help="Extra request header; repeatable. For a receiver that wants a static key.",
    )
    notify_add.add_argument(
        "--secret-env",
        help=(
            "Name of an environment variable holding the signing key. Each "
            "delivery then carries an HMAC-SHA256 of its body. The secret "
            "itself is never stored."
        ),
    )
    add_db_option(
        notify_add,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(notify_add, handle_notify_add, "notify add")

    notify_list = notify_commands.add_parser(
        "list",
        help="List a project's destinations and its notification policy.",
    )
    notify_list.add_argument("project_id", help="Project identifier.")
    add_db_option(
        notify_list,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(notify_list, handle_notify_list, "notify list")

    notify_remove = notify_commands.add_parser(
        "remove",
        help="Remove a destination and everything queued for it.",
    )
    notify_remove.add_argument("project_id", help="Project identifier.")
    notify_remove.add_argument("destination", help="Destination identifier or name.")
    add_db_option(
        notify_remove,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(notify_remove, handle_notify_remove, "notify remove")

    notify_test = notify_commands.add_parser(
        "test",
        help="Send one test delivery now and report what the destination said.",
    )
    notify_test.add_argument("project_id", help="Project identifier.")
    notify_test.add_argument("destination", help="Destination identifier or name.")
    add_db_option(
        notify_test,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(notify_test, handle_notify_test, "notify test")

    notify_deliveries = notify_commands.add_parser(
        "deliveries",
        help="Show recent deliveries, including what failed and why.",
    )
    notify_deliveries.add_argument("project_id", help="Project identifier.")
    notify_deliveries.add_argument(
        "--status",
        choices=("pending", "delivered", "failed"),
        help="Show only deliveries in this state.",
    )
    notify_deliveries.add_argument(
        "--limit",
        type=int,
        default=20,
        help="How many deliveries to show. Defaults to 20.",
    )
    add_db_option(
        notify_deliveries,
        help_text=f"Path to the SQLite store containing the project. {DB_OPTION_NOTE}",
    )
    set_handler(notify_deliveries, handle_notify_deliveries, "notify deliveries")

