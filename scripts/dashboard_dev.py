"""Run the Foreman dashboard frontend and backend in local development mode."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"
FOREMAN_BIN = REPO_ROOT / "venv" / "bin" / "foreman"

DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8080
DEFAULT_FRONTEND_HOST = "127.0.0.1"
DEFAULT_FRONTEND_PORT = 5173


def build_parser() -> argparse.ArgumentParser:
    """Build the local dashboard development runner parser."""

    parser = argparse.ArgumentParser(
        prog="dashboard_dev.py",
        description="Run the Foreman dashboard backend and Vite frontend together.",
    )
    parser.add_argument(
        "--db",
        help="Optional SQLite store path to pass through to the dashboard backend.",
    )
    parser.add_argument(
        "--backend-host",
        default=DEFAULT_BACKEND_HOST,
        help=f"Dashboard backend host (default: {DEFAULT_BACKEND_HOST}).",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=DEFAULT_BACKEND_PORT,
        help=f"Dashboard backend port (default: {DEFAULT_BACKEND_PORT}).",
    )
    parser.add_argument(
        "--frontend-host",
        default=DEFAULT_FRONTEND_HOST,
        help=f"Vite frontend host (default: {DEFAULT_FRONTEND_HOST}).",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=DEFAULT_FRONTEND_PORT,
        help=f"Vite frontend port (default: {DEFAULT_FRONTEND_PORT}).",
    )
    parser.add_argument(
        "--backend-reload",
        action="store_true",
        help="Enable uvicorn reload for the backend process.",
    )
    return parser


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()


def _kill(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()


def _wait_for_any(processes: Sequence[subprocess.Popen[str]]) -> subprocess.Popen[str]:
    while True:
        for process in processes:
            if process.poll() is not None:
                return process
        time.sleep(0.1)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local dashboard development workflow."""

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not FOREMAN_BIN.is_file():
        print(
            f"Missing Foreman CLI entrypoint at {FOREMAN_BIN}. Run `./venv/bin/pip install -e . --no-build-isolation` first.",
            file=sys.stderr,
        )
        return 1
    if shutil.which("npm") is None:
        print("Missing `npm` in PATH. Install Node.js tooling before running dashboard_dev.py.", file=sys.stderr)
        return 1

    frontend_dev_url = f"http://{args.frontend_host}:{args.frontend_port}"
    backend_url = f"http://{args.backend_host}:{args.backend_port}"

    backend_command = [
        str(FOREMAN_BIN),
        "dashboard",
        "--host",
        args.backend_host,
        "--port",
        str(args.backend_port),
        "--frontend-mode",
        "dev",
        "--frontend-dev-url",
        frontend_dev_url,
    ]
    if args.db:
        backend_command.extend(["--db", args.db])
    if args.backend_reload:
        backend_command.append("--reload")

    frontend_command = [
        "npm",
        "run",
        "dev",
        "--",
        "--host",
        args.frontend_host,
        "--port",
        str(args.frontend_port),
        "--strictPort",
    ]

    frontend_env = os.environ.copy()
    frontend_env["FOREMAN_DASHBOARD_BACKEND_URL"] = backend_url

    print(f"Dashboard backend: {backend_url}")
    print(f"Dashboard frontend: {frontend_dev_url}/dashboard")
    print("Press Ctrl+C to stop both processes.")

    backend_process = subprocess.Popen(
        backend_command,
        cwd=REPO_ROOT,
    )
    frontend_process = subprocess.Popen(
        frontend_command,
        cwd=FRONTEND_DIR,
        env=frontend_env,
    )

    processes = [backend_process, frontend_process]
    try:
        completed = _wait_for_any(processes)
    except KeyboardInterrupt:
        completed = None
    finally:
        for process in processes:
            _terminate(process)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _kill(process)
        for process in processes:
            if process.poll() is None:
                process.wait()

    if completed is None:
        return 130
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
