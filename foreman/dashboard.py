"""Dashboard runtime entrypoint and frontend asset helpers."""

from __future__ import annotations

from pathlib import Path

from .dashboard_api import (
    STREAM_BATCH_LIMIT,
    STREAM_HEARTBEAT_SECONDS,
    STREAM_POLL_INTERVAL_SECONDS,
)
from .store import ForemanStore


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


def run_dashboard(db_path: str, host: str = "localhost", port: int = 8080) -> None:
    """Run the dashboard web server through the FastAPI backend."""

    from .dashboard_backend import create_dashboard_app

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "Dashboard backend dependencies are missing; install FastAPI and uvicorn."
        ) from exc

    ensure_dashboard_assets()

    init_store = ForemanStore(db_path)
    init_store.initialize()
    init_store.close()

    print(f"Foreman dashboard running at http://{host}:{port}/dashboard")
    print(f"Database: {db_path}")
    print("Press Ctrl+C to stop.")
    uvicorn.run(
        create_dashboard_app(db_path),
        host=host,
        port=port,
        log_level="warning",
    )
