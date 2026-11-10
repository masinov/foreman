# PR Summary: refactor/dashboard-information-architecture

## Withdrawal — 2026-09-08

The user rejected the UX refactor and requested a return to the preceding
`docs/reviews-ui-methodology` branch, retaining documentation only. The
uncommitted implementation is discarded. The two review documents and their
screenshots are retained unchanged. No proposed UI or backend behavior from
this refactor is accepted or delivered.

The previous work-in-progress summary below is historical context only. Its
preview URL, validation results and acceptance claims do not describe the
retained documentation-only state. The next task is to review the findings
before proposing any further UX implementation.

---

# PR Summary: refactor/dashboard-information-architecture

## Summary

Work in progress. The user rejected the first broad UI iteration. The current
review pass is limited to the project sprints overview; task-level layout is
awaiting a separate pass. Do not merge this branch as a completed refactor.

## Scope

Overview correction on 2026-09-08: restore the Manager edge control, expose
repository, branch and worktree information, make the entire active sprint
card navigable by mouse and keyboard, remove the redundant Open sprint label,
and increase titles, goals and task-summary text to readable sizes. Preserve
the Active / Queue / Archive structure and the full-width scroll boundary.

## Files changed

- `frontend/src/components.jsx`: overview structure and interactions.
- `frontend/src/styles.css`: overview typography and panel layout.
- `foreman/dashboard_frontend_dist/`: rebuilt dashboard preview.
- Earlier uncommitted functional and UI work remains on this branch.
- Both original reviews and their screenshots are preserved in `docs/reviews/`.

## Migrations

None for the UI refactor. FOR-12 notification delivery was merged separately.

## Risks

The broader refactor is unfinished. Preview data is a snapshot and therefore
has stale heartbeat/task status. The remote preview disables Manager execution;
its panel remains inspectable. User feedback on this overview is pending.

## Tests

- All 49 frontend tests pass; production build passes.
- Browser screenshot inspected at 1440 × 1000 against the copied database.
- `git diff --check` passes.

## Screenshots or output examples

Current preview: `http://odin:8211/dashboard/projects/foreman`.
Local overview capture: `/tmp/refactor-project.png`.

## Acceptance criteria satisfied

Repository visible, readable overview text, one active-card navigation target,
Manager available at the right edge, existing planning groups preserved.

## Follow-ups

Review the overview with the user before continuing to sprint/task detail.
Do not carry the rejected large header, extra bars, or removed Activity composer
forward as accepted design decisions.
