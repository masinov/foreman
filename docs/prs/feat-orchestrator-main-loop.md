# PR Summary: feat/orchestrator-main-loop

## Summary

- implement the first persisted orchestrator loop against the shipped workflow
  definitions
- add explicit built-ins for tests, merge, mark-done, and human-gate pause
- cover the workflow engine with real git-backed integration tests

## Scope

- `foreman.orchestrator` task selection, workflow execution, run or event
  persistence, carried output, loop limits, and crash recovery
- `foreman.builtins` and `foreman.git` seams for workflow execution
- store query helpers needed by the orchestrator
- orchestrator integration tests and repo-memory updates

## Files changed

- `foreman/orchestrator.py`
- `foreman/builtins.py`
- `foreman/git.py`
- `foreman/store.py`
- `tests/test_orchestrator.py`
- `tests/test_store.py`
- `README.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-02-orchestrator.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `CHANGELOG.md`

## Migrations

- none

## Risks

- native agent runners are still unimplemented, so the orchestrator currently
  depends on an injected executor in tests and higher-level integrations
- shipped workflow definitions treat `_builtin:mark_done` as a terminal step
  without an outgoing edge, which the runtime now handles explicitly and the
  repo memory records as a documented ambiguity
- context projection and human-gate resume still sit outside this slice

## Tests

- `./venv/bin/python -m py_compile foreman/store.py foreman/git.py foreman/builtins.py foreman/orchestrator.py tests/test_orchestrator.py tests/test_store.py`
- `./venv/bin/python -m unittest discover -s tests -p 'test_orchestrator.py' -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`
- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/foreman --help`
- `./venv/bin/foreman projects`
- `./venv/bin/foreman status`
- `./venv/bin/foreman roles`
- `./venv/bin/foreman workflows`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- one persisted task can advance through develop, review, test, merge, and
  done states using the loaded workflow graph
- transitions are driven by the declarative workflow definitions rather than
  hard-coded branching
- built-in test, merge, and mark-done steps execute through explicit seams
- docs and validation are current enough for a fresh agent to start the next
  scaffold slice without extra human context

## Follow-ups

- implement `foreman init` and repo scaffold generation in `sprint-03-scaffold`
- project `.foreman/context.md` and `.foreman/status.md` before orchestrator
  runs
- add human-gate approve or deny commands and native runner backends
