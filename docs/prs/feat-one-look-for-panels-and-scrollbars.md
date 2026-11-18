# PR Summary: feat/one-look-for-panels-and-scrollbars

## Summary

- After the board's column panels (owner, 2026-11-18), the rest of the app
  is brought to the same look:
  1. **Tones with one meaning each.** A tinted panel holds a group of things
     one may act on; what needs the person is said in gold. An item on a
     panel is one step lighter (`--color-panel-item`, renamed from
     `--color-board-card`). The design README's "Look" is revised.
  2. **The proposal card is a panel.** It was the only outlined component.
  3. **One scrollbar everywhere**, the page's own included: thin, a grey
     thumb, no track. This moves from the board's rules to `base.css`.
  4. **Everything else stays flat.**
- Found while checking: on the manager side bar's bar tone, a panel barely
  showed. The side bar now has the page's ground, and its line sets it
  apart.

## Scope

- `frontend/src/styles/tokens.css`, `base.css`, `sprint.css`, `manager.css`,
  `shell.css`, `ui.css`, `task.css` (comments)
- `docs/design/dashboard-v7/README.md` ("Look"), `docs/STATUS.md`,
  `CHANGELOG.md`

## Files changed

- the above, and this file

## Migrations

- none

## Risks

- The design's drawings still show the outlined proposal card, the bar-toned
  side bar and the browser's scrollbars. STATUS records this.

## Tests

- Frontend lint, tests (451) and build. In a browser on a copy of the live
  data:
  - Assay's project page with the manager open;
  - a proposal card on the bar tone (too faint), then on the ground (reads
    like Needs you);
  - a task's Changes tab, with the diff's scrollbar at 8px (measured).

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- One panel look, one item tone, one scrollbar, and no outlined component.

## Follow-ups

- none
