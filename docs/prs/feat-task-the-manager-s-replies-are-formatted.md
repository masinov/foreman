# PR Summary: feat/task-the-manager-s-replies-are-formatted

## Summary

- A finished manager reply in the side bar is rendered with the shared `ui/Markdown.jsx` (no raw HTML, same link rules), in the side bar's text size.
- Streaming choice: a reply still arriving stays plain text with its cursor and is formatted when it ends. Rendering as it streams would reflow the thread as list marks, fences and bold appear (an open fence turns all that follows into a code block until it closes). Plain-until-done reads steadier.
- A user's own messages stay plain. Proposals and cards are unchanged.

## Scope

- `frontend/src/pages/manager/ManagerPanel.jsx`, `frontend/src/styles/manager.css`, tests, docs.

## Files changed

- ManagerPanel.jsx, manager.css, ManagerPanel.test.jsx, design README Manager line, CHANGELOG.md, docs/sprints/current.md, docs/sprints/backlog.md, this note.

## Migrations

- none

## Risks

- A long reply shows as text and changes shape once, when it ends.

## Tests

- Manager panel tests: formatted finished reply, plain user message with the same marks, streaming reply with marks stays plain then formats. Frontend lint, tests, build.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- All three behaviours, with tests; docs and note updated.

## Follow-ups

- none
