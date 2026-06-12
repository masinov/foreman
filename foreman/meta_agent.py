"""Meta-agent service: durable, store-backed planning chat per project.

Each project gets one long-lived Claude Code session. Sessions and turns are
persisted in SQLite (``meta_sessions`` / ``meta_turns``) so chat history and
session resumption survive dashboard restarts. The Claude Code resume id is
read from and written to the store rather than an in-process registry.

Every turn rebuilds a compact, authoritative state header from the database so
the manager always reasons about current world state instead of stale memory.
The first turn of a session also injects an explicit operating contract that
enumerates exactly what the manager may do through the ``foreman`` CLI.

NDJSON event types emitted by process_message():
  {"type": "text_delta", "text": "..."}       — streaming text fragment
  {"type": "tool_use",   "name": "..."}       — tool invocation seen
  {"type": "done",       "session_id": "..."}  — turn completed
  {"type": "error",      "message": "..."}     — error, turn aborted
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncIterator
from typing import Any


# ---------------------------------------------------------------------------
# Store-backed history wrappers
# ---------------------------------------------------------------------------

def get_history(
    store: Any,
    project_id: str,
    *,
    limit: int = 50,
    before_id: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Return persisted conversation turns (oldest-first) plus ``has_more``."""
    return store.list_meta_turns(project_id, limit=limit, before_id=before_id)


def clear_session(store: Any, project_id: str) -> None:
    """Delete the persisted session row and all turns for one project."""
    store.clear_meta_session(project_id)


# ---------------------------------------------------------------------------
# Compact world-state header (rebuilt every turn)
# ---------------------------------------------------------------------------

_NOTEWORTHY_EVENT_MARKERS = ("blocked", "evidence", "sprint", "conflict", "error")


def _truncate(text: str | None, width: int) -> str:
    value = (text or "").replace("\n", " ").strip()
    if len(value) <= width:
        return value
    return value[: max(0, width - 1)].rstrip() + "…"


def build_state_header(store: Any, project: Any) -> str:
    """Return a compact, fixed-format snapshot of current project state.

    The header is regenerated on every turn and reflects the database now. It
    is deliberately bounded (≈≤1,500 tokens) so it can be cheaply re-injected.
    """

    settings = project.settings or {}
    lines: list[str] = [
        "## FOREMAN STATE (regenerated each turn)",
        (
            "This state block is regenerated each turn and reflects the database "
            "now; trust it over your memory of earlier turns."
        ),
        "",
        f"Project: {project.name} ({project.id})",
        f"Workflow: {project.workflow_id} | Autonomy: {project.autonomy_level}",
        "",
        "### Sprints",
    ]

    sprints = store.list_sprints(project.id)
    if not sprints:
        lines.append("(none)")
    else:
        for sprint in sprints:
            tasks = store.list_tasks(sprint_id=sprint.id)
            counts: dict[str, int] = {}
            for task in tasks:
                counts[task.status] = counts.get(task.status, 0) + 1
            count_text = ", ".join(
                f"{status}={n}" for status, n in sorted(counts.items())
            ) or "0 tasks"
            lines.append(
                f"- [{sprint.status}] {sprint.title} ({sprint.id}) — {count_text}"
            )

    active = store.get_active_sprint(project.id)
    if active is not None:
        lines += ["", f"### Active sprint task table — {active.title} ({active.id})"]
        active_tasks = store.list_tasks(sprint_id=active.id)
        if not active_tasks:
            lines.append("(no tasks)")
        else:
            lines.append("id | status | type | title | model_override | blocked_reason")
            for task in active_tasks:
                override = getattr(task, "assigned_role", None) or "-"
                lines.append(
                    f"{task.id} | {task.status} | {task.task_type} | "
                    f"{_truncate(task.title, 40)} | {override} | "
                    f"{_truncate(task.blocked_reason, 80) or '-'}"
                )

    gates = store.list_decision_gates(project.id, status="pending")
    lines += ["", "### Pending decision gates"]
    if not gates:
        lines.append("(none)")
    else:
        for gate in gates:
            lines.append(f"- {gate.id}: {_truncate(gate.conflict_description, 100)}")

    lines += ["", "### Recent noteworthy events (newest first)"]
    recent = store.list_recent_events(project_id=project.id, limit=40)
    noteworthy = [
        event
        for event in recent
        if any(marker in event.event_type for marker in _NOTEWORTHY_EVENT_MARKERS)
    ]
    if not noteworthy:
        lines.append("(none)")
    else:
        for event in noteworthy[:5]:
            lines.append(f"- {event.timestamp} {event.event_type}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# First-turn operating contract
# ---------------------------------------------------------------------------

def build_operating_contract(project: Any) -> str:
    """Return the explicit manager operating contract for a fresh session."""

    pid = project.id
    return "\n".join(
        [
            "## OPERATING CONTRACT",
            "You are the manager seat for the Foreman engine. You plan and steer",
            "work through the `foreman` CLI. You operate in the project repository",
            f"at {project.repo_path}.",
            "",
            "Inspect:",
            f"  foreman board {pid}",
            "  foreman task show <task-id>",
            f"  foreman history {pid}",
            f"  foreman cost {pid}",
            f"  foreman sprint list {pid}",
            "",
            "Plan:",
            f"  foreman sprint add {pid} --title ... --goal ...",
            "",
            "Promote (create a task):",
            f"  foreman task add {pid} --title ... --type ... --criteria ... \\",
            "      --description ... --sprint <sprint-id> --depends-on <task-id,...>",
            "",
            "Assign (per-task model override; Phase 3):",
            "  foreman task override <task-id> --step develop --model ... [--ladder-start N]",
            "",
            "Steer:",
            "  foreman approve <task-id> --note ...",
            "  foreman deny <task-id> --note ...",
            "  foreman task block/unblock/cancel <task-id>",
            "",
            "Hard rules:",
            "- Never edit anything under `.foreman/` (tool-managed runtime state).",
            "- Never merge branches manually.",
            "- Never run `foreman run` yourself; the human or supervision loop",
            "  triggers engine runs.",
            "- Always re-read the FOREMAN STATE header above before acting; it is",
            "  the source of truth and overrides your memory.",
        ]
    )


# ---------------------------------------------------------------------------
# Claude Code backend
# ---------------------------------------------------------------------------

async def _run_claude(
    session_id: str | None,
    prompt: str,
    *,
    repo_path: str,
    executable: str,
    model: str | None,
) -> AsyncIterator[dict[str, Any]]:
    """Invoke Claude Code and yield structured event dicts."""

    cmd = [
        executable,
        "--print",
        "--verbose",
        "--output-format", "stream-json",
        "--permission-mode", "bypassPermissions",
    ]
    if model:
        cmd.extend(["--model", model])
    if session_id:
        cmd.extend(["--resume", session_id])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo_path,
        )
    except (OSError, FileNotFoundError) as exc:
        yield {"type": "error", "message": f"Failed to start Claude Code: {exc}"}
        return

    assert proc.stdin is not None
    assert proc.stdout is not None

    try:
        proc.stdin.write(prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()
    except OSError as exc:
        try:
            proc.kill()
        except OSError:
            pass
        yield {"type": "error", "message": f"Failed to write prompt: {exc}"}
        return

    async for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        event_type = str(event.get("type", ""))

        if event_type == "assistant":
            message_obj = event.get("message", event)
            content = message_obj.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = str(block.get("text", ""))
                    if text:
                        yield {"type": "text_delta", "text": text}
                elif block.get("type") == "tool_use":
                    yield {
                        "type": "tool_use",
                        "name": str(block.get("name", "tool")),
                        "input": block.get("input") or {},
                    }

        elif event_type == "result":
            sid = event.get("session_id")
            if sid:
                yield {"type": "session", "session_id": str(sid)}
            if bool(event.get("is_error")):
                result_text = str(event.get("result") or "Claude Code returned an error.")
                yield {"type": "error", "message": result_text}
                await proc.wait()
                return

    await proc.wait()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def process_message(
    project_id: str,
    message: str,
    *,
    store: Any,
    project: Any,
    executable: str = "claude",
    origin: str = "chat",
    consumed_event_id: str | None = None,
) -> AsyncIterator[str]:
    """Stream NDJSON events for one user message turn, persisting both turns.

    The user turn is persisted before the model is invoked. The assistant turn
    is persisted in the ``finally`` path with whatever text accumulated, flagged
    ``interrupted`` if the stream errored or was cancelled, so a crash never
    silently drops a turn.

    ``origin`` flags the turn provenance (``"chat"`` or ``"supervision"``).
    ``consumed_event_id`` records, in the user turn metadata, the
    ``engine.attention_needed`` event that triggered a supervision turn so it
    cannot be replayed.
    """

    backend = (project.settings or {}).get("meta_agent_backend", "claude")
    if backend != "claude":
        yield json.dumps({
            "type": "error",
            "message": f"Meta-agent backend '{backend}' is not yet supported.",
        }) + "\n"
        return

    if shutil.which(executable) is None:
        yield json.dumps({
            "type": "error",
            "message": (
                f"Claude Code CLI not found (`{executable}`). "
                "Install it and ensure it is in PATH."
            ),
        }) + "\n"
        return

    session_id = store.get_meta_session(project_id)
    is_first_turn = session_id is None

    # Persist the user turn up front so it survives a mid-stream failure.
    user_tool_uses: list[dict[str, Any]] = []
    if consumed_event_id:
        user_tool_uses.append({"consumed_event_id": consumed_event_id})
    store.append_meta_turn(
        project_id,
        role="user",
        text=message,
        tool_uses=user_tool_uses,
        origin=origin,
    )

    state_header = build_state_header(store, project)
    parts = [state_header, "---"]
    if is_first_turn:
        parts += [build_operating_contract(project), "---"]
    parts.append(message)
    prompt = "\n\n".join(parts)

    model = (project.settings or {}).get("meta_agent_model") or None

    assistant_text = ""
    tool_uses: list[dict[str, Any]] = []
    interrupted = False
    new_session_id = session_id

    try:
        async for event in _run_claude(
            session_id,
            prompt,
            repo_path=project.repo_path,
            executable=executable,
            model=model,
        ):
            etype = event["type"]
            if etype == "text_delta":
                assistant_text += event["text"]
                yield json.dumps({"type": "text_delta", "text": event["text"]}) + "\n"
            elif etype == "tool_use":
                tool_uses.append({"name": event["name"], "input": event["input"]})
                yield json.dumps({"type": "tool_use", "name": event["name"]}) + "\n"
            elif etype == "session":
                new_session_id = event["session_id"]
            elif etype == "error":
                interrupted = True
                yield json.dumps({"type": "error", "message": event["message"]}) + "\n"
    except (asyncio.CancelledError, GeneratorExit):
        interrupted = True
        raise
    except Exception as exc:  # noqa: BLE001 - surface any backend failure as a turn error
        interrupted = True
        yield json.dumps({"type": "error", "message": f"Meta-agent stream failed: {exc}"}) + "\n"
    finally:
        if new_session_id and new_session_id != session_id:
            store.save_meta_session(project_id, new_session_id)
        persisted_tool_uses = list(tool_uses)
        if interrupted:
            persisted_tool_uses.append({"interrupted": True})
        store.append_meta_turn(
            project_id,
            role="assistant",
            text=assistant_text,
            tool_uses=persisted_tool_uses,
            origin=origin,
        )

    if not interrupted:
        yield json.dumps({"type": "done", "session_id": new_session_id}) + "\n"
