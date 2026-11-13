# feat/dashboard-live-updates

## Summary

Sprint 58 slice 12, the part about data: pages update without a reload.

## Scope

- `app/useLiveData.js`, mounted once in the application. Inside a project
  (its page, a sprint, a task, settings, the backlog) it follows
  `GET /projects/{id}/stream` and calls the application-wide `refresh()`,
  which makes every loaded resource load again while keeping what it shows.
  - Events that are an agent's or a test run's output are ignored.
  - The replay a new listener is sent in its first 1.5 s is ignored: the page
    has just read that state.
  - A burst is one reload (400 ms settle), and reloads are at least 2 s apart.
- The workspace follows no stream (it spans projects); it reads again every
  20 s while visible.
- Any page reads again when its tab becomes visible.
- The settings form and a task's overrides restart their draft only when the
  values read differ, so a background reload never wipes typing.
- The task page keeps its own stream for the task that is running, which
  also carries the output the project-wide reload ignores.

## Migrations

None. No API change.

## Risks

A task page with a running step holds two streams (project and sprint).
Browsers allow six connections per host over HTTP/1.1; several tabs on
running tasks could reach that. One stream per tab is the follow-up if it
is ever seen.

## Tests

`app/App.test.jsx` (staying current), `ProjectSettings.test.jsx` (a
background refresh), the task page's stream tests; the whole frontend suite.

## Follow-ups

Motion that depends on live data (a row arriving); ESLint; docs.
