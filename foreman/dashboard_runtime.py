"""Dashboard runtime entrypoint and frontend asset helpers."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
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


def is_loopback_host(host: str) -> bool:
    """Return whether a bind host only reaches this machine."""

    candidate = host.strip().lower()
    if candidate in {"localhost", "ip6-localhost"}:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class DashboardSecurity:
    """Resolved security posture for one dashboard process."""

    host: str
    auth_token: str | None
    manager_enabled: bool
    notices: tuple[str, ...] = field(default_factory=tuple)


def dashboard_security_policy(
    host: str,
    *,
    auth_token: str | None,
    allow_insecure_network: bool = False,
    allow_remote_manager: bool = False,
) -> DashboardSecurity:
    """Decide what a bind host is allowed to expose.

    A non-loopback bind needs a shared token unless the operator explicitly
    accepts an open network; the manager chat, which runs a full-access agent
    on the server, stays loopback-only unless explicitly allowed.
    """

    loopback = is_loopback_host(host)
    notices: list[str] = []
    if not loopback and not auth_token and not allow_insecure_network:
        raise RuntimeError(
            f"Refusing to bind the dashboard to {host!r} without a token. Pass --token "
            "(or set FOREMAN_DASHBOARD_TOKEN), or pass --allow-insecure-network on a "
            "network you trust."
        )
    if not loopback and not auth_token:
        notices.append(
            f"WARNING: the dashboard is reachable on {host} without a token; anyone on "
            "the network can start and stop agents."
        )
    manager_enabled = loopback or allow_remote_manager
    if not manager_enabled:
        notices.append(
            "Manager chat disabled: it runs a full-access agent session on this host and "
            "is loopback-only unless --allow-remote-manager is passed."
        )
    elif not loopback:
        notices.append(
            "WARNING: the manager chat is enabled on a non-loopback bind; every token "
            "holder can run an agent with full access to the project repositories."
        )
    return DashboardSecurity(
        host=host,
        auth_token=auth_token or None,
        manager_enabled=manager_enabled,
        notices=tuple(notices),
    )


def run_dashboard_server(
    db_path: str,
    *,
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
    frontend_mode: str = "dist",
    frontend_dev_url: str = DEFAULT_FRONTEND_DEV_URL,
    reload: bool = False,
    auth_token: str | None = None,
    allowed_origins: tuple[str, ...] = (),
    allow_insecure_network: bool = False,
    allow_remote_manager: bool = False,
) -> None:
    """Run the dashboard web server through the FastAPI backend."""

    from .dashboard_backend import create_dashboard_app

    security = dashboard_security_policy(
        host,
        auth_token=auth_token,
        allow_insecure_network=allow_insecure_network,
        allow_remote_manager=allow_remote_manager,
    )

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
    print("Access token: required" if security.auth_token else "Access token: none (loopback only)")
    for notice in security.notices:
        print(notice)
    print("Press Ctrl+C to stop.")
    if reload:
        os.environ["FOREMAN_DASHBOARD_DB_PATH"] = db_path
        os.environ["FOREMAN_DASHBOARD_FRONTEND_MODE"] = frontend_mode
        if security.auth_token:
            os.environ["FOREMAN_DASHBOARD_TOKEN"] = security.auth_token
        else:
            os.environ.pop("FOREMAN_DASHBOARD_TOKEN", None)
        os.environ["FOREMAN_DASHBOARD_ALLOWED_ORIGINS"] = ",".join(allowed_origins)
        os.environ["FOREMAN_DASHBOARD_MANAGER"] = "1" if security.manager_enabled else "0"
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
            auth_token=security.auth_token,
            allowed_origins=allowed_origins,
            manager_enabled=security.manager_enabled,
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
