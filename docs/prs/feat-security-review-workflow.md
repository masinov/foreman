# PR Summary: feat-security-review-workflow

## Summary

- prove the shipped `development_secure` workflow executes end to end through
  orchestrator runtime tests
- cover security-review approval and denial behavior explicitly, including
  carried feedback back into development
- document when bootstrap project initialization should choose
  `development_secure`

## Scope

- add orchestrator integration tests for secure workflow success and denial
  loops
- add CLI coverage for secure workflow selection during `foreman init`
- improve `foreman init --workflow` help text for the secure workflow option
- archive sprint 16 and roll repo memory forward to sprint 17

## Files changed

- `tests/test_orchestrator.py` — added end-to-end `development_secure`
  coverage and denial-loop assertions
- `tests/test_cli.py` — added secure workflow initialization coverage
- `foreman/cli.py` — clarified secure workflow selection in init help text
- `README.md` — documented secure workflow selection and moved the next slice
  to backend preflight checks
- `docs/STATUS.md` — marked security workflow runtime complete and defined the
  next sprint
- `docs/sprints/current.md` — rolled current sprint to backend preflight
  checks
- `docs/sprints/backlog.md` — moved backend preflight out of backlog and added
  the next follow-up slice
- `docs/sprints/archive/sprint-16-security-review-workflow.md` — archived the
  completed sprint
- `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/TESTING.md`,
  `docs/RELEASES.md`, `CHANGELOG.md` — aligned repo memory to the completed
  slice
- `docs/prs/feat-security-review-workflow.md` — branch summary

## Migrations

- none

## Risks

- secure workflow selection remains an explicit project-level opt-in rather
  than a policy-driven default
- native backends still rely on runtime process failures instead of explicit
  preflight checks
- `foreman watch` still lags behind the dashboard's live transport model

## Tests

- `./venv/bin/python -m py_compile foreman/cli.py tests/test_cli.py tests/test_orchestrator.py`
- `./venv/bin/python -m unittest tests.test_orchestrator.ForemanOrchestratorTests.test_secure_workflow_runs_through_security_review_and_finishes_task tests.test_orchestrator.ForemanOrchestratorTests.test_security_review_denial_carries_output_back_into_development tests.test_cli.ForemanCLISmokeTests.test_init_command_accepts_secure_workflow_selection -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- `development_secure` is exercised by automated runtime tests, not just
  loader tests
- security review approval and denial semantics are explicit in tests and docs
- bootstrap project initialization docs explain secure workflow usage clearly

## Follow-ups

- implement `sprint-17-native-backend-preflight-checks`
- decide whether secure workflow selection should remain an explicit init-time
  choice or become policy-driven later
