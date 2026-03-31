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

import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest

from foreman.models import Project, Sprint, Task, utc_now_text
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
    """Navigate to the dashboard root and return the ready Playwright page."""
    page.goto(f"{live_dashboard_url}/dashboard")
    # Wait for the React app to mount — the page title div is always present.
    expect(page.locator(".page-title").get_by_text("Projects")).to_be_visible(timeout=10_000)
    return page


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDashboardLoad:

    def test_project_list_visible(self, dashboard_page: Page) -> None:
        expect(dashboard_page.get_by_text("E2E Test Project")).to_be_visible()

    def test_foreman_logo_visible(self, dashboard_page: Page) -> None:
        expect(dashboard_page.get_by_text("FOREMAN")).to_be_visible()

    def test_page_title_set(self, dashboard_page: Page) -> None:
        assert "Foreman" in dashboard_page.title() or dashboard_page.title() != ""


class TestProjectNavigation:

    def test_open_project_shows_sprint_list(self, dashboard_page: Page) -> None:
        dashboard_page.get_by_role("button", name="Open project E2E Test Project").click()
        expect(dashboard_page.get_by_text("E2E Sprint One")).to_be_visible()

    def test_sprint_card_navigates_to_board(self, dashboard_page: Page) -> None:
        dashboard_page.get_by_role("button", name="Open project E2E Test Project").click()
        dashboard_page.get_by_role("button", name="Open sprint E2E Sprint One").click()
        # The sprint board shows task status column headers (scoped to .col-title
        # so we don't collide with the task detail status span).
        expect(dashboard_page.locator(".col-title", has_text="Todo")).to_be_visible()
        expect(dashboard_page.locator(".col-title", has_text="In Progress")).to_be_visible()
        expect(dashboard_page.locator(".col-title", has_text="Blocked")).to_be_visible()

    def test_sprint_board_shows_seeded_tasks(self, dashboard_page: Page) -> None:
        dashboard_page.get_by_role("button", name="Open project E2E Test Project").click()
        dashboard_page.get_by_role("button", name="Open sprint E2E Sprint One").click()
        # Use .card-title to scope to board cards only (detail drawer may be open).
        expect(dashboard_page.locator(".card-title", has_text="Scaffold the database layer")).to_be_visible()
        expect(dashboard_page.locator(".card-title", has_text="Build the REST endpoints")).to_be_visible()
        expect(dashboard_page.locator(".card-title", has_text="Write acceptance tests")).to_be_visible()


class TestTaskDetail:

    def _navigate_to_board(self, page: Page) -> None:
        page.get_by_role("button", name="Open project E2E Test Project").click()
        page.get_by_role("button", name="Open sprint E2E Sprint One").click()
        expect(page.locator(".card-title", has_text="Scaffold the database layer")).to_be_visible()

    def test_task_card_opens_detail_drawer(self, dashboard_page: Page) -> None:
        self._navigate_to_board(dashboard_page)
        # Detail drawer may already be open; close it first then click a card.
        close_btn = dashboard_page.get_by_role("button", name="Close task detail")
        if close_btn.is_visible():
            close_btn.click()
        dashboard_page.locator(".card-title", has_text="Scaffold the database layer").click()
        expect(dashboard_page.get_by_role("complementary", name="Task detail")).to_be_visible()

    def test_task_detail_shows_title(self, dashboard_page: Page) -> None:
        self._navigate_to_board(dashboard_page)
        # The in_progress task detail drawer opens automatically — check its title.
        detail = dashboard_page.get_by_role("complementary", name="Task detail")
        expect(detail).to_be_visible()
        expect(detail.locator("h2")).to_be_visible()

    def test_task_detail_shows_acceptance_criteria(self, dashboard_page: Page) -> None:
        self._navigate_to_board(dashboard_page)
        dashboard_page.locator(".card-title", has_text="Scaffold the database layer").click()
        detail = dashboard_page.get_by_role("complementary", name="Task detail")
        expect(detail.get_by_text("Criteria for: Scaffold the database layer")).to_be_visible()

    def test_task_detail_close_button_dismisses_drawer(self, dashboard_page: Page) -> None:
        self._navigate_to_board(dashboard_page)
        # Ensure drawer is open (auto-selected or manually selected).
        detail = dashboard_page.get_by_role("complementary", name="Task detail")
        if not detail.is_visible():
            dashboard_page.locator(".card-title", has_text="Build the REST endpoints").click()
        expect(detail).to_be_visible()
        dashboard_page.get_by_role("button", name="Close task detail").click()
        expect(detail).not_to_be_visible()


class TestSettingsPanel:

    def _navigate_to_project(self, page: Page) -> None:
        page.get_by_role("button", name="Open project E2E Test Project").click()
        expect(page.get_by_text("E2E Sprint One")).to_be_visible()

    def test_settings_button_opens_panel(self, dashboard_page: Page) -> None:
        self._navigate_to_project(dashboard_page)
        dashboard_page.locator("button[title='Settings']").click()
        expect(dashboard_page.get_by_role("complementary", name="Project settings")).to_be_visible()

    def test_settings_panel_shows_workflow_field(self, dashboard_page: Page) -> None:
        self._navigate_to_project(dashboard_page)
        dashboard_page.locator("button[title='Settings']").click()
        panel = dashboard_page.get_by_role("complementary", name="Project settings")
        expect(panel.get_by_text("Default workflow")).to_be_visible()

    def _get_merge_input(self, panel):
        # Settings form labels have no for/id association; find input within the form-group.
        return panel.locator(".form-group").filter(has_text="Merge target").locator("input")

    def test_settings_change_reveals_save_button(self, dashboard_page: Page) -> None:
        self._navigate_to_project(dashboard_page)
        dashboard_page.locator("button[title='Settings']").click()
        panel = dashboard_page.get_by_role("complementary", name="Project settings")
        merge_input = self._get_merge_input(panel)
        merge_input.click(click_count=3)
        merge_input.type("feat/e2e")
        expect(panel.get_by_role("button", name="Save settings")).to_be_visible()

    def test_settings_save_persists_and_closes_footer(self, dashboard_page: Page) -> None:
        self._navigate_to_project(dashboard_page)
        dashboard_page.locator("button[title='Settings']").click()
        panel = dashboard_page.get_by_role("complementary", name="Project settings")
        merge_input = self._get_merge_input(panel)
        merge_input.click(click_count=3)
        merge_input.type("feat/e2e-saved")
        panel.get_by_role("button", name="Save settings").click()
        # Footer disappears after successful save.
        expect(panel.get_by_role("button", name="Save settings")).not_to_be_visible()


class TestNewSprint:

    def _navigate_to_project(self, page: Page) -> None:
        page.get_by_role("button", name="Open project E2E Test Project").click()
        expect(page.get_by_text("E2E Sprint One")).to_be_visible()

    def test_new_sprint_button_opens_modal(self, dashboard_page: Page) -> None:
        self._navigate_to_project(dashboard_page)
        dashboard_page.get_by_role("button", name="New sprint").click()
        expect(dashboard_page.get_by_role("heading", name="New Sprint")).to_be_visible()

    def test_create_sprint_disabled_without_title(self, dashboard_page: Page) -> None:
        self._navigate_to_project(dashboard_page)
        dashboard_page.get_by_role("button", name="New sprint").click()
        create_btn = dashboard_page.get_by_role("button", name="Create sprint")
        expect(create_btn).to_be_disabled()

    def test_create_sprint_submits_and_appears_in_list(self, dashboard_page: Page) -> None:
        self._navigate_to_project(dashboard_page)
        dashboard_page.get_by_role("button", name="New sprint").click()
        dashboard_page.get_by_placeholder("Sprint 5").fill("E2E New Sprint")
        dashboard_page.get_by_role("button", name="Create sprint").click()
        # Modal should close and new sprint should appear in the list.
        expect(dashboard_page.get_by_role("heading", name="New Sprint")).not_to_be_visible()
        expect(dashboard_page.get_by_text("E2E New Sprint")).to_be_visible()


class TestNewTask:

    def _navigate_to_board(self, page: Page) -> None:
        page.get_by_role("button", name="Open project E2E Test Project").click()
        page.get_by_role("button", name="Open sprint E2E Sprint One").click()
        expect(page.locator(".card-title", has_text="Scaffold the database layer")).to_be_visible()
        # Close the auto-opened detail drawer so the board toolbar is not obscured.
        close_btn = page.get_by_role("button", name="Close task detail")
        if close_btn.is_visible():
            close_btn.click()
        expect(page.get_by_role("complementary", name="Task detail")).not_to_be_visible()

    def test_new_task_button_opens_modal(self, dashboard_page: Page) -> None:
        self._navigate_to_board(dashboard_page)
        dashboard_page.get_by_role("button", name="New task").click()
        expect(dashboard_page.get_by_role("heading", name="New Task")).to_be_visible()

    def test_create_task_disabled_without_title(self, dashboard_page: Page) -> None:
        self._navigate_to_board(dashboard_page)
        dashboard_page.get_by_role("button", name="New task").click()
        create_btn = dashboard_page.get_by_role("button", name="Create task")
        expect(create_btn).to_be_disabled()

    def test_create_task_submits_and_appears_on_board(self, dashboard_page: Page) -> None:
        self._navigate_to_board(dashboard_page)
        dashboard_page.get_by_role("button", name="New task").click()
        dashboard_page.get_by_placeholder("Short description of the task").fill("E2E Created Task")
        dashboard_page.get_by_role("button", name="Create task").click()
        # Modal closes and new task card appears in the Todo column.
        expect(dashboard_page.get_by_role("heading", name="New Task")).not_to_be_visible()
        expect(dashboard_page.locator(".card-title", has_text="E2E Created Task")).to_be_visible()
