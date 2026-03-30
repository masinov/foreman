# Sprint Archive: sprint-16-security-review-workflow

- Sprint: `sprint-16-security-review-workflow`
- Status: completed
- Goal: make the shipped secure workflow variant execute end to end with
  orchestrator and CLI coverage
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `roles/security_reviewer.toml`
  - `workflows/development_secure.toml`
  - `foreman/orchestrator.py`
  - `foreman/cli.py`
  - `tests/test_orchestrator.py`
  - `tests/test_cli.py`

## Final task statuses

1. `[done]` Execute the shipped secure workflow variant end to end
   Deliverable: `development_secure` now runs through `security_review` with
   durable orchestrator state instead of existing only as a loaded
   configuration artifact.

2. `[done]` Add security review outcome coverage
   Deliverable: approve and deny paths from the security-review step are now
   covered by orchestrator tests and produce the expected workflow
   transitions.

3. `[done]` Document secure workflow selection in bootstrap flows
   Deliverable: repo docs now explain when to choose `development_secure`
   during project initialization and what behavior it adds over the default
   workflow.

## Deliverables

- end-to-end runtime coverage for the `development_secure` workflow
- explicit security-review denial coverage with carry-output back into
  development
- CLI coverage for `foreman init --workflow development_secure`
- repo-memory rollover from the security workflow sprint to backend preflight
  checks

## Demo notes

- `./venv/bin/python -m unittest tests.test_orchestrator.ForemanOrchestratorTests.test_secure_workflow_runs_through_security_review_and_finishes_task tests.test_orchestrator.ForemanOrchestratorTests.test_security_review_denial_carries_output_back_into_development tests.test_cli.ForemanCLISmokeTests.test_init_command_accepts_secure_workflow_selection -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/python scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-17-native-backend-preflight-checks`: validate required backend
  executables and startup assumptions before long-running native execution
- `sprint-18-event-retention-pruning`: implement spec-aligned pruning for old
  event rows
- `sprint-19-watch-live-tail-alignment`: align `foreman watch` with the
  dashboard live transport and live-tail intent
