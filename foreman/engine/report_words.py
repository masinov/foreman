"""A step's record, written out for the next step's prompt (ADR-0042).

The developer's report reaches a reviewer as sections, one entry per
criterion, not as the developer's free text. Plain words, no narrative.
"""

from __future__ import annotations

from typing import Any

DEVELOPER_REPORT = "developer_report"

_LIST_SECTIONS = (
    ("not_verified", "Not verified, and why"),
    ("beyond_task", "Behaviour changed beyond the task"),
    ("docs_touched", "Docs touched"),
    ("follow_ups", "Follow-ups filed"),
)


def developer_report_text(fields: dict[str, Any]) -> str:
    """The developer's report as markdown sections for a reviewer's prompt."""

    parts = ["#### What changed and why", str(fields.get("summary") or "").strip() or "(blank)"]
    criteria = fields.get("criteria") or []
    parts.append("#### Acceptance criteria, as the developer verified them")
    if not criteria:
        parts.append("None listed.")
    for number, entry in enumerate(criteria, start=1):
        verified = "yes" if entry.get("verified") else "no"
        parts.append(
            f"{number}. {str(entry.get('criterion') or '').strip()}\n"
            f"   - Verified by the developer: {verified}\n"
            f"   - How: {str(entry.get('verification') or '').strip() or '(not said)'}"
        )
    for key, title in _LIST_SECTIONS:
        items = [str(item).strip() for item in fields.get(key) or [] if str(item).strip()]
        parts.append(f"#### {title}")
        parts.append("\n".join(f"- {item}" for item in items) if items else "Nothing.")
    return "\n\n".join(parts)


def record_text(record: dict[str, Any] | None) -> str:
    """A stored record as prompt text, or "" when it has no words of its own."""

    if not record or record.get("kind") != DEVELOPER_REPORT:
        return ""
    try:
        return developer_report_text(record.get("fields") or {})
    except (AttributeError, TypeError):
        # A project's own role may declare a record of this kind with another
        # shape. Its record is then not written out, rather than breaking
        # every later prompt of the task.
        return ""
