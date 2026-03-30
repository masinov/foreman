# TESTING

## Principle

Foreman testing should verify durable workflow behavior, not just syntax.
Compilation-only checks are insufficient.

## Current baseline

The repo is still pre-release, so the current mandatory checks include both
repo-memory validation and code-level regression coverage:

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`
- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/python -m unittest discover -s tests -v`

## Slice coverage that exists today

The current suite covers:

- `tests/test_store.py` for SQLite round-trips, status-filtered reads, run
  totals, recent-event slices, and sprint-scoped event queries
- `tests/test_roles.py` and `tests/test_workflows.py` for shipped declarative
  configuration loading and validation
- `tests/test_scaffold.py` for generated `AGENTS.md`, idempotent `.gitignore`
  updates, default `.foreman.db` ignore behavior, and repo re-initialization
  behavior
- `tests/test_context.py` for `.foreman/context.md` and `.foreman/status.md`
  rendering
- `tests/test_orchestrator.py` for workflow execution, dependency-aware task
  selection, test failure carry-output, secure workflow approval and denial
  loops, native runner execution, human-gate resume, retry persistence, and
  fresh-process native session reuse
- `tests/test_cli.py` for CLI smoke paths, repo-local DB discovery, explicit
  override semantics, secure workflow initialization, and monitoring command
  subprocess behavior
- `tests/test_runner_claude.py` for Claude Code command construction, event
  mapping, signal extraction, and failure handling
- `tests/test_runner_codex.py` for Codex app-server startup, thread start or
  resume, approval responses, streamed event mapping, and failure handling
- `tests/test_dashboard.py` for dashboard HTML shell rendering, SQLite-backed
  API reads, task detail data, human message affordances, activity filtering,
  project switching, incremental sprint-event serialization, and approve or
  deny integration behavior
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
- dashboard handler read logic
- dashboard live transport serialization
- git helper behavior that can be isolated

Integration tests:

- project initialization
- sprint and task lifecycle
- orchestrator transitions
- `development_secure` approval and denial paths through `security_review`
- built-in test, merge, and human-gate steps
- context projection into `.foreman/`
- cross-invocation native session reuse for Claude Code, Codex, and
  non-persistent reviewer roles

Runner smoke tests:

- Claude Code runner wiring
- Codex runner wiring
- event capture and retry behavior

UI validation:

- manual checks against `docs/mockups/foreman-mockup-v6.html`
- project dashboard navigation
- sprint board interactions
- activity feed behavior and live stream updates
- human message, filter, and approve or deny flows

## Definition of done

Do not mark a task done unless:

- the relevant automated checks pass,
- new behavior is covered by tests when practical,
- user-visible changes include validation notes,
- the docs reflect the new reality.

If a slice cannot reasonably add tests yet, explain why in the PR summary and
record the follow-up explicitly.
