# fix/needs-you-empty-keeps-its-surface

## Summary

Follow-up to `fix/needs-you-heading-outside-surface`. That change removed the
tinted surface when nothing needs a person, which the design never showed and
the owner did not expect. The surface is back for the empty state, holding
the sentence; the heading stays above it.

## Scope

`frontend/src/pages/shared/NeedsYou.jsx`, `frontend/src/styles/lists.css`.

## Files changed

Two frontend files, changelog.

## Migrations

None.

## Risks

None known.

## Tests

`npm --prefix frontend test` (239 pass). Frontend only, so the Python suite
was not re-run. Looked at in a headless Chrome screenshot of the workspace.

## Follow-ups

None.
