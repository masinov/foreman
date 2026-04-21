#!/usr/bin/env python3

import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from foreman.store import ForemanStore
from foreman.supervisor_state import finalize_supervisor_merge as finalize_supervisor_merge_state

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_SERVER_CMD = os.environ.get("CODEX_APP_SERVER_CMD", "codex app-server")
CLIENT_INFO = {
    "name": "reviewed-codex",
    "version": "0.1.0",
}
TASK_COMPLETE_MARKER = "REVIEWED_CODEX_TASK_COMPLETE"
SPEC_COMPLETE_MARKER = "REVIEWED_CODEX_SPEC_COMPLETE"
STATUS_PATH = REPO_ROOT / "docs" / "STATUS.md"
CURRENT_SPRINT_PATH = REPO_ROOT / "docs" / "sprints" / "current.md"
BACKLOG_PATH = REPO_ROOT / "docs" / "sprints" / "backlog.md"
SPEC_PATH = REPO_ROOT / "docs" / "specs" / "engine-design-v3.md"
MOCKUP_PATH = REPO_ROOT / "docs" / "mockups" / "foreman-mockup-v6.html"

RUN_DIR = REPO_ROOT / ".codex" / "run"
RUN_DIR.mkdir(parents=True, exist_ok=True)

DEV_LOG = RUN_DIR / "developer.log"
REVIEW_LOG = RUN_DIR / "reviewer.log"
REVIEWER_CONFIG_PATH = REPO_ROOT / ".codex" / "agents" / "reviewer.toml"

DOC_PATHS = [
    REPO_ROOT / "AGENTS.md",
    STATUS_PATH,
    CURRENT_SPRINT_PATH,
    BACKLOG_PATH,
    SPEC_PATH,
    MOCKUP_PATH,
]

TEST_LINE_RE = re.compile(
    r"(\./venv/bin/python|pytest|unittest|git diff --check|Ran \d+ tests?|OK\b|FAILED\b|ERROR\b|Traceback)",
    re.IGNORECASE,
)

DEVELOPER_BOOTSTRAP_PROMPT = """
Continue autonomous development in this repository from current repo state.

Before non-trivial work, read:
- AGENTS.md
- docs/STATUS.md
- docs/sprints/current.md
- docs/sprints/backlog.md
- docs/specs/engine-design-v3.md
- docs/mockups/foreman-mockup-v6.html
- relevant ADRs
- relevant package README files
- relevant tests

Rules:
- follow AGENTS.md and repository docs as the source of truth
- do not ask the human to create branches, task files, or run commands
- own the full workflow yourself: planning, branch work, repo doc updates, code, tests, and PR summary
- use only ./venv/bin/python and ./venv/bin/pip for Python work
- work in one coherent slice at a time
- keep the repository in a reviewable state
- NEVER merge to main or commit directly to main while working a slice; the supervisor merges after reviewer approval
- when you receive reviewer feedback, apply it directly and continue autonomously
- never bypass a denied or approval-gated operation by editing tool-managed internal state directly
- use sanctioned commands for branch or repository state changes
- if a command needs approval and is denied or deferred, wait for supervisor feedback rather than trying to satisfy it by editing internal state files yourself
- keep working across as many turns as needed until the assigned work is actually complete; an intermediate turn ending does not mean the task is done
- when finishing a tracked slice, include a standalone line `TASK_ID: <task-id>` in your completion summary before the completion marker
- only when the assigned work is fully complete and ready for final review, end your final message with the exact line `{task_complete_marker}`
- if after reading docs/sprints/backlog.md and docs/STATUS.md there is genuinely no remaining work, end your message with the exact line `{spec_complete_marker}` instead — do not invent work

If docs/sprints/current.md is done, use docs/sprints/backlog.md and docs/STATUS.md
to select the next valid slice and update repo state as part of the same flow.

Proceed autonomously.
""".strip().format(
    task_complete_marker=TASK_COMPLETE_MARKER,
    spec_complete_marker=SPEC_COMPLETE_MARKER,
)

DEFAULT_REVIEWER_INSTRUCTIONS = """
You are the reviewer/project manager for the Foreman repository.

The authoritative product references are:
- docs/specs/engine-design-v3.md
- docs/mockups/foreman-mockup-v6.html

Use only surfaced evidence.
You are not a per-action gate for normal development work.
Review only risky approvals and completed work.

Return exactly one:
APPROVE
DENY: <reason>
STEER: <specific next action>
""".strip()

FINAL_REVIEW_PROMPT_TEMPLATE = """
AGENTS.md
{agents_md}

docs/STATUS.md
{status_md}

docs/sprints/current.md
{current_sprint_md}

docs/sprints/backlog.md
{backlog_md}

PRIMARY PRODUCT REFERENCES
- docs/specs/engine-design-v3.md
- docs/mockups/foreman-mockup-v6.html

BRANCH
{branch}

GIT STATUS
{git_status}

CHANGED FILES
{changed_files}

DIFF SUMMARY
{diff_summary}

TERMINAL OUTPUT TAIL
{terminal_tail}

TEST OUTPUT TAIL
{test_tail}

APPROVAL REQUEST
{approval_request}

DEVELOPER COMPLETION CLAIM
{completion_claim}

APPROVAL REVIEW RULES
- If APPROVAL REQUEST is not "None" and the requested action should happen now, return APPROVE even if follow-up steps are still required after it.
- Use STEER only when the requested action itself should not run yet.
- Never require or permit forbidden direct edits to tool-managed internal state as a substitute for a sanctioned command.

Return exactly one:
APPROVE
DENY: <reason>
STEER: <specific next action>
""".strip()

APPROVAL_REVIEW_PROMPT_TEMPLATE = """
REVIEW MODE
risky_approval

AGENTS.md
{agents_md}

BRANCH
{branch}

GIT STATUS
{git_status}

APPROVAL REQUEST
{approval_request}

RECENT TERMINAL OUTPUT
{terminal_tail}

RISKY APPROVAL REVIEW RULES
- Review only the surfaced approval request.
- Ignore unrelated dirty files or broader repo follow-up work unless the request itself is risky because of them.
- Do not restart project planning during approval review.
- Approve routine in-repo edits and normal development actions; deny or steer only when this specific request is risky or premature.
- Never require or permit forbidden direct edits to tool-managed internal state as a substitute for a sanctioned command.

Return exactly one:
APPROVE
DENY: <reason>
STEER: <specific next action>
""".strip()


@dataclass(frozen=True)
class ReviewerConfig:
    model: Optional[str]
    reasoning_effort: Optional[str]
    sandbox_mode: Optional[str]
    developer_instructions: str


BRANCH_COMMAND_RE = re.compile(
    r"git\s+(?:switch|checkout)(?:\s+-[bc])?\s+(?P<branch>[A-Za-z0-9._/-]+)"
)
FORBIDDEN_INTERNAL_STATE_PREFIXES = (".git",)
RISKY_COMMAND_PATTERNS = (
    re.compile(r"\bgit\s+(?:merge|rebase|reset|clean|push|pull|fetch|cherry-pick|tag)\b", re.IGNORECASE),
    re.compile(r"\bgit\s+checkout\s+--\b", re.IGNORECASE),
    re.compile(r"\bgit\s+branch\s+-D\b", re.IGNORECASE),
    re.compile(r"(^|[\s'\"`])rm\s", re.IGNORECASE),
    re.compile(r"(^|[\s'\"`])dd\s", re.IGNORECASE),
    re.compile(r"(^|[\s'\"`])mkfs\b", re.IGNORECASE),
    re.compile(r"(^|[\s'\"`])mount\b", re.IGNORECASE),
    re.compile(r"(^|[\s'\"`])umount\b", re.IGNORECASE),
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


COLOR_ENABLED = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None and os.environ.get("TERM") != "dumb"
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
AGENT_COLORS = {
    "SUPERVISOR": "\033[1;36m",
    "DEVELOPER": "\033[1;32m",
    "REVIEWER": "\033[1;33m",
    "RPC": "\033[1;34m",
}
ACTION_COLORS = {
    "error": "\033[1;31m",
    "decision": "\033[1;35m",
    "approval-request": "\033[1;35m",
    "approval-response": "\033[1;35m",
    "command": "\033[1;37m",
    "turn-start": "\033[1;37m",
    "turn-state": "\033[1;37m",
    "details": "\033[2m",
}


def apply_style(text: str, *styles: str) -> str:
    if not COLOR_ENABLED:
        return text
    prefix = "".join(style for style in styles if style)
    return f"{prefix}{text}{ANSI_RESET}" if prefix else text


def format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "none"
    if isinstance(value, str):
        return truncate_text(value, 320)
    return str(value)


def flatten_payload(payload: Any, prefix: str = "") -> List[str]:
    if payload is None:
        return []

    if isinstance(payload, dict):
        lines: List[str] = []
        for key, value in payload.items():
            if value in (None, "", [], {}):
                continue
            field = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                lines.extend(flatten_payload(value, field))
            elif isinstance(value, list):
                if not value:
                    continue
                if all(not isinstance(item, (dict, list)) for item in value):
                    rendered = ", ".join(format_scalar(item) for item in value)
                    lines.append(f"{field}: {rendered}")
                else:
                    for index, item in enumerate(value):
                        lines.extend(flatten_payload(item, f"{field}[{index}]"))
            else:
                lines.append(f"{field}: {format_scalar(value)}")
        return lines

    if isinstance(payload, list):
        if all(not isinstance(item, (dict, list)) for item in payload):
            return [", ".join(format_scalar(item) for item in payload)]
        lines: List[str] = []
        for index, item in enumerate(payload):
            lines.extend(flatten_payload(item, f"{prefix}[{index}]" if prefix else f"[{index}]"))
        return lines

    if prefix:
        return [f"{prefix}: {format_scalar(payload)}"]
    return [format_scalar(payload)]


def terminal_report(agent: str, action: str, message: str, *, payload: Any = None) -> None:
    timestamp = apply_style(f"[{utc_timestamp()}]", ANSI_DIM)
    agent_label = apply_style(agent.ljust(10), AGENT_COLORS.get(agent, ""), ANSI_BOLD)
    action_label = apply_style(action.ljust(18), ACTION_COLORS.get(action, ANSI_DIM))
    print(f"{timestamp} {agent_label} {action_label} {message}", flush=True)
    for line in flatten_payload(payload):
        detail_action = apply_style("details".ljust(18), ACTION_COLORS.get("details", ANSI_DIM))
        print(f"{timestamp} {agent_label} {detail_action} {line}", flush=True)


def relative_repo_path(path_text: str) -> str:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    try:
        return str(path.resolve(strict=False).relative_to(REPO_ROOT))
    except ValueError:
        return path_text


def is_forbidden_internal_state_path(path_text: str) -> bool:
    relative_path = relative_repo_path(path_text)
    return any(
        relative_path == prefix or relative_path.startswith(f"{prefix}/")
        for prefix in FORBIDDEN_INTERNAL_STATE_PREFIXES
    )


def forbidden_internal_change_paths(item: Dict[str, Any]) -> List[str]:
    paths: List[str] = []
    for change in item.get("changes", []):
        if not isinstance(change, dict):
            continue
        path = change.get("path")
        if isinstance(path, str) and is_forbidden_internal_state_path(path):
            paths.append(relative_repo_path(path))
    return paths


def split_reviewer_decision(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if stripped == "APPROVE":
        return "APPROVE", ""
    if stripped.startswith("DENY:"):
        return "DENY", stripped[5:].strip()
    if stripped.startswith("STEER:"):
        return "STEER", stripped[6:].strip()
    return "STEER", stripped


def extract_branch_name_from_command(command: str) -> Optional[str]:
    match = BRANCH_COMMAND_RE.search(command)
    if not match:
        return None
    return match.group("branch")


def steer_requires_requested_branch_change(method: str, params: Dict[str, Any], decision: str) -> bool:
    decision_kind, detail = split_reviewer_decision(decision)
    if decision_kind != "STEER":
        return False
    if method != "item/commandExecution/requestApproval":
        return False

    branch = extract_branch_name_from_command(params.get("command", ""))
    if not branch:
        return False

    lowered = detail.lower()
    if "do not" in lowered or "don't" in lowered:
        return False

    branch_lower = branch.lower()
    return branch_lower in lowered and any(
        phrase in lowered
        for phrase in (
            "create and switch",
            "switch to",
            "checkout",
            "proceed only on",
            "rather than `main`",
            "rather than main",
        )
    )


def is_risky_command(command: str) -> bool:
    normalized = command.strip()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in RISKY_COMMAND_PATTERNS)


def approval_requires_reviewer(method: str, params: Dict[str, Any]) -> bool:
    if method == "item/commandExecution/requestApproval":
        return is_risky_command(params.get("command", ""))
    if method == "item/fileChange/requestApproval":
        return params.get("grantRoot") is not None
    if method == "item/permissions/requestApproval":
        return True
    if method == "execCommandApproval":
        return True
    if method == "applyPatchApproval":
        return False
    return True


def developer_declared_completion(text: str) -> bool:
    return any(line.strip() == TASK_COMPLETE_MARKER for line in text.splitlines())


def developer_declared_spec_complete(text: str) -> bool:
    return any(line.strip() == SPEC_COMPLETE_MARKER for line in text.splitlines())


def extract_task_id(text: str) -> Optional[str]:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("TASK_ID:"):
            continue
        task_id = stripped.partition(":")[2].strip()
        return task_id or None
    return None


def truncate_text(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def summarize_input_items(items: List[Dict[str, Any]]) -> List[str]:
    previews: List[str] = []
    for item in items[:3]:
        item_type = item.get("type", "unknown")
        if item_type == "text":
            previews.append(f"text:{truncate_text(item.get('text', ''), 120)}")
        elif item_type == "image":
            previews.append(f"image:{truncate_text(item.get('url', ''), 80)}")
        elif item_type == "localImage":
            previews.append(f"localImage:{truncate_text(item.get('path', ''), 80)}")
        elif item_type in {"skill", "mention"}:
            previews.append(f"{item_type}:{truncate_text(item.get('name', ''), 80)}")
        else:
            previews.append(item_type)
    if len(items) > 3:
        previews.append(f"... +{len(items) - 3} more")
    return previews


def summarize_command_actions(actions: List[Dict[str, Any]]) -> List[str]:
    summaries: List[str] = []
    for action in actions[:4]:
        action_type = action.get("type", "unknown")
        target = action.get("path") or action.get("name") or action.get("command") or ""
        summaries.append(f"{action_type}:{truncate_text(str(target), 100)}")
    if len(actions) > 4:
        summaries.append(f"... +{len(actions) - 4} more")
    return summaries


def summarize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "type": item.get("type"),
        "id": item.get("id"),
    }
    item_type = item.get("type")

    if item_type == "commandExecution":
        summary.update(
            {
                "status": item.get("status"),
                "command": truncate_text(item.get("command", ""), 140),
                "cwd": item.get("cwd"),
                "exit_code": item.get("exitCode"),
                "duration_ms": item.get("durationMs"),
            }
        )
        if item.get("commandActions"):
            summary["actions"] = summarize_command_actions(item["commandActions"])
        if item.get("aggregatedOutput"):
            summary["output_preview"] = truncate_text(item["aggregatedOutput"], 180)
        return summary

    if item_type == "agentMessage":
        summary.update(
            {
                "phase": item.get("phase"),
                "text_preview": truncate_text(item.get("text", ""), 180),
            }
        )
        return summary

    if item_type == "userMessage":
        content = item.get("content") or []
        texts = [chunk.get("text", "") for chunk in content if chunk.get("type") == "text"]
        summary["text_preview"] = truncate_text(" ".join(texts), 180)
        return summary

    if item_type == "reasoning":
        summary["summary_count"] = len(item.get("summary", []))
        return summary

    return summary


def summarize_rpc_request(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if method == "initialize":
        return {"clientInfo": params.get("clientInfo")}
    if method == "thread/start":
        return {
            "cwd": params.get("cwd"),
            "approvalPolicy": params.get("approvalPolicy"),
            "sandbox": params.get("sandbox"),
            "personality": params.get("personality"),
            "model": params.get("model"),
            "developerInstructions_preview": truncate_text(params.get("developerInstructions", ""), 120)
            if params.get("developerInstructions")
            else None,
        }
    if method in {"turn/start", "turn/steer"}:
        summary: Dict[str, Any] = {
            "threadId": params.get("threadId"),
            "input_preview": summarize_input_items(params.get("input", [])),
        }
        if "expectedTurnId" in params:
            summary["expectedTurnId"] = params.get("expectedTurnId")
        if "effort" in params:
            summary["effort"] = params.get("effort")
        return summary
    return {"keys": sorted(params.keys())}


def summarize_rpc_response(method: str, result: Dict[str, Any]) -> Dict[str, Any]:
    if method == "initialize":
        return {
            "userAgent": result.get("userAgent"),
            "platformFamily": result.get("platformFamily"),
            "platformOs": result.get("platformOs"),
        }
    if method == "thread/start":
        thread = result.get("thread", {})
        return {
            "threadId": thread.get("id"),
            "model": result.get("model"),
            "approvalPolicy": result.get("approvalPolicy"),
            "approvalsReviewer": result.get("approvalsReviewer"),
            "cwd": result.get("cwd"),
        }
    if method in {"turn/start", "turn/steer"}:
        turn = result.get("turn", {})
        return {
            "turnId": turn.get("id"),
            "status": turn.get("status"),
        }
    return {"keys": sorted(result.keys())}


def summarize_notification(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if method.startswith("item/") and method.endswith("/requestApproval"):
        summary: Dict[str, Any] = {
            "threadId": params.get("threadId"),
            "turnId": params.get("turnId"),
            "itemId": params.get("itemId"),
            "reason": params.get("reason"),
        }
        if "command" in params:
            summary["command"] = truncate_text(str(params.get("command", "")), 180)
        if "grantRoot" in params:
            summary["grantRoot"] = params.get("grantRoot")
        if params.get("availableDecisions"):
            summary["availableDecisions"] = params.get("availableDecisions")
        return summary
    if "item" in params and isinstance(params["item"], dict):
        return {
            "threadId": params.get("threadId"),
            "turnId": params.get("turnId"),
            "item": summarize_item(params["item"]),
        }
    if method == "thread/status/changed":
        return {"threadId": params.get("threadId"), "status": params.get("status")}
    if method == "thread/tokenUsage/updated":
        total = (params.get("tokenUsage") or {}).get("total", {})
        return {
            "threadId": params.get("threadId"),
            "turnId": params.get("turnId"),
            "totalTokens": total.get("totalTokens"),
            "outputTokens": total.get("outputTokens"),
            "reasoningOutputTokens": total.get("reasoningOutputTokens"),
        }
    if "turn" in params and isinstance(params["turn"], dict):
        return {
            "threadId": params.get("threadId"),
            "turn": {
                "id": params["turn"].get("id"),
                "status": params["turn"].get("status"),
            },
        }
    if "delta" in params:
        return {
            "threadId": params.get("threadId"),
            "turnId": params.get("turnId"),
            "itemId": params.get("itemId"),
            "delta_preview": truncate_text(params.get("delta", ""), 80),
        }
    return {"keys": sorted(params.keys())}


def format_duration(duration_ms: Optional[int]) -> Optional[str]:
    if duration_ms is None:
        return None
    if duration_ms < 1000:
        return f"{duration_ms} ms"
    return f"{duration_ms / 1000:.2f} s"


def describe_item_event(method: str, item: Dict[str, Any], buffered_text: str = "") -> Optional[Dict[str, Any]]:
    item_type = item.get("type")

    if item_type == "commandExecution":
        command = truncate_text(item.get("command", ""), 180)
        actions = summarize_command_actions(item.get("commandActions", []))
        if method == "item/started":
            payload: Dict[str, Any] = {"cwd": item.get("cwd")}
            if actions:
                payload["actions"] = actions
            return {
                "action": "command",
                "message": f"Started command: {command}",
                "payload": payload,
            }

        status = item.get("status") or "completed"
        payload = {
            "status": status,
            "exit_code": item.get("exitCode"),
            "duration": format_duration(item.get("durationMs")),
        }
        if actions:
            payload["actions"] = actions
        if status != "completed" and item.get("aggregatedOutput"):
            payload["output"] = truncate_text(item["aggregatedOutput"], 220)
        return {
            "action": "command",
            "message": f"Finished command ({status}): {command}",
            "payload": payload,
        }

    if item_type == "agentMessage":
        if method != "item/completed":
            return None
        text = (item.get("text") or buffered_text).strip()
        payload = {"phase": item.get("phase")}
        if text:
            payload["text"] = truncate_text(text, 260)
        return {
            "action": "message",
            "message": "Completed agent message.",
            "payload": payload,
        }

    if item_type == "userMessage":
        if method != "item/started":
            return None
        content = item.get("content") or []
        texts = [chunk.get("text", "") for chunk in content if chunk.get("type") == "text"]
        return {
            "action": "message",
            "message": "Accepted user message.",
            "payload": {"text": truncate_text(" ".join(texts), 220)},
        }

    if item_type == "reasoning":
        verb = "Started" if method == "item/started" else "Completed"
        return {
            "action": "reasoning",
            "message": f"{verb} reasoning step.",
            "payload": {"summary_count": len(item.get('summary', []))} if method == "item/completed" else None,
        }

    if item_type == "fileChange":
        paths = [
            relative_repo_path(change.get("path", ""))
            for change in item.get("changes", [])
            if isinstance(change, dict) and change.get("path")
        ]
        return {
            "action": "file-change",
            "message": f"Applied file changes ({len(paths)} files).",
            "payload": {"paths": paths[:8]} if paths else None,
        }

    return {
        "action": "event",
        "message": f"Observed {method} for item type {item_type or 'unknown'}.",
        "payload": summarize_item(item),
    }


def describe_terminal_event(method: str, params: Dict[str, Any], buffered_text: str = "") -> Optional[Dict[str, Any]]:
    if method in {"turn/started", "turn/completed", "thread/tokenUsage/updated"}:
        return None

    if "item" in params and isinstance(params["item"], dict):
        return describe_item_event(method, params["item"], buffered_text=buffered_text)

    if method == "thread/status/changed":
        status = params.get("status") or {}
        status_type = status.get("type") if isinstance(status, dict) else status
        active_flags = status.get("activeFlags") if isinstance(status, dict) else None
        payload = {"active_flags": active_flags} if active_flags else None
        return {
            "action": "thread",
            "message": f"Thread status changed to {status_type or 'unknown'}.",
            "payload": payload,
        }

    if method.startswith("item/") and method.endswith("/requestApproval"):
        return {
            "action": "approval-request",
            "message": f"Approval requested via {method}.",
            "payload": summarize_notification(method, params),
        }

    return {
        "action": "event",
        "message": f"Observed {method}.",
        "payload": summarize_notification(method, params),
    }


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def ensure_repo_files() -> None:
    missing = [str(path.relative_to(REPO_ROOT)) for path in DOC_PATHS if not path.exists()]
    if missing:
        raise SystemExit(f"Missing required repo files: {', '.join(missing)}")
    terminal_report(
        "SUPERVISOR",
        "repo-check",
        "Validated required repository files.",
        payload={"files": [str(path.relative_to(REPO_ROOT)) for path in DOC_PATHS]},
    )


def run_git(args: List[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout or result.stderr).strip()


def run_git_command(args: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def current_branch() -> str:
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"])


def current_head() -> str:
    return run_git(["rev-parse", "HEAD"])


def worktree_dirty() -> bool:
    return bool(run_git(["status", "--short"]).strip())


def git_status() -> str:
    out = run_git(["status", "--short", "--branch"])
    return out or "(empty)"


def changed_files() -> str:
    out = run_git(["diff", "--name-only"])
    return out or "(none)"


def diff_summary() -> str:
    out = run_git(["diff", "--stat"])
    return out or "(none)"


def finalize_supervisor_merge(branch: str, *, task_id: Optional[str] = None) -> str:
    db_path = REPO_ROOT / ".foreman.db"
    if not db_path.exists():
        return f"repo-local database is missing: {db_path}"
    with ForemanStore(db_path) as store:
        store.initialize()
        result = finalize_supervisor_merge_state(
            store,
            repo_path=REPO_ROOT,
            branch_name=branch,
            task_id=task_id,
        )
    if result is None:
        return (
            "could not map the merged branch back to a tracked project task in SQLite; "
            "supervised completion state was not persisted"
        )
    terminal_report(
        "SUPERVISOR",
        "state-sync",
        "Persisted supervisor merge state to SQLite.",
        payload={
            "project_id": result.project_id,
            "task_id": result.task_id,
            "sprint_id": result.sprint_id,
            "task_status": result.task_status,
            "sprint_status": result.sprint_status,
            "stop_reason": result.stop_reason,
        },
    )
    return ""


def tail_text(path: Path, max_lines: int = 250) -> str:
    if not path.exists():
        return "(empty)"
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:]) if lines else "(empty)"


def test_tail(path: Path, max_lines: int = 120) -> str:
    if not path.exists():
        return "(empty)"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    filtered = [line for line in lines if TEST_LINE_RE.search(line)]
    return "\n".join(filtered[-max_lines:]) if filtered else "(no explicit test lines captured)"


def text_input(text: str) -> List[Dict[str, str]]:
    return [{"type": "text", "text": text}]


def load_reviewer_config() -> ReviewerConfig:
    text = read_text(REVIEWER_CONFIG_PATH)
    if not text:
        terminal_report(
            "SUPERVISOR",
            "reviewer-config",
            "Reviewer config file not found; using defaults.",
            payload={"path": str(REVIEWER_CONFIG_PATH.relative_to(REPO_ROOT))},
        )
        return ReviewerConfig(
            model="gpt-5.4",
            reasoning_effort="high",
            sandbox_mode="read-only",
            developer_instructions=DEFAULT_REVIEWER_INSTRUCTIONS,
        )

    def extract_scalar(key: str) -> Optional[str]:
        match = re.search(rf'^{re.escape(key)}\s*=\s*"([^"]*)"', text, re.MULTILINE)
        return match.group(1) if match else None

    def extract_multiline(key: str) -> Optional[str]:
        match = re.search(rf'^{re.escape(key)}\s*=\s*"""(.*?)"""', text, re.MULTILINE | re.DOTALL)
        if not match:
            return None
        return textwrap.dedent(match.group(1)).strip()

    config = ReviewerConfig(
        model=extract_scalar("model") or "gpt-5.4",
        reasoning_effort=extract_scalar("model_reasoning_effort") or "high",
        sandbox_mode=extract_scalar("sandbox_mode") or "read-only",
        developer_instructions=extract_multiline("developer_instructions") or DEFAULT_REVIEWER_INSTRUCTIONS,
    )
    terminal_report(
        "SUPERVISOR",
        "reviewer-config",
        "Loaded reviewer configuration.",
        payload={
            "path": str(REVIEWER_CONFIG_PATH.relative_to(REPO_ROOT)),
            "model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "sandbox_mode": config.sandbox_mode,
        },
    )
    return config


class JsonRpcClient:
    def __init__(self, cmd: str, cwd: Path):
        terminal_report(
            "RPC",
            "spawn",
            "Starting Codex app server.",
            payload={"command": cmd, "cwd": str(cwd)},
        )
        self.proc = subprocess.Popen(
            shlex.split(cmd),
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._next_id = 1
        self._pending_messages: Deque[Dict[str, Any]] = deque()
        self.call("initialize", {"clientInfo": CLIENT_INFO})
        terminal_report("RPC", "initialize", "Initialized Codex app server.", payload=CLIENT_INFO)

    def _write_json(self, payload: Dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def _read_message(self) -> Dict[str, Any]:
        assert self.proc.stdout is not None
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("Codex App Server closed unexpectedly")
            stripped = line.strip()
            if not stripped:
                continue
            return json.loads(stripped)

    def call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        req_id = self._next_id
        self._next_id += 1
        terminal_report(
            "RPC",
            "request",
            f"Sending {method}.",
            payload={"id": req_id, "request": summarize_rpc_request(method, params)},
        )
        self._write_json(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            }
        )

        while True:
            message = self._read_message()
            if message.get("id") == req_id and "method" not in message:
                if "error" in message:
                    terminal_report(
                        "RPC",
                        "error",
                        f"{method} failed.",
                        payload={"id": req_id, "error": message["error"]},
                    )
                    raise RuntimeError(f"RPC error for {method}: {message['error']}")
                terminal_report(
                    "RPC",
                    "response",
                    f"Received response for {method}.",
                    payload={"id": req_id, "response": summarize_rpc_response(method, message.get("result", {}))},
                )
                return message.get("result", {})
            self._pending_messages.append(message)

    def respond(self, request_id: Any, result: Dict[str, Any]) -> None:
        terminal_report(
            "RPC",
            "response",
            "Responding to server request.",
            payload={"id": request_id, "result": result},
        )
        self._write_json(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        )

    def next_message(self) -> Dict[str, Any]:
        if self._pending_messages:
            message = self._pending_messages.popleft()
        else:
            message = self._read_message()
        return message


class ReviewedCodex:
    def __init__(self) -> None:
        self.rpc = JsonRpcClient(APP_SERVER_CMD, REPO_ROOT)
        self.reviewer_config = load_reviewer_config()
        self.dev_thread_id: Optional[str] = None
        self.rev_thread_id: Optional[str] = None
        self.dev_turn_id: Optional[str] = None
        self.rev_turn_id: Optional[str] = None
        self.current_developer_output: List[str] = []
        self.last_developer_output: str = ""
        self.current_reviewer_output: List[str] = []
        self.agent_message_buffers: Dict[str, List[str]] = {}
        self.last_supervisor_merge_main_head: Optional[str] = None
        terminal_report("SUPERVISOR", "init", "ReviewedCodex supervisor initialized.")

    def append_log(self, path: Path, text: str) -> None:
        if not text:
            return
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")

    def start_thread(
        self,
        *,
        developer_instructions: Optional[str] = None,
        model: Optional[str] = None,
        sandbox_mode: Optional[str] = None,
        approval_policy: Optional[str] = None,
        personality: Optional[str] = "pragmatic",
    ) -> str:
        params: Dict[str, Any] = {"cwd": str(REPO_ROOT)}
        if developer_instructions is not None:
            params["developerInstructions"] = developer_instructions
        if model is not None:
            params["model"] = model
        if sandbox_mode is not None:
            params["sandbox"] = sandbox_mode
        if approval_policy is not None:
            params["approvalPolicy"] = approval_policy
        if personality is not None:
            params["personality"] = personality

        result = self.rpc.call("thread/start", params)
        thread_id = result["thread"]["id"]
        agent_label = "REVIEWER" if model == self.reviewer_config.model and sandbox_mode == self.reviewer_config.sandbox_mode and approval_policy == "never" else "DEVELOPER"
        terminal_report(
            agent_label,
            "thread-start",
            f"Started thread {thread_id}.",
            payload={
                "model": result.get("model"),
                "approval_policy": result.get("approvalPolicy"),
                "approvals_reviewer": result.get("approvalsReviewer"),
                "sandbox": result.get("sandbox"),
                "cwd": result.get("cwd"),
            },
        )
        return thread_id

    def start_turn(
        self,
        thread_id: str,
        prompt: str,
        *,
        effort: Optional[str] = None,
    ) -> str:
        params: Dict[str, Any] = {
            "threadId": thread_id,
            "input": text_input(prompt),
        }
        if effort is not None:
            params["effort"] = effort

        result = self.rpc.call("turn/start", params)
        turn_id = result["turn"]["id"]
        agent_label = "DEVELOPER" if thread_id == self.dev_thread_id else "REVIEWER" if thread_id == self.rev_thread_id else "SUPERVISOR"
        terminal_report(
            agent_label,
            "turn-start",
            f"Started turn {turn_id}.",
            payload={
                "thread_id": thread_id,
                "effort": effort,
                "prompt_preview": truncate_text(prompt),
            },
        )
        return turn_id

    def steer_turn(self, thread_id: str, turn_id: str, prompt: str) -> str:
        agent_label = "DEVELOPER" if thread_id == self.dev_thread_id else "REVIEWER"
        terminal_report(
            agent_label,
            "turn-steer",
            f"Steering active turn {turn_id}.",
            payload={"thread_id": thread_id, "prompt_preview": truncate_text(prompt)},
        )
        result = self.rpc.call(
            "turn/steer",
            {
                "threadId": thread_id,
                "expectedTurnId": turn_id,
                "input": text_input(prompt),
            },
        )
        next_turn_id = result.get("turn", {}).get("id", turn_id)
        terminal_report(
            agent_label,
            "turn-steered",
            f"Turn steering acknowledged for {turn_id}.",
            payload={"thread_id": thread_id, "current_turn_id": next_turn_id},
        )
        return next_turn_id

    def message_thread_id(self, event: Dict[str, Any]) -> Optional[str]:
        params = event.get("params", {})
        thread_id = params.get("threadId")
        if thread_id:
            return thread_id
        thread = params.get("thread")
        if isinstance(thread, dict):
            return thread.get("id")
        return None

    def record_turn_state(self, event: Dict[str, Any]) -> None:
        method = event.get("method")
        params = event.get("params", {})
        thread_id = self.message_thread_id(event)
        turn = params.get("turn")
        turn_id = turn.get("id") if isinstance(turn, dict) else params.get("turnId")

        if method == "turn/started" and turn_id:
            if thread_id == self.dev_thread_id:
                self.current_developer_output = []
                self.dev_turn_id = turn_id
                terminal_report("DEVELOPER", "turn-state", f"Turn is now active: {turn_id}.")
            elif thread_id == self.rev_thread_id:
                self.rev_turn_id = turn_id
                terminal_report("REVIEWER", "turn-state", f"Turn is now active: {turn_id}.")
        elif method == "turn/completed":
            if thread_id == self.dev_thread_id:
                terminal_report("DEVELOPER", "turn-state", f"Turn completed: {self.dev_turn_id}.")
                self.dev_turn_id = None
            elif thread_id == self.rev_thread_id:
                terminal_report("REVIEWER", "turn-state", f"Turn completed: {self.rev_turn_id}.")
                self.rev_turn_id = None

    def handle_thread_event(self, event: Dict[str, Any], thread_id: Optional[str], log_path: Path) -> None:
        if thread_id is None:
            return

        self.record_turn_state(event)

        if self.message_thread_id(event) != thread_id:
            return

        method = event.get("method", "")
        params = event.get("params", {})
        agent_label = "DEVELOPER" if thread_id == self.dev_thread_id else "REVIEWER" if thread_id == self.rev_thread_id else "SUPERVISOR"
        item = params.get("item", {})
        if (
            method in {"item/started", "item/completed"}
            and isinstance(item, dict)
            and item.get("type") == "fileChange"
        ):
            unsafe_paths = forbidden_internal_change_paths(item)
            if unsafe_paths:
                self.append_log(log_path, f"[forbidden-internal-edit] {json.dumps({'paths': unsafe_paths}, ensure_ascii=False)}")
                terminal_report(
                    "SUPERVISOR",
                    "error",
                    "Detected a forbidden direct edit to tool-managed internal state; stopping supervision.",
                    payload={"paths": unsafe_paths},
                )
                raise RuntimeError("Forbidden direct edit to tool-managed internal state detected")
        delta = params.get("delta")
        if isinstance(delta, str) and delta:
            self.append_log(log_path, delta)
            if method == "item/agentMessage/delta":
                item_id = params.get("itemId")
                if item_id:
                    self.agent_message_buffers.setdefault(item_id, []).append(delta)
                if thread_id == self.dev_thread_id:
                    self.current_developer_output.append(delta)
            return

        if method in {
            "turn/started",
            "turn/completed",
            "item/started",
            "item/completed",
            "thread/status/changed",
            "thread/tokenUsage/updated",
        }:
            self.append_log(log_path, f"[{method}] {json.dumps(params, ensure_ascii=False)}")
            if method in {"turn/started", "turn/completed", "thread/tokenUsage/updated"}:
                return
            buffered = ""
            if method == "item/completed":
                item = params.get("item", {})
                if isinstance(item, dict) and item.get("type") == "agentMessage":
                    item_id = item.get("id")
                    buffered = "".join(self.agent_message_buffers.pop(item_id, [])) if item_id else ""
            description = describe_terminal_event(method, params, buffered_text=buffered)
            if description is not None:
                terminal_report(
                    agent_label,
                    description["action"],
                    description["message"],
                    payload=description.get("payload"),
                )

    def start(self) -> None:
        terminal_report("SUPERVISOR", "startup", "Starting developer and reviewer threads.")
        self.dev_thread_id = self.start_thread(
            developer_instructions=DEVELOPER_BOOTSTRAP_PROMPT,
            approval_policy="on-request",
        )
        self.rev_thread_id = self.start_thread(
            developer_instructions=self.reviewer_config.developer_instructions,
            model=self.reviewer_config.model,
            sandbox_mode=self.reviewer_config.sandbox_mode,
            approval_policy="never",
        )
        self.dev_turn_id = self.start_turn(
            self.dev_thread_id,
            "Continue autonomous development in this repository from current repo state.",
        )
        terminal_report(
            "SUPERVISOR",
            "startup-complete",
            "Developer and reviewer startup completed.",
            payload={
                "developer_thread_id": self.dev_thread_id,
                "reviewer_thread_id": self.rev_thread_id,
                "developer_turn_id": self.dev_turn_id,
            },
        )

    def build_review_prompt(self, approval_request: Optional[Dict[str, Any]] = None) -> str:
        if approval_request is not None:
            return APPROVAL_REVIEW_PROMPT_TEMPLATE.format(
                agents_md=read_text(REPO_ROOT / "AGENTS.md"),
                branch=current_branch(),
                git_status=git_status(),
                approval_request=json.dumps(approval_request, indent=2),
                terminal_tail=tail_text(DEV_LOG, 80),
            )

        return FINAL_REVIEW_PROMPT_TEMPLATE.format(
            agents_md=read_text(REPO_ROOT / "AGENTS.md"),
            status_md=read_text(STATUS_PATH),
            current_sprint_md=read_text(CURRENT_SPRINT_PATH),
            backlog_md=read_text(BACKLOG_PATH),
            branch=current_branch(),
            git_status=git_status(),
            changed_files=changed_files(),
            diff_summary=diff_summary(),
            terminal_tail=tail_text(DEV_LOG, 250),
            test_tail=test_tail(DEV_LOG, 120),
            approval_request="None",
            completion_claim=truncate_text(self.last_developer_output, 600) if self.last_developer_output else "(empty)",
        )

    def continue_developer_turn(self, reason: str, *, allow_spec_complete: bool = False) -> None:
        assert self.dev_thread_id is not None
        prompt = f"{reason}\n\nContinue from the current repository state. Do not restart from scratch. Keep working until the assigned work is actually complete. "
        if allow_spec_complete:
            prompt += (
                f"If there is genuinely no remaining work, end your final message with the exact line {SPEC_COMPLETE_MARKER}. "
                f"Otherwise, only when the next slice is fully complete, end your final message with the exact line {TASK_COMPLETE_MARKER}."
            )
        else:
            prompt += f"Only end your final completion message with the exact line {TASK_COMPLETE_MARKER}."
        terminal_report(
            "SUPERVISOR",
            "developer-continue",
            "Developer turn ended without completion; starting another turn.",
            payload={"reason": reason, "allow_spec_complete": allow_spec_complete},
        )
        self.dev_turn_id = self.start_turn(self.dev_thread_id, prompt)

    def normalize_decision(self, text: str) -> str:
        stripped = text.strip()
        for line in reversed(stripped.splitlines()):
            candidate = line.strip()
            if candidate == "APPROVE":
                return "APPROVE"
            if candidate.startswith("DENY:"):
                return candidate
            if candidate.startswith("STEER:"):
                return candidate
        return f"STEER: reviewer output was malformed; revise and continue.\n\n{text}"

    def ask_reviewer(self, approval_request: Optional[Dict[str, Any]] = None) -> str:
        assert self.rev_thread_id is not None
        self.current_reviewer_output = []
        approval_summary = None
        if approval_request:
            approval_summary = {
                "method": approval_request.get("method"),
                "summary": summarize_notification(
                    approval_request.get("method", ""),
                    approval_request.get("params", {}),
                ),
            }
        terminal_report(
            "SUPERVISOR",
            "review-pass",
            "Starting reviewer pass.",
            payload={"approval_request": approval_summary},
        )
        self.rev_turn_id = self.start_turn(
            self.rev_thread_id,
            self.build_review_prompt(approval_request=approval_request),
            effort=self.reviewer_config.reasoning_effort,
        )

        while True:
            event = self.rpc.next_message()
            method = event.get("method")
            if not method:
                continue

            thread_id = self.message_thread_id(event)
            if thread_id == self.rev_thread_id:
                self.handle_thread_event(event, self.rev_thread_id, REVIEW_LOG)
                delta = event.get("params", {}).get("delta")
                if isinstance(delta, str) and delta:
                    self.current_reviewer_output.append(delta)
                if method == "turn/completed":
                    text = "".join(self.current_reviewer_output).strip()
                    if not text:
                        text = tail_text(REVIEW_LOG, 40)
                    decision = self.normalize_decision(text)
                    self.append_log(REVIEW_LOG, f"[decision] {decision}")
                    terminal_report(
                        "REVIEWER",
                        "decision",
                        f"Reviewer returned {decision}.",
                        payload={"review_preview": truncate_text(text, 240)},
                    )
                    return decision
            elif thread_id == self.dev_thread_id:
                self.handle_thread_event(event, self.dev_thread_id, DEV_LOG)

    def reviewer_allows_approval_request(self, method: str, params: Dict[str, Any], decision: str) -> bool:
        decision_kind, _ = split_reviewer_decision(decision)
        if decision_kind == "APPROVE":
            return True
        if steer_requires_requested_branch_change(method, params, decision):
            return True
        return False

    def approval_result(
        self,
        method: str,
        params: Dict[str, Any],
        decision: str,
        *,
        approved: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if approved is None:
            approved = self.reviewer_allows_approval_request(method, params, decision)
        cancel_decision = "cancel" if "cancel" in (params.get("availableDecisions") or []) else "decline"

        if method == "item/commandExecution/requestApproval":
            result = {"decision": "accept" if approved else cancel_decision}
            terminal_report("SUPERVISOR", "approval-map", f"Mapped {method} to {result['decision']}.", payload=result)
            return result
        if method == "item/fileChange/requestApproval":
            result = {"decision": "accept" if approved else cancel_decision}
            terminal_report("SUPERVISOR", "approval-map", f"Mapped {method} to {result['decision']}.", payload=result)
            return result
        if method == "item/permissions/requestApproval":
            result = {
                "permissions": params.get("permissions") if approved else {},
                "scope": "turn",
            }
            terminal_report("SUPERVISOR", "approval-map", f"Mapped {method} to {'granted' if approved else 'cleared'}.", payload=result)
            return result
        if method == "execCommandApproval":
            result = {"decision": "approved" if approved else "denied"}
            terminal_report("SUPERVISOR", "approval-map", f"Mapped {method} to {result['decision']}.", payload=result)
            return result
        if method == "applyPatchApproval":
            result = {"decision": "approved" if approved else "denied"}
            terminal_report("SUPERVISOR", "approval-map", f"Mapped {method} to {result['decision']}.", payload=result)
            return result

        raise RuntimeError(f"Unsupported approval request method: {method}")

    def steer_or_restart_developer(self, decision: str, *, prior_request_already_satisfied: bool = False) -> None:
        assert self.dev_thread_id is not None
        prompt = f"Reviewer feedback:\n{decision}\n\n"
        if prior_request_already_satisfied:
            prompt += (
                "The supervisor has already approved and answered the specific request that triggered this review. "
                "Do not request or attempt that same action again. Treat it as satisfied, continue with only the remaining follow-up work, "
                "and do not bypass denied or approval-gated operations by editing internal state files directly."
            )
        else:
            prompt += "Revise and continue autonomously. Do not bypass denied or approval-gated operations by editing internal state files directly."
        if self.dev_turn_id is not None:
            terminal_report("SUPERVISOR", "developer-steer", "Steering active developer turn.", payload={"turn_id": self.dev_turn_id, "decision": decision})
            self.dev_turn_id = self.steer_turn(self.dev_thread_id, self.dev_turn_id, prompt)
        else:
            terminal_report("SUPERVISOR", "developer-restart", "Developer turn already completed; starting a new turn.", payload={"decision": decision})
            self.dev_turn_id = self.start_turn(self.dev_thread_id, prompt)

    def merge_branch_into_main(self, branch: str) -> str:
        if not branch or branch == "main":
            return ""

        result = run_git_command(["switch", "main"])
        if result.returncode != 0:
            error = (result.stderr or result.stdout).strip() or "git switch main failed"
            terminal_report(
                "SUPERVISOR",
                "merge-fail",
                "Could not switch to main for automatic merge.",
                payload={"branch": branch, "error": truncate_text(error, 240)},
            )
            return error

        result = run_git_command(
            ["merge", "--no-ff", branch, "-m", f"merge: {branch} into main"]
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout).strip() or "git merge failed"
            terminal_report(
                "SUPERVISOR",
                "merge-fail",
                "Automatic merge into main failed.",
                payload={"branch": branch, "error": truncate_text(error, 240)},
            )
            return error

        terminal_report(
            "SUPERVISOR",
            "merge-ok",
            f"Merged {branch} into main.",
        )
        return ""

    def handle_approved_completion(self) -> None:
        branch = current_branch()

        if branch == "main":
            terminal_report(
                "SUPERVISOR",
                "main-violation",
                "Approved work is currently on main; developer must recover branch isolation before continuing.",
            )
            self.continue_developer_turn(
                "VIOLATION: the approved work is currently on `main`. This is forbidden. "
                "Create or recover a feature branch containing the approved work, restore `main` to the correct state using sanctioned git commands, "
                "and continue autonomous development only from a feature branch.",
                allow_spec_complete=True,
            )
            return

        merge_error = self.merge_branch_into_main(branch)
        if merge_error:
            self.continue_developer_turn(
                f"Reviewer approved the completed work but the automatic merge of `{branch}` into `main` failed:\n\n"
                f"{merge_error}\n\n"
                "Finalize the approved slice by committing any remaining changes if needed, resolve the branch or merge issue, merge the branch into `main`, "
                "and then continue autonomous development from the updated repository state.",
                allow_spec_complete=True,
            )
            return

        state_error = finalize_supervisor_merge(
            branch,
            task_id=extract_task_id(self.last_developer_output),
        )
        if state_error:
            self.continue_developer_turn(
                f"Reviewer approved the completed work and the branch `{branch}` was merged into `main`, "
                "but the supervisor could not reconcile the SQLite runtime state:\n\n"
                f"{state_error}\n\n"
                "Create a new feature branch from the merged `main`, reconcile the missing backend state through sanctioned repository changes, "
                "and continue autonomous development only after the persisted project state matches git history.",
                allow_spec_complete=True,
            )
            return

        self.last_supervisor_merge_main_head = current_head()
        self.continue_developer_turn(
            f"Reviewer approved the completed work. Branch `{branch}` has been merged into `main`.\n\n"
            "Continue autonomous development: read `docs/STATUS.md` and `docs/sprints/backlog.md` to select the next valid slice, update repo state as part of the same flow, and proceed autonomously.",
            allow_spec_complete=True,
        )

    def post_merge_main_violation_reason(self) -> Optional[str]:
        if self.last_supervisor_merge_main_head is None:
            return None
        if current_branch() != "main":
            return None
        if worktree_dirty():
            return (
                "VIOLATION: the supervisor already merged the approved slice into `main`, "
                "but there are still uncommitted changes on `main`. Create a new feature branch "
                "for any further work or discard the accidental main-only edits before continuing. "
                "If there is genuinely no remaining work, return to a clean merged `main` first and then emit "
                f"{SPEC_COMPLETE_MARKER}."
            )
        if current_head() != self.last_supervisor_merge_main_head:
            return (
                "VIOLATION: the supervisor already merged the approved slice into `main`, "
                "but new commits were created on `main` afterward. Move any follow-up work onto a new feature branch, "
                "or restore `main` to the supervisor-merged commit before continuing. "
                "If there is genuinely no remaining work, return to the clean merged `main` first and then emit "
                f"{SPEC_COMPLETE_MARKER}."
            )
        return None

    def loop(self) -> None:
        assert self.dev_thread_id is not None
        terminal_report("SUPERVISOR", "loop", "Entering supervisor event loop.")

        while True:
            event = self.rpc.next_message()
            method = event.get("method")
            if not method:
                continue

            thread_id = self.message_thread_id(event)
            if thread_id == self.dev_thread_id:
                self.handle_thread_event(event, self.dev_thread_id, DEV_LOG)

            if method == "turn/completed" and thread_id == self.dev_thread_id:
                self.last_developer_output = "".join(self.current_developer_output).strip()
                main_violation = self.post_merge_main_violation_reason()
                if main_violation is not None:
                    terminal_report(
                        "SUPERVISOR",
                        "main-violation",
                        "Detected post-merge work on main after supervisor approval.",
                        payload={"main_head": current_head()},
                    )
                    self.continue_developer_turn(main_violation, allow_spec_complete=True)
                    continue
                if developer_declared_spec_complete(self.last_developer_output):
                    terminal_report(
                        "SUPERVISOR",
                        "spec-complete",
                        "Developer declared the full Foreman backlog complete. Stopping supervision.",
                        payload={"completion_marker": SPEC_COMPLETE_MARKER},
                    )
                    return
                if not developer_declared_completion(self.last_developer_output):
                    self.continue_developer_turn(
                        "The previous developer turn ended without an explicit completion marker."
                    )
                    continue
                terminal_report(
                    "SUPERVISOR",
                    "review-trigger",
                    "Developer declared completion; requesting reviewer decision.",
                    payload={"completion_marker": TASK_COMPLETE_MARKER},
                )
                decision = self.ask_reviewer()
                if decision != "APPROVE":
                    self.steer_or_restart_developer(decision)
                else:
                    terminal_report(
                        "SUPERVISOR",
                        "review-approve",
                        "Reviewer approved the current slice; finalizing it and continuing autonomous development.",
                    )
                    self.handle_approved_completion()
                    continue

            if method in {
                "item/commandExecution/requestApproval",
                "item/fileChange/requestApproval",
                "item/permissions/requestApproval",
                "execCommandApproval",
                "applyPatchApproval",
            }:
                params = event.get("params", {})
                if params.get("threadId") == self.dev_thread_id:
                    if params.get("turnId"):
                        self.dev_turn_id = params.get("turnId")
                    self.append_log(DEV_LOG, f"[{method}] {json.dumps(params, ensure_ascii=False)}")
                    description = describe_terminal_event(method, params)
                    if description is not None:
                        terminal_report(
                            "DEVELOPER",
                            description["action"],
                            description["message"],
                            payload=description.get("payload"),
                        )
                    if approval_requires_reviewer(method, params):
                        terminal_report(
                            "SUPERVISOR",
                            "approval-review",
                            "Routing risky approval request to reviewer.",
                            payload={"method": method, "reason": params.get("reason")},
                        )
                        decision = self.ask_reviewer(
                            approval_request={
                                "method": method,
                                "params": params,
                            }
                        )
                        approved_request = self.reviewer_allows_approval_request(method, params, decision)
                    else:
                        decision = "APPROVE"
                        approved_request = True
                        terminal_report(
                            "SUPERVISOR",
                            "approval-auto",
                            "Auto-approving routine request without reviewer.",
                            payload={"method": method, "reason": params.get("reason")},
                        )
                    self.rpc.respond(
                        event["id"],
                        self.approval_result(method, params, decision, approved=approved_request),
                    )
                    terminal_report(
                        "SUPERVISOR",
                        "approval-response",
                        f"Responded to {method} with reviewer decision {decision}.",
                        payload={"request_approved": approved_request},
                    )
                    if split_reviewer_decision(decision)[0] != "APPROVE":
                        self.steer_or_restart_developer(
                            decision,
                            prior_request_already_satisfied=approved_request,
                        )


def main() -> int:
    ensure_repo_files()
    DEV_LOG.write_text("", encoding="utf-8")
    REVIEW_LOG.write_text("", encoding="utf-8")
    terminal_report(
        "SUPERVISOR",
        "log-reset",
        "Reset developer and reviewer log files.",
        payload={
            "developer_log": str(DEV_LOG.relative_to(REPO_ROOT)),
            "reviewer_log": str(REVIEW_LOG.relative_to(REPO_ROOT)),
        },
    )

    runner = ReviewedCodex()
    runner.start()
    runner.loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
