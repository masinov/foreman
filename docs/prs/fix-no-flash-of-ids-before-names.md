# fix/no-flash-of-ids-before-names

## Summary

Reported by the owner: clicking a project showed the title in lower case
first and then with a capital, and the breadcrumb did the same.

## What happened

The lower-case text was the project's id, shown while its name was loading.
The breadcrumb did the same for projects, sprints and tasks. And each page
loaded the workspace, sprint or task again even when the page before it had
just loaded it, so the stand-in appeared on every navigation.

## Scope

- `api/useResource.js`: a cache of what each resource key last loaded, per
  API client. A hook starts from the cached value and still refreshes it.
- `app/Breadcrumb.jsx`, `pages/project/ProjectLayout.jsx`: a name is shown as
  itself or not at all; an id is never shown in its place.

## Files changed

Three frontend files, one test, changelog.

## Migrations

None.

## Risks

A page can show a value up to one request old for the moment before its
refresh returns. Every page refreshes on mount, so it does not stay stale.

## Tests

`npm --prefix frontend test` (273 pass, 1 new: a remounted hook starts from
the cached value and refreshes). Frontend only; the Python suite was not
re-run. A still screenshot cannot show a flash, so this was not checked by
eye.

## Follow-ups

The fidelity pass should look for other values that change after first
paint.
