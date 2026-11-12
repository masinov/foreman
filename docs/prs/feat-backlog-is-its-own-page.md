# feat/backlog-is-its-own-page

## Summary

The owner's objection: "A tab being selected is not a view. It is not a
page." The backlog was a tab of the project page, yet a backlog task's
breadcrumb named it as a place ("Project / Backlog / task").

## Decision

Offered two ways to make it coherent; the owner chose the first.

1. The backlog is a page below the project, like a sprint. (Chosen.)
2. The backlog stays a tab and leaves the breadcrumb.

Other trackers were looked at for comparison. They show the backlog as a
view of the project reached from project navigation, with sprints stacked
above it for planning; they do not put a view's name in an item's
breadcrumb. Here the backlog holds tasks the way a sprint does and a task
page needs somewhere to go "up" to, so it is treated as a place.

## Scope

- `pages/project/ProjectPages.jsx`: the backlog page has its own head
  ("Backlog", and a line saying whose and what it is) and no project header.
- `app/Breadcrumb.jsx`: "Project / Backlog" on that page; no tab names in
  any breadcrumb.
- `pages/project/ProjectLayout.jsx`: tabs are Sprints and Activity.
- `pages/project/SprintsTab.jsx`: a "Backlog" line under the queue with how
  many tasks are in no sprint, linking to the page.
- This changes ADR-0020's screen list (the backlog is no longer a project
  tab); `docs/design/dashboard-v7/README.md` should be amended when the
  design is next revised.

## Files changed

Four components, one route title, styles, four test files, changelog.

## Migrations

None. The address is unchanged.

## Risks

On the backlog page the engine's state is not shown (it is on the project
page, and in the top bar on sprint and task pages).

## Tests

`npm --prefix frontend test` (309 pass). Frontend only; the Python suite was
not re-run. Both pages seen in screenshots.

## Follow-ups

- Engine state in the top bar on the backlog page, as on a sprint page.
- Amend the design README and ADR-0020's wording about project tabs.
