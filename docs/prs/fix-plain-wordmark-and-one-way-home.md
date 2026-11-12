# fix/plain-wordmark-and-one-way-home

## Summary

Two things the owner said after seeing `feat/identity-icons-motion`: the
drawn F with a gold square was disliked and unclear, and the wordmark and the
"Workspace" breadcrumb step went to the same page.

## Scope

- `ui/Logo`: the name as type, in Fraunces (loaded with the other fonts),
  chosen from eleven typefaces compared in a screenshot. No mark, no colour,
  no `running` state.
- `app/Breadcrumb`: no "Workspace" step inside a project; the project
  switcher's menu starts with "All projects". Workspace pages keep
  "Workspace" as their label.
- Favicon without the square; tokens, motion and tests updated.

## Files changed

`frontend/src/ui/Logo*`, `frontend/src/app/Breadcrumb.jsx`, styles, tests,
`frontend/index.html`, changelog.

## Migrations

None.

## Risks

Taste. The owner said to go ahead and will critique afterwards.

## Tests

`npm --prefix frontend test` (272 pass). Frontend only; the Python suite was
not re-run. Looked at in screenshots of the workspace, project and sprint
pages.

## Follow-ups

Sprint 58's live-updates task was told to make the wordmark's square
breathe; that part no longer applies and the task is updated.
