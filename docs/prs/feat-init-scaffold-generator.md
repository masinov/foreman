# PR Summary: feat/init-scaffold-generator

## Summary

- implement the first `foreman init` path for repo scaffold generation and
  persisted project initialization
- add idempotent scaffold helpers plus the generated `AGENTS.md` template used
  for target repositories
- cover new-project and re-initialization behavior through scaffold, CLI, and
  store tests
- close out `sprint-03-scaffold` and roll repo memory forward to
  `sprint-04-context-projection`

## Scope

- `foreman.scaffold` repo generation helpers and instruction-template loading
- `foreman.cli` initialization, workflow selection, persisted settings, and
  project upsert behavior
- `foreman.store` repo-path lookup for in-place project updates
- scaffold, CLI, and store tests plus repo-memory documentation updates

## Files changed

- `foreman/cli.py`
- `foreman/scaffold.py`
- `foreman/store.py`
- `templates/agents_md.md.j2`
- `tests/test_cli.py`
- `tests/test_scaffold.py`
- `tests/test_store.py`
- `README.md`
- `docs/STATUS.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/README.md`
- `docs/sprints/archive/sprint-03-scaffold.md`
- `docs/checkpoints/project-init-scaffold.md`
- `docs/prs/feat-init-scaffold-generator.md`
- `CHANGELOG.md`

## Migrations

- none

## Risks

- the bootstrap CLI still requires explicit `--db PATH` until engine-level
  database discovery exists
- generated `AGENTS.md` content will need revision as native runner and
  human-gate resume semantics become concrete
- runtime context projection remains outside this slice, so initialized repos
  still do not receive `.foreman/context.md` or `.foreman/status.md`

## Tests

- `./venv/bin/python -m unittest tests.test_scaffold tests.test_cli tests.test_store -v`
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

- `foreman init` can create the minimal repo scaffold described by the spec
- initialized projects are persisted into SQLite with enough data to support
  later orchestrator runs
- generated files align to the repo instructions model from `AGENTS.md` and do
  not treat `.foreman/` as committed project state
- docs and validation now point a fresh agent at the context projection slice
  without additional human context

## Follow-ups

- implement `.foreman/context.md` and `.foreman/status.md` projection in
  `sprint-04-context-projection`
- add `foreman approve` and `foreman deny` so paused human gates can resume
- land the first native Claude Code or Codex runner backend
