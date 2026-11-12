"""Browser-driven end-to-end tests for the Foreman dashboard.

These tests require Playwright and Chromium browser binaries.  Install with:

    ./venv/bin/pip install playwright pytest-playwright
    ./venv/bin/playwright install chromium

The full suite is skipped gracefully if the playwright package or Chromium is
not available.  All other pytest runs are unaffected.

The fixture starts a real uvicorn server with a seeded SQLite database and
serves the built React frontend assets from
``foreman/dashboard_frontend_dist/``.  No Vite dev server or network access is
required.
"""

from __future__ import annotations

import re
import socket
import threading
import time
import unittest

try:
    import pytest
except ImportError as exc:  # pragma: no cover - exercised in minimal envs.
    raise unittest.SkipTest("pytest package not installed") from exc

from foreman.models import Project, Sprint, Task
from foreman.store import ForemanStore

# ---------------------------------------------------------------------------
# Skip the entire module if Playwright or Chromium is unavailable.
# ---------------------------------------------------------------------------

try:
    import playwright  # noqa: F401
    from playwright.sync_api import Page, expect
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

pytestmark = pytest.mark.skipif(
    not _HAS_PLAYWRIGHT,
    reason="playwright package not installed",
)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

_PROJECT_ID = "e2e-project-1"
_SPRINT_ID = "e2e-sprint-1"
_TASK_TODO_ID = "e2e-task-todo"
_TASK_IP_ID = "e2e-task-inprogress"
_TASK_BLOCKED_ID = "e2e-task-blocked"


def _seed_database(db_path: str) -> None:
    store = ForemanStore(db_path)
    store.initialize()
    try:
        project = Project(
            id=_PROJECT_ID,
            name="E2E Test Project",
            repo_path="/tmp/e2e",
            workflow_id="development",
            settings={"default_model": "claude-sonnet", "max_step_visits": 5},
        )
        store.save_project(project)

        sprint = Sprint(
            id=_SPRINT_ID,
            project_id=_PROJECT_ID,
            title="E2E Sprint One",
            goal="Validate the dashboard end to end.",
            status="active",
        )
        store.save_sprint(sprint)

        for tid, title, status in [
            (_TASK_TODO_ID, "Scaffold the database layer", "todo"),
            (_TASK_IP_ID, "Build the REST endpoints", "in_progress"),
            (_TASK_BLOCKED_ID, "Write acceptance tests", "blocked"),
        ]:
            store.save_task(
                Task(
                    id=tid,
                    sprint_id=_SPRINT_ID,
                    project_id=_PROJECT_ID,
                    title=title,
                    status=status,  # type: ignore[arg-type]
                    acceptance_criteria=f"Criteria for: {title}",
                    blocked_reason="Awaiting human approval" if status == "blocked" else None,
                )
            )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Live server fixture
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_dashboard_url(tmp_path_factory):
    """Start a real uvicorn dashboard server with seeded test data."""
    try:
        import uvicorn
        from foreman.dashboard_backend import create_dashboard_app
        from foreman.dashboard_runtime import DASHBOARD_INDEX_PATH
    except ImportError as exc:
        pytest.skip(f"Dashboard backend dependencies not available: {exc}")

    if not DASHBOARD_INDEX_PATH.is_file():
        pytest.skip(
            "Built frontend assets not found. Run `npm --prefix frontend run build` first."
        )

    db_path = str(tmp_path_factory.mktemp("e2e_db") / "e2e.db")
    _seed_database(db_path)

    port = _free_port()
    app = create_dashboard_app(db_path, frontend_mode="dist")
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait until the server is accepting connections (up to 5 s).
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("Live dashboard server did not start within 5 seconds.")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Page fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def dashboard_page(page: Page, live_dashboard_url: str) -> Page:
    """Open the workspace (ADR-0020) and wait for its projects table."""
    page.goto(f"{live_dashboard_url}/dashboard")
    expect(page.get_by_role("link", name="E2E Test Project")).to_be_visible(timeout=10_000)
    return page


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWorkspace:

    def test_project_list_visible(self, dashboard_page: Page) -> None:
        expect(dashboard_page.get_by_role("link", name="E2E Test Project")).to_be_visible()

    def test_page_title_set(self, dashboard_page: Page) -> None:
        expect(dashboard_page).to_have_title("Workspace \u00b7 Foreman")


class TestProjectNavigation:

    def test_open_project_shows_sprint_queue(self, dashboard_page: Page) -> None:
        dashboard_page.get_by_role("link", name="E2E Test Project").click()
        expect(dashboard_page).to_have_url(re.compile(f"/dashboard/projects/{_PROJECT_ID}$"))
        expect(dashboard_page.get_by_text("E2E Sprint One")).to_be_visible()

    def test_task_address_says_the_page_is_not_built_and_names_a_command(
        self, dashboard_page: Page, live_dashboard_url: str
    ) -> None:
        dashboard_page.goto(f"{live_dashboard_url}/dashboard/tasks/{_TASK_TODO_ID}")
        expect(dashboard_page.get_by_role("heading", name="This page is not built yet")).to_be_visible()
        expect(dashboard_page.get_by_text(f"foreman approve {_TASK_TODO_ID}")).to_be_visible()

    def test_legacy_address_is_not_found(self, dashboard_page: Page, live_dashboard_url: str) -> None:
        dashboard_page.goto(f"{live_dashboard_url}/dashboard/legacy")
        expect(dashboard_page.get_by_role("heading", name="Nothing is at this address")).to_be_visible()


class TestNewSprint:

    def _open_project(self, page: Page) -> None:
        page.get_by_role("link", name="E2E Test Project").click()
        expect(page.get_by_text("E2E Sprint One")).to_be_visible()

    def test_new_sprint_button_opens_dialog(self, dashboard_page: Page) -> None:
        self._open_project(dashboard_page)
        dashboard_page.get_by_role("button", name="New sprint").click()
        expect(dashboard_page.get_by_role("dialog", name="New sprint")).to_be_visible()

    def test_create_sprint_appears_in_the_queue(self, dashboard_page: Page) -> None:
        self._open_project(dashboard_page)
        dashboard_page.get_by_role("button", name="New sprint").click()
        dialog = dashboard_page.get_by_role("dialog", name="New sprint")
        dialog.get_by_role("textbox", name="Title").fill("E2E New Sprint")
        dialog.get_by_role("button", name="Create sprint").click()
        expect(dialog).not_to_be_visible()
        expect(dashboard_page.get_by_text("E2E New Sprint")).to_be_visible()
