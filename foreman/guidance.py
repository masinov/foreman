"""Guidance a person writes for a task, and whether an agent has read it.

A note is a ``human.message`` event. It is *recorded* when saved and
*delivered* when the engine has put it into the prompt of an agent step, which
it marks with a ``human.message_delivered`` event naming the notes, the role
and the step. Nothing is called delivered before that event exists.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .models import Event

GUIDANCE_EVENT = "human.message"
GUIDANCE_DELIVERED_EVENT = "human.message_delivered"


@dataclass(frozen=True)
class GuidanceNote:
    """One note and, when an agent step received it, which one and when."""

    event_id: str
    text: str
    recorded_at: str
    delivered_at: str | None = None
    delivered_role: str | None = None
    delivered_step: str | None = None

    @property
    def delivered(self) -> bool:
        return self.delivered_at is not None


def guidance_notes(events: Iterable[Event]) -> list[GuidanceNote]:
    """Return a task's notes, oldest first, each with its delivery state."""

    ordered = sorted(events, key=lambda event: (event.timestamp, event.id))
    deliveries: dict[str, Event] = {}
    for event in ordered:
        if event.event_type != GUIDANCE_DELIVERED_EVENT:
            continue
        for message_id in event.payload.get("message_event_ids") or ():
            deliveries.setdefault(str(message_id), event)
    notes: list[GuidanceNote] = []
    for event in ordered:
        if event.event_type != GUIDANCE_EVENT:
            continue
        text = str(event.payload.get("text") or "").strip()
        if not text:
            continue
        delivery = deliveries.get(event.id)
        notes.append(
            GuidanceNote(
                event_id=event.id,
                text=text,
                recorded_at=event.timestamp,
                delivered_at=delivery.timestamp if delivery else None,
                delivered_role=str(delivery.payload.get("role") or "") if delivery else None,
                delivered_step=str(delivery.payload.get("step") or "") if delivery else None,
            )
        )
    return notes


def pending_guidance(events: Iterable[Event]) -> list[GuidanceNote]:
    """Return the notes no agent step has received yet."""

    return [note for note in guidance_notes(events) if not note.delivered]


def prompt_with_guidance(prompt: str, notes: list[GuidanceNote]) -> str:
    """Append undelivered notes to an agent prompt, where they are read last."""

    if not notes:
        return prompt
    lines = [
        "## Guidance from a person",
        "",
        "A person overseeing this task wrote the following since the last agent",
        "step. Follow it in this step. Where it conflicts with earlier feedback,",
        "the guidance wins. If it asks for work that is not this step's job, say so",
        "in your final message so the next step picks it up.",
        "",
    ]
    for note in notes:
        body = note.text.replace("\n", "\n  ")
        lines.append(f"- ({note.recorded_at}) {body}")
    return f"{prompt.rstrip()}\n\n" + "\n".join(lines) + "\n"
