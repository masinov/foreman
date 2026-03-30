# Sprint Archive: sprint-20-production-hardening-reset

- Sprint: `sprint-20-production-hardening-reset`
- Status: completed
- Goal: tighten repository rules so bootstrap status cannot justify
  prototype-grade implementation choices, and record a concrete hardening
  detour for the known weak surfaces
- Primary references:
  - `AGENTS.md`
  - `README.md`
  - `docs/STATUS.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ROADMAP.md`
  - `docs/adr/ADR-0003-web-ui-api-boundary.md`

## Final task statuses

1. `[done]` Tighten repo instructions around implementation quality
   Deliverable: docs now state explicitly that bootstrap refers to repo memory
   and sequencing, not permission for throwaway architecture.

2. `[done]` Accept a product web UI and API boundary
   Deliverable: ADR-0003 now makes a dedicated React frontend plus Python API
   the accepted dashboard direction.

3. `[done]` Record a ranked remediation detour
   Deliverable: repo planning docs now sequence dashboard API extraction,
   React frontend replacement, product-surface hardening, migration work, and
   history lifecycle follow-up.

## Deliverables

- tighter governing docs in `AGENTS.md` and repo memory files
- accepted ADR for the web UI and API boundary
- production-hardening audit checkpoint
- replanned active and next-up sprints around the remediation detour

## Demo notes

- `./venv/bin/python scripts/validate_repo_memory.py`
- `./venv/bin/python -m py_compile scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py`

## Follow-ups moved forward

- `sprint-21-dashboard-api-extraction`
- `sprint-22-react-dashboard-foundation`
- `sprint-23-product-surface-hardening`
- `sprint-24-migration-framework-bootstrap`
