# PR Summary: feat-engine-db-discovery

## Summary

- add repo-local SQLite discovery so normal Foreman CLI flows no longer
  require explicit `--db`
- keep `--db PATH` as a deterministic override for alternate or out-of-repo
  stores
- roll repo memory forward from engine DB discovery to the security review
  workflow sprint

## Scope

- add repo-local `.foreman.db` discovery in the CLI
- make `foreman init` default to `<repo>/.foreman.db`
- update scaffold `.gitignore` handling so the default DB file stays
  uncommitted
- add CLI and scaffold coverage for discovery, override, and fallback cases
- archive sprint 15 and define sprint 16

## Files changed

- `foreman/cli.py` — added repo-local DB discovery and optional `--db`
  handling across CLI commands
- `foreman/scaffold.py` — added `.foreman.db` to scaffolded `.gitignore`
- `tests/test_cli.py` — added discovery, override, init-default, and fallback
  coverage
- `tests/test_scaffold.py` — updated scaffold expectations for the default DB
  file
- `docs/STATUS.md` — updated current sprint and repo state
- `docs/sprints/current.md` — rolled current sprint to security review
  workflow
- `docs/sprints/backlog.md` — reordered next-up backlog
- `docs/sprints/archive/sprint-15-engine-db-discovery.md` — archived the
  completed sprint
- `README.md`, `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`,
  `docs/RELEASES.md`, `CHANGELOG.md` — aligned repo memory to the completed
  slice
- `docs/prs/feat-engine-db-discovery.md` — branch summary

## Migrations

- none

## Risks

- repo-local discovery currently depends on an existing `.foreman.db` in the
  current repo lineage or on `foreman init` creating one
- out-of-repo and cross-repo inspection still requires explicit `--db`
- the bootstrap runtime still lacks a broader engine-instance configuration
  layer

## Tests

- `./venv/bin/python -m py_compile foreman/cli.py foreman/scaffold.py tests/test_cli.py tests/test_scaffold.py`
- `./venv/bin/python -m unittest tests.test_scaffold tests.test_cli -v`
- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py foreman/cli.py foreman/scaffold.py tests/test_cli.py tests/test_scaffold.py`
- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/python -m unittest discover -s tests -v`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- normal SQLite-backed CLI flows work without explicit `--db`
- `--db PATH` remains a deterministic override
- docs and tests explain the discovery boundary clearly enough for autonomous
  supervisors to continue without reconstructing prior chat context

## Follow-ups

- implement `sprint-16-security-review-workflow`
- decide whether repo-local `.foreman.db` should remain long-term or give way
  to a broader engine-instance configuration model
