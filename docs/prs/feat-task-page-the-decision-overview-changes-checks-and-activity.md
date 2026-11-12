# PR Summary: feat/task-page-the-decision-overview-changes-checks-and-activity

## Summary

- Sprint 58 slice 8. The task page at `/dashboard/tasks/{id}` and its
  `/changes`, `/checks` and `/activity` routes, built from
  `docs/design/dashboard-v7/05`, `12`, `13` and `14` on the slice 7 reads.
- One header on all four tabs: title; a mono line (key, type, branch, commit,
  size of change); Edit (dialog); More, holding only the actions that exist
  for the task's state (Run next, Stop, Block or Unblock, Cancel, Delete).
  Each action opens a dialog that says what will happen and shows an API
  refusal as its sentence.
- The decision, on the one tinted surface, only while the task waits for a
  person. It asks one of four questions: "Approve the merge into main?",
  "Approve this plan?", "Accept this task?", or the reason the task is blocked
  ("Blocked: …"). It shows the facts that bear on the question, has a button
  that sends the task back (asking for guidance) and the one filled gold
  button.
- The API had no route to block or unblock a task (only the CLI could). This
  branch adds `POST /tasks/{id}/block` and `POST /tasks/{id}/unblock` over the
  shared mutation service, and `created_at` on the task payload for "Filed
  by".

## Scope

- Planning, as AGENTS.md asks:
  - Goal: the four task routes from live data, with the decision and every
    task action.
  - Constraints: ADR-0020 (layout, tokens, no inline styles, tests per page,
    bundle committed), ADR-0019 (one error envelope), ADR-0018 (facts and
    claims kept apart). No invented data. No new dependency.
  - Affected areas: `frontend/src/pages/task/` (new),
    `api/tasks.js`, `api/client.js`, `api/useEventStream.js`,
    `app/Breadcrumb.jsx`, `ui/Table.jsx`, `styles/task.css`; and on the
    Python side `foreman/dashboard_service.py` and the tasks router.
  - Risks and validation: see below.
- Backend:
  - `POST /tasks/{id}/block` takes `reason` (required) and parks the task with
    `Mutations.block_task`.
  - `POST /tasks/{id}/unblock` takes an optional `note`. It calls
    `Mutations.unblock_task`, and then, if a note was given, records it as
    guidance the same way `POST /tasks/{id}/messages` does. A refused unblock
    (for example, a task at a gate) records nothing.
  - `GET /tasks/{id}` carries `created_at`.
- Frontend:
  - `TaskLayout` loads the task, its checks and its changes once for the
    header and the decision. Each tab adds only what it needs: Overview loads
    the project's workflow, Changes one diff at a time, Activity the paged
    runs and the selected run's output.
  - Decision kinds and their calls:
    - merge, plan or another gate: approve calls `POST /approve`; "Send back"
      (guidance required) calls `POST /deny` with `note`.
    - filed work: Accept calls `POST /accept`; Decline calls `POST /decline`
      with `reason`.
    - blocked: Unblock calls `POST /unblock`; "Send back" (guidance
      required) calls `POST /unblock` with `note`.
    - After each, the page reloads and shows the API's sentence, for example
      "No engine is running, so the task waits…".
  - Overview:
    - Steps: one row per workflow step except the closing mark-done step,
      with result, who did it, and how many runs. The step a task waits at
      says "Waiting for you".
    - A one-line Checks summary that links to Checks.
    - "Guidance for the next agent step": a labelled text area that saves
      through `POST /tasks/{id}/messages`. Every note written is listed with
      "Waiting for the next agent step" or "Read by the agent at <step> on
      <time>".
    - Details: stage, sprint, workflow, who decides (for the gates the
      workflow has, with where the setting came from), branch, spend, filed
      by.
    - The description and the acceptance criteria as filed.
  - Changes:
    - Totals; "<head> against <base>. Measured by the engine from git."
    - The file list, each file a pressed or unpressed button. The first file
      is selected by default.
    - The selected file's diff, with line numbers from each hunk. An added
      line has a green `+` sign column and a removed line a red `−`, so colour
      is never the only cue.
    - A truncated diff says how long it was and how much is shown.
    - An empty change shows the API's `empty_reason`.
    - A binary file, or a rename with no edits, says that there are no lines
      to show.
  - Checks:
    - "Measured by the engine" (tests with the result line, branch, size) and
      "Reported by an agent" (reviews, then each acceptance criterion) are two
      separate tables.
    - Evidence files show "None required by this workflow." (design README,
      Phase 5).
  - Activity:
    - Runs newest first, 25 at a time, with "Earlier".
    - The newest run is selected until another is picked. The selected run
      shows its output entries and a disclosure, "Show the prompt this run
      was given".
  - Live refresh: while the task is `in_progress`, the page follows
    `GET /sprints/{id}/stream` and reads the task, checks and changes again
    300 ms after the last event about this task. `client.stream()` puts the
    token in the query, which the API accepts for streams, because an
    EventSource cannot send headers.
  - Breadcrumb: Workspace / project / sprint (or Backlog) / task key. The
    engine menu sits in the top bar, as on the sprint page.
  - "Run next" in More, for a queued task in a sprint, calls
    `POST /projects/{id}/agent/start` with `task_id`. The legacy checklist
    gave this to slice 8.
- Deviation, on purpose: for filed work, the decision's second button says
  "Decline", not "Send back". Declining is what the endpoint does, and it is
  the Backlog tab's word for the same action.
- Out of scope: the manager side bar (slice 9), per-task overrides (models,
  who decides), evidence files (Phase 5).

## Files changed

- `foreman/dashboard_service.py`: `block_task` and `unblock_task`, plus
  `created_at` in `get_task`.
- `foreman/dashboard/schemas.py`: `TaskBlock` and `TaskUnblock`.
- `foreman/dashboard/routers/tasks.py`: the two routes.
- `tests/test_dashboard_task_block.py`: new.
- `frontend/src/api/`:
  - `tasks.js`: every task read and action.
  - `client.js`: `stream`.
  - `useEventStream.js`: new.
  - `backlog.js`: decline takes a reason.
  - `engine.js`: `runTaskNext`.
- `frontend/src/pages/task/`, all new:
  - `TaskLayout`, `TaskHead`, `TaskActions`, `EditTaskDialog`,
    `ReasonDialog` and `Decision`.
  - `OverviewTab`, `ChangesTab`, `ChecksTab` and `ActivityTab`.
  - `TaskPages`.
  - `taskWords.js` and `diff.js`.
  - Tests: `TaskPage.test.jsx` and `diff.test.js`.
- `frontend/src/app/`:
  - `pages.js`: registers the four routes.
  - `Breadcrumb.jsx`: project and sprint crumbs above a task.
  - `App.test.jsx`: the two tests that assumed the task page was not built.
- `frontend/src/ui/`:
  - `Table.jsx`: `selected(row)` shades the picked row.
  - `format.js`: `formatDuration`.
  - Tests for both.
- `frontend/src/styles/`:
  - `task.css`: new.
  - `base.css`: `tone-*` word colours.
  - `ui.css`: the selected row.
- `frontend/src/testing/`:
  - `taskFixture.js`: new.
  - `fakeApi.jsx`: a fake EventSource.
- `foreman/dashboard_frontend_dist/`: rebuilt.
- `docs/ARCHITECTURE.md`: the new routes, the task page's reads and the
  stream.
- `docs/design/dashboard-v7/legacy-capabilities.md`: every slice 8 row is now
  built, plus a row for block and unblock.

## Migrations

- none

## Risks

- Opening a stream without a cursor first delivers the most recent events.
  This costs at most one extra reload per stream that is opened.
- Only a running task follows the stream. A queued task that the engine
  picks up is not refreshed until the page is opened again. Slice 12 owns
  live updates in general.
- The breadcrumb and the top bar's engine menu read the task on their own,
  as on the sprint page. They are not re-read after an action. Today nothing
  they show changes as a result of one.
- In the Overview steps, Develop shows its outcome and duration. The design's
  "Committed <sha>" needs a commit per run, which the runs payload does not
  carry.

## Tests

- `npm --prefix frontend test`: 25 files, 214 tests, all passed. Of these,
  `TaskPage.test.jsx` has 48 tests covering:
  - the same header on all four routes; the breadcrumb, including a task in
    the backlog; the not-found case; Edit;
  - the decision for merge, plan, filed work and blocked tasks, and its
    absence for running, queued and done tasks; both of its buttons and the
    endpoint each calls; a refusal;
  - More: the actions for each state; every action confirmed, calling its
    endpoint and showing a refusal; Block needing a reason; Delete going to
    the sprint; Run next;
  - Overview: steps, the checks line, details, guidance saving with its read
    and waiting states, the stream refresh, and no stream while nothing
    runs;
  - Changes: the file list, the diff marked by sign, picking another file, a
    truncated diff, a binary file, empty changes;
  - Checks: separate tables for facts and claims, evidence files, and the
    state with no claims;
  - Activity: runs, the selected run's output and prompt, paging with
    Earlier, and no runs.
- `npm --prefix frontend run build`: the bundle is rebuilt and committed.
- `./venv/bin/python -m unittest discover -s tests`: 1245 tests, OK, 1
  skipped. `tests/test_dashboard_task_block.py` has 8 tests.
- `ruff check foreman tests`: passed.
  `./venv/bin/python scripts/validate_repo_memory.py`: passed.
- No real browser is available on this host (ADR-0020). The look is still to
  be checked by a person against the drawings.

## Screenshots or output examples

- n/a (jsdom only)

## Acceptance criteria satisfied

- All four routes render from live data with the same header component
  (`TaskLayout` and `TaskHead`).
- The decision appears only when a person is needed, and asks the right
  question for each of the four kinds. Its two actions call the right
  endpoints. Tested for each kind and for tasks that need nothing.
- Every action in More is confirmed, calls its endpoint, and shows a refusal.
  Tested.
- Guidance saves, and shows whether it is waiting or has been read. Tested.
- Changes renders the file list and a diff, and marks additions and removals
  by a leading sign as well as by colour. It handles truncated and empty
  cases. Tested.
- Checks keeps facts and claims in separate tables. Tested.
- Activity pages its runs and shows the selected run's output. Tested.
- Frontend tests pass, the bundle is rebuilt and committed, the Python suite
  passes, and this file exists.

## Follow-ups

- Per-task overrides from the screen map ("who decides, which model for a
  step") have no place on the page yet.
- A commit per run, so the Develop row can say "Committed <sha>" as the
  design does.
- Show tokens per run on Activity: the legacy drawer showed them, and the
  runs payload has them.
- Slice 12: follow the stream for every state, not only while a step runs,
  and resume from the last event id.
- Evidence files (Phase 5) fill the Evidence section. Its list rendering is
  minimal until their shape is used for real.
