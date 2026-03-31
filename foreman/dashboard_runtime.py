"""Dashboard runtime entrypoint and frontend asset helpers."""

from __future__ import annotations

import os
from pathlib import Path

from .dashboard_service import (
    STREAM_BATCH_LIMIT,
    STREAM_HEARTBEAT_SECONDS,
    STREAM_POLL_INTERVAL_SECONDS,
)
from .store import ForemanStore


DEFAULT_DASHBOARD_HOST = "localhost"
DEFAULT_DASHBOARD_PORT = 8080
DEFAULT_FRONTEND_DEV_URL = "http://127.0.0.1:5173"

DASHBOARD_DIST_DIR = Path(__file__).with_name("dashboard_frontend_dist")
DASHBOARD_INDEX_PATH = DASHBOARD_DIST_DIR / "index.html"
DASHBOARD_ASSETS_DIR = DASHBOARD_DIST_DIR / "assets"


def ensure_dashboard_assets() -> None:
    """Fail clearly when the built React dashboard is not present."""

    if DASHBOARD_INDEX_PATH.is_file():
        return
    raise RuntimeError(
        "Dashboard frontend assets are missing. Run `npm install` and `npm run build` in `frontend/`."
    )


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


def run_dashboard_server(
    db_path: str,
    *,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
    frontend_mode: str = "dist",
    frontend_dev_url: str = DEFAULT_FRONTEND_DEV_URL,
    reload: bool = False,
) -> None:
    """Run the dashboard web server through the FastAPI backend."""

    from .dashboard_backend import create_dashboard_app

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "Dashboard backend dependencies are missing; install FastAPI and uvicorn."
        ) from exc

    if frontend_mode == "dist":
        ensure_dashboard_assets()
    elif frontend_mode == "dev":
        frontend_dev_url = normalize_frontend_dev_url(frontend_dev_url)
    else:
        raise RuntimeError(
            f"Unsupported dashboard frontend mode: {frontend_mode}. Expected `dist` or `dev`."
        )

    init_store = ForemanStore(db_path)
    init_store.initialize()
    init_store.close()

    if frontend_mode == "dist":
        print(f"Foreman dashboard running at http://{host}:{port}/dashboard")
    else:
        print(f"Foreman dashboard backend running at http://{host}:{port}")
        print(f"Frontend dev server: {frontend_dev_url}/dashboard")
    print(f"Database: {db_path}")
    print("Press Ctrl+C to stop.")
    if reload:
        os.environ["FOREMAN_DASHBOARD_DB_PATH"] = db_path
        os.environ["FOREMAN_DASHBOARD_FRONTEND_MODE"] = frontend_mode
        if frontend_mode == "dev":
            os.environ["FOREMAN_DASHBOARD_FRONTEND_DEV_URL"] = frontend_dev_url
        else:
            os.environ.pop("FOREMAN_DASHBOARD_FRONTEND_DEV_URL", None)
        app_target = "foreman.dashboard_backend:create_dashboard_app_from_env"
        app_kwargs = {"factory": True}
    else:
        app_target = create_dashboard_app(
            db_path,
            frontend_mode=frontend_mode,
            frontend_dev_url=frontend_dev_url if frontend_mode == "dev" else None,
        )
        app_kwargs = {}

    uvicorn.run(
        app_target,
        host=host,
        port=port,
        log_level="warning",
        reload=reload,
        **app_kwargs,
    )
