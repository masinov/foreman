"""Managed child processes for native runners and built-ins.

Every agent or test process Foreman launches goes through ``ManagedProcess``:

- stdout is read on a thread into a queue, so the caller can enforce
  wall-clock time, cost, and lease heartbeats even while the child is silent;
- stderr is drained continuously into a bounded buffer, so a chatty child can
  never deadlock on a full pipe;
- the child runs in its own session, so ``terminate`` and ``kill`` reach the
  whole process group (test runners, dev servers, subagents the child spawned);
- live processes sit in a registry that ``install_shutdown_handlers`` drains
  on SIGTERM, SIGINT, and interpreter exit.

The wrapper degrades gracefully around fake processes used in tests: streams
may only support ``readline``, iteration, or ``read``, and a process without a
``pid`` is signalled through its own ``terminate`` / ``kill`` methods.
"""

from __future__ import annotations

import atexit
import os
import queue
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class EngineShutdown(BaseException):
    """Raised in the main thread when a shutdown signal arrives.

    A ``BaseException`` so ordinary ``except Exception`` fallbacks never
    swallow it. The orchestrator marks the active run killed, keeps the task
    resumable, releases its lease, and lets the CLI exit with status 130.
    """

    def __init__(self, signal_name: str) -> None:
        super().__init__(f"Shutdown requested ({signal_name}).")
        self.signal_name = signal_name


DEFAULT_TICK_SECONDS = 15.0
DEFAULT_GRACE_SECONDS = 5.0
STDERR_BUFFER_LINES = 4000

_EOF = object()

_registry_lock = threading.Lock()
_registry: set["ManagedProcess"] = set()
_handlers_installed = False
_previous_handlers: dict[int, Any] = {}


def popen_kwargs(*, cwd: str | Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Standard ``Popen`` keyword arguments for a managed child.

    Pipes on all three streams, UTF-8 text with replacement so an odd byte
    can never abort a run, line buffering, and a new session so the child
    leads its own process group.
    """

    kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
        "start_new_session": True,
    }
    if env:
        kwargs["env"] = {**os.environ, **env}
    return kwargs


class ManagedProcess:
    """One child process with pumped streams, wall-clock ticks, and group kill."""

    def __init__(
        self,
        proc: Any,
        *,
        name: str = "child",
        tick_seconds: float = DEFAULT_TICK_SECONDS,
        pump: bool = True,
    ) -> None:
        self.proc = proc
        self.name = name
        self.tick_seconds = max(0.01, float(tick_seconds))
        self._stdout: queue.Queue[Any] = queue.Queue()
        self._stderr: deque[str] = deque(maxlen=STDERR_BUFFER_LINES)
        self._stderr_dropped = 0
        self._stderr_done = threading.Event()
        self._registered = False
        self._threads: list[threading.Thread] = []

        if pump and getattr(proc, "stdout", None) is not None:
            self._threads.append(
                threading.Thread(
                    target=self._pump_stdout, name=f"foreman-{name}-stdout", daemon=True
                )
            )
        else:
            self._stdout.put(_EOF)
        if pump and getattr(proc, "stderr", None) is not None:
            self._threads.append(
                threading.Thread(
                    target=self._pump_stderr, name=f"foreman-{name}-stderr", daemon=True
                )
            )
        else:
            self._stderr_done.set()
        for thread in self._threads:
            thread.start()

        with _registry_lock:
            _registry.add(self)
        self._registered = True

    # ── stream pumps ──────────────────────────────────────────────────────

    def _pump_stdout(self) -> None:
        try:
            for line in _iter_stream(self.proc.stdout):
                self._stdout.put(line)
        except Exception as exc:  # noqa: BLE001 - surfaced to the consumer
            self._stdout.put(exc)
        finally:
            self._stdout.put(_EOF)

    def _pump_stderr(self) -> None:
        try:
            for line in _iter_stream(self.proc.stderr):
                if len(self._stderr) == self._stderr.maxlen:
                    self._stderr_dropped += 1
                self._stderr.append(line.rstrip("\n"))
        except Exception:  # noqa: BLE001 - stderr is best effort
            pass
        finally:
            self._stderr_done.set()

    # ── reading ───────────────────────────────────────────────────────────

    def iter_lines(self) -> Iterator[str | None]:
        """Yield stdout lines as they arrive and ``None`` after each silent tick.

        Stops at end of stream. A read error on the pump thread is re-raised
        here so the caller sees it on its own thread.
        """

        while True:
            line = self.readline(timeout=self.tick_seconds)
            if line is None:
                yield None
                continue
            if line == "":
                return
            yield line

    def readline(self, *, timeout: float | None) -> str | None:
        """Return the next stdout line, ``""`` at end of stream, ``None`` on timeout."""

        try:
            item = self._stdout.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is _EOF:
            self._stdout.put(_EOF)  # keep EOF sticky for later readers
            return ""
        if isinstance(item, BaseException):
            raise item
        return str(item)

    def stderr_text(self, *, wait_seconds: float = 1.0) -> str:
        """Return drained stderr, waiting briefly for the pump to finish."""

        self._stderr_done.wait(wait_seconds)
        text = "\n".join(self._stderr)
        if self._stderr_dropped:
            text = (
                f"[... {self._stderr_dropped} earlier stderr lines dropped ...]\n{text}"
            )
        return text.strip()

    # ── lifecycle ─────────────────────────────────────────────────────────

    def poll(self) -> int | None:
        poll = getattr(self.proc, "poll", None)
        if callable(poll):
            return poll()
        return getattr(self.proc, "returncode", None)

    def is_running(self) -> bool:
        return self.poll() is None

    def wait(self, timeout: float | None = None) -> int | None:
        try:
            if timeout is None:
                return self.proc.wait()
            return self.proc.wait(timeout=timeout)
        except TypeError:  # fakes without a timeout parameter
            return self.proc.wait()
        except subprocess.TimeoutExpired:
            return None
        except OSError:
            return self.poll()

    def terminate(self, *, grace_seconds: float = DEFAULT_GRACE_SECONDS) -> None:
        """SIGTERM the process group, escalating to SIGKILL after the grace period."""

        if not self.is_running():
            self._unregister()
            return
        if not _signal_group(self.proc, signal.SIGTERM):
            _call_quietly(self.proc, "terminate")
        deadline = time.monotonic() + max(0.0, grace_seconds)
        while self.is_running() and time.monotonic() < deadline:
            time.sleep(0.05)
        if self.is_running():
            self.kill()
            return
        self._unregister()

    def kill(self) -> None:
        """SIGKILL the process group immediately and reap the child."""

        if not _signal_group(self.proc, signal.SIGKILL):
            _call_quietly(self.proc, "kill")
        self.wait(timeout=DEFAULT_GRACE_SECONDS)
        self._unregister()

    def close(self) -> None:
        """Stop the child if it is still running and leave the registry."""

        if self.is_running():
            self.terminate()
            return
        self._unregister()

    def _unregister(self) -> None:
        if self._registered:
            with _registry_lock:
                _registry.discard(self)
            self._registered = False
        self._release_streams()

    def _release_streams(self) -> None:
        """Close the child's pipes once it has exited and the pumps are done."""

        if self.is_running():
            return
        for thread in self._threads:
            thread.join(timeout=1.0)
        for name in ("stdin", "stdout", "stderr"):
            stream = getattr(self.proc, name, None)
            close = getattr(stream, "close", None)
            if stream is None or not callable(close) or getattr(stream, "closed", False):
                continue
            try:
                close()
            except (OSError, ValueError):
                pass


# ── shutdown handling ────────────────────────────────────────────────────


def live_processes() -> int:
    """Return how many managed processes are currently registered."""

    with _registry_lock:
        return len(_registry)


def terminate_all(*, grace_seconds: float = DEFAULT_GRACE_SECONDS) -> int:
    """Terminate every registered process group. Returns how many were signalled."""

    with _registry_lock:
        processes = list(_registry)
    for managed in processes:
        try:
            managed.terminate(grace_seconds=grace_seconds)
        except Exception:  # noqa: BLE001 - shutdown must not raise
            pass
    return len(processes)


def install_shutdown_handlers() -> bool:
    """Install SIGTERM / SIGINT handlers that stop children and raise ``EngineShutdown``.

    Only the main thread may install handlers; returns False when called from
    elsewhere so callers can proceed without them. Idempotent.
    """

    global _handlers_installed
    if _handlers_installed:
        return True
    if threading.current_thread() is not threading.main_thread():
        return False
    for signum in (signal.SIGTERM, signal.SIGINT):
        _previous_handlers[signum] = signal.signal(signum, _handle_shutdown_signal)
    atexit.register(terminate_all)
    _handlers_installed = True
    return True


def reset_shutdown_handlers() -> None:
    """Restore the handlers that were in place before ``install_shutdown_handlers``."""

    global _handlers_installed
    if not _handlers_installed:
        return
    for signum, previous in _previous_handlers.items():
        try:
            signal.signal(signum, previous if previous is not None else signal.SIG_DFL)
        except (ValueError, OSError):
            pass
    _previous_handlers.clear()
    _handlers_installed = False


def _handle_shutdown_signal(signum: int, _frame: Any) -> None:
    try:
        name = signal.Signals(signum).name
    except ValueError:
        name = str(signum)
    terminate_all(grace_seconds=2.0)
    raise EngineShutdown(name)


# ── helpers ───────────────────────────────────────────────────────────────


def _iter_stream(stream: Any) -> Iterator[str]:
    readline = getattr(stream, "readline", None)
    if callable(readline):
        while True:
            line = readline()
            if not line:
                return
            yield line
        return
    if hasattr(stream, "__iter__"):
        yield from stream
        return
    read = getattr(stream, "read", None)
    if callable(read):
        text = read()
        if text:
            yield from str(text).splitlines(keepends=True)


def _signal_group(proc: Any, sig: signal.Signals) -> bool:
    """Signal the child's process group. Returns False when that is not possible."""

    pid = getattr(proc, "pid", None)
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    if pgid != pid:
        # Not a session leader: the child shares a group with us, and killing
        # that group would kill this engine. Fall back to the single process.
        return False
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        return False
    return True


def _call_quietly(proc: Any, method_name: str) -> None:
    method = getattr(proc, method_name, None)
    if not callable(method):
        return
    try:
        method()
    except OSError:
        pass
