"""Whether to speak: a project's notification policy, and which events it covers.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..domain.models import Project, Task
from ..domain.policy import POLICY_DEFAULTS, POLICY_VALUES, PolicyMatrix

#: The values the ``notification`` policy decision may take, quietest first.
NOTIFICATION_POLICIES: tuple[str, ...] = POLICY_VALUES["notification"]


#: Used when nothing resolved a policy. ``attention`` rather than ``none``: a
#: project that configured a destination at all wants the moments that need a
#: person, and silence is the failure mode nobody notices.
DEFAULT_NOTIFICATION_POLICY = POLICY_DEFAULTS["notification"]


#: What a delivery is about.
ATTENTION = "attention"


HUMAN_GATE = "human_gate"


TASK_COMPLETED = "task_completed"


NOTIFICATION_KINDS: tuple[str, ...] = (ATTENTION, HUMAN_GATE, TASK_COMPLETED)


#: Which kinds each policy delivers. ``all`` is ``attention`` plus completions,
#: so the ladder is inclusive rather than three unrelated sets.
_POLICY_KINDS: dict[str, frozenset[str]] = {
    "none": frozenset(),
    "attention": frozenset({ATTENTION, HUMAN_GATE}),
    "all": frozenset({ATTENTION, HUMAN_GATE, TASK_COMPLETED}),
}


#: The persisted event types that can become a notification, and the kind each
#: one carries. ``workflow.paused`` is only announceable when it paused for a
#: person; the quota pause is the engine waiting, not a human gate.
_EVENT_KINDS: dict[str, str] = {
    "engine.attention_needed": ATTENTION,
    "workflow.paused": HUMAN_GATE,
    "task.completed": TASK_COMPLETED,
}


def policy_allows(policy: str | None, kind: str) -> bool:
    """Return whether ``policy`` asks for deliveries of ``kind``."""

    allowed = _POLICY_KINDS.get(_clean_policy(policy))
    return kind in allowed if allowed else False


def resolve_notification_policy(
    project: Project | None, task: Task | None = None
) -> str:
    """Resolve the ``notification`` decision for one task.

    Resolution belongs to the canonical policy matrix, including task
    overrides, per-task-type rules, project defaults, and the built-in default.
    """

    matrix = PolicyMatrix.for_project(project)
    if task is None:
        return matrix.resolve("notification").value
    return matrix.resolve(
        "notification",
        task_type=task.task_type,
        overrides=task.executor_overrides,
    ).value


def notify_decision(
    payload: Mapping[str, Any] | None,
    *,
    project: Project | None = None,
    task: Task | None = None,
) -> str:
    """Return the notification policy that governs one event.

    The engine stamps the resolved decision on the event as ``notify`` at the
    moment it emits it, and that stamp wins: it records what the policy said
    *then*, so a project whose setting changed mid-run does not retroactively
    silence or amplify an event already written. Only an event without the
    stamp -- one written before the field existed -- falls back to resolving
    the policy now.
    """

    if isinstance(payload, Mapping):
        stamped = payload.get("notify")
        if isinstance(stamped, str) and stamped in NOTIFICATION_POLICIES:
            return stamped
    return resolve_notification_policy(project, task)


def kind_for_event(event_type: str, payload: Mapping[str, Any] | None = None) -> str | None:
    """Return the notification kind one persisted event carries, if any."""

    kind = _EVENT_KINDS.get(event_type)
    if kind is None:
        return None
    if kind == HUMAN_GATE:
        reason = (payload or {}).get("reason")
        # A question to a person waits for one as a gate does.
        if reason not in ("human_gate", "question"):
            return None
    return kind


def _clean_policy(value: Any) -> str:
    return value if isinstance(value, str) and value in NOTIFICATION_POLICIES else ""
