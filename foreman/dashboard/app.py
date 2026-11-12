"""FastAPI backend for the Foreman dashboard."""

from __future__ import annotations

import hmac
import mimetypes
import os
from pathlib import Path

import logging

from fastapi import FastAPI, Request

from .. import __version__
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from ..dashboard_runtime import (
    DASHBOARD_ASSETS_DIR,
    DASHBOARD_INDEX_PATH,
    MISSING_BUNDLE_MESSAGE,
    build_frontend_dev_redirect_url,
    dashboard_assets_present,
    normalize_frontend_dev_url,
)
from ..api_tokens import looks_like_api_token
from ..dashboard_guard import browser_request_violation
from ..dashboard_service import (
    DashboardActionError,
    DashboardAuthError,
    DashboardNotFoundError,
    DashboardPermissionError,
    DashboardValidationError,
)
from ..store import ForemanStore
from .context import (
    API_PREFIXES,
    TOKEN_HEADER,
    ApiContext,
    DashboardForbiddenError,
    presented_token,
)
from .routers import (
    backlog,
    engine,
    gates,
    intake,
    meta,
    projects,
    roles,
    sprints,
    tasks,
    worktrees,
)

#: Mounted in this order under every API prefix.
ROUTERS = (projects, intake, backlog, sprints, meta, gates, engine, worktrees, tasks, roles)

_LOGGER = logging.getLogger("foreman.dashboard")


def _token_matches(request: Request, expected: str) -> bool:
    presented = presented_token(request)
    if not presented:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


def _error_body(message: str, code: str) -> dict[str, str]:
    """The one shape of an API error: a sentence for people, a code for programs."""

    return {"error": message, "code": code}


def _is_intake_path(path: str) -> bool:
    """True for ``<api prefix>/projects/{id}/intake`` and nothing else.

    Project ids are opaque but never contain a slash, so the segment count is
    an exact test rather than a prefix guess. Every prefix the API is served
    under is recognised, longest first, so ``/api/v1/...`` is not mistaken
    for a project called ``v1``.
    """

    for prefix in sorted(API_PREFIXES, key=len, reverse=True):
        if path.startswith(prefix + "/"):
            parts = path[len(prefix) :].strip("/").split("/")
            return len(parts) == 3 and parts[0] == "projects" and parts[2] == "intake"
    return False


def create_dashboard_app(
    db_path: str,
    *,
    frontend_mode: str = "dist",
    frontend_dev_url: str | None = None,
    auth_token: str | None = None,
    allowed_origins: tuple[str, ...] | list[str] = (),
    manager_enabled: bool = True,
    trusted_hosts: tuple[str, ...] | list[str] | None = None,
) -> FastAPI:
    """Create the FastAPI application used for dashboard delivery.

    ``auth_token`` protects every ``/api`` route with a shared token
    (``Authorization: Bearer``, ``X-Foreman-Token``, or ``?token=`` for the
    event stream). ``allowed_origins`` enables CORS only for the listed
    origins; the shipped frontend is same-origin and needs none.
    ``manager_enabled`` gates the manager chat, which runs a full-access
    agent session on the server and must stay off on non-loopback binds
    unless explicitly allowed. ``trusted_hosts`` lists the host names the API
    answers to; the runtime sets it whenever no token protects the API, so a
    hostile name re-pointed at this machine is refused. ``None`` leaves the
    ``Host`` header unchecked.
    """

    # The API does not depend on the bundle: it is built, not committed
    # (ADR-0020), so the app starts without it and the shell route says so.
    if frontend_mode == "dist":
        pass
    elif frontend_mode == "dev":
        if frontend_dev_url is None:
            raise RuntimeError("Frontend dev mode requires a frontend dev URL.")
        frontend_dev_url = normalize_frontend_dev_url(frontend_dev_url)
    else:
        raise RuntimeError(
            f"Unsupported dashboard frontend mode: {frontend_mode}. Expected `dist` or `dev`."
        )

    init_store = ForemanStore(db_path)
    try:
        init_store.initialize()
    finally:
        init_store.close()

    app = FastAPI(
        title="Foreman Dashboard API",
        version=__version__,
        # The generated schema carries no request or response models yet, and
        # these routes sit outside /api, so they would be served without the
        # token. They return with the typed API contract.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.db_path = db_path
    app.state.frontend_mode = frontend_mode
    app.state.frontend_dev_url = frontend_dev_url
    app.state.auth_token = auth_token or None
    app.state.manager_enabled = bool(manager_enabled)
    origins = tuple(origin.strip() for origin in allowed_origins if origin and origin.strip())
    app.state.trusted_hosts = tuple(trusted_hosts) if trusted_hosts is not None else None
    # In dev mode the browser talks to the Vite server, which proxies /api
    # here and forwards its own origin.
    guard_origins = origins + ((frontend_dev_url,) if frontend_mode == "dev" and frontend_dev_url else ())
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", TOKEN_HEADER],
        )

    @app.middleware("http")
    async def require_dashboard_token(request: Request, call_next):
        """Separate the two credentials that can reach ``/api``.

        The shared dashboard token opens every route except intake; a project
        API token opens intake and nothing else. The second half holds whether
        or not a dashboard token is configured, so a leaked intake token can
        never be replayed as a dashboard session on an unauthenticated bind.
        The intake route authenticates its own token against the database --
        the middleware only decides which credential is allowed where.
        """

        path = request.url.path
        expected = app.state.auth_token
        if path.startswith("/api/") and request.method != "OPTIONS":
            is_intake = _is_intake_path(path)
            presented = presented_token(request)
            is_dashboard_token = bool(expected) and _token_matches(request, expected)
            if is_intake:
                # The dashboard's shared token is a session credential, not an
                # attributable identity; intake records who filed the work.
                if not looks_like_api_token(presented):
                    return JSONResponse(
                        {
                            "error": (
                                "Unauthorized: intake requires a project API token "
                                "(`foreman token create`) as `Authorization: Bearer <token>`."
                            )
                        },
                        status_code=401,
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            elif not is_dashboard_token and looks_like_api_token(presented):
                return JSONResponse(
                    _error_body(
                        "Forbidden: a project API token is only valid on "
                        "POST /api/v1/projects/{id}/intake.",
                        "forbidden",
                    ),
                    status_code=403,
                )
            elif expected and not is_dashboard_token:
                return JSONResponse(
                    _error_body("Unauthorized: a dashboard token is required.", "unauthorized"),
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)

    @app.middleware("http")
    async def refuse_foreign_browser_requests(request: Request, call_next):
        """Refuse cross-site and rebinding requests before any credential check.

        Intake is exempt from the origin rules: it is a server-to-server route
        that authenticates its own project API token, which no web page holds.
        """

        path = request.url.path
        if path.startswith("/api/") and request.method != "OPTIONS" and not _is_intake_path(path):
            violation = browser_request_violation(
                method=request.method,
                headers=request.headers,
                trusted_hosts=app.state.trusted_hosts,
                allowed_origins=guard_origins,
            )
            if violation is not None:
                return JSONResponse(_error_body(violation, "forbidden"), status_code=403)
        return await call_next(request)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> Response:
        # An unknown route or a method the route does not take. Inside the
        # API the body is the same envelope as every other error.
        if not request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(
            _error_body(str(exc.detail), code),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ()) if part != "query")
        message = f"{where}: {first.get('msg', 'invalid value')}" if where else "Invalid request"
        return JSONResponse(_error_body(message, "invalid_request"), status_code=400)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # A bug. The caller gets the envelope and no internals; the log gets
        # the traceback.
        _LOGGER.error(
            "Unhandled error in %s %s", request.method, request.url.path, exc_info=exc
        )
        return JSONResponse(
            _error_body("Internal error. See the dashboard log.", "internal_error"),
            status_code=500,
        )

    @app.exception_handler(DashboardNotFoundError)
    async def handle_not_found(_: Request, exc: DashboardNotFoundError) -> JSONResponse:
        return JSONResponse(_error_body(str(exc), "not_found"), status_code=404)

    @app.exception_handler(DashboardValidationError)
    async def handle_validation(_: Request, exc: DashboardValidationError) -> JSONResponse:
        return JSONResponse(_error_body(str(exc), "invalid_request"), status_code=400)

    @app.exception_handler(DashboardActionError)
    async def handle_action(_: Request, exc: DashboardActionError) -> JSONResponse:
        return JSONResponse(_error_body(str(exc), "action_failed"), status_code=500)

    @app.exception_handler(DashboardAuthError)
    async def handle_auth(_: Request, exc: DashboardAuthError) -> JSONResponse:
        return JSONResponse(
            _error_body(str(exc), "unauthorized"),
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(DashboardPermissionError)
    async def handle_permission(_: Request, exc: DashboardPermissionError) -> JSONResponse:
        return JSONResponse(_error_body(str(exc), "not_permitted"), status_code=403)

    @app.exception_handler(DashboardForbiddenError)
    async def handle_forbidden(_: Request, exc: DashboardForbiddenError) -> JSONResponse:
        return JSONResponse(_error_body(str(exc), "forbidden"), status_code=403)

    context = ApiContext(db_path=db_path, manager_enabled=bool(manager_enabled))
    for prefix in API_PREFIXES:
        for module in ROUTERS:
            app.include_router(module.build_router(context), prefix=prefix)


    def _resolve_asset_path(asset_path: str) -> Path | None:
        candidate = (DASHBOARD_ASSETS_DIR / asset_path).resolve()
        try:
            candidate.relative_to(DASHBOARD_ASSETS_DIR.resolve())
        except ValueError:
            return None
        if not candidate.is_file():
            return None
        return candidate

    @app.get("/", include_in_schema=False)
    async def dashboard_root() -> RedirectResponse:
        if frontend_mode == "dev":
            return RedirectResponse(
                url=build_frontend_dev_redirect_url(frontend_dev_url, "/dashboard")
            )
        return RedirectResponse(url="/dashboard")

    @app.get("/assets/{asset_path:path}", include_in_schema=False)
    async def dashboard_asset(asset_path: str) -> Response:
        if frontend_mode != "dist":
            return Response(status_code=404)
        asset_file = _resolve_asset_path(asset_path)
        if asset_file is None:
            return Response(status_code=404)
        media_type = mimetypes.guess_type(asset_file.name)[0] or "application/octet-stream"
        return Response(asset_file.read_bytes(), media_type=media_type)

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/dashboard/{path:path}", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard_shell(path: str = "") -> Response:
        if frontend_mode == "dev":
            route_path = "/dashboard"
            if path:
                route_path = f"{route_path}/{path}"
            return RedirectResponse(
                url=build_frontend_dev_redirect_url(frontend_dev_url, route_path)
            )
        # Read per request, so a rebuilt bundle is served without a restart.
        if not dashboard_assets_present():
            return HTMLResponse(
                f"<!doctype html><title>Foreman</title><p>{MISSING_BUNDLE_MESSAGE}</p>",
                status_code=503,
            )
        return HTMLResponse(DASHBOARD_INDEX_PATH.read_text(encoding="utf-8"))

    return app


def create_dashboard_app_from_env() -> FastAPI:
    """Create the dashboard app from environment for uvicorn reload mode."""

    db_path = os.environ.get("FOREMAN_DASHBOARD_DB_PATH")
    if not db_path:
        raise RuntimeError("FOREMAN_DASHBOARD_DB_PATH is required for dashboard reload mode.")

    frontend_mode = os.environ.get("FOREMAN_DASHBOARD_FRONTEND_MODE", "dist")
    frontend_dev_url = os.environ.get("FOREMAN_DASHBOARD_FRONTEND_DEV_URL")
    auth_token = os.environ.get("FOREMAN_DASHBOARD_TOKEN") or None
    allowed_origins = tuple(
        origin for origin in os.environ.get("FOREMAN_DASHBOARD_ALLOWED_ORIGINS", "").split(",") if origin
    )
    manager_enabled = os.environ.get("FOREMAN_DASHBOARD_MANAGER", "1") != "0"
    trusted_hosts_setting = os.environ.get("FOREMAN_DASHBOARD_TRUSTED_HOSTS")
    trusted_hosts = (
        tuple(name for name in trusted_hosts_setting.split(",") if name)
        if trusted_hosts_setting
        else None
    )
    return create_dashboard_app(
        db_path,
        frontend_mode=frontend_mode,
        frontend_dev_url=frontend_dev_url,
        auth_token=auth_token,
        allowed_origins=allowed_origins,
        manager_enabled=manager_enabled,
        trusted_hosts=trusted_hosts,
    )
