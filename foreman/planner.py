"""Sprint planner chat session service.

Provides a turn-by-turn conversational planning session backed by the
Anthropic Messages API.  The planner has access to eight Foreman management
tools (list/create/update/delete for sprints and tasks) that call the
existing DashboardService methods directly.

Session history is kept in memory keyed by project_id.  One active session
per project for this MVP; history is lost on server restart.  A future slice
can move history to a planner_sessions SQLite table.
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

from .dashboard_service import DashboardService, DashboardNotFoundError, DashboardValidationError

# ---------------------------------------------------------------------------
# Tool definitions (JSON schema for the Anthropic tool_use API)
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "foreman_list_sprints",
        "description": "List all sprints for the current project.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "foreman_create_sprint",
        "description": "Create a new planned sprint.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Sprint title"},
                "goal": {"type": "string", "description": "Sprint goal (optional)"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "foreman_update_sprint",
        "description": "Update a sprint's title, goal, or order_index.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sprint_id": {"type": "string"},
                "title": {"type": "string"},
                "goal": {"type": "string"},
                "order_index": {"type": "integer"},
            },
            "required": ["sprint_id"],
        },
    },
    {
        "name": "foreman_delete_sprint",
        "description": "Delete a sprint by id. Only planned or cancelled sprints can be deleted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sprint_id": {"type": "string"},
            },
            "required": ["sprint_id"],
        },
    },
    {
        "name": "foreman_list_tasks",
        "description": "List all tasks in a sprint.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sprint_id": {"type": "string"},
            },
            "required": ["sprint_id"],
        },
    },
    {
        "name": "foreman_create_task",
        "description": "Create a new task inside a sprint.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sprint_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "task_type": {
                    "type": "string",
                    "enum": ["feature", "fix", "refactor", "docs", "spike", "chore"],
                },
                "acceptance_criteria": {"type": "string"},
            },
            "required": ["sprint_id", "title"],
        },
    },
    {
        "name": "foreman_update_task",
        "description": "Update a task's title, description, task_type, or acceptance_criteria.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "task_type": {
                    "type": "string",
                    "enum": ["feature", "fix", "refactor", "docs", "spike", "chore"],
                },
                "acceptance_criteria": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "foreman_delete_task",
        "description": "Delete a task by id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
]

# ---------------------------------------------------------------------------
# Session store (in-memory MVP)
# ---------------------------------------------------------------------------

# Maps project_id → list of {"role": "user"|"assistant", "content": ...}
_sessions: dict[str, list[dict[str, Any]]] = {}


def get_session_history(project_id: str) -> list[dict[str, Any]]:
    return list(_sessions.get(project_id, []))


def clear_session(project_id: str) -> None:
    _sessions.pop(project_id, None)


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def _execute_tool(
    name: str,
    tool_input: dict[str, Any],
    *,
    project_id: str,
    api: DashboardService,
) -> Any:
    """Execute one Foreman tool call and return a JSON-serialisable result."""

    try:
        if name == "foreman_list_sprints":
            return api.list_project_sprints(project_id)

        if name == "foreman_create_sprint":
            return api.create_sprint(
                project_id,
                title=str(tool_input["title"]),
                goal=tool_input.get("goal"),
            )

        if name == "foreman_update_sprint":
            updates = {k: v for k, v in tool_input.items() if k != "sprint_id"}
            return api.update_sprint_fields(str(tool_input["sprint_id"]), updates=updates)

        if name == "foreman_delete_sprint":
            return api.delete_sprint(str(tool_input["sprint_id"]))

        if name == "foreman_list_tasks":
            return api.list_sprint_tasks(str(tool_input["sprint_id"]))

        if name == "foreman_create_task":
            sprint_id = str(tool_input["sprint_id"])
            return api.create_task(
                sprint_id,
                title=str(tool_input["title"]),
                description=tool_input.get("description"),
                task_type=tool_input.get("task_type", "feature"),
                acceptance_criteria=tool_input.get("acceptance_criteria"),
            )

        if name == "foreman_update_task":
            updates = {k: v for k, v in tool_input.items() if k != "task_id"}
            return api.update_task_fields(str(tool_input["task_id"]), updates=updates)

        if name == "foreman_delete_task":
            return api.delete_task(str(tool_input["task_id"]))

        return {"error": f"Unknown tool: {name}"}

    except (DashboardNotFoundError, DashboardValidationError) as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Main planner entry point
# ---------------------------------------------------------------------------

async def process_message(
    project_id: str,
    user_message: str,
    *,
    api: DashboardService,
    model: str = "claude-opus-4-6",
) -> AsyncIterator[str]:
    """Process one user message and yield NDJSON lines.

    Each line is a JSON object with one of these shapes:
      {"type": "text_delta", "text": "..."}
      {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
      {"type": "tool_result", "tool_use_id": "...", "name": "...", "result": {...}}
      {"type": "done"}
      {"type": "error", "message": "..."}
    """

    try:
        import anthropic as _anthropic
    except ImportError:
        yield _ndjson({"type": "error", "message": "Anthropic SDK not installed."})
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        yield _ndjson({"type": "error", "message": "ANTHROPIC_API_KEY is not set."})
        return

    # Build context summary for system prompt injection
    try:
        sprints_data = api.list_project_sprints(project_id)
        project_data = api.get_project(project_id)
        sprint_lines = [
            f"- [{s['status']}] {s['title']} (id: {s['id']})"
            for s in sprints_data.get("sprints", [])
        ]
        sprint_summary = "\n".join(sprint_lines) if sprint_lines else "No sprints yet."
        project_name = project_data.get("name", project_id)
    except Exception:
        sprint_summary = "(could not load sprints)"
        project_name = project_id

    system = (
        f"You are a sprint planning collaborator for the Foreman project "
        f'management system. You are helping with the project "{project_name}" '
        f"(id: {project_id}).\n\n"
        f"Current sprint queue:\n{sprint_summary}\n\n"
        "Use the Foreman management tools to apply changes directly when the "
        "user asks — do not describe changes without applying them unless the "
        "user asks to preview first.\n\n"
        "Keep sprint goals concise and outcome-focused. Tasks should be concrete "
        "and independently executable by an AI agent. Prefer 3-7 tasks per sprint. "
        "Order sprints by logical dependency.\n\n"
        "You do not have access to code execution or file system tools."
    )

    # Append user message to session history
    history = _sessions.setdefault(project_id, [])
    history.append({"role": "user", "content": user_message})

    client = _anthropic.AsyncAnthropic(api_key=api_key)

    # Tool-use loop: keep calling the API until no more tool_use blocks
    while True:
        collected_text = ""
        tool_uses: list[dict[str, Any]] = []

        async with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system,
            messages=history,
            tools=_TOOLS,  # type: ignore[arg-type]
        ) as stream:
            async for event in stream:
                event_type = type(event).__name__

                if event_type == "RawContentBlockDeltaEvent":
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", None) == "text_delta":
                        chunk = delta.text
                        collected_text += chunk
                        yield _ndjson({"type": "text_delta", "text": chunk})

                elif event_type == "RawContentBlockStartEvent":
                    block = getattr(event, "content_block", None)
                    if block and getattr(block, "type", None) == "tool_use":
                        tool_uses.append({
                            "id": block.id,
                            "name": block.name,
                            "input_raw": "",
                        })

                elif event_type == "RawContentBlockDeltaEvent":
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", None) == "input_json_delta" and tool_uses:
                        tool_uses[-1]["input_raw"] += delta.partial_json

            final = await stream.get_final_message()

        # Parse tool inputs and build assistant message content
        assistant_content: list[dict[str, Any]] = []
        if collected_text:
            assistant_content.append({"type": "text", "text": collected_text})

        parsed_tool_uses: list[dict[str, Any]] = []
        for tu in tool_uses:
            try:
                parsed_input = json.loads(tu["input_raw"]) if tu["input_raw"] else {}
            except json.JSONDecodeError:
                parsed_input = {}
            parsed_tool_uses.append({
                "id": tu["id"],
                "name": tu["name"],
                "input": parsed_input,
            })
            assistant_content.append({
                "type": "tool_use",
                "id": tu["id"],
                "name": tu["name"],
                "input": parsed_input,
            })

        # Persist assistant turn
        if assistant_content:
            history.append({"role": "assistant", "content": assistant_content})

        # No tool use — conversation turn is complete
        if not parsed_tool_uses:
            break

        # Execute tools and stream results
        tool_results: list[dict[str, Any]] = []
        for tu in parsed_tool_uses:
            yield _ndjson({"type": "tool_use", "id": tu["id"], "name": tu["name"], "input": tu["input"]})
            result = _execute_tool(tu["name"], tu["input"], project_id=project_id, api=api)
            yield _ndjson({"type": "tool_result", "tool_use_id": tu["id"], "name": tu["name"], "result": result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": json.dumps(result),
            })

        # Add tool results as user turn and loop
        history.append({"role": "user", "content": tool_results})

    yield _ndjson({"type": "done"})


def _ndjson(obj: dict[str, Any]) -> str:
    return json.dumps(obj) + "\n"
