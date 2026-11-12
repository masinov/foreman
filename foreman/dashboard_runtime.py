"""Dashboard runtime entrypoint and frontend asset helpers."""

from __future__ import annotations

import ipaddress
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dashboard_guard import trusted_hosts_for_bind
from .store import ForemanStore


DEFAULT_DASHBOARD_HOST = "localhost"
DEFAULT_DASHBOARD_PORT = 8080
DEFAULT_FRONTEND_DEV_URL = "http://127.0.0.1:5173"

DASHBOARD_DIST_DIR = Path(__file__).with_name("dashboard_frontend_dist")
DASHBOARD_INDEX_PATH = DASHBOARD_DIST_DIR / "index.html"
DASHBOARD_ASSETS_DIR = DASHBOARD_DIST_DIR / "assets"


#: The frontend source beside the package, present in a source checkout and
#: absent from an installed package (which ships the built bundle instead).
FRONTEND_SOURCE_DIR = Path(__file__).resolve().parent.parent / "frontend"

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
