"""Former home of the dashboard API. It lives in ``foreman.dashboard`` now.

Kept so ``foreman.dashboard_backend:create_dashboard_app_from_env`` (the
target uvicorn reloads) and existing imports keep working.
"""

from __future__ import annotations

from .dashboard.app import create_dashboard_app, create_dashboard_app_from_env

__all__ = ["create_dashboard_app", "create_dashboard_app_from_env"]
