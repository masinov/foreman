# PR Summary: fix/sprint-head-checkpoint-and-goal

## Summary

- From the owner's look at slice 2 (2026-11-23):
  - **The Tag and Note rows are gone from the sprint's Details.** They were
    long lines the panel could not show, and the note's path told a user
    nothing.
  - **State says the commit:** "Finished 20 Nov at 6f79f4a", with the tag's
    name on hover. If tagging failed: "Finished 20 Nov, not tagged", with
    the reason on hover.
  - **The note is not shown.** It repeats the page's goal and tasks for
    people who read the repository.
  - **The goal fills the height beside Details** (`useLinesBeside`), never
    less than four lines. Before, it was always four lines, however tall
    Details was. Stacked on a phone, it keeps four.
- "No code browser" is no longer a rule (owner, 2026-11-23). A view of the
  code and one of the repository's history are open questions in
  direction 6.

## Scope

- **Frontend:**
  - `pages/sprint/SprintHead.jsx`;
  - `ui/LongText.jsx` (a `lines` prop) and `ui/useLinesBeside.js` (new);
  - `styles/ui.css` (the unused one-line cut removed).
- **Docs:**
  - `docs/sprints/backlog.md` (direction 6), `docs/ROADMAP.md` (stage 5);
  - ADR-0036 item 7, `docs/design/dashboard-v7/README.md`, `CHANGELOG.md`.

## Files changed

- As in Scope.
- **Tests:** `frontend/src/pages/sprint/SprintPage.test.jsx`,
  `frontend/src/ui/useLinesBeside.test.jsx` (new).

## Migrations

- None.

## Risks

- The fit is measured in the browser, on load, on resize and when Details
  changes size. Where `ResizeObserver` is missing it follows only the
  window's size.

## Tests

- `npm test` (489), `npm run lint`, `npm run build`.
- Screenshots on a copy of the database, with a real checkpoint made on a
  clone of Assay, at desktop and phone width. With a fourth Details row the
  goal grows from four lines to six.

## Acceptance criteria satisfied

- No long rows in Details. The commit is in State.
- The goal is not cut shorter than the Details beside it.

## Follow-ups

- Slice 3.
