# feat/identity-icons-motion

## Summary

The owner asked, before the rebuild started, for better typography for the
logo, icons and some life in the interface. It had been left for a late
slice. Done by hand, looking at screenshots, because it is a matter of taste
that the conversation with the owner informs and a task description does not.

## Scope

- `ui/Logo`: the wordmark. Seven typefaces and five drawn variants were
  compared in screenshots; the one kept draws the F to the cap height and
  stem of the letters beside it and gives it one gold square.
- `ui/Icon`: ten icons on a 16px grid with one stroke, always beside a word.
  `Button` takes an `icon`.
- Top bar: the wordmark is the way home (tooltip says where; no gold hover);
  the "/" after it is gone; Workspace settings has an icon; the Manager
  toggle is quiet with the side-bar icon and a pressed state.
- Project head: folder and branch icons on the location line; Project
  settings has an icon. Engine controls and the add buttons have icons.
- `styles/motion.css` and tokens for durations and distances.
- Favicon in `frontend/index.html`.

## Files changed

`frontend/src/ui/` (Icon, Logo, Button), `frontend/src/app/` (Shell, App,
ManagerToggle, mountApp), `frontend/src/pages/project/`, `frontend/src/styles/`,
`frontend/index.html`, one test, changelog.

## Migrations

None.

## Risks

Taste. The owner has not seen it yet.

## Tests

`npm --prefix frontend test` (243 pass, 4 new for Icon and Logo); whole
Python suite. Looked at in headless Chrome screenshots of the project page.

## Follow-ups

- The wordmark's square should breathe while the project's engine runs
  (`Logo running`); the shell does not know the engine state yet. Sprint 58's
  live-updates slice wires it.
- Icons for milestone kinds and for checks (tests, review) belong to the
  fidelity pass.
