# PR Summary: fix/dashboard-working-copy-settings

## Summary

The sprint overview exposed a hidden Git storage path and a worktree counter
that could be mistaken for parallel-agent capacity. Move storage maintenance
to Settings → Task working copies. Explain retained checkouts, display the
stored count separately from the configured disk-use limit, and put the path
under collapsed Storage details. Rename Prune worktrees to Remove unused
copies.

## Scope

Sprint 54 operator UI correction after header commit `166e992`. Existing API,
storage configuration and cleanup semantics are preserved. Opening the sprint
overview no longer requests working-copy data; opening settings loads it.

## Files changed

- `frontend/src/components.jsx`: maintenance section, placement and wording.
- `frontend/src/App.jsx`: settings project/services binding.
- `frontend/src/styles.css`: settings layout and collapsible storage details.
- `frontend/src/App.test.jsx`, `frontend/src/components.test.jsx`: settings
  loading, cleanup binding, count/limit labels and hidden path coverage.
- `foreman/dashboard_frontend_dist/`: rebuilt frontend.
- STATUS, current sprint, MANUAL, ADR-0012 and this summary.

## Migrations

None.

## Risks

The storage cap remains a soft limit and can be exceeded to preserve dirty
checkouts. It is not a concurrency setting. Cleanup remains an explicit action
against copies of completed, cancelled or deleted tasks; live task copies stay.

## Tests

- Frontend suite: 40 tests passed.
- Production build: passed.
- Live browser and repository validation: pending.

## Screenshots or output examples

Local captures: `/tmp/foreman-overview-without-worktrees.png` and
`/tmp/foreman-working-copy-settings.png`.

## Acceptance criteria satisfied

- General sprint overview carries no storage count, hidden-folder path or
  cleanup control.
- Settings explains working copies and distinguishes disk usage from agents.
- Storage path appears only after expanding Storage details.
- Cleanup keeps the existing service/API behavior.

## Follow-ups

Treat maximum concurrent workflows as a separate scheduling capability when
parallel execution is implemented; do not repurpose `max_live_worktrees`.
