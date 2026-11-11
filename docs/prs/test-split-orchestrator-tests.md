# test/split-orchestrator-tests

## Summary

Sprint 57 slice 8. The engine tests are organised like the engine.

## Scope

- `tests/test_orchestrator.py` is split, text-exact, into 13 files. The
  4500-line `ForemanOrchestratorTests` class became six classes by topic
  (workflow, branches, gates, agent step, recovery, task control) on a
  shared `OrchestratorTestCase`.
- `tests/engine_support.py`: `RepoTestCase`, `OrchestratorTestCase`, the
  scripted executors and runners. Fixture methods that were verbatim copies
  were removed from the classes that now inherit them; a class whose copy
  differed keeps its own.
- `tests/test_git.py`, `tests/test_store_concurrency.py` (new).

## Files changed

`tests/` only, plus `docs/TESTING.md`, changelog, sprint.

## Migrations

None.

## Risks

Test files import the fixtures as `engine_support`, which resolves because
`unittest discover -s tests` puts `tests/` on the path. Running one file is
`python -m unittest discover -s tests -p "test_engine_gates.py"`.

## Tests

Full suite: 1128 tests (1110 before, 18 new). The concurrency tests were run
three times in a row.

## Acceptance criteria satisfied

Slice 8 as written in `docs/sprints/current.md`.

## Follow-ups

The completion-guard and evidence test classes still carry their own
`seed_project` variants.
