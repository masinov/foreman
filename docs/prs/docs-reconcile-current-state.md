# PR: docs/reconcile-current-state

## Summary

- Reconciled stale repo-memory docs with the actual latest completed sprint and
  current backlog.
- Updated the README, STATUS, architecture baseline, and backlog so they no
  longer point at sprint 24 or pre-E2E / pre-queue-advancement assumptions.
- Documented two remaining mismatches explicitly: the broader-than-ADR meta
  agent surface and the likely dashboard `Run` subprocess wiring issue.

## Scope

- `README.md`
- `docs/STATUS.md`
- `docs/ARCHITECTURE.md`
- `docs/sprints/backlog.md`

## Files changed

- `README.md`
- `docs/STATUS.md`
- `docs/ARCHITECTURE.md`
- `docs/sprints/backlog.md`
- `docs/prs/docs-reconcile-current-state.md` (new)

## Migrations

None.

## Risks

- This branch updates documentation only; it does not fix the underlying
  dashboard `Run` subprocess mismatch.
- The meta-agent / ADR divergence is now documented, but the shipped runtime
  still behaves according to code rather than the narrower ADR text.

## Tests

- `./venv/bin/python scripts/validate_repo_memory.py`

## Acceptance criteria satisfied

- Stale "current sprint" references reconciled to sprint 41
- Architecture doc no longer claims E2E and CLI-stub gaps that are already closed
- Backlog no longer references removed kanban behavior as if it were current
- Branch-specific PR summary added for repo-memory validation

## Follow-ups

- Verify and fix `DashboardService.start_agent()` subprocess invocation if the
  source-level mismatch with the CLI parser is real at runtime
- Persist meta-agent history to SQLite
- Expand E2E coverage for the meta-agent panel and newer queue/editing flows
