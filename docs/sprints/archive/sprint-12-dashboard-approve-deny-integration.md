# Sprint Archive: sprint-12-dashboard-approve-deny-integration

- Sprint: `sprint-12-dashboard-approve-deny-integration`
- Status: completed
- Goal: wire dashboard approve and deny buttons to the orchestrator so
  human-gate decisions actually resume workflow execution
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `foreman/dashboard.py`
  - `foreman/orchestrator.py`
  - `foreman/cli.py`

## Final task statuses

1. `[done]` Wire approve button to orchestrator resume
   Deliverable: clicking approve on a blocked task calls the orchestrator to
   resume the workflow with approval outcome.

2. `[done]` Wire deny button to orchestrator resume
   Deliverable: clicking deny on a blocked task calls the orchestrator to
   resume the workflow with denial outcome.

3. `[done]` Update dashboard UI after approve or deny
   Deliverable: after approve or deny, the task status and activity stream
   update to reflect the decision.

## Deliverables

- dashboard approve endpoint calling `ForemanOrchestrator.resume_human_gate`
- dashboard deny endpoint calling `ForemanOrchestrator.resume_human_gate`
- UI refresh after human-gate decisions so board and activity stay current
- integration coverage for approve and deny paths in `tests/test_dashboard.py`
- repo-memory rollover from dashboard human-gate integration to persistent
  session reload

## Demo notes

- `./venv/bin/python -m unittest tests.test_dashboard -v`
- `./venv/bin/python -m unittest discover -s tests -v`
- `./venv/bin/foreman dashboard --help`

## Follow-ups moved forward

- `sprint-13-persistent-session-reload`: reload persisted native sessions from
  SQLite on fresh orchestrator invocations
- backlog: dashboard streaming transport, security review workflow variant,
  event-retention pruning, optional PR or checkpoint automation, and
  engine-level database discovery
