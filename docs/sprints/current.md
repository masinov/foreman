# Current Sprint

- Sprint: `sprint-16-security-review-workflow`
- Status: active
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

## Included tasks

1. `[todo]` Execute the shipped secure workflow variant end to end
   Deliverable: the `development_secure` workflow can run through
   `security_review` with durable orchestrator state instead of existing only
   as a loaded configuration artifact.

2. `[todo]` Add security review outcome coverage
   Deliverable: approve and deny paths from the security-review step are
   covered by orchestrator tests and produce the expected workflow
   transitions.

3. `[todo]` Document secure workflow selection in bootstrap flows
   Deliverable: repo docs explain when to choose `development_secure` during
   project initialization and what behavior it currently adds over the default
   workflow.

## Excluded from this sprint

- backend preflight health checks
- event-retention pruning
- multi-user dashboard concerns
- migration framework work

## Acceptance criteria

- `development_secure` is exercised by automated runtime tests, not just loader
  tests
- security review approval and denial semantics are explicit in tests and docs
- bootstrap project initialization docs clearly explain secure workflow usage
