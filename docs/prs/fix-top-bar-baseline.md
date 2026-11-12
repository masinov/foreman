# fix/top-bar-baseline

## Summary

Four reports from the owner, looking at the running dashboard.

## Scope

- Top bar: the serif wordmark sat lower than the sans breadcrumb. `--logo-lift`
  moves it onto the same baseline (seen at 3x magnification).
- Engine row: label, state and sentence on one baseline. `ui/StatusDot` is
  inline text with an inline dot; as a flex box it took its baseline from
  the dot. This applies wherever a status dot is used.
- Row hover: the highlight no longer bleeds past the table (reverting the
  bleed added in `fix/sprint-list-hover-empty-planned-finished`). The first
  and last cell, header included, are inset by `--row-inset`.
- Breadcrumb: no "All projects" entry in the project switcher and no
  "Workspace" step or label anywhere. The wordmark is the one link to the
  workspace. Workspace settings shows "Workspace settings" as its place.

## Files changed

`frontend/src/app/Breadcrumb.jsx`, `frontend/src/styles/` (tokens, ui,
project, motion), `frontend/src/app/App.test.jsx`, changelog.

## Migrations

None.

## Risks

Table content is now 8px inside its header line on both sides, on every
table. The owner has not seen that yet.

## Tests

`npm --prefix frontend test` (274 pass). Frontend only; the Python suite was
not re-run. The bar, the engine row and the inset were seen in screenshots;
the hover highlight itself cannot be captured.

## Follow-ups

None.
