# PR Summary: fix/frontend-landing-copy

## Summary

Closes the two still-open Flow 1 (landing) items from
`docs/reviews/frontend-ux-review.md`: the dev-jargon project-overview subtitle
and the project-card footer that leaked raw internal ids. Both are plain-text /
labeling polish on the primary landing screen, with no behavior change.

## Scope

- `frontend/src/format.js`: added `formatSelectionMode` and
  `formatWorkflowLabel` (plus a shared `titleizeId` helper). They map known
  `task_selection_mode` / `workflow_id` values to friendly labels
  (`directed` → "Directed", `development_tiered` → "Tiered workflow") and
  title-case any unknown id as a fallback.
- `frontend/src/components.jsx` (`ProjectOverview`):
  - replaced the subtitle "SQLite-backed project state, active sprint summaries,
    and aggregate engine totals." with "Pick a project to see its active sprint,
    task progress, and engine activity."
  - the card footer now renders
    `formatSelectionMode(...) · formatWorkflowLabel(...)` instead of the raw
    `directed · development_tiered`.
- `frontend/src/format.test.js`: coverage for the two new helpers (friendly
  labels + title-case fallback + undefined defaults).
- `foreman/dashboard_frontend_dist/`: rebuilt committed bundle.

## Migrations

None.

## Risks

Low. Display-only string changes; no API, schema, or state changes. The footer
helpers fall back to a title-cased id for any unknown mode/workflow, so new
backend values still render readably rather than throwing.

## Tests

- `npx vitest run` — 13 tests passing (8 in `format.test.js`, 5 in
  `App.test.jsx`).
- `npm run build` — clean production build.

## Acceptance criteria satisfied

- Landing subtitle is plain language, not implementation-speak.
- Project-card footer shows friendly mode/workflow labels, not raw ids.
- Review doc, changelog updated; remaining deferred items recorded.

## Follow-ups

Still deferred (recorded in the review's "Not done" section):

- the Flow-2 "engine-status vs Run/Stop can disagree" semantics decision
  (inferred `projectStatus` vs live `agent_running`);
- the full icon-system overhaul (mixed unicode-glyph/SVG → one SVG library).
