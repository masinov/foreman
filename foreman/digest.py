"""Compact attention digests for engine → manager supervision turns.

When the engine needs a human/manager decision (a task blocked, evidence
failed, a loop limit hit, a sprint resolved), it emits an
``engine.attention_needed`` event. The dashboard can then run one supervision
turn through the persisted meta session; ``build_attention_digest`` produces the
compact, fixed-format prompt body for that turn.
"""

from __future__ import annotations

from typing import Any

# Human-readable description per trigger id.
_TRIGGER_LABELS: dict[str, str] = {
    "task_blocked": "A task was blocked and needs a decision.",
    "evidence_failed": "Completion evidence failed the proof gate.",
    "loop_limit": "A task hit the workflow step-visit loop limit.",
    "sprint_resolved": "A sprint finished and the next move needs confirmation.",
}


def _truncate(text: str | None, width: int) -> str:
    value = (text or "").strip()
    if len(value) <= width:
        return value
    return value[: max(0, width - 1)].rstrip() + "…"


def build_attention_digest(
    store: Any,
    project: Any,
    *,
    trigger: str,
    task_id: str | None,
) -> str:
    """Return a compact (~≤800 token) supervision digest for one trigger.

    The digest names the trigger, summarizes the affected task (status, step,
    visits, blocked reason, evidence verdict + failure reasons, last run outcome
    detail), and lists the manager's allowed responses.
    """

    lines: list[str] = [
        "## ATTENTION NEEDED",
        _TRIGGER_LABELS.get(trigger, f"Engine raised: {trigger}."),
        f"Trigger: {trigger}",
        f"Project: {project.name} ({project.id}) | autonomy={project.autonomy_level}",
    ]

    task = store.get_task(task_id) if task_id else None
    if task is not None:
        visits = ", ".join(
            f"{step}={n}" for step, n in sorted((task.step_visit_counts or {}).items())
        ) or "none"
        lines += [
            "",
            "### Affected task",
            f"id: {task.id}",
            f"title: {_truncate(task.title, 100)}",
            f"status: {task.status} | type: {task.task_type}",
            f"current step: {task.workflow_current_step or '-'}",
            f"step visits: {visits}",
        ]
        if task.blocked_reason:
            lines.append(f"blocked reason: {_truncate(task.blocked_reason, 200)}")

        evidence = task.completion_evidence
        if evidence is not None:
            lines.append(
                f"evidence: verdict={evidence.verdict} | proof={evidence.proof_status} "
                f"| score={evidence.score:.0f}/100 | judged_by={evidence.judged_by}"
            )
            if evidence.failure_reasons:
                lines.append("evidence failure reasons:")
                for reason in evidence.failure_reasons:
                    lines.append(f"  - {_truncate(reason, 160)}")

        runs = store.list_runs(task_id=task.id)
        if runs:
            last = runs[-1]
            lines.append(
                f"last run: {last.role_id} / {last.workflow_step} -> "
                f"{last.outcome or last.status}"
            )
            if last.outcome_detail:
                lines.append(f"last run detail: {_truncate(last.outcome_detail, 400)}")
    elif task_id:
        lines += ["", f"### Affected task\nid: {task_id} (not found)"]

    directed = getattr(project, "autonomy_level", "supervised") == "directed"
    lines += ["", "### Your allowed responses"]
    if directed:
        lines += [
            "This project is in DIRECTED mode: you may NOT run state-mutating",
            "`foreman` commands. Recommend a course of action in prose; the human",
            "will execute it.",
        ]
    else:
        lines += [
            "You may act through the `foreman` CLI per your operating contract:",
            "- inspect: foreman board / task show / history / cost / sprint list",
            "- plan: foreman sprint add ...",
            "- promote: foreman task add ... --sprint ... --depends-on ...",
            "- assign: foreman task override <task-id> --step ... --model ...",
            "- steer: foreman approve/deny --note, foreman task block/unblock/cancel",
            "Never edit `.foreman/`, never merge manually, never run `foreman run`.",
        ]

    return "\n".join(lines)
