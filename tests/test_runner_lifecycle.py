"""Regression coverage for the sprint-53 runner process lifecycle slice.

An unattended engine must never hang on a silent agent, leak an agent's
process group, deadlock on stderr, or leave a run row ``running`` after a
shutdown signal. These tests exercise the managed-process layer with real
subprocesses, both runners with silent or noisy fakes, the orchestrator's
tick, shutdown, and lease-loss handling, and the test built-in timeout.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from foreman.builtins import BuiltinExecutor
from foreman.models import Project, Sprint, Task
from foreman.orchestrator import ForemanOrchestrator, LeaseLostError
from foreman.runner import AgentRunConfig, ClaudeCodeRunner, CodexRunner, InfrastructureError
from foreman.runner.base import AgentEvent
from foreman.runner.codex import _JsonRpcClient
from foreman.runner.process import (
    EngineShutdown,
    ManagedProcess,
    install_shutdown_handlers,
    live_processes,
    popen_kwargs,
    reset_shutdown_handlers,
    terminate_all,
)
from foreman.store import ForemanStore


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie still answers signal 0; reap-check via /proc when available.
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            state = handle.read().rsplit(")", 1)[1].split()[0]
        return state != "Z"
    except OSError:
        return True


def _wait_until(predicate, *, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _python(script: str, *, cwd: str | Path = ".") -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", script], **popen_kwargs(cwd=cwd))


class ManagedProcessTests(unittest.TestCase):
    """Real subprocesses: ticks, stderr draining, and group termination."""

    def test_iter_lines_ticks_while_the_child_is_silent(self) -> None:
        proc = _python("import time; time.sleep(0.6); print('done', flush=True)")
        managed = ManagedProcess(proc, name="silent", tick_seconds=0.1)
        try:
            ticks = 0
            lines: list[str] = []
            for line in managed.iter_lines():
                if line is None:
                    ticks += 1
                else:
                    lines.append(line.strip())
            self.assertGreaterEqual(ticks, 3)
            self.assertEqual(lines, ["done"])
        finally:
            managed.close()
        self.assertEqual(live_processes(), 0)

    def test_stderr_flood_does_not_deadlock_stdout(self) -> None:
        script = (
            "import sys\n"
            "sys.stderr.write('e' * 300000)\n"
            "sys.stderr.flush()\n"
            "print('after-flood', flush=True)\n"
        )
        proc = _python(script)
        managed = ManagedProcess(proc, name="noisy", tick_seconds=0.2)
        try:
            started = time.monotonic()
            lines = [line.strip() for line in managed.iter_lines() if line is not None]
            elapsed = time.monotonic() - started
            self.assertEqual(lines, ["after-flood"])
            self.assertLess(elapsed, 10.0)
            self.assertIn("e" * 100, managed.stderr_text())
        finally:
            managed.close()

    def test_terminate_kills_the_whole_process_group(self) -> None:
        script = (
            "import subprocess, sys, time\n"
            "child = subprocess.Popen(['sleep', '60'])\n"
            "print(child.pid, flush=True)\n"
            "time.sleep(60)\n"
        )
        proc = _python(script)
        managed = ManagedProcess(proc, name="parent", tick_seconds=0.2)
        grandchild_pid = int(managed.readline(timeout=5.0).strip())
        self.assertTrue(_pid_is_alive(grandchild_pid))

        managed.terminate(grace_seconds=1.0)

        self.assertFalse(managed.is_running())
        self.assertTrue(_wait_until(lambda: not _pid_is_alive(grandchild_pid)))
        self.assertEqual(live_processes(), 0)

    def test_terminate_all_stops_every_registered_process(self) -> None:
        procs = [
            ManagedProcess(_python("import time; time.sleep(60)"), name=f"p{i}", tick_seconds=0.2)
            for i in range(3)
        ]
        self.assertEqual(live_processes(), 3)
        signalled = terminate_all(grace_seconds=1.0)
        self.assertEqual(signalled, 3)
        for managed in procs:
            self.assertFalse(managed.is_running())
        self.assertEqual(live_processes(), 0)

    def test_shutdown_signal_terminates_children_and_raises_in_main_thread(self) -> None:
        self.assertTrue(install_shutdown_handlers())
        self.addCleanup(reset_shutdown_handlers)
        managed = ManagedProcess(_python("import time; time.sleep(60)"), name="victim", tick_seconds=0.2)
        try:
            with self.assertRaises(EngineShutdown) as raised:
                os.kill(os.getpid(), signal.SIGTERM)
                time.sleep(1.0)  # give the handler a chance to run
            self.assertEqual(raised.exception.signal_name, "SIGTERM")
            self.assertTrue(_wait_until(lambda: not managed.is_running()))
        finally:
            managed.close()

    def test_fake_process_without_pid_is_signalled_directly(self) -> None:
        class _Fake:
            def __init__(self) -> None:
                self.returncode: int | None = None
                self.killed = False
                self.stdout = None
                self.stderr = None

            def poll(self) -> int | None:
                return self.returncode

            def kill(self) -> None:
                self.killed = True
                self.returncode = -9

            def wait(self, timeout: float | None = None) -> int:
                return self.returncode or 0

        fake = _Fake()
        managed = ManagedProcess(fake, name="fake", tick_seconds=0.1)
        managed.kill()
        self.assertTrue(fake.killed)
        self.assertEqual(live_processes(), 0)


class _BlockingOutput:
    """A stdout fake that serves scripted lines, then blocks like a hung tool."""

    def __init__(self, lines: list[str], *, block_seconds: float = 5.0) -> None:
        self._lines = list(lines)
        self._block_seconds = block_seconds
        self._released = threading.Event()

    def readline(self) -> str:
        if self._lines:
            return self._lines.pop(0)
        self._released.wait(self._block_seconds)
        return ""

    def release(self) -> None:
        self._released.set()


class _FakeStdin:
    def __init__(self) -> None:
        self.text = ""

    def write(self, text: str) -> None:
        self.text += text

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakeErr:
    def read(self) -> str:
        return ""


class _FakeProcess:
    def __init__(self, stdout: _BlockingOutput) -> None:
        self.stdin = _FakeStdin()
        self.stdout = stdout
        self.stderr = _FakeErr()
        self.returncode: int | None = None
        self.killed = False
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode if self.returncode is not None else 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self.stdout.release()

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self.stdout.release()


class ClaudeRunnerLifecycleTests(unittest.TestCase):
    def _config(self, cwd: Path, *, timeout_seconds: int) -> AgentRunConfig:
        return AgentRunConfig(
            backend="claude_code",
            model=None,
            prompt="Implement the task.",
            working_dir=cwd,
            session_id=None,
            permission_mode="bypassPermissions",
            timeout_seconds=timeout_seconds,
            max_cost_usd=0.0,
        )

    def test_time_gate_fires_while_the_agent_is_silent(self) -> None:
        stdout = _BlockingOutput([], block_seconds=10.0)
        fake = _FakeProcess(stdout)
        runner = ClaudeCodeRunner(
            popen_factory=lambda *args, **kwargs: fake,
            which=lambda name: "/usr/bin/claude",
            tick_seconds=0.05,
        )
        with tempfile.TemporaryDirectory() as tmp:
            started = time.monotonic()
            events = list(runner.run(self._config(Path(tmp), timeout_seconds=1)))
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 5.0)
        self.assertTrue(fake.killed)
        types = [event.event_type for event in events]
        self.assertIn("agent.tick", types)
        self.assertEqual(types[-1], "agent.killed")
        self.assertEqual(events[-1].payload["gate_type"], "time")

    def test_popen_gets_utf8_replacement_and_its_own_session(self) -> None:
        recorded: dict[str, object] = {}

        def factory(*args, **kwargs):
            recorded.update(kwargs)
            return _FakeProcess(_BlockingOutput([
                json.dumps({"type": "result", "result": "TASK_COMPLETE", "session_id": "s", "is_error": False}) + "\n",
            ]))

        runner = ClaudeCodeRunner(popen_factory=factory, which=lambda name: "/usr/bin/claude", tick_seconds=0.05)
        with tempfile.TemporaryDirectory() as tmp:
            list(runner.run(self._config(Path(tmp), timeout_seconds=0)))
        self.assertEqual(recorded["encoding"], "utf-8")
        self.assertEqual(recorded["errors"], "replace")
        self.assertTrue(recorded["start_new_session"])
        self.assertNotIn("text", recorded)

    def test_stderr_flood_from_a_real_child_completes(self) -> None:
        script = (
            "import json, sys\n"
            "sys.stdin.read()\n"
            "sys.stderr.write('x' * 300000)\n"
            "sys.stderr.flush()\n"
            "print(json.dumps({'type': 'result', 'result': 'Done. TASK_COMPLETE',"
            " 'session_id': 'sess-flood', 'total_cost_usd': 0.01, 'duration_ms': 5,"
            " 'is_error': False}), flush=True)\n"
        )

        def factory(command, **kwargs):
            return subprocess.Popen([sys.executable, "-c", script], **kwargs)

        runner = ClaudeCodeRunner(popen_factory=factory, which=lambda name: "/usr/bin/claude", tick_seconds=0.2)
        with tempfile.TemporaryDirectory() as tmp:
            started = time.monotonic()
            events = list(runner.run(self._config(Path(tmp), timeout_seconds=30)))
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 10.0)
        completed = [event for event in events if event.event_type == "agent.completed"]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].payload["session_id"], "sess-flood")
        self.assertEqual(live_processes(), 0)

    def test_abandoned_generator_kills_the_agent_process_group(self) -> None:
        script = (
            "import json, subprocess, sys, time\n"
            "sys.stdin.read()\n"
            "child = subprocess.Popen(['sleep', '60'])\n"
            "print(json.dumps({'type': 'assistant', 'message': {'content': [{'type': 'text',"
            " 'text': str(child.pid)}]}}), flush=True)\n"
            "time.sleep(60)\n"
        )

        def factory(command, **kwargs):
            return subprocess.Popen([sys.executable, "-c", script], **kwargs)

        runner = ClaudeCodeRunner(popen_factory=factory, which=lambda name: "/usr/bin/claude", tick_seconds=0.2)
        with tempfile.TemporaryDirectory() as tmp:
            stream = runner.run(self._config(Path(tmp), timeout_seconds=0))
            grandchild_pid: int | None = None
            for event in stream:
                if event.event_type == "agent.message":
                    grandchild_pid = int(event.payload["text"].strip())
                    break
            self.assertIsNotNone(grandchild_pid)
            assert grandchild_pid is not None
            self.assertTrue(_pid_is_alive(grandchild_pid))

            stream.close()  # the orchestrator raised; the generator is abandoned

        self.assertTrue(_wait_until(lambda: not _pid_is_alive(grandchild_pid), timeout=8.0))
        self.assertEqual(live_processes(), 0)


class CodexRunnerLifecycleTests(unittest.TestCase):
    def test_startup_handshake_times_out_instead_of_hanging(self) -> None:
        fake = _FakeProcess(_BlockingOutput([], block_seconds=10.0))
        started = time.monotonic()
        with self.assertRaises(InfrastructureError) as raised:
            _JsonRpcClient(
                ["codex", "app-server", "--listen", "stdio://"],
                cwd=Path("/tmp"),
                popen_factory=lambda *args, **kwargs: fake,
                tick_seconds=0.05,
                startup_timeout_seconds=0.3,
            )
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertIn("did not answer initialize", str(raised.exception))
        self.assertTrue(fake.killed)

    def test_time_gate_fires_while_the_turn_is_silent(self) -> None:
        lines = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"userAgent": "codex-tests"}}) + "\n",
            json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"thread": {"id": "thread-1"}}}) + "\n",
            json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"turn": {"id": "turn-1"}}}) + "\n",
        ]
        fake = _FakeProcess(_BlockingOutput(lines, block_seconds=10.0))
        runner = CodexRunner(
            popen_factory=lambda *args, **kwargs: fake,
            which=lambda name: "/usr/bin/codex",
            tick_seconds=0.05,
        )
        config = AgentRunConfig(
            backend="codex",
            model=None,
            prompt="Implement the task.",
            working_dir=Path("/tmp"),
            session_id=None,
            permission_mode="bypassPermissions",
            timeout_seconds=1,
            max_cost_usd=0.0,
        )
        started = time.monotonic()
        events = list(runner.run(config))
        self.assertLess(time.monotonic() - started, 5.0)
        types = [event.event_type for event in events]
        self.assertEqual(types[0], "agent.started")
        self.assertIn("agent.tick", types)
        self.assertEqual(types[-1], "agent.killed")
        self.assertTrue(fake.killed)


class TestBuiltinTimeoutTests(unittest.TestCase):
    def test_run_tests_times_out_and_kills_the_command_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Project(
                id="p",
                name="P",
                repo_path=tmp,
                workflow_id="development",
                settings={"test_command": "sleep 30 & sleep 30; wait", "test_timeout_seconds": 1},
            )
            task = Task(id="t", sprint_id="s", project_id="p", title="T")
            recorded = []
            started = time.monotonic()
            result = BuiltinExecutor().execute(
                "_builtin:run_tests",
                project=project,
                task=task,
                step_id="test",
                carried_output=None,
                event_recorder=recorded.append,
            )
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 10.0)
        self.assertEqual(result.outcome, "failure")
        self.assertIn("timed out", result.detail)
        run_events = [event for event in recorded if event.event_type == "engine.test_run"]
        self.assertEqual(len(run_events), 1)
        self.assertTrue(run_events[0].payload["timed_out"])
        self.assertIsNone(run_events[0].payload["exit_code"])
        self.assertEqual(live_processes(), 0)


class _ScriptedRunner:
    """A native runner whose behaviour is scripted per call."""

    def __init__(self, behaviours) -> None:
        self._behaviours = list(behaviours)
        self.calls = 0

    def run(self, config: AgentRunConfig):
        self.calls += 1
        behaviour = self._behaviours.pop(0)
        yield from behaviour(config)


def _ticks_then_complete(config: AgentRunConfig):
    yield AgentEvent("agent.started", payload={"command": "fake"})
    for _ in range(3):
        yield AgentEvent("agent.tick", payload={"elapsed_seconds": 1.0})
    yield AgentEvent("agent.message", payload={"text": "Implemented.\nTASK_COMPLETE", "phase": "result"})
    yield AgentEvent("agent.completed", payload={"session_id": "dev-session", "cost_usd": 0.5, "duration_ms": 10, "token_count": 100})


def _shutdown_mid_run(config: AgentRunConfig):
    yield AgentEvent("agent.started", payload={"command": "fake"})
    raise EngineShutdown("SIGTERM")


class OrchestratorLifecycleTests(unittest.TestCase):
    """Ticks heartbeat the lease and vanish; interruptions settle the run row."""

    def _workspace(self) -> tuple[Path, Path]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repo = root / "repo"
        repo.mkdir()
        self._git(repo, "init")
        self._git(repo, "checkout", "-b", "main")
        self._git(repo, "config", "user.email", "foreman-tests@example.com")
        self._git(repo, "config", "user.name", "Foreman Tests")
        (repo / "README.md").write_text("# repo\n", encoding="utf-8")
        (repo / ".gitignore").write_text(".foreman/\n", encoding="utf-8")
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", "init")
        return repo, root / "foreman.db"

    @staticmethod
    def _git(repo: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)

    def _seed(self, store: ForemanStore, repo: Path) -> tuple[Project, Task]:
        project = Project(
            id="project-1",
            name="Lifecycle",
            repo_path=str(repo),
            workflow_id="development",
            default_branch="main",
            settings={"task_selection_mode": "directed", "test_command": "true", "default_model": "m"},
        )
        store.save_project(project)
        store.save_sprint(Sprint(id="sprint-1", project_id=project.id, title="S", status="active"))
        task = Task(
            id="task-1",
            sprint_id="sprint-1",
            project_id=project.id,
            title="Implement",
            status="todo",
            acceptance_criteria="Implemented.",
        )
        store.save_task(task)
        return project, task

    def test_ticks_are_not_persisted_and_shutdown_leaves_the_task_resumable(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo)
            runner = _ScriptedRunner([_ticks_then_complete, _shutdown_mid_run])
            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={"claude_code": runner},
                native_step_heartbeat_seconds=0.0001,
            )

            with self.assertRaises(EngineShutdown):
                orchestrator.run_project(project.id)

            runs = [r for r in store.list_runs(task_id=task.id) if r.role_id != "_builtin:orchestrator"]
            self.assertEqual([run.workflow_step for run in runs], ["develop", "review"])
            develop_run, review_run = runs
            self.assertEqual(develop_run.status, "completed")
            self.assertEqual(develop_run.outcome, "done")
            tick_events = [
                event for event in store.list_events(run_id=develop_run.id)
                if event.event_type == "agent.tick"
            ]
            self.assertEqual(tick_events, [])

            self.assertEqual(review_run.status, "killed")
            killed = [
                event for event in store.list_events(run_id=review_run.id)
                if event.event_type == "agent.killed"
            ]
            self.assertEqual(len(killed), 1)
            self.assertEqual(killed[0].payload["gate_type"], "shutdown")

            resumed = store.get_task(task.id)
            self.assertEqual(resumed.status, "in_progress")
            self.assertEqual(resumed.workflow_current_step, "review")
            self.assertIsNone(
                store.get_active_lease(project_id=project.id, resource_type="task", resource_id=task.id)
            )
            self.assertEqual(
                subprocess.run(["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True).stdout.strip(),
                "main",
            )

    def test_lost_lease_stops_the_engine_without_touching_the_task(self) -> None:
        repo, db_path = self._workspace()
        with ForemanStore(db_path) as store:
            store.initialize()
            project, task = self._seed(store, repo)

            def _takeover_then_tick(config: AgentRunConfig):
                yield AgentEvent("agent.started", payload={"command": "fake"})
                store.expire_resource_leases(
                    project_id=project.id, resource_type="task", resource_id=task.id, force=True
                )
                store.acquire_lease(
                    project_id=project.id,
                    resource_type="task",
                    resource_id=task.id,
                    holder_id="other-engine",
                    lease_token="other-token",
                )
                yield AgentEvent("agent.tick", payload={"elapsed_seconds": 1.0})
                yield AgentEvent("agent.completed", payload={"session_id": "x"})

            orchestrator = ForemanOrchestrator(
                store,
                agent_runners={"claude_code": _ScriptedRunner([_takeover_then_tick])},
                native_step_heartbeat_seconds=0.0001,
            )

            with self.assertRaises(LeaseLostError):
                orchestrator.run_project(project.id)

            runs = [r for r in store.list_runs(task_id=task.id) if r.role_id != "_builtin:orchestrator"]
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "killed")
            killed = [
                event for event in store.list_events(run_id=runs[0].id)
                if event.event_type == "agent.killed"
            ]
            self.assertEqual(killed[0].payload["gate_type"], "lease_lost")

            untouched = store.get_task(task.id)
            self.assertEqual(untouched.status, "in_progress")
            self.assertEqual(untouched.workflow_current_step, "develop")
            lease = store.get_active_lease(
                project_id=project.id, resource_type="task", resource_id=task.id
            )
            self.assertIsNotNone(lease)
            self.assertEqual(lease.holder_id, "other-engine")


if __name__ == "__main__":
    unittest.main()
