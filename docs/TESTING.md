# TESTING

## Principle

Foreman testing should verify durable workflow behavior, not just syntax.
Compilation-only checks are insufficient.
String-presence assertions are acceptable for bootstrap seams, but not as the
final validation strategy for finished product surfaces.

## Current baseline

The repo is still pre-release, so the current mandatory checks include both
repo-memory validation and code-level regression coverage:

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`
- `./venv/bin/pip install -e . --no-build-isolation`
- `npm --prefix frontend test`
- `npm --prefix frontend run build`
- `./venv/bin/python scripts/dashboard_dev.py --help`
- `./venv/bin/python -m unittest discover -s tests -v`

## Slice coverage that exists today

The current suite covers:

- `tests/test_store.py` for SQLite round-trips, status-filtered reads, run
  totals, recent-event slices, incremental event cursors, sprint-scoped event
  queries, and event retention pruning
- `tests/test_roles.py` and `tests/test_workflows.py` for shipped declarative
  configuration loading and validation
- `tests/test_scaffold.py` for generated `AGENTS.md`, idempotent `.gitignore`
  updates, default `.foreman.db` ignore behavior, and repo re-initialization
  behavior
- `tests/test_context.py` for `.foreman/context.md` and `.foreman/status.md`
  rendering
- `tests/test_orchestrator.py` for workflow execution, dependency-aware task
  selection, test failure carry-output, secure workflow approval and denial
  loops, native runner execution, preflight no-retry behavior, human-gate
  resume, event-retention startup behavior, retry persistence, and
  fresh-process native session reuse
- `tests/test_cli.py` for CLI smoke paths, repo-local DB discovery, explicit
  override semantics, secure workflow initialization, live watch tails,
  monitoring command subprocess behavior, and the shipped project, sprint,
  task, run, and config command flows
- `tests/test_runner_claude.py` for Claude Code command construction, startup
  preflight, event mapping, signal extraction, and failure handling
- `tests/test_runner_codex.py` for Codex app-server startup, thread start or
  resume, startup preflight, approval responses, streamed event mapping, and
  failure handling
- `tests/test_dashboard.py` for the extracted dashboard service contract,
  FastAPI HTTP routes, built frontend shell delivery, frontend-dev redirect
  behavior, task detail data, human message persistence, incremental
  sprint-event stream payloads, and approve or deny integration behavior
- `frontend/src/App.test.jsx` for React dashboard navigation, message
  submission, and stream-driven activity updates
- `tests/test_executor.py` for runner-backed execution config, event
  translation, completion handling, and infrastructure-error behavior in
  `foreman.executor`
- `tests/test_reviewed_codex.py` for reviewed Codex continuation behavior

## Expected testing layers

Unit tests:

- model validation
- SQLite store round-trips
- role and workflow parsing
- signal parsing
- dashboard service payloads and action behavior
- dashboard FastAPI route behavior over ASGI transport
- dashboard shell and asset delivery over the dedicated frontend boundary
- dashboard frontend-dev redirect behavior and local proxy assumptions
- dashboard live transport serialization
- git helper behavior that can be isolated
- frontend component behavior in the dedicated React app

Integration tests:

- project initialization
- sprint and task lifecycle
- orchestrator transitions
- `development_secure` approval and denial paths through `security_review`
- event-retention pruning with preserved blocked and in-progress task history
- CLI live-tail watch behavior across project, sprint, and run scopes
- built-in test, merge, and human-gate steps
- context projection into `.foreman/`
- cross-invocation native session reuse for Claude Code, Codex, and
  non-persistent reviewer roles
- dashboard API contract behavior independent of the frontend implementation
- local dashboard dev-runner smoke behavior where practical

Runner smoke tests:

- Claude Code runner wiring
- Codex runner wiring
- preflight classification plus event capture and retry behavior

UI validation:

- manual checks against `docs/mockups/foreman-mockup-v6.html`
- project dashboard navigation
- sprint board interactions
- activity feed behavior and live stream updates
- alignment between dashboard sprint streaming and CLI watch tailing
- human message, filter, and approve or deny flows
- browser-driven validation for the dedicated frontend

## Definition of done

Do not mark a task done unless:

- the relevant automated checks pass,
- new behavior is covered by tests when practical,
- user-visible changes include validation notes,
- the docs reflect the new reality.

For product UI work, "done" should include API contract coverage, frontend
behavior coverage, and browser or bundle-level validation rather than only
backend tests that inspect HTML strings.

If a slice cannot reasonably add tests yet, explain why in the PR summary and
record the follow-up explicitly.
