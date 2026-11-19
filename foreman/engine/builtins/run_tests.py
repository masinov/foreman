"""``_builtin:run_tests``: the project's test command, in the task's worktree.
"""

from __future__ import annotations

import selectors
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from ...domain.models import Project
from ...domain.settings import settings_of
from ...runner.process import ManagedProcess
from .base import BuiltinEventRecord, BuiltinExecutorBase, BuiltinResult, _safe_head_sha

DEFAULT_TEST_TIMEOUT_SECONDS = 1800


def _combine_output(stdout: str, stderr: str) -> str:
    stdout = stdout.strip()
    stderr = stderr.strip()
    if stdout and stderr:
        return f"{stdout}\n{stderr}"
    return stdout or stderr


def _tail_lines(text: str, limit: int) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    return "\n".join(lines[-limit:])


class RunTestsStep(BuiltinExecutorBase):
    """Running the project's tests."""

    def _run_tests(
        self,
        *,
        project: Project,
        working_dir: Path,
        event_recorder: Callable[[BuiltinEventRecord], None] | None = None,
    ) -> BuiltinResult:
        settings = settings_of(project)
        command = settings.test_command.strip()
        emitted_events: list[BuiltinEventRecord] = []

        def emit(event_type: str, payload: dict[str, Any]) -> None:
            record = BuiltinEventRecord(event_type=event_type, payload=payload)
            if event_recorder is not None:
                event_recorder(record)
            else:
                emitted_events.append(record)

        if not command:
            detail = "Project test_command is not configured."
            emit(
                "engine.test_run",
                {
                    "command": command,
                    "exit_code": None,
                    "stdout": "",
                    "stderr": "",
                    "output_tail": detail,
                },
            )
            return BuiltinResult(outcome="failure", detail=detail, events=tuple(emitted_events))

        timeout_seconds = settings.test_timeout_seconds
        emit(
            "engine.test_started",
            {
                "command": command,
                "timeout_seconds": timeout_seconds,
                "working_dir": str(working_dir),
            },
        )
        started_at = time.monotonic()
        proc = subprocess.Popen(
            ["bash", "-lc", command],
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=True,
        )
        assert proc.stdout is not None
        assert proc.stderr is not None
        # Registered (not pumped) so a shutdown signal kills the whole test
        # process group along with any agent processes.
        managed = ManagedProcess(proc, name="tests", pump=False)

        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        deadline = time.monotonic() + timeout_seconds if timeout_seconds > 0 else None
        timed_out = False

        try:
            while selector.get_map():
                remaining: float | None = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                for key, _ in selector.select(timeout=remaining):
                    stream_name = str(key.data)
                    line = key.fileobj.readline()
                    if line == "":
                        selector.unregister(key.fileobj)
                        continue
                    text = line.rstrip("\n")
                    if stream_name == "stdout":
                        stdout_chunks.append(line)
                    else:
                        stderr_chunks.append(line)
                    emit(
                        "engine.test_output",
                        {
                            "command": command,
                            "stream": stream_name,
                            "text": text,
                        },
                    )
        finally:
            selector.close()
            if timed_out:
                managed.kill()
            else:
                proc.wait()
                managed.close()

        duration_seconds = round(max(time.monotonic() - started_at, 0.0), 1)
        stdout_text = "".join(stdout_chunks).strip()
        stderr_text = "".join(stderr_chunks).strip()
        output = _combine_output(stdout_text, stderr_text)
        output_tail = _tail_lines(output, 200)
        if timed_out:
            outcome = "failure"
            detail = (
                f"Test command timed out after {timeout_seconds}s and was killed."
                + (f"\n\n{output_tail}" if output_tail else "")
            )
            exit_code: int | None = None
        else:
            outcome = "success" if proc.returncode == 0 else "failure"
            verdict = "passed" if proc.returncode == 0 else "failed"
            detail = (
                f"Tests {verdict} in {duration_seconds:.1f}s (exit {proc.returncode})."
                + (f"\n\n{output_tail}" if output_tail else "")
            )
            exit_code = proc.returncode
        emit(
            "engine.test_run",
            {
                "command": command,
                "working_dir": str(working_dir),
                "exit_code": exit_code,
                "passed": exit_code == 0,
                "timed_out": timed_out,
                "duration_seconds": duration_seconds,
                "head_sha": _safe_head_sha(working_dir),
                "stdout": stdout_text,
                "stderr": stderr_text,
                "output_tail": output_tail,
            },
        )
        return BuiltinResult(
            outcome=outcome,
            detail=detail,
            events=tuple(emitted_events),
        )
