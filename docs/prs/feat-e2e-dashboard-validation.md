# PR: feat/e2e-dashboard-validation

## Summary

Adds browser-driven end-to-end validation of the Foreman dashboard.  20
Playwright tests in `tests/test_e2e.py` drive a real Chromium browser against
a live uvicorn server backed by a seeded SQLite database, exercising the full
React → FastAPI → SQLite stack.

## Scope

- `tests/test_e2e.py` — 20 E2E tests across 6 test classes
- `pyproject.toml` — `e2e` optional dependency group (`playwright`, `pytest-playwright`)
- sprint and repo-memory docs

## Files changed

| File | Change |
|------|--------|
| `tests/test_e2e.py` | new |
| `pyproject.toml` | `e2e` optional-deps group added |
| `docs/prs/feat-e2e-dashboard-validation.md` | new |
| `docs/sprints/archive/sprint-27-e2e-dashboard-validation.md` | new |
| `docs/sprints/current.md` | sprint-27 tasks |
| `docs/sprints/backlog.md` | E2E item removed from next-up |
| `docs/STATUS.md` | updated |
| `docs/ARCHITECTURE.md` | next-slice updated |
| `docs/ROADMAP.md` | near-term priorities updated |
| `CHANGELOG.md` | updated |

## Test coverage

| Class | Tests | Flows covered |
|-------|-------|---------------|
| `TestDashboardLoad` | 3 | page renders, project visible, logo visible |
| `TestProjectNavigation` | 3 | open project, open sprint, board shows all task cards |
| `TestTaskDetail` | 4 | card click opens drawer, title, criteria, close button |
| `TestSettingsPanel` | 4 | open, workflow field, edit reveals save, save clears footer |
| `TestNewSprint` | 3 | modal opens, disabled without title, sprint appears after create |
| `TestNewTask` | 3 | modal opens, disabled without title, task appears after create |

## Live server fixture

`live_dashboard_url` (session scope): creates a temp SQLite database, seeds it
with a project, an active sprint, and three tasks (todo/in_progress/blocked),
starts a uvicorn server on a random free port using `create_dashboard_app()`,
waits up to 5 seconds for the socket to accept connections, and tears down on
session exit.

Skips gracefully when Playwright is not installed or built frontend assets are
absent.

## Risks

- E2E tests depend on the built React assets in `foreman/dashboard_frontend_dist/`.
  If the frontend is rebuilt with breaking changes the tests will surface
  selector drift immediately.
- The session-scoped server is shared across all 20 tests; tests that mutate
  data (sprint creation, task creation) run against the same database.  Test
  isolation relies on unique names for created entities.

## Tests

```
./venv/bin/python -m pytest tests/test_e2e.py -v
# 20 passed

./venv/bin/python -m pytest tests/ -x -q
# 208 passed
```

## Install E2E dependencies

```
./venv/bin/pip install playwright pytest-playwright
./venv/bin/playwright install chromium
```

## Acceptance criteria satisfied

- 20 E2E tests pass against the full stack ✓
- tests skip cleanly when Playwright is not installed ✓
- 208 total tests pass ✓
