# PR Summary: chore/foreman-autonomy-bootstrap

## Summary

- repurposes the transplanted autonomous-development scaffold so it belongs to
  the Foreman project instead of the old Apparatus repo

## Scope

- rewrites repo-memory docs around the Foreman spec and mockup
- initializes the active sprint and backlog
- aligns the Codex and Claude wrapper scripts with current file paths and
  product references
- fixes repo-validation assumptions to match this repository

## Files changed

- top-level instructions and README
- status, roadmap, architecture, branching, testing, and release docs
- sprint/backlog docs and templates
- autonomous wrapper scripts and validation helpers
- `.gitignore`

## Migrations

- none

## Risks

- the wrapper scripts are still bootstrap tooling and may need further changes
  once native Foreman runners land

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py`
- `./venv/bin/python -m py_compile scripts/reviewed_claude.py`
- `./venv/bin/python -m py_compile scripts/repo_validation.py`
- `./venv/bin/python -m py_compile scripts/validate_repo_memory.py`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- the repo now describes Foreman rather than Apparatus
- the autonomous entry points have a valid current sprint and backlog to read
- validation logic points at the actual spec, mockup, and sprint files in this
  repo

## Follow-ups

- bootstrap the `foreman` Python package and CLI shell
- implement the SQLite store baseline
