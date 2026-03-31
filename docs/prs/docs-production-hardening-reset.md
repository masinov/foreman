# PR Summary: docs-production-hardening-reset

## Summary

- tighten repo instructions so bootstrap status no longer excuses weak product
  architecture
- accept a dedicated React frontend plus Python API boundary for the dashboard
- replan the next work around a production-hardening detour

## Scope

- rewrite governing docs and architecture notes
- add ADR-0003 for the product web UI boundary
- add a checkpoint audit covering known structural debt
- replace the previously active migration sprint with a dashboard-first
  hardening sequence

## Files changed

- `AGENTS.md` — tightened implementation-quality rules and bootstrap language
- `README.md`, `docs/STATUS.md`, `docs/ARCHITECTURE.md`,
  `docs/ROADMAP.md`, `docs/TESTING.md`, `docs/RELEASES.md`,
  `docs/sprints/current.md`, `docs/sprints/backlog.md`, `CHANGELOG.md` —
  realigned repo memory around production hardening
- `docs/adr/ADR-0003-web-ui-api-boundary.md` — accepted UI and API boundary
- `docs/checkpoints/production-hardening-audit.md` — ranked remediation plan
- `docs/sprints/archive/sprint-20-production-hardening-reset.md` — archived
  the reset sprint
- `docs/prs/docs-production-hardening-reset.md` — branch summary

## Migrations

- none

## Risks

- the current dashboard implementation is still in place until sprint 21 and
  sprint 22 land
- migration work is delayed while the product-surface boundary is corrected
- the audit identifies debt, but the codebase still needs the follow-through
  sprints to remove it

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py`

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- repo instructions now reject bootstrap as a rationale for throwaway
  architecture
- the dashboard direction is now explicitly a React frontend plus Python API
- the next work is replanned around a ranked remediation detour

## Follow-ups

- implement `sprint-21-dashboard-api-extraction`
- implement `sprint-22-dashboard-backend-foundation`
- implement `sprint-23-react-dashboard-foundation`
- implement `sprint-24-product-surface-hardening`
