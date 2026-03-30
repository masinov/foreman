# Current Sprint

- Sprint: `sprint-12-dashboard-approve-deny-integration`
- Status: active
- Goal: wire dashboard approve/deny buttons to the orchestrator so human-gate
  decisions actually resume workflow execution
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `foreman/dashboard.py`
  - `foreman/orchestrator.py`
  - `foreman/cli.py`

## Included tasks

1. `[todo]` Wire approve button to orchestrator resume
   Deliverable: clicking approve on a blocked task calls the orchestrator to
   resume the workflow with approval outcome.

2. `[todo]` Wire deny button to orchestrator resume
   Deliverable: clicking deny on a blocked task calls the orchestrator to
   resume the workflow with denial outcome.

3. `[todo]` Update dashboard UI after approve/deny
   Deliverable: after approve/deny, the task status and activity stream update
   to reflect the decision.

## Excluded from this sprint

- streaming transport for dashboard
- event-retention pruning
- security review workflow variant

## Acceptance criteria

- clicking approve on a human-gate task resumes the workflow
- clicking deny on a human-gate task resumes the workflow with steer outcome
- dashboard reflects the updated task status immediately
