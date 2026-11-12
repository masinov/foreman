# PR Summary: feat/task-manager-side-bar-on-project-sprint-and-task-pages

## Summary

- Sprint 58 slice 9. The shell's manager slot is now the manager side bar
  from `06-manager-open.html` and `05-task-overview.html`, driven by the
  existing manager endpoints.
- A "Manager" toggle sits in the top bar on every page inside a project
  (project tabs, project settings, sprint, task) and nowhere on the workspace
  pages. Open or closed is kept in `localStorage` and survives navigation.
- The conversation is one per project: history loads (with "Earlier
  messages"), a message goes with the page context, the reply is read as a
  stream and grows as it is written with a block cursor, a failure is a
  sentence with Retry, and "Start a new conversation" clears the session after
  a confirmation.

## Scope

- Frontend: `pages/manager/` (panel and `useConversation`), `app/manager.js`
  (remembered state, the route to project and "You are on" label),
  `app/ManagerToggle.jsx`, `api/manager.js`, `client.postLines` (NDJSON over
  POST), `styles/manager.css`, the column and overlay in `styles/shell.css`,
  and three tokens (`--breakpoint-manager-overlay`, `--layer-overlay`, the
  block cursor size).
- API, one addition: `POST /projects/{id}/meta/message` takes an optional
  `context` (`page`, `sprint_id`, `task_id`, strings). A message could not
  carry the page before. The server turns it into one line in that turn's
  prompt and does not store it, so the transcript holds only what the person
  wrote. A malformed `context` is a 400.
- Below 960px the side bar is a fixed full-height overlay with a Close button;
  the button is hidden by CSS above that width, where the toggle does the job.
- Not in scope: the "Ask the manager" banner (`/meta/supervise`), live
  updates, the mark and motion.

## Files changed

- `foreman/meta_agent.py`, `foreman/dashboard/routers/meta.py`: page context.
- `tests/test_meta_agent.py`, `tests/test_dashboard.py`: context tests.
- `frontend/src/pages/manager/*`, `frontend/src/app/{App,Shell,manager,ManagerToggle}.*`,
  `frontend/src/api/{client,manager}.js`, `frontend/src/styles/{manager,shell,tokens}.css`,
  `frontend/src/testing/fakeApi.jsx` (a handler may return a raw `Response`).
- `docs/ARCHITECTURE.md`, `docs/design/dashboard-v7/legacy-capabilities.md`.

## Migrations

- none

## Risks

- Retry sends the message again. The server stored the first attempt's user
  turn and an interrupted reply, so history after a reload shows the failed
  attempt next to the retry. The panel shows only the retry.
- The manager acts through the `foreman` CLI while it replies. Nothing in the
  side bar can hold such an action back (see Follow-ups).
- Replies are shown as plain text with line breaks kept. Markdown the manager
  writes is not rendered; no dependency was added.
- No new dependency.

## Tests

- `npm --prefix frontend test`: 233 passed (19 new in
  `pages/manager/ManagerPanel.test.jsx`): toggle on project, sprint and task
  pages and absent on workspace pages, remembered across navigation and a new
  visit, "You are on" from the route, history and earlier messages, a message
  sent with the page context, a reply rendered incrementally from a mocked
  stream with the cursor, Enter and Shift+Enter, an error event, a refused
  request and a stream that stops early each offering Retry, clearing after a
  confirmation, and the overlay rules in CSS.
- `npm --prefix frontend run build` succeeds (the bundle is no longer committed, ADR-0020 decision 10).
- `./venv/bin/python -m unittest discover -s tests`: 1248 run, OK (1 skipped).

## Screenshots or output examples

- n/a. Not checked in a real browser in this task; the overlay is covered by
  a test of the CSS rules, not by rendering.

## Acceptance criteria satisfied

- Toggle on project, sprint and task pages, absent on workspace pages;
  remembered; survives navigation. Tested.
- History loads, a message is sent with the page context, a streamed reply
  renders incrementally, an error offers Retry. Tested with a mocked stream.
- "You are on" follows the route. Tested.
- Narrow-width overlay is in CSS; the Close control is a button, so it is
  reachable by keyboard.
- Frontend tests pass, build succeeds, Python suite passes, this
  file exists with the proposal gap named below.

## Follow-ups

- **No structured proposal.** The manager endpoints stream only `text_delta`,
  `tool_use`, `done` and `error`. The manager changes things itself through
  the CLI during its turn, and there is no proposal object to show as a card
  with "Not now" and "Confirm". So the side bar shows the reply as text and
  has no card and no Confirm step, and nothing in the frontend invents a
  format. Delivering the design's "nothing happens until you confirm" needs
  a backend piece first: the manager returns a proposal (what it will
  create, change or leave) and holds its actions until a confirm call.
- The "Ask the manager" banner for attention events
  (`POST /projects/{id}/meta/supervise`) has no home yet.
- Markdown in replies is not rendered.
- The overlay has no focus trap or Escape to close; it is a plain fixed panel.
