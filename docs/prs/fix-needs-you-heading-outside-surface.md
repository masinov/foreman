# fix/needs-you-heading-outside-surface

## Summary

Reported by the owner: "Needs you" was inside the same tinted component as
its rows, with nothing dividing heading from content. The design
(`docs/design/dashboard-v7/README.md`, "One tinted surface means act here";
`02-project-sprints.html`) has the heading above the surface.

## Scope

- `frontend/src/pages/shared/NeedsYou.jsx`: the section is a plain section;
  the heading and notices sit above; the tinted `Surface` wraps only the
  rows (and "Show all"). With no items there is no surface, only the
  sentence.
- `frontend/src/styles/lists.css`: the surface's padding around rows.

## Files changed

Two frontend files, changelog.

## Migrations

None.

## Risks

None known.

## Tests

`npm --prefix frontend test` (239 pass); whole Python suite. Looked at in a
headless Chrome screenshot of the project page with three waiting approvals.

## Follow-ups

The pages were built by agents that could not see them. System Chrome can
take screenshots on this host (`google-chrome --headless=new --screenshot`),
so a fidelity pass against the design, and a screenshot check in every
remaining frontend task, are filed in sprint 58.
