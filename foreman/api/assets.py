"""The dashboard's frontend bundle: where it is, whether it is current, building it.

The bundle is not kept in git (``frontend/`` builds it into
``foreman/dashboard_frontend_dist``). ``foreman dashboard`` builds it when it
is missing or older than its source; ``app`` serves it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

#: The built bundle, inside the package so an installed Foreman ships it.
DASHBOARD_DIST_DIR = Path(__file__).resolve().parent.parent / "dashboard_frontend_dist"
DASHBOARD_INDEX_PATH = DASHBOARD_DIST_DIR / "index.html"
DASHBOARD_ASSETS_DIR = DASHBOARD_DIST_DIR / "assets"


#: The frontend source beside the package, present in a source checkout and
#: absent from an installed package (which ships the built bundle instead).
FRONTEND_SOURCE_DIR = Path(__file__).resolve().parents[2] / "frontend"

#: What decides whether a built bundle is older than its source.
_FRONTEND_BUILD_INPUTS = ("src", "index.html", "package.json", "package-lock.json", "vite.config.js")

MISSING_BUNDLE_MESSAGE = (
    "The dashboard frontend is not built. It is not kept in git: run "
    "`npm --prefix frontend ci` and `npm --prefix frontend run build`, or start "
    "the dashboard with `foreman dashboard`, which builds it."
)


def dashboard_assets_present() -> bool:
    """Whether a built dashboard bundle is there to serve."""

    return DASHBOARD_INDEX_PATH.is_file()


def ensure_dashboard_assets() -> None:
    """Fail clearly when the built React dashboard is not present."""

    if dashboard_assets_present():
        return
    raise RuntimeError(MISSING_BUNDLE_MESSAGE)


def _newest_mtime(path: Path) -> float:
    if path.is_file():
        return path.stat().st_mtime
    newest = 0.0
    for child in path.rglob("*"):
        if child.is_file():
            newest = max(newest, child.stat().st_mtime)
    return newest


def dashboard_bundle_is_stale(
    source_dir: Path = FRONTEND_SOURCE_DIR, index_path: Path = DASHBOARD_INDEX_PATH
) -> bool:
    """Whether the frontend source changed after the bundle was built.

    True when there is no bundle. False when there is no source to compare
    with (an installed package).
    """

    if not index_path.is_file():
        return True
    if not (source_dir / "package.json").is_file():
        return False
    built_at = index_path.stat().st_mtime
    return any(
        _newest_mtime(source_dir / name) > built_at
        for name in _FRONTEND_BUILD_INPUTS
        if (source_dir / name).exists()
    )


def build_dashboard_assets(
    source_dir: Path = FRONTEND_SOURCE_DIR,
    *,
    run: Any = subprocess.run,
    which: Any = shutil.which,
    announce: Any = print,
) -> None:
    """Build the bundle from the source checkout with npm.

    The bundle is not in git (ADR-0020, decision 10), so a checkout has none
    until this runs. ``npm ci`` runs first when dependencies are not installed.
    """

    npm = which("npm")
    if npm is None:
        raise RuntimeError(
            "The dashboard frontend needs building and `npm` was not found. Install "
            "Node.js, or install Foreman from a built package, which includes the bundle."
        )
    steps: list[list[str]] = []
    if not (source_dir / "node_modules").exists():
        steps.append([npm, "ci"])
    steps.append([npm, "run", "build"])
    for step in steps:
        announce(f"Building the dashboard frontend: {' '.join(['npm', *step[1:]])} (in {source_dir})")
        result = run(step, cwd=str(source_dir), capture_output=True, text=True, check=False)
        if result.returncode != 0:
            tail = "\n".join((result.stdout + "\n" + result.stderr).strip().splitlines()[-15:])
            raise RuntimeError(
                f"Building the dashboard frontend failed (`npm {' '.join(step[1:])}`):\n{tail}"
            )


def prepare_dashboard_assets() -> None:
    """Make sure there is a current bundle to serve, building it if needed.

    In a source checkout the bundle is built when it is missing or older than
    the frontend source, unless ``FOREMAN_DASHBOARD_NO_BUILD`` is set. An
    installed package has no source and must already contain the bundle.
    """

    has_source = (FRONTEND_SOURCE_DIR / "package.json").is_file()
    if has_source and not os.environ.get("FOREMAN_DASHBOARD_NO_BUILD") and dashboard_bundle_is_stale():
        build_dashboard_assets()
    ensure_dashboard_assets()


def normalize_frontend_dev_url(frontend_dev_url: str) -> str:
    """Normalize one dev-server origin for backend redirects."""

    normalized = frontend_dev_url.strip().rstrip("/")
    if not normalized:
        raise RuntimeError("Dashboard frontend dev URL is required in frontend dev mode.")
    if "://" not in normalized:
        raise RuntimeError(
            "Dashboard frontend dev URL must include a scheme, for example http://127.0.0.1:5173."
        )
    return normalized


def build_frontend_dev_redirect_url(frontend_dev_url: str, path: str) -> str:
    """Build one redirect URL into the frontend dev server."""

    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalize_frontend_dev_url(frontend_dev_url)}{normalized_path}"
