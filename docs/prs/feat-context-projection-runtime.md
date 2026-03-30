# PR Summary: feat/context-projection-runtime

## Summary

- implement store-driven runtime projection for `.foreman/context.md` and
  `.foreman/status.md`
- wire automatic context refresh into orchestrator agent execution and task
  completion
- add `_builtin:context_write` so workflows can force explicit runtime context
  projection
- close out `sprint-04-context-projection` and roll repo memory forward to
  `sprint-05-human-gates`

## Scope

- `foreman.context` rendering and write helpers for runtime context
- `foreman.orchestrator` prompt-context reuse plus automatic context writes
- `foreman.builtins` support for `_builtin:context_write`
- context projection tests and repo-memory updates

## Files changed

- `foreman/context.py`
- `foreman/builtins.py`
- `foreman/orchestrator.py`
- `tests/test_context.py`
- `tests/test_orchestrator.py`
- `README.md`
- `docs/STATUS.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/README.md`
- `docs/sprints/archive/sprint-04-context-projection.md`
- `docs/checkpoints/context-projection-runtime.md`
- `docs/prs/feat-context-projection-runtime.md`
- `CHANGELOG.md`

## Migrations

- none

## Risks

- open decisions are still not modeled in SQLite, so status projection uses a
  placeholder instead of structured decision records
- human-gate resume commands remain outside this slice, so paused tasks still
  cannot be resumed from the CLI
- runtime context writes assume repos keep `.foreman/` gitignored; initialized
  repos do, but ad hoc repos can still choose not to

## Tests

- `./venv/bin/python -m unittest tests.test_context tests.test_orchestrator -v`
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

- `.foreman/context.md` and `.foreman/status.md` are projected from SQLite
  records rather than hand-authored markdown
- orchestrator activity refreshes runtime context before agent execution and
  after task completion
- explicit workflow context writes reuse the same projection implementation
- docs and validation now point a fresh agent at the human-gate slice without
  additional human context

## Follow-ups

- implement `foreman approve` and `foreman deny` in `sprint-05-human-gates`
- add the first native Claude Code or Codex runner backend
- create the first ADR once human-gate or runner constraints harden
