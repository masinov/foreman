"""Running the dashboard: its bind, its security posture, and the server.

The frontend bundle it serves is ``assets``.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field

from .app import create_dashboard_app
from .assets import normalize_frontend_dev_url, prepare_dashboard_assets
from .guard import trusted_hosts_for_bind
from ..store import ForemanStore


DEFAULT_DASHBOARD_HOST = "localhost"
DEFAULT_DASHBOARD_PORT = 8080
DEFAULT_FRONTEND_DEV_URL = "http://127.0.0.1:5173"

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
    accepts an open network; the manager chat, whose agent session reads the
    repository and runs foreman commands on the server, stays loopback-only unless explicitly allowed.
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
            "Manager chat disabled: its agent session reads the repository and runs foreman commands on this "
            "host, so it is loopback-only unless --allow-remote-manager is passed."
        )
    elif not loopback:
        notices.append(
            "WARNING: the manager chat is enabled on a non-loopback bind; every token "
            "holder can start an agent session that reads the project repositories and runs "
            "foreman commands on this host."
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
        prepare_dashboard_assets()
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
    # Without a token nothing but the Host header tells the dashboard's own
    # page from a hostile name re-pointed at this machine.
    trusted_hosts = None if security.auth_token else trusted_hosts_for_bind(host)
    if reload:
        os.environ["FOREMAN_DASHBOARD_DB_PATH"] = db_path
        os.environ["FOREMAN_DASHBOARD_FRONTEND_MODE"] = frontend_mode
        if security.auth_token:
            os.environ["FOREMAN_DASHBOARD_TOKEN"] = security.auth_token
        else:
            os.environ.pop("FOREMAN_DASHBOARD_TOKEN", None)
        os.environ["FOREMAN_DASHBOARD_ALLOWED_ORIGINS"] = ",".join(allowed_origins)
        os.environ["FOREMAN_DASHBOARD_MANAGER"] = "1" if security.manager_enabled else "0"
        if trusted_hosts is None:
            os.environ.pop("FOREMAN_DASHBOARD_TRUSTED_HOSTS", None)
        else:
            os.environ["FOREMAN_DASHBOARD_TRUSTED_HOSTS"] = ",".join(trusted_hosts)
        if frontend_mode == "dev":
            os.environ["FOREMAN_DASHBOARD_FRONTEND_DEV_URL"] = frontend_dev_url
        else:
            os.environ.pop("FOREMAN_DASHBOARD_FRONTEND_DEV_URL", None)
        app_target = "foreman.api.app:create_dashboard_app_from_env"
        app_kwargs = {"factory": True}
    else:
        app_target = create_dashboard_app(
            db_path,
            frontend_mode=frontend_mode,
            frontend_dev_url=frontend_dev_url if frontend_mode == "dev" else None,
            auth_token=security.auth_token,
            allowed_origins=allowed_origins,
            manager_enabled=security.manager_enabled,
            trusted_hosts=trusted_hosts,
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
