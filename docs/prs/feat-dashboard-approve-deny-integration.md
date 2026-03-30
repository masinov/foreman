# PR Summary: feat/dashboard-approve-deny-integration

## Summary
- wire dashboard approve/deny buttons to the orchestrator for human-gate decisions
- make the blocked task approve/deny buttons actually trigger workflow resume

## Scope
- update approve/deny API endpoints to call orchestrator
- refresh dashboard state after approve/deny

## Files changed
- `foreman/dashboard.py` — wire approve/deny to orchestrator
- `tests/test_dashboard.py` — integration tests

## Migrations
- none

## Tests
- `./venv/bin/python -m unittest tests.test_dashboard -v`

## Acceptance criteria
- [ ] clicking approve resumes workflow
- [ ] clicking deny resumes workflow with steer outcome
- [ ] dashboard updates after decision
