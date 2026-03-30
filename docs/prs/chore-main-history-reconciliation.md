# PR Summary: chore-main-history-reconciliation

## Summary

- reconcile the loose recovery and feature branch history into one integrated
  mainline candidate
- restore the missing runner-session ADR artifacts and sprint archives so repo
  memory matches the code that actually shipped
- roll project memory forward to `sprint-13-persistent-session-reload`

## Scope

- merge the recovery and monitoring or runner branch lines into one branch
- preserve the later dashboard implementation line where histories conflicted
- restore missing docs from the loose runner ADR branch without regressing
  newer dashboard work
- normalize README, status, roadmap, testing, releases, changelog, current
  sprint, backlog, and sprint archive docs
- close stale loose branches once their content is represented in the
  reconciled history

## Files changed

- `README.md`
- `CHANGELOG.md`
- `docs/STATUS.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `docs/adr/ADR-0001-runner-session-backend-contract.md`
- `docs/checkpoints/runner-session-backend-contract.md`
- `docs/prs/docs-runner-session-backend-adr.md`
- `docs/prs/chore-main-history-reconciliation.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-09-runner-session-backend-adr.md`
- `docs/sprints/archive/sprint-10-dashboard-implementation.md`
- `docs/sprints/archive/sprint-11-multi-project-dashboard-polish.md`
- `docs/sprints/archive/sprint-12-dashboard-approve-deny-integration.md`

## Migrations

- none

## Risks

- the reconciled branch intentionally keeps the later dashboard and Codex
  implementations when earlier feature branches diverged, so stale branches
  must not be treated as fresher than the integrated line
- cross-invocation native session reuse remains an open implementation gap and
  is now the current sprint

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`
- `./venv/bin/pip install -e . --no-build-isolation --no-deps`
- `./venv/bin/python -m unittest discover -s tests -v`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- the completed feature work is represented in one integrated history that can
  advance `main`
- missing repo-memory artifacts from the loose runner ADR branch are restored
- sprint history now covers the completed work through sprint 12
- repo-memory docs now point at the actual next implementation slice

## Follow-ups

- implement `sprint-13-persistent-session-reload`
- decide whether to prune or retain the reconciled feature branches after
  `main` is updated
