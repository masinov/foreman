# Current Sprint

- Sprint: `sprint-15-engine-db-discovery`
- Status: active
- Goal: remove the bootstrap requirement to pass explicit `--db` paths for
  normal SQLite-backed CLI flows
- Primary references:
  - `docs/specs/engine-design-v3.md`
  - `docs/STATUS.md`
  - `foreman/cli.py`
  - `foreman/store.py`
  - `scripts/reviewed_codex.py`
  - `scripts/reviewed_claude.py`

## Included tasks

1. `[todo]` Add engine-level database discovery
   Deliverable: Foreman resolves a default SQLite path for normal repo-local
   usage without requiring `--db` on every command.

2. `[todo]` Wire CLI flows to discovery with explicit override semantics
   Deliverable: inspection, monitoring, and human-gate resume commands work
   without explicit `--db`, while `--db PATH` still overrides discovery
   deterministically.

3. `[todo]` Document discovery and fallback behavior
   Deliverable: repo docs explain how Foreman finds or creates the active
   engine database and how that interacts with bootstrap initialization.

## Excluded from this sprint

- a migration framework for schema evolution
- remote or multi-host engine discovery
- security review workflow implementation
- dashboard authentication and multi-user concerns

## Acceptance criteria

- normal SQLite-backed CLI flows work without explicit `--db`
- `--db PATH` remains a deterministic override
- docs and tests explain the discovery boundary clearly enough for autonomous
  supervisors to continue without reconstructing prior chat context
