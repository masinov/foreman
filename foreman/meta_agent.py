"""Meta-agent service: persistent Claude Code session per project.

Each project gets one long-lived session. Messages are sent to a Claude Code
subprocess (via --resume) so the agent retains full conversation context and
tool history. The first message in a new session prepends a rich Foreman
context block so the agent understands the project structure.

Conversation history is kept in memory and returned to the frontend when the
panel reopens.

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
# In-memory session registry
# ---------------------------------------------------------------------------

class _Session:
    __slots__ = ("session_id", "history")

    def __init__(self) -> None:
        self.session_id: str | None = None  # Claude --resume session ID
        self.history: list[dict[str, Any]] = []  # [{role, text, tool_uses}]


_sessions: dict[str, _Session] = {}


def _get_session(project_id: str) -> _Session:
    if project_id not in _sessions:
        _sessions[project_id] = _Session()
    return _sessions[project_id]


def get_history(project_id: str) -> list[dict[str, Any]]:
    """Return the stored conversation turns for one project."""
    session = _sessions.get(project_id)
    if session is None:
        return []
    return list(session.history)


def clear_session(project_id: str) -> None:
    """Discard the in-memory session for one project."""
    _sessions.pop(project_id, None)


# ---------------------------------------------------------------------------
# Context injection
# ---------------------------------------------------------------------------

def _build_context(project: Any, sprints: list[dict[str, Any]]) -> str:
    """Return the system context injected at the start of a new session."""

    lines: list[str] = [
        "You are a meta-operator for the Foreman project management system.",
        "",
        f"Project: {project.name}",
        f"Repository: {project.repo_path}",
        f"Autonomy level: {project.autonomy_level}",
        "",
        "You have full access to the repository file system, git, and the `foreman` CLI.",
        "Use your tools to inspect code, run tests, create branches, update tasks, and",
        "make concrete changes — do not just describe what could be done.",
        "",
        "## Current sprint plan",
    ]

    if not sprints:
        lines.append("No sprints exist yet.")
    else:
        for s in sprints:
            counts = s.get("task_counts") or {}
            total = sum(counts.values())
            status = s.get("status", "unknown")
            lines.append(
                f"  [{status}] {s.get('title', s.get('id', '?'))} "
                f"({total} tasks)"
            )
            if s.get("goal"):
                lines.append(f"    Goal: {s['goal']}")

    active = next((s for s in sprints if s.get("status") == "active"), None)
    if active:
        lines += [
            "",
            f"Active sprint: {active.get('title', active.get('id'))}",
        ]
        if active.get("goal"):
            lines.append(f"Goal: {active['goal']}")

    lines += [
        "",
        "---",
        "The user's message follows.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude Code backend
# ---------------------------------------------------------------------------

async def _run_claude(
    session: _Session,
    prompt: str,
    *,
    repo_path: str,
    executable: str = "claude",
) -> AsyncIterator[str]:
    """Invoke Claude Code and yield NDJSON event strings."""

    cmd = [
        executable,
        "--print",
        "--output-format", "stream-json",
        "--permission-mode", "default",
    ]
    if session.session_id:
        cmd.extend(["--resume", session.session_id])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo_path,
        )
    except (OSError, FileNotFoundError) as exc:
        yield json.dumps({"type": "error", "message": f"Failed to start Claude Code: {exc}"}) + "\n"
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
        yield json.dumps({"type": "error", "message": f"Failed to write prompt: {exc}"}) + "\n"
        return

    assistant_text = ""
    tool_uses: list[dict[str, Any]] = []
    new_session_id: str | None = None

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
                        assistant_text += text
                        yield json.dumps({"type": "text_delta", "text": text}) + "\n"
                elif block.get("type") == "tool_use":
                    tool_name = str(block.get("name", "tool"))
                    tool_input = block.get("input") or {}
                    tool_uses.append({"name": tool_name, "input": tool_input})
                    yield json.dumps({"type": "tool_use", "name": tool_name}) + "\n"

        elif event_type == "result":
            sid = event.get("session_id")
            if sid:
                new_session_id = str(sid)
            is_error = bool(event.get("is_error"))
            if is_error:
                result_text = str(event.get("result") or "Claude Code returned an error.")
                yield json.dumps({"type": "error", "message": result_text}) + "\n"
                await proc.wait()
                return

    await proc.wait()

    if new_session_id:
        session.session_id = new_session_id

    yield json.dumps({"type": "done", "session_id": session.session_id}) + "\n"

    # Persist assistant turn after successful completion
    session.history.append({
        "role": "assistant",
        "text": assistant_text,
        "tool_uses": tool_uses,
    })


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def process_message(
    project_id: str,
    message: str,
    *,
    project: Any,
    sprints: list[dict[str, Any]],
    executable: str = "claude",
) -> AsyncIterator[str]:
    """Stream NDJSON events for one user message turn.

    Args:
        project_id: Identifies the session to use.
        message: The user's raw input.
        project: The Project model instance (needs .repo_path, .settings, .autonomy_level).
        sprints: List of sprint dicts from DashboardService (for context injection).
        executable: Claude CLI binary name.
    """

    session = _get_session(project_id)
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

    # Record user turn before sending (so history survives even if stream fails)
    session.history.append({"role": "user", "text": message, "tool_uses": []})

    # First message in a fresh session: prepend rich Foreman context
    is_new_session = session.session_id is None and len(session.history) == 1
    if is_new_session:
        prompt = _build_context(project, sprints) + "\n\n" + message
    else:
        prompt = message

    async for chunk in _run_claude(
        session,
        prompt,
        repo_path=project.repo_path,
        executable=executable,
    ):
        yield chunk
