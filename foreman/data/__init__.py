"""Files Foreman ships with: role and workflow definitions, scaffold templates.

They live inside the package so an installed Foreman has them. ``DATA_DIR`` is
where they are on disk.
"""

from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
ROLES_DIR = DATA_DIR / "roles"
WORKFLOWS_DIR = DATA_DIR / "workflows"
TEMPLATES_DIR = DATA_DIR / "templates"
