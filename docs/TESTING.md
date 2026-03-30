# TESTING

## Principle

Foreman testing should verify durable workflow behavior, not just syntax.
Compilation-only checks are insufficient.

## Current baseline

The repo is still pre-implementation, so the current mandatory checks are
scaffold checks:

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`

The first package slice also adds CLI smoke coverage:

- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/foreman --help`
- `./venv/bin/foreman projects`
- `./venv/bin/foreman status`

The SQLite store slice adds:

- `tests/test_store.py` for round-trip persistence across projects, sprints,
  tasks, runs, and events
- subprocess coverage proving `foreman projects --db <path>` and
  `foreman status --db <path>` can inspect persisted store data

The declarative loader slice adds:

- `tests/test_roles.py` for shipped role loading, duplicate-id rejection, and
  prompt rendering behavior
- `tests/test_workflows.py` for shipped workflow loading, transition validation,
  and unknown-role rejection
- subprocess coverage proving `foreman roles` and `foreman workflows` can load
  the shipped definitions

The bootstrap supervisor path now also has regression coverage for reviewed
Codex continuation behavior in `tests/test_reviewed_codex.py`.

The orchestrator slice adds:

- `tests/test_orchestrator.py` for the shipped development workflow's happy
  path, reviewer denial carry-output, test-failure carry-output, workflow
  fallback blocking, and dependency-aware task selection
- real temporary git repos inside the integration tests so merge behavior and
  reviewer prompt context are exercised against actual git state
- store coverage for status-filtered task and run queries plus stable
  latest-run lookup behavior

The scaffold slice adds:

- `tests/test_scaffold.py` for generated `AGENTS.md`, idempotent `.gitignore`
  updates, and preservation of a user-owned `AGENTS.md`
- subprocess coverage proving `foreman init --db <path>` can scaffold a target
  repo, persist a new project, and update that same project on re-run
- store coverage for repo-path lookup used by project re-initialization

The context projection slice adds:

- `tests/test_context.py` for store-driven `.foreman/context.md` and
  `.foreman/status.md` rendering plus configurable runtime context directories
- orchestrator integration coverage proving runtime context is written before
  agent steps, after task completion, and through `_builtin:context_write`
- temporary repo fixtures now include `.foreman/` in `.gitignore` so runtime
  context stays untracked during git-backed workflow tests

The human-gate resume slice adds:

- orchestrator integration coverage for human-gate approval, denial, persisted
  resume metadata, native immediate resume, and deferred resume when runtime
  prerequisites are missing
- subprocess CLI coverage proving `foreman approve --db <path>` and
  `foreman deny --db <path>` update paused tasks and persist the next workflow
  step correctly
- command help validation for the new human-gate CLI surfaces

The native Claude runner slice adds:

- `tests/test_runner_claude.py` for command construction, Claude stream-json
  event mapping, signal extraction, terminal failure detection, and retry
  helper behavior
- orchestrator integration coverage proving the native runner path executes
  shipped Claude-backed roles, reuses developer session IDs, and persists
  retry-driven runner failures into run and event history

The native Codex runner slice adds:

- `tests/test_runner_codex.py` for Codex app-server startup, thread start or
  resume, approval-response handling, streamed event mapping, and terminal
  failure detection
- orchestrator integration coverage proving Codex-backed roles execute through
  the native runner path, reuse persistent developer sessions, and resume
  immediately after human approval when the repo and backend are available

The monitoring CLI slice adds:

- store coverage for sprint-scoped task counts, aggregate run totals,
  per-task rollups, and recent event slices used by monitoring reads
- subprocess CLI coverage proving `foreman board --db <path>`,
  `foreman history --db <path>`, `foreman cost --db <path>`, and
  `foreman watch --db <path>` expose persisted activity without mutating
  store state
- run-scoped and project-scoped watch validation so polling output stays
  bounded and reviewable in terminal workflows

## Expected testing layers once code lands

Unit tests:

- model validation
- SQLite store round-trips
- role and workflow parsing
- signal parsing
- git helper behavior that can be isolated

Integration tests:

- project initialization
- sprint and task lifecycle
- orchestrator transitions
- built-in test, merge, and human-gate steps
- context projection into `.foreman/`

Runner smoke tests:

- Claude Code runner wiring
- Codex runner wiring
- event capture and retry behavior

UI validation:

- manual checks against `docs/mockups/foreman-mockup-v6.html`
- project dashboard navigation
- sprint board interactions
- activity feed behavior

## Definition of done

Do not mark a task done unless:

- the relevant automated checks pass,
- new behavior is covered by tests when practical,
- user-visible changes include validation notes,
- the docs reflect the new reality.

If a slice cannot reasonably add tests yet, explain why in the PR summary and
record the follow-up explicitly.
