"""Meta-agent service: durable, store-backed planning chat per project.

Each project gets one long-lived Claude Code session. Sessions and turns are
persisted in SQLite (``meta_sessions`` / ``meta_turns``) so chat history and
session resumption survive dashboard restarts. The Claude Code resume id is
read from and written to the store rather than an in-process registry.

Every turn rebuilds a compact, authoritative state header from the database so
the manager always reasons about current world state instead of stale memory.
The first turn of a session also injects an explicit operating contract that
enumerates exactly what the manager may do through the ``foreman`` CLI.

The manager proposes; a person confirms (ADR-0022). Its Claude Code process
runs with ``FOREMAN_MANAGER_SESSION`` and ``FOREMAN_MANAGER_TURN`` set, and the
CLI refuses every command that changes project state from inside it except
``foreman proposal create``.

NDJSON event types emitted by process_message():
  {"type": "text_delta", "text": "..."}       — streaming text fragment
  {"type": "tool_use",   "name": "..."}       — tool invocation seen
  {"type": "proposal",   "proposal_id": "..."} — a proposal made in this turn
  {"type": "done",       "session_id": "..."}  — turn completed
  {"type": "error",      "message": "..."}     — error, turn aborted
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import sys
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from .proposals import MANAGER_SESSION_ENV, MANAGER_TURN_ENV, OPERATION_KINDS, Proposals
from ..store.meta import REPLY_IN_PROGRESS, REPLY_INTERRUPTED
from ..runner.env import agent_environment

#: The one folder a manager session can write to, relative to the project's
#: repository: where it puts a proposal document before proposing it.
MANAGER_DRAFTS_DIR = ".foreman/manager"

# The longest line of the manager's output that is read. Claude Code prints
# one JSON object per line, and the result of a tool is inside it: reading a
# 71 KB specification is one line longer than asyncio's 64 KB default, which
# ended the turn with "Separator is not found, and chunk exceed the limit".
MANAGER_STREAM_LINE_LIMIT = 64 * 1024 * 1024

#: The manager's whole tool set (ADR-0022, ADR-0023).
MANAGER_TOOLS: tuple[str, ...] = ("Read", "Grep", "Glob", "Bash", "Write")

#: What those tools may do without asking. Nobody is there to ask in a
#: headless session, so everything else is refused. Checked against the real
#: CLI (2.1.325) on 2026-11-15: `foreman ...` runs; commands the CLI itself
#: classes as read-only run inside the repository (`ls`, `cat`, `git
#: status`); a redirect, a chain with a writing part, a variable prefix,
#: `env`, `sqlite3`, `python`, `git commit`, a read outside the repository
#: and a write outside the drafts folder are all refused.
MANAGER_PERMISSIONS: tuple[str, ...] = (
    "Read",
    "Grep",
    "Glob",
    "Bash(foreman:*)",
    f"Edit({MANAGER_DRAFTS_DIR}/**)",
)

#: Said in every turn, so a session begun under older instructions follows
#: these too.
PROPOSING_REMINDER = "\n".join(
    [
        "### How to propose (the only way to change anything)",
        f"Write the proposal document to `{MANAGER_DRAFTS_DIR}/<name>.json` with the Write",
        "tool, then run `foreman proposal create <project-id> --json` with that path.",
        "Your shell runs `foreman` commands and commands that only read inside the",
        "repository (ls, cat, git log, git diff). Anything that writes, a redirect, a",
        "heredoc, or a read outside the repository is refused.",
        f"You can write files only in `{MANAGER_DRAFTS_DIR}/`.",
    ]
)


def manager_command(
    executable: str, *, model: str | None, session_id: str | None
) -> list[str]:
    """The Claude Code command line for one manager turn."""

    command = [
        executable,
        "--print",
        "--verbose",
        "--output-format", "stream-json",
        # Not bypassPermissions: the permission rules below are what confine
        # the session, and that mode ignores them.
        "--permission-mode", "default",
        "--tools", ",".join(MANAGER_TOOLS),
        "--allowed-tools", ",".join(MANAGER_PERMISSIONS),
        # None of the connectors the dashboard's user set up for themselves.
        "--strict-mcp-config",
    ]
    if model:
        command.extend(["--model", model])
    if session_id:
        command.extend(["--resume", session_id])
    return command


def manager_process_env(env: dict[str, str] | None) -> dict[str, str]:
    """The whole environment of a manager session's process.

    The short list every agent gets (ADR-0023) and the session's marks, with
    this installation's `foreman` first on the path: the session may run only
    commands that begin with that word.
    """

    environment = agent_environment(env)
    bin_dir = Path(sys.executable).parent
    if (bin_dir / "foreman").exists():
        environment["PATH"] = os.pathsep.join(
            part for part in (str(bin_dir), environment.get("PATH", "")) if part
        )
    return environment


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


_CONTEXT_FIELDS = (
    ("page", "the page"),
    ("sprint_id", "sprint id"),
    ("task_id", "task id"),
)
_CONTEXT_MAX_LENGTH = 200


def describe_page_context(context: Any) -> str | None:
    """Return one line saying where in the dashboard the person is, or None.

    ``context`` is the optional object a client sends with a message:
    ``{"page": "Sprints", "sprint_id": "...", "task_id": "..."}``. Unknown keys
    are ignored and values are clipped, so the line stays short and is never
    free-form instructions. Raises ``ValueError`` for a value that is not an
    object of strings.
    """
    if context is None:
        return None
    if not isinstance(context, dict):
        raise ValueError("context must be an object.")
    parts: list[str] = []
    for key, label in _CONTEXT_FIELDS:
        value = context.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"context.{key} must be a string.")
        value = " ".join(value.split())[:_CONTEXT_MAX_LENGTH]
        if value:
            parts.append(f"{label}: {value}")
    if not parts:
        return None
    return "The person is looking at the dashboard (" + "; ".join(parts) + ")."


def clear_session(store: Any, project_id: str, *, via: str, actor: str | None = None) -> list[str]:
    """Forget a project's conversation; return the proposals declined with it.

    A proposal is shown beside the reply it came with, and nowhere else. Once
    the conversation is gone nothing would show one still waiting, so it is
    declined with the conversation, by the person clearing it, rather than
    left where nobody can answer it.
    """
    pending, _ = store.page_proposals(project_id, states=["proposed"])
    proposals = Proposals(store, via=via, actor=actor)
    declined: list[str] = []
    for proposal in pending:
        proposals.decline(proposal.id, sentence=CLEARED_PROPOSAL)
        declined.append(proposal.id)
    store.clear_meta_session(project_id)
    return declined


#: What a proposal declined because its conversation was cleared says.
CLEARED_PROPOSAL = "Declined when the conversation it was made in was cleared. Nothing was changed."


# ---------------------------------------------------------------------------
# Compact world-state header (rebuilt every turn)
# ---------------------------------------------------------------------------

_NOTEWORTHY_EVENT_MARKERS = ("blocked", "evidence", "sprint", "conflict", "error")


def _truncate(text: str | None, width: int) -> str:
    value = (text or "").replace("\n", " ").strip()
    if len(value) <= width:
        return value
    return value[: max(0, width - 1)].rstrip() + "…"


#: How many filed and how many accepted backlog tasks the header names.
BACKLOG_HEAD_LIMIT = 5


def _backlog_section(store: Any, project: Any) -> list[str]:
    """Return the backlog block: counts, then the head of filed and accepted.

    The backlog is not a sprint (ADR-0021), so ``list_sprints`` never shows
    it; without this block the manager could not see work waiting for a
    decision. Declined work is counted but not listed.
    """

    lines = ["", "### Backlog (not a sprint; unplanned work)"]
    heads: list[tuple[str, list[Any]]] = []
    counts: dict[str, int] = {}
    for label, status in (("filed", "triage"), ("accepted", "todo")):
        tasks, total, counts = store.page_backlog_tasks(
            project.id, statuses=[status], limit=BACKLOG_HEAD_LIMIT
        )
        heads.append((label, tasks))
    lines.append(
        f"filed={counts['triage']}, accepted={counts['todo']}, "
        f"declined={counts['declined']}"
    )
    for label, tasks in heads:
        total = counts["triage" if label == "filed" else "todo"]
        if not tasks:
            continue
        lines.append(f"{label.capitalize()} (showing {len(tasks)} of {total}):")
        for task in tasks:
            lines.append(
                f"- {task.id} | {task.task_type} | {_truncate(task.title, 60)}"
            )
    return lines


def build_state_header(store: Any, project: Any) -> str:
    """Return a compact, fixed-format snapshot of current project state.

    The header is regenerated on every turn and reflects the database now. It
    is deliberately bounded (≈≤1,500 tokens) so it can be cheaply re-injected.
    """

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

    lines += _backlog_section(store, project)

    active = store.get_active_sprint(project.id)
    if active is not None:
        lines += ["", f"### Active sprint task table — {active.title} ({active.id})"]
        active_tasks = store.list_tasks(sprint_id=active.id)
        if not active_tasks:
            lines.append("(no tasks)")
        else:
            lines.append("id | status | type | title | assigned_role | blocked_reason")
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
    """Return the explicit manager operating contract for a fresh session.

    The manager reads anything and changes nothing itself: every change is a
    proposal a person confirms (ADR-0022). The CLI enforces it; this says it.
    """

    pid = project.id
    kinds = ", ".join(OPERATION_KINDS)
    return "\n".join(
        [
            "## OPERATING CONTRACT",
            "You are the manager seat for the Foreman engine. You read the project",
            "and propose changes; a person confirms them. Nothing you propose",
            "happens until they do. You operate in the project repository",
            f"at {project.repo_path}.",
            "",
            "Read (these work; read the repository freely too):",
            f"  foreman board {pid}",
            f"  foreman status {pid}",
            "  foreman task show <task-id>",
            f"  foreman task list {pid}",
            "  foreman history <task-id>",
            "  foreman transcript <task-id>",
            f"  foreman cost {pid}",
            f"  foreman sprint list {pid}",
            f"  foreman backlog list {pid} [--status filed|accepted|declined]",
            f"  foreman worktree list {pid}",
            f"  foreman notify list {pid}",
            f"  foreman notify deliveries {pid} [--status pending|delivered|failed]",
            f"  foreman engine status {pid}",
            f"  foreman proposal list {pid}",
            "  foreman proposal show <proposal-id>",
            "",
            "Change (only this way):",
            f"  1. Write the document to {MANAGER_DRAFTS_DIR}/<name>.json with the Write tool:",
            '     {"reason": "<one paragraph: why>",',
            '      "operations": [<operation>, ...],',
            '      "leaves": [<task-id the plan deliberately leaves where it is>, ...]}',
            "  2. Then run:",
            f"  foreman proposal create {pid} --json {MANAGER_DRAFTS_DIR}/<name>.json",
            "",
            f"Operation kinds: {kinds}.",
            "  create_sprint {title, goal?, ref?}",
            "  edit_sprint {sprint_id, title?, goal?}",
            "  activate_sprint {sprint_id} | finish_sprint {sprint_id}",
            "  file_task {title, task_type?, description?, acceptance_criteria?,",
            "             priority?, complexity?, accept?, ref?}  (into the backlog)",
            "  add_task {sprint_id, title, task_type?, description?,",
            "            acceptance_criteria?, priority?, complexity?, ref?, waits_for?}",
            "            (straight into a planned or active sprint; `waits_for`",
            "            lists the tasks it starts after)",
            "  accept_task {task_id} | decline_task {task_id, reason?}",
            "  plan_tasks {task_ids, sprint_id} or {task_ids, new_sprint: {title, goal?}}",
            "  unplan_task {task_id}",
            "  edit_task {task_id, title?, task_type?, description?,",
            "             acceptance_criteria?, priority?, complexity?,",
            "             depends_on_task_ids?}  (what it waits for; [] for nothing;",
            "             only before the task starts)",
            "  block_task {task_id, reason} | unblock_task {task_id}",
            "  cancel_task {task_id}",
            "  complete_task {task_id, reason}  (done by hand, without running its",
            "             remaining steps: for work finished outside the engine)",
            "  reopen_task {task_id}  (a done or cancelled task, back to the queue)",
            "  send_back {task_id, guidance}  (a task waiting at a gate, or blocked)",
            "  approve_gate {task_id}",
            "`ref` is a name you give what an operation creates (a sprint or a",
            "task), which has no id until the proposal is confirmed. A later",
            "operation of the same proposal may use it wherever it takes a sprint",
            "id or a task id: create a sprint and add_task into it, or file tasks",
            "and plan_tasks them, in one proposal.",
            "",
            "The command checks every operation against the project as it is now,",
            "in order, and stores nothing if one is refused; it prints why. Fix the",
            "proposal and create it again. Once stored, the person sees it beside",
            "your reply with Confirm and Not now. Say in your reply what it does;",
            "do not claim a change has happened.",
            "",
            "Hard rules:",
            "- Every other `foreman` command that changes state is refused in this",
            "  session. Do not try to work around that: no direct database writes,",
            "  no manual merges, no `foreman run`.",
            "- Your shell runs `foreman` commands and commands that only read inside",
            "  the repository (ls, cat, git log, git diff). Anything that writes, a",
            "  redirect, a heredoc, or a read outside the repository is refused.",
            f"  You can write files only in `{MANAGER_DRAFTS_DIR}/`.",
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
    env: dict[str, str] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Invoke Claude Code and yield structured event dicts.

    ``env`` marks the process as a manager session (ADR-0022). The process is
    started with a fixed tool set and permission rules (``manager_command``)
    and without the dashboard's own environment (``manager_process_env``).
    """

    cmd = manager_command(executable, model=model, session_id=session_id)
    try:
        (Path(repo_path) / MANAGER_DRAFTS_DIR).mkdir(parents=True, exist_ok=True)
    except OSError:
        # Without the folder the session cannot draft a proposal; it will
        # say so. Reading still works.
        pass

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo_path,
            env=manager_process_env(env),
            limit=MANAGER_STREAM_LINE_LIMIT,
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

    # However the reading ends (the reply finished, a line that could not be
    # read, the person's request cancelled), the process ends with it. Left
    # running, it would go on working, and storing proposals, for a turn that
    # is already over.
    try:
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
                    return

        await proc.wait()
    finally:
        await _end_process(proc)


async def _end_process(proc: asyncio.subprocess.Process) -> None:
    """Kill the manager's process if it is still running, and reap it."""

    if proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=PROCESS_REAP_SECONDS)
    except (asyncio.TimeoutError, ProcessLookupError):
        pass


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

#: How long a killed manager process is waited for before the turn ends anyway.
PROCESS_REAP_SECONDS = 5.0

#: How often, at most, a reply is saved while it is written, so anyone else
#: looking at the conversation sees it grow.
REPLY_SAVE_SECONDS = 1.0

#: Said when a message arrives while the manager is still answering another.
MANAGER_BUSY = (
    "The manager is still answering another message in this project. "
    "Wait for that reply to finish."
)


def manager_session_env(project_id: str, turn_id: str, db_path: str | None) -> dict[str, str]:
    """The environment that marks a Claude Code process as a manager session.

    The CLI refuses state changes when ``FOREMAN_MANAGER_SESSION`` is set
    (ADR-0022); ``FOREMAN_MANAGER_TURN`` ties a proposal to the turn it was
    made in; ``FOREMAN_DB`` points the manager's commands at the database
    this dashboard uses.
    """

    env = {MANAGER_SESSION_ENV: project_id, MANAGER_TURN_ENV: turn_id}
    if db_path and db_path != ":memory:":
        env["FOREMAN_DB"] = str(db_path)
    return env


async def process_message(
    project_id: str,
    message: str,
    *,
    store: Any,
    project: Any,
    executable: str = "claude",
    origin: str = "chat",
    consumed_event_id: str | None = None,
    page_context: str | None = None,
    instructions: str | None = None,
    after_turn: Callable[[str], list[str]] | None = None,
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

    ``page_context`` is a line from :func:`describe_page_context`. It goes into
    this turn's prompt after the state header and is not stored with the turn,
    so the transcript keeps only what the person wrote.

    ``instructions`` is what the manager is told for this turn beyond
    ``message``; it too goes into the prompt and is not stored. ``after_turn``
    is called with the turn's id when the reply has ended without an error,
    and returns the ids of proposals it settled, which are announced again so
    the conversation shows them as they now are (planning, ``foreman.manager.planning``).
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

    # The message and an empty reply marked in progress are stored before the
    # model is asked: the message survives a failure, and anyone else looking
    # at the conversation sees that it is being answered.
    user_tool_uses: list[dict[str, Any]] = []
    if consumed_event_id:
        user_tool_uses.append({"consumed_event_id": consumed_event_id})
    started = store.start_meta_reply(
        project_id, text=message, tool_uses=user_tool_uses, origin=origin
    )
    if started is None:
        yield json.dumps({"type": "error", "message": MANAGER_BUSY}) + "\n"
        return
    user_turn_id, reply_turn_id = started
    # The stored ids of this message and its reply, so a client showing the
    # reply as it streams knows which turns of the history they are.
    yield json.dumps({"type": "turn", "message_id": user_turn_id, "reply_id": reply_turn_id}) + "\n"

    state_header = build_state_header(store, project)
    parts = [state_header, "---"]
    if is_first_turn:
        parts += [build_operating_contract(project), "---"]
    else:
        parts += [PROPOSING_REMINDER, "---"]
    if page_context:
        parts.append(page_context)
    parts.append(message)
    if instructions:
        parts.append(instructions)
    prompt = "\n\n".join(parts)

    model = (project.settings or {}).get("meta_agent_model") or None

    assistant_text = ""
    tool_uses: list[dict[str, Any]] = []
    interrupted = False
    new_session_id = session_id
    session_env = manager_session_env(project_id, user_turn_id, getattr(store, "db_path", None))
    announced: set[str] = set()

    saved_at = 0.0

    def save_progress() -> None:
        """Save the reply as it stands, at most every REPLY_SAVE_SECONDS."""
        nonlocal saved_at
        now = time.monotonic()
        if now - saved_at < REPLY_SAVE_SECONDS:
            return
        saved_at = now
        try:
            store.update_meta_turn(
                reply_turn_id, text=assistant_text, tool_uses=[*tool_uses, REPLY_IN_PROGRESS]
            )
        except sqlite3.Error:
            # Only what others see while the reply is written; its end is saved.
            pass

    def new_proposals() -> list[str]:
        """Proposals made in this turn and not announced yet, oldest first."""
        fresh = [
            proposal.id
            for proposal in store.list_turn_proposals(user_turn_id)
            if proposal.id not in announced
        ]
        for proposal_id in fresh:
            announced.add(proposal_id)
            tool_uses.append({"proposal_id": proposal_id})
        return fresh

    try:
        async for event in _run_claude(
            session_id,
            prompt,
            repo_path=project.repo_path,
            executable=executable,
            model=model,
            env=session_env,
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
            for proposal_id in new_proposals():
                yield json.dumps({"type": "proposal", "proposal_id": proposal_id}) + "\n"
            save_progress()
        for proposal_id in new_proposals():
            yield json.dumps({"type": "proposal", "proposal_id": proposal_id}) + "\n"
        if after_turn is not None and not interrupted:
            for proposal_id in after_turn(user_turn_id):
                yield json.dumps({"type": "proposal", "proposal_id": proposal_id, "settled": True}) + "\n"
    except (asyncio.CancelledError, GeneratorExit):
        interrupted = True
        raise
    except Exception as exc:  # noqa: BLE001 - surface any backend failure as a turn error
        interrupted = True
        yield json.dumps({"type": "error", "message": f"Meta-agent stream failed: {exc}"}) + "\n"
    finally:
        if new_session_id and new_session_id != session_id:
            store.save_meta_session(project_id, new_session_id)
        # A proposal stored just before the stream broke still belongs to
        # this turn's record, so the conversation shows it again.
        try:
            new_proposals()
        except Exception:  # noqa: BLE001 - never lose the turn over this read
            pass
        persisted_tool_uses = list(tool_uses)
        if interrupted:
            persisted_tool_uses.append(REPLY_INTERRUPTED)
        store.update_meta_turn(reply_turn_id, text=assistant_text, tool_uses=persisted_tool_uses)

    if not interrupted:
        yield json.dumps({"type": "done", "session_id": new_session_id}) + "\n"
