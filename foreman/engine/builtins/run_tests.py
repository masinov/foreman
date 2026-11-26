"""``_builtin:run_tests``: the project's test command, in the task's worktree.
"""

from __future__ import annotations

import os
import selectors
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from ...domain.models import Project
from ...domain.settings import settings_of
from ...runner.process import ManagedProcess
from .base import BuiltinEventRecord, BuiltinExecutorBase, BuiltinResult, _safe_head_sha
from .test_report import REPORT_DIR_ENV, read_reports

DEFAULT_TEST_TIMEOUT_SECONDS = 1800

#: How often a running test command checks whether it has been stopped.
INTERRUPT_POLL_SECONDS = 2.0


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
        interrupt_poll: Callable[[], None] | None = None,
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
        # A fresh directory outside the working copy, so a report left from
        # an earlier run is never counted and nothing lands in the branch.
        report_dir = Path(tempfile.mkdtemp(prefix="foreman-test-report-"))
        try:
            return self._run_command(
                command=command,
                timeout_seconds=timeout_seconds,
                working_dir=working_dir,
                report_dir=report_dir,
                emit=emit,
                emitted_events=emitted_events,
                interrupt_poll=interrupt_poll,
            )
        finally:
            shutil.rmtree(report_dir, ignore_errors=True)

    def _run_command(
        self,
        *,
        command: str,
        timeout_seconds: int,
        working_dir: Path,
        report_dir: Path,
        emit: Callable[[str, dict[str, Any]], None],
        emitted_events: list[BuiltinEventRecord],
        interrupt_poll: Callable[[], None] | None = None,
    ) -> BuiltinResult:
        """Run the test command, stream its output, and record how it ended.

        ``interrupt_poll`` raising (a user's Stop) kills the test process
        group and lets the exception through.
        """

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
            env={**os.environ, REPORT_DIR_ENV: str(report_dir)},
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
        interrupted = False
        last_poll = time.monotonic()

        try:
            while selector.get_map():
                remaining: float | None = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                wait = remaining
                if interrupt_poll is not None:
                    wait = INTERRUPT_POLL_SECONDS if wait is None else min(wait, INTERRUPT_POLL_SECONDS)
                    if time.monotonic() - last_poll >= INTERRUPT_POLL_SECONDS:
                        last_poll = time.monotonic()
                        try:
                            interrupt_poll()
                        except BaseException:
                            interrupted = True
                            raise
                for key, _ in selector.select(timeout=wait):
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
            if timed_out or interrupted:
                managed.kill()
            else:
                proc.wait()
                managed.close()

        duration_seconds = round(max(time.monotonic() - started_at, 0.0), 1)
        stdout_text = "".join(stdout_chunks).strip()
        stderr_text = "".join(stderr_chunks).strip()
        output = _combine_output(stdout_text, stderr_text)
        output_tail = _tail_lines(output, 200)
        report, report_problems = read_reports(report_dir)
        counted = f" {report.words()}." if report is not None else ""
        if timed_out:
            outcome = "failure"
            detail = (
                f"Test command timed out after {timeout_seconds}s and was killed."
                + counted
                + (f"\n\n{output_tail}" if output_tail else "")
            )
            exit_code: int | None = None
        else:
            outcome = "success" if proc.returncode == 0 else "failure"
            verdict = "passed" if proc.returncode == 0 else "failed"
            detail = (
                f"Tests {verdict} in {duration_seconds:.1f}s (exit {proc.returncode})."
                + counted
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
                # How many tests ran, from the JUnit reports the command
                # wrote; null when it wrote none Foreman could read.
                "report": report.as_payload() if report is not None else None,
                "report_problems": report_problems,
            },
        )
        return BuiltinResult(
            outcome=outcome,
            detail=detail,
            events=tuple(emitted_events),
        )
