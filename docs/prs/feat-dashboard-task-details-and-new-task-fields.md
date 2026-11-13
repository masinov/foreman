# feat/dashboard-task-details-and-new-task-fields

## Summary

Items 7 and 10 of `docs/design/dashboard-v7/legacy-capabilities.md`.

## Scope

- `GET /tasks/{id}` adds `dependencies`: `[{id, task_key, title, status}]`,
  so the page names what a task waits for instead of showing ids.
- Task Overview, Details: "Depends on" (links, each saying whether it is
  done), "Size", and "Priority" when one was set. A closed "More details"
  line holds the working copy path, tokens in/out/cached, times at each step
  and the last role.
- New task: "Size" (not said, small, medium, large) in the backlog and in a
  sprint. In a sprint, "Make it wait for other tasks" lists the sprint's
  unfinished tasks to tick.

## Migrations

None.

## Risks

The New task dialog was not seen in a screenshot; it is covered by tests.

## Tests

`tests/test_dashboard.py` (dependencies are named), frontend tests for the
details rows, More details, and both New task forms; both whole suites.

## Follow-ups

Items 8 and 9 (advanced project settings, working copies). Editing a task's
size, priority or dependencies after it is filed is not offered yet.
