# PR Summary: fix/dashboard-project-header

## Summary

The sprint overview interleaved engine status with project descriptors and
styled blocked counts like buttons. The header now orders its descriptors as
Repository, Branch, Workflow, followed by worktree details. Engine residency,
heartbeat and blocked counts share a plain-text status row beneath them.

## Scope

Sprint 54 operator UI correction, based on the completed Manager panel fix
at `1690a2a`. Header spacing and grouping only.

## Files changed

- `frontend/src/components.jsx`: ordered descriptors and grouped activity.
- `frontend/src/styles.css`: line height, spacing, wrapping, plain status text.
- `foreman/dashboard_frontend_dist/`: rebuilt dashboard assets.
- `docs/STATUS.md`, `docs/sprints/current.md`, this summary.

## Migrations

None.

## Risks

Long descriptors and activity summaries wrap when the available width is
insufficient. Status counts remain informational; Run/Pause and Prune worktrees
remain actual controls.

## Tests

- Frontend suite: 39 tests passed.
- Production frontend build: passed.
- Live Chromium at 1440 × 1000, Manager folded and open: descriptor order,
  activity below metadata on one line, no status border/background or button
  semantics; passed with no page errors. Screenshots inspected.
- Repository memory validation and `git diff --check`: passed.

## Screenshots or output examples

Local browser captures: `/tmp/foreman-header-manager-folded.png` and
`/tmp/foreman-header-manager-open.png`.

## Acceptance criteria satisfied

- Repository precedes Branch, which precedes Workflow.
- Engine summary and blocked counts share a row below project descriptors.
- Status summaries have no button-like border, background or uppercase badge.
- Header rows have deliberate spacing and consistent line height.

## Follow-ups

Review the revised header on the running dashboard before the next UI change.
