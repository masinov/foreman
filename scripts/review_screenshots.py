"""Screenshots of dashboard pages for a review, at desktop and phone widths.

Usage, from a checkout with its own virtualenv (the sandbox has one):

    ./venv/bin/python scripts/review_screenshots.py /dashboard/projects/foreman [more paths]

It builds the frontend, copies Foreman's database read-only into
``.review/``, serves this checkout's dashboard from that copy on a free port
on localhost, and writes ``.review/<page>-1440.png`` and
``.review/<page>-390.png`` for each path. The live database and the live
dashboard are never touched. Needs the ``e2e`` extra (Playwright) and a
Chromium-family browser: Playwright's own, or one found on the PATH.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request

WIDTHS = ((1440, 900), (390, 844))
BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def copy_database(source: Path, target: Path) -> None:
    target.unlink(missing_ok=True)
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def wait_for(url: str, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise SystemExit(f"The preview dashboard did not answer at {url}.")


def main_checkout(root: Path) -> Path:
    """The main checkout a worktree or sandbox belongs to (where the database lives)."""

    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"], cwd=root, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, check=True,
    )
    return (root / common.stdout.strip()).resolve().parent


def page_name(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "root"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", help="Dashboard paths, e.g. /dashboard/projects/foreman")
    parser.add_argument(
        "--db",
        default=None,
        help="The database to copy (default: .foreman.db in the main checkout this worktree belongs to).",
    )
    parser.add_argument("--no-build", action="store_true", help="Use the bundle already built.")
    args = parser.parse_args()

    root = Path.cwd()
    out = root / ".review"
    out.mkdir(exist_ok=True)
    source = Path(args.db) if args.db else main_checkout(root) / ".foreman.db"
    if not source.is_file():
        print(f"No database at {source}; give one with --db.", file=sys.stderr)
        return 2
    if not args.no_build:
        subprocess.run(["npm", "--prefix", "frontend", "run", "build"], check=True, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL)
    copy_database(source, out / "review.db")
    # The dashboard no longer migrates when it opens (a deploy step since
    # FOR-87): the copy is brought to this checkout's schema, so a branch that
    # adds a migration can still be looked at.
    migrated = subprocess.run(
        [str(root / "venv/bin/foreman"), "db", "migrate", "--db", str(out / "review.db")],
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    if migrated.returncode != 0:
        print(f"Could not migrate the copy of the database:\n{migrated.stderr or migrated.stdout}", file=sys.stderr)
        return 1

    from playwright.sync_api import sync_playwright

    port = free_port()
    log = (out / "dashboard.log").open("w")
    server = subprocess.Popen(
        [str(root / "venv/bin/foreman"), "dashboard", "--db", str(out / "review.db"), "--port", str(port)],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
    )
    try:
        try:
            wait_for(f"http://127.0.0.1:{port}/dashboard")
        except SystemExit:
            log.flush()
            print((out / "dashboard.log").read_text(encoding="utf-8")[-2000:], file=sys.stderr)
            raise
        executable = next((shutil.which(name) for name in BROWSERS if shutil.which(name)), None)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable) if executable else playwright.chromium.launch()
            for path in args.paths:
                for width, height in WIDTHS:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.goto(f"http://127.0.0.1:{port}{path}")
                    page.wait_for_load_state("networkidle")
                    target = out / f"{page_name(path)}-{width}.png"
                    page.screenshot(path=str(target), full_page=True)
                    page.close()
                    print(target)
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
        log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
