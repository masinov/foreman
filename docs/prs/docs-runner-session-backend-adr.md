# PR Summary: docs-runner-session-backend-adr

## Summary

- accept ADR-0001 for runner sessions, approval policy, and backend contract
  boundaries
- document the current persistent-session reuse gap explicitly instead of
  leaving it implicit in the orchestrator implementation
- roll repo memory forward from the ADR sprint to the dashboard sprint

## Scope

- new ADR in `docs/adr/`
- status, architecture, roadmap, sprint, and release-note updates tied to the
  accepted decision
- sprint archive, checkpoint, changelog, and README rollover

## Files changed

- `docs/adr/ADR-0001-runner-session-backend-contract.md`
- `README.md`
- `docs/STATUS.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/TESTING.md`
- `docs/RELEASES.md`
- `CHANGELOG.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/sprints/archive/sprint-09-runner-session-backend-adr.md`
- `docs/checkpoints/runner-session-backend-contract.md`
- `docs/prs/docs-runner-session-backend-adr.md`

## Migrations

- none

## Risks

- ADR-0001 deliberately records a real runtime gap around cross-invocation
  session reuse; later implementation must either close that gap or revise the
  decision explicitly
- the dashboard slice still needs to choose a concrete UI or API boundary
  consistent with the ADR and the current polling-based activity model

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- an accepted ADR now exists in `docs/adr/` for runner sessions and backend
  contract boundaries
- repo-memory docs cite the ADR as an active implementation constraint
- current runtime behavior is documented accurately, including the current
  session-reuse limitation

## Follow-ups

- implement `sprint-10-dashboard-implementation`
- decide how live dashboard activity should relate to the current polling
  `foreman watch` model
