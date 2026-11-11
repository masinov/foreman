"""SQLite persistence layer for Foreman.

``ForemanStore`` is the one object the rest of Foreman talks to. It is put
together from a part per aggregate, each in its own module, over the
connection and write helper in ``base``:

- ``projects``: ``ProjectStore``
- ``sprints``: ``SprintStore``
- ``tasks``: ``TaskStore``
- ``runs``: ``RunStore``
- ``events``: ``EventStore``
- ``gates``: ``GateStore``
- ``meta``: ``MetaSessionStore``
- ``leases``: ``LeaseStore``
- ``commands``: ``EngineCommandStore``
- ``tokens``: ``ApiTokenStore``
- ``notifications``: ``NotificationStore``
"""

from __future__ import annotations

from .base import ENGINE_RESOURCE_TYPE, MigrationError, StoreBase, _SCHEMA_MIGRATIONS_DDL
from .commands import EngineCommandStore
from .events import EventStore
from .gates import GateStore
from .leases import LeaseStore
from .meta import MetaSessionStore
from .notifications import NotificationStore
from .projects import ProjectStore
from .runs import RunStore
from .sprints import SprintStore
from .tasks import TaskStore
from .tokens import ApiTokenStore
from .rows import derive_task_key_prefix


class ForemanStore(
    ProjectStore,
    SprintStore,
    TaskStore,
    RunStore,
    EventStore,
    GateStore,
    MetaSessionStore,
    LeaseStore,
    EngineCommandStore,
    ApiTokenStore,
    NotificationStore,
):
    """Persist and query Foreman entities in SQLite."""


__all__ = [
    "ENGINE_RESOURCE_TYPE",
    "ForemanStore",
    "MigrationError",
    "StoreBase",
    "_SCHEMA_MIGRATIONS_DDL",
    "derive_task_key_prefix",
]
