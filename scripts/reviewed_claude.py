#!/usr/bin/env python3
"""reviewed_claude.py

Autonomous development supervisor using Claude Code (--print mode).

Mirrors reviewed_codex.py but drives `claude --print` via subprocess
instead of the Codex JSON-RPC protocol.

The developer loop runs until:
- The developer ends a turn with REVIEWED_CLAUDE_TASK_COMPLETE (task done,
  reviewer pass runs; on APPROVE the branch is merged and the next task starts)
- The developer ends a turn with REVIEWED_CLAUDE_SPEC_COMPLETE (backlog
  genuinely empty, loop exits cleanly)
- MAX_CONSECUTIVE_API_FAILURES consecutive API/process errors (credits
  exhausted or provider down, loop exits with an error message)

Usage:
    python scripts/reviewed_claude.py

Environment variables (all optional):
    CLAUDE_DEV_MODEL    model for the developer (default: claude default)
    CLAUDE_DEV_EFFORT   effort level for the developer (low/medium/high/max)
"""

import json
import os
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from foreman.store import ForemanStore
from foreman.supervisor_state import finalize_supervisor_merge as finalize_supervisor_merge_state

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_COMPLETE_MARKER = "REVIEWED_CLAUDE_TASK_COMPLETE"
SPEC_COMPLETE_MARKER = "REVIEWED_CLAUDE_SPEC_COMPLETE"
MAX_CONSECUTIVE_API_FAILURES = 3
STATUS_PATH = REPO_ROOT / "docs" / "STATUS.md"
CURRENT_SPRINT_PATH = REPO_ROOT / "docs" / "sprints" / "current.md"
BACKLOG_PATH = REPO_ROOT / "docs" / "sprints" / "backlog.md"
SPEC_PATH = REPO_ROOT / "docs" / "specs" / "engine-design-v3.md"
MOCKUP_PATH = REPO_ROOT / "docs" / "mockups" / "foreman-mockup-v6.html"

RUN_DIR = REPO_ROOT / ".claude" / "run"
RUN_DIR.mkdir(parents=True, exist_ok=True)

DEV_LOG = RUN_DIR / "developer.log"
REVIEW_LOG = RUN_DIR / "reviewer.log"
REVIEWER_CONFIG_PATH = REPO_ROOT / ".claude" / "agents" / "reviewer.toml"

DOC_PATHS = [
    REPO_ROOT / "AGENTS.md",
    STATUS_PATH,
    CURRENT_SPRINT_PATH,
    BACKLOG_PATH,
    SPEC_PATH,
    MOCKUP_PATH,
]


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
- NEVER merge to main or commit directly to main — work on a feature branch; the supervisor merges after reviewer approval
- when you receive reviewer feedback, apply it directly and continue autonomously
- keep working across as many turns as needed until the assigned work is actually complete; an intermediate turn ending does not mean the task is done
- when finishing a tracked slice, include the exact task id in the completion summary
- only when the assigned work is fully complete and ready for final review, write a structured completion summary (see format below) and then end your final message with the exact line `{task_complete_marker}`
- if after reading docs/sprints/backlog.md and docs/STATUS.md there is genuinely no remaining work (all backlog tasks are done and no follow-ups are recorded), end your message with the exact line `{spec_complete_marker}` instead — do not invent work

If docs/sprints/current.md is done, use docs/sprints/backlog.md and docs/STATUS.md
to select the next valid slice and update repo state as part of the same flow.

COMPLETION SUMMARY FORMAT
When you are done, your final message must include the following structured block
before the {task_complete_marker} line. The reviewer receives only this summary
plus basic git state — make it self-contained.

## Completion summary

**Sprint**: <sprint id>
**Branch**: <branch name>
**Task ID**: <task id>
**Task**: <one-sentence description of what was done>

**What was implemented**:
- <bullet per logical unit of work>

**Files changed**:
- <path> — <what changed>

**Tests**: <N new tests added>, <M total tests pass>

**Acceptance criteria satisfied**:
- [x] <criterion>

**Docs updated**: <which docs were updated>

**Follow-ups**:
- <any incomplete edges or recommended next tasks>

Proceed autonomously.
""".strip().format(
    task_complete_marker=TASK_COMPLETE_MARKER,
    spec_complete_marker=SPEC_COMPLETE_MARKER,
)

DEFAULT_REVIEWER_INSTRUCTIONS = """
You are the reviewer/project manager for the Foreman repository.

You receive a structured completion summary from the developer plus basic git state.
You have Read, Glob, and Grep tools available — use them to verify the developer's
claims directly against the repository before deciding.

Do not approve based on the summary alone. Verify:
1. The claimed files exist and contain what the summary describes.
2. The claimed tests exist and the test count is plausible.
3. The sprint and backlog docs reflect the completed work.
4. The branch name matches the sprint or task scope.
5. The work stays within the approved product direction (check AGENTS.md plus
   `docs/specs/engine-design-v3.md` and `docs/mockups/foreman-mockup-v6.html`).

Return exactly one of:

APPROVE
DENY: <reason>
STEER: <specific next action>

Ground denial or steering in evidence you verified directly in the repository.
Do not ask the human to create branches, task files, or run commands.
""".strip()

FINAL_REVIEW_PROMPT_TEMPLATE = """
DEVELOPER COMPLETION SUMMARY
{completion_summary}

BRANCH
{branch}

GIT STATUS
{git_status}

CHANGED FILES
{changed_files}

RECENT COMMITS
{recent_commits}

PRIMARY PRODUCT REFERENCES
- docs/specs/engine-design-v3.md
- docs/mockups/foreman-mockup-v6.html

REVIEW INSTRUCTIONS
Use your Read, Glob, and Grep tools to verify the claims in the summary above.
Check the files listed, confirm the tests exist and pass count is plausible,
and verify that sprint/backlog docs reflect the completed work.

Return exactly one:
APPROVE
DENY: <reason>
STEER: <specific next action>
""".strip()

# ─── Colours ──────────────────────────────────────────────────────────────────

COLOR_ENABLED = (
    sys.stdout.isatty()
    and os.environ.get("NO_COLOR") is None
    and os.environ.get("TERM") != "dumb"
)
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
AGENT_COLORS = {
    "SUPERVISOR": "\033[1;36m",
    "DEVELOPER": "\033[1;32m",
    "REVIEWER": "\033[1;33m",
}
ACTION_COLORS = {
    "error": "\033[1;31m",
    "decision": "\033[1;35m",
    "turn-start": "\033[1;37m",
    "turn-state": "\033[1;37m",
    "details": "\033[2m",
}


def apply_style(text: str, *styles: str) -> str:
    if not COLOR_ENABLED:
        return text
    prefix = "".join(s for s in styles if s)
    return f"{prefix}{text}{ANSI_RESET}" if prefix else text


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def truncate_text(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


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
                    lines.append(f"{field}: {', '.join(str(i) for i in value)}")
                else:
                    for idx, item in enumerate(value):
                        lines.extend(flatten_payload(item, f"{field}[{idx}]"))
            else:
                val = "true" if value is True else "false" if value is False else str(value)
                lines.append(f"{field}: {truncate_text(val, 320)}")
        return lines
    if isinstance(payload, list):
        lines = []
        for idx, item in enumerate(payload):
            lines.extend(flatten_payload(item, f"{prefix}[{idx}]" if prefix else f"[{idx}]"))
        return lines
    val = str(payload)
    return [f"{prefix}: {truncate_text(val, 320)}" if prefix else truncate_text(val, 320)]


def terminal_report(agent: str, action: str, message: str, *, payload: Any = None) -> None:
    timestamp = apply_style(f"[{utc_timestamp()}]", ANSI_DIM)
    agent_label = apply_style(agent.ljust(10), AGENT_COLORS.get(agent, ""), ANSI_BOLD)
    action_label = apply_style(action.ljust(18), ACTION_COLORS.get(action, ANSI_DIM))
    print(f"{timestamp} {agent_label} {action_label} {message}", flush=True)
    for line in flatten_payload(payload):
        detail_label = apply_style("details".ljust(18), ACTION_COLORS.get("details", ANSI_DIM))
        print(f"{timestamp} {agent_label} {detail_label} {line}", flush=True)


# ─── Git helpers ──────────────────────────────────────────────────────────────


def run_git(args: List[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout or result.stderr).strip()


def current_branch() -> str:
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"])


def main_head() -> str:
    """Return the current HEAD commit of main branch."""
    return run_git(["rev-parse", "main"]) or ""


def git_status() -> str:
    return run_git(["status", "--short", "--branch"]) or "(empty)"


def changed_files() -> str:
    return run_git(["diff", "--name-only"]) or "(none)"


def recent_commits(n: int = 10) -> str:
    return run_git(["log", "--oneline", f"-{n}"]) or "(none)"


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


# ─── File helpers ─────────────────────────────────────────────────────────────


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def append_log(path: Path, text: str) -> None:
    if not text:
        return
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


# ─── Decision helpers ─────────────────────────────────────────────────────────


def developer_declared_completion(text: str) -> bool:
    return any(line.strip() == TASK_COMPLETE_MARKER for line in text.splitlines())


def developer_declared_spec_complete(text: str) -> bool:
    return any(line.strip() == SPEC_COMPLETE_MARKER for line in text.splitlines())


def extract_task_id(text: str) -> Optional[str]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.upper().startswith("TASK_ID:"):
            task_id = stripped.partition(":")[2].strip()
            return task_id or None
        if stripped.lower().startswith("**task id**:"):
            task_id = stripped.partition(":")[2].strip()
            return task_id or None
        if stripped.lower() == "**task id**" and index + 1 < len(lines):
            candidate = lines[index + 1].strip().lstrip("-").strip()
            return candidate or None
    return None


def split_reviewer_decision(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if stripped == "APPROVE":
        return "APPROVE", ""
    if stripped.startswith("DENY:"):
        return "DENY", stripped[5:].strip()
    if stripped.startswith("STEER:"):
        return "STEER", stripped[6:].strip()
    return "STEER", stripped


def normalize_decision(text: str) -> str:
    for line in reversed(text.strip().splitlines()):
        candidate = line.strip()
        if candidate == "APPROVE":
            return "APPROVE"
        if candidate.startswith("DENY:") or candidate.startswith("STEER:"):
            return candidate
    return f"STEER: reviewer output was malformed; revise and continue.\n\n{text}"


# ─── Repo validation ──────────────────────────────────────────────────────────


def ensure_repo_files() -> None:
    missing = [str(p.relative_to(REPO_ROOT)) for p in DOC_PATHS if not p.exists()]
    if missing:
        raise SystemExit(f"Missing required repo files: {', '.join(missing)}")
    terminal_report(
        "SUPERVISOR",
        "repo-check",
        "Validated required repository files.",
        payload={"files": [str(p.relative_to(REPO_ROOT)) for p in DOC_PATHS]},
    )


# ─── Reviewer config ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReviewerConfig:
    model: str
    effort: str
    instructions: str


def load_reviewer_config() -> ReviewerConfig:
    text = read_text(REVIEWER_CONFIG_PATH)
    if not text:
        terminal_report(
            "SUPERVISOR",
            "reviewer-config",
            "Reviewer config not found; using defaults.",
            payload={"path": str(REVIEWER_CONFIG_PATH.relative_to(REPO_ROOT))},
        )
        return ReviewerConfig(
            model="claude-sonnet-4-6",
            effort="high",
            instructions=DEFAULT_REVIEWER_INSTRUCTIONS,
        )

    def extract_scalar(key: str) -> Optional[str]:
        m = re.search(rf'^{re.escape(key)}\s*=\s*"([^"]*)"', text, re.MULTILINE)
        return m.group(1) if m else None

    def extract_multiline(key: str) -> Optional[str]:
        m = re.search(rf'^{re.escape(key)}\s*=\s*"""(.*?)"""', text, re.MULTILINE | re.DOTALL)
        if not m:
            return None
        return textwrap.dedent(m.group(1)).strip()

    config = ReviewerConfig(
        model=extract_scalar("model") or "claude-sonnet-4-6",
        effort=extract_scalar("effort") or "high",
        instructions=extract_multiline("instructions") or DEFAULT_REVIEWER_INSTRUCTIONS,
    )
    terminal_report(
        "SUPERVISOR",
        "reviewer-config",
        "Loaded reviewer configuration.",
        payload={
            "path": str(REVIEWER_CONFIG_PATH.relative_to(REPO_ROOT)),
            "model": config.model,
            "effort": config.effort,
        },
    )
    return config


# ─── Supervisor ───────────────────────────────────────────────────────────────


class ReviewedClaude:
    def __init__(self) -> None:
        self.reviewer_config = load_reviewer_config()
        self.dev_session_id: Optional[str] = None
        self.last_developer_output: str = ""
        self.consecutive_api_failures: int = 0
        self._pre_turn_branch: str = ""
        self._pre_turn_main_head: str = ""
        terminal_report("SUPERVISOR", "init", "ReviewedClaude supervisor initialized.")

    def _build_developer_cmd(self) -> List[str]:
        cmd = [
            "claude",
            "--print",
            "--verbose",
            "--output-format", "stream-json",
            "--permission-mode", "bypassPermissions",
        ]
        if self.dev_session_id:
            cmd += ["--resume", self.dev_session_id]
        dev_model = os.environ.get("CLAUDE_DEV_MODEL", "")
        if dev_model:
            cmd += ["--model", dev_model]
        dev_effort = os.environ.get("CLAUDE_DEV_EFFORT", "")
        if dev_effort:
            cmd += ["--effort", dev_effort]
        return cmd

    def _run_developer_turn(self, prompt: str) -> str:
        """Run one developer turn via claude --print stream-json. Returns final result text."""
        cmd = self._build_developer_cmd()
        terminal_report(
            "DEVELOPER",
            "turn-start",
            "Starting developer turn.",
            payload={
                "session_id": self.dev_session_id or "(new)",
                "prompt_preview": truncate_text(prompt),
            },
        )

        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None

        proc.stdin.write(prompt)
        proc.stdin.close()

        result_text = ""
        all_assistant_text: List[str] = []

        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            append_log(DEV_LOG, raw_line)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type")

            if event_type == "assistant":
                message = event.get("message", {})
                for block in message.get("content", []):
                    block_type = block.get("type")
                    if block_type == "text":
                        text = block.get("text", "")
                        if text.strip():
                            all_assistant_text.append(text)
                            terminal_report(
                                "DEVELOPER",
                                "message",
                                truncate_text(text, 300),
                            )
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_input = block.get("input", {})
                        if tool_name == "Bash":
                            cmd_str = tool_input.get("command", "")
                            terminal_report(
                                "DEVELOPER",
                                "command",
                                f"Bash: {truncate_text(cmd_str, 180)}",
                            )
                        elif tool_name in {"Read", "Write", "Edit", "NotebookEdit"}:
                            path = tool_input.get("file_path", tool_input.get("path", ""))
                            terminal_report(
                                "DEVELOPER",
                                "file-change",
                                f"{tool_name}: {path}",
                            )
                        elif tool_name in {"Glob", "Grep"}:
                            terminal_report(
                                "DEVELOPER",
                                "event",
                                f"{tool_name}: {truncate_text(str(tool_input), 120)}",
                            )
                        else:
                            terminal_report(
                                "DEVELOPER",
                                "event",
                                f"Tool: {tool_name}",
                            )

            elif event_type == "result":
                self.dev_session_id = event.get("session_id", self.dev_session_id)
                result_text = event.get("result", "")
                is_error = event.get("is_error", False)
                terminal_report(
                    "DEVELOPER",
                    "turn-state",
                    "Turn completed.",
                    payload={
                        "session_id": self.dev_session_id,
                        "is_error": is_error,
                        "cost_usd": event.get("total_cost_usd", event.get("cost_usd")),
                        "duration_ms": event.get("duration_ms"),
                        "num_turns": event.get("num_turns"),
                    },
                )
                if is_error:
                    terminal_report(
                        "SUPERVISOR",
                        "error",
                        "Developer turn returned an error.",
                        payload={"result": truncate_text(result_text, 240)},
                    )
                    raise RuntimeError(f"Developer API error: {result_text[:300]}")

        proc.wait()

        if proc.returncode != 0 and not result_text:
            stderr = proc.stderr.read() if proc.stderr else ""
            terminal_report(
                "SUPERVISOR",
                "error",
                f"claude process exited with code {proc.returncode}.",
                payload={"stderr": truncate_text(stderr, 240)},
            )
            raise RuntimeError(f"claude exited with code {proc.returncode}: {stderr[:300]}")

        # Use accumulated assistant text for completion marker check; fall back to result field.
        full_output = "\n".join(all_assistant_text)
        if result_text and not full_output:
            full_output = result_text
        return full_output

    def _run_reviewer_turn(self, context: str) -> str:
        """Run one reviewer turn via claude --print. Returns raw decision text.

        Uses --output-format text to capture the final response directly.
        This works for both native Claude models and OpenRouter-proxied models.
        stream-json was tried previously but some OpenRouter models emit the
        result event JSON as a text block in an assistant event, making the
        captured text a JSON blob rather than the actual APPROVE/DENY/STEER
        decision.
        """
        cmd = [
            "claude",
            "--print",
            "--output-format", "text",
            "--system-prompt", self.reviewer_config.instructions,
            "--no-session-persistence",
            "--model", self.reviewer_config.model,
            "--effort", self.reviewer_config.effort,
            "--disallowed-tools", "Bash,Write,Edit,NotebookEdit",
        ]
        terminal_report(
            "REVIEWER",
            "turn-start",
            "Starting reviewer turn.",
            payload={
                "model": self.reviewer_config.model,
                "effort": self.reviewer_config.effort,
            },
        )

        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert proc.stdin is not None
        proc.stdin.write(context)
        proc.stdin.close()

        text = proc.stdout.read().strip()
        proc.wait()

        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            terminal_report(
                "SUPERVISOR",
                "error",
                f"Reviewer process exited with code {proc.returncode}.",
                payload={"stderr": truncate_text(stderr, 240)},
            )
            return "STEER: reviewer failed to respond; developer should continue autonomously."

        append_log(REVIEW_LOG, text + "\n" if text else "")

        if not text:
            text = "(no response from reviewer)"

        terminal_report(
            "REVIEWER",
            "turn-state",
            "Reviewer turn completed.",
            payload={"result_preview": truncate_text(text, 240)},
        )
        return text

    def build_review_prompt(self) -> str:
        return FINAL_REVIEW_PROMPT_TEMPLATE.format(
            completion_summary=(
                self.last_developer_output.strip()
                if self.last_developer_output
                else "(no completion summary — developer did not produce one)"
            ),
            branch=current_branch(),
            git_status=git_status(),
            changed_files=changed_files(),
            recent_commits=recent_commits(),
        )

    def ask_reviewer(self) -> str:
        terminal_report("SUPERVISOR", "review-pass", "Starting reviewer pass.")
        context = self.build_review_prompt()
        raw = self._run_reviewer_turn(context)
        decision = normalize_decision(raw)
        append_log(REVIEW_LOG, f"[decision] {decision}\n")
        terminal_report(
            "REVIEWER",
            "decision",
            f"Reviewer returned {split_reviewer_decision(decision)[0]}.",
            payload={"review_preview": truncate_text(raw, 240)},
        )
        return decision

    def continue_developer(self, reason: str) -> str:
        prompt = (
            f"{reason}\n\n"
            "Continue from the current repository state. Do not restart from scratch. "
            "Keep working until the assigned work is actually complete. "
            f"Only when done, end your final message with the exact line {TASK_COMPLETE_MARKER}."
        )
        terminal_report(
            "SUPERVISOR",
            "developer-continue",
            "Starting next developer turn.",
            payload={"reason": truncate_text(reason, 120)},
        )
        return self._run_developer_turn(prompt)

    def _developer_turn_safe(self, prompt: str) -> Optional[str]:
        """Run a developer turn, tracking consecutive API failures and main violations.

        Returns the turn output, or None if a failure was recorded and the
        caller should check self.consecutive_api_failures to decide whether
        to halt.
        """
        # Record state before turn
        self._pre_turn_branch = current_branch()
        self._pre_turn_main_head = main_head()

        try:
            text = self._run_developer_turn(prompt)
            self.consecutive_api_failures = 0
        except RuntimeError as exc:
            self.consecutive_api_failures += 1
            terminal_report(
                "SUPERVISOR",
                "api-failure",
                f"Developer turn failed "
                f"({self.consecutive_api_failures}/{MAX_CONSECUTIVE_API_FAILURES}).",
                payload={"error": truncate_text(str(exc), 240)},
            )
            return None

        # Check for main violation after successful turn
        post_branch = current_branch()
        post_main_head = main_head()
        if post_branch == "main" or post_main_head != self._pre_turn_main_head:
            terminal_report(
                "SUPERVISOR",
                "main-violation",
                "Developer modified main branch directly. Rejecting turn.",
                payload={
                    "pre_branch": self._pre_turn_branch,
                    "post_branch": post_branch,
                    "main_changed": post_main_head != self._pre_turn_main_head,
                },
            )
            return "__MAIN_VIOLATION__"

        return text

    def loop(self) -> None:
        terminal_report("SUPERVISOR", "loop", "Entering supervisor event loop.")
        text = self._developer_turn_safe(DEVELOPER_BOOTSTRAP_PROMPT)

        while True:
            if text is None:
                if self.consecutive_api_failures >= MAX_CONSECUTIVE_API_FAILURES:
                    terminal_report(
                        "SUPERVISOR",
                        "halt",
                        f"Stopping: {MAX_CONSECUTIVE_API_FAILURES} consecutive API "
                        "failures. Likely out of credits or provider is down.",
                    )
                    return
                text = self._developer_turn_safe(
                    "The previous turn failed due to an API error. "
                    "Resume from current repository state and continue autonomously. "
                    f"When the work is fully complete, end with {TASK_COMPLETE_MARKER}."
                )
                continue

            if text == "__MAIN_VIOLATION__":
                text = self._developer_turn_safe(
                    "VIOLATION: You merged or committed directly to main. "
                    "This is forbidden. The supervisor handles merges after reviewer approval.\n\n"
                    "If you need to preserve the mistaken main state, create a recovery branch first. "
                    "Then restore `main` to the remote state using sanctioned git commands and continue "
                    "working only on your feature branch. "
                    "When done, emit REVIEWED_CLAUDE_TASK_COMPLETE. "
                    "The reviewer will approve, and the supervisor will merge for you."
                )
                continue

            self.last_developer_output = text

            if developer_declared_spec_complete(text):
                terminal_report(
                    "SUPERVISOR",
                    "spec-complete",
                    "Developer declared the full spec is complete. Stopping.",
                )
                return

            if not developer_declared_completion(text):
                text = self._developer_turn_safe(
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
            kind, _detail = split_reviewer_decision(decision)

            if kind == "APPROVE":
                terminal_report(
                    "SUPERVISOR",
                    "review-approve",
                    "Reviewer approved. Merging branch to main.",
                )
                branch = current_branch()
                merge_error: str = ""
                if branch and branch != "main":
                    result = subprocess.run(
                        ["git", "checkout", "main"],
                        cwd=str(REPO_ROOT), capture_output=True, text=True,
                    )
                    if result.returncode == 0:
                        result = subprocess.run(
                            ["git", "merge", "--no-ff", branch,
                             "-m", f"merge: {branch} into main\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"],
                            cwd=str(REPO_ROOT), capture_output=True, text=True,
                        )
                        if result.returncode == 0:
                            terminal_report(
                                "SUPERVISOR", "merge-ok",
                                f"Merged {branch} into main.",
                            )
                        else:
                            merge_error = result.stderr.strip() or result.stdout.strip()
                            terminal_report(
                                "SUPERVISOR", "merge-fail",
                                f"Merge failed: {truncate_text(merge_error, 200)}",
                            )
                    else:
                        merge_error = result.stderr.strip()
                        terminal_report(
                            "SUPERVISOR", "merge-fail",
                            f"Could not checkout main: {truncate_text(merge_error, 200)}",
                        )

                if merge_error:
                    text = self._developer_turn_safe(
                        f"Reviewer approved the work but the automatic merge of "
                        f"`{branch}` into main failed:\n\n{merge_error}\n\n"
                        "Resolve the merge conflict or any blocking issue, merge the "
                        "branch into main yourself, then continue to the next task. "
                        f"When the next slice is fully complete, end your final message "
                        f"with the exact line {TASK_COMPLETE_MARKER}."
                    )
                else:
                    state_error = finalize_supervisor_merge(
                        branch,
                        task_id=extract_task_id(text),
                    )
                    if state_error:
                        text = self._developer_turn_safe(
                            f"Reviewer approved the completed work and the branch `{branch}` was merged into `main`, "
                            "but the supervisor could not reconcile the SQLite runtime state:\n\n"
                            f"{state_error}\n\n"
                            "Create a new feature branch from the merged `main`, reconcile the missing backend state through sanctioned repository changes, "
                            "and continue autonomous development only after the persisted project state matches git history. "
                            f"When the next slice is fully complete, end your final message with the exact line {TASK_COMPLETE_MARKER}."
                        )
                        continue
                    text = self._developer_turn_safe(
                        f"Reviewer approved the completed work. "
                        f"Branch `{branch}` has been merged into main.\n\n"
                        "Continue autonomous development: read docs/STATUS.md and "
                        "docs/sprints/backlog.md to select the next valid slice, update "
                        "repo state as part of the same flow, and proceed autonomously. "
                        f"If there is genuinely no remaining work, end with "
                        f"{SPEC_COMPLETE_MARKER}. Otherwise end with {TASK_COMPLETE_MARKER}."
                    )
                continue

            # STEER or DENY — feed reviewer feedback back to the developer.
            terminal_report(
                "SUPERVISOR",
                "developer-restart",
                "Reviewer did not approve; sending feedback to developer.",
                payload={"decision": truncate_text(decision, 160)},
            )
            feedback_prompt = (
                f"Reviewer feedback:\n{decision}\n\n"
                "Revise and continue autonomously. "
                f"When the work is fully corrected and complete, end your final message with the exact line {TASK_COMPLETE_MARKER}."
            )
            text = self._developer_turn_safe(feedback_prompt)


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
    runner = ReviewedClaude()
    runner.loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
