# fix/menu-fits-its-items

## Summary

A menu's list was at least 240px wide whatever it held, so a short menu (a
task's More: "Reopen", "Delete") opened with a wide empty band beside its
items. The list is now as wide as its longest item and never narrower than
the button that opens it.

## Scope

Styles only. Every menu uses the same rule: the task and sprint More menus,
the engine menu, the breadcrumb's project menu and the user menu.

## Files changed

- `frontend/src/styles/ui.css`
- `CHANGELOG.md`

## Migrations

None.

## Risks

A menu with one very long item is as wide as that item. No current menu has
one.

## Tests

- `npm run lint`, `npx vitest run`, `npm run build` in `frontend/`
- Looked at each menu open at 1440 wide and at 390 wide.

## Acceptance criteria satisfied

- The More menu leaves no empty space beside its items.

## Follow-ups

None.
