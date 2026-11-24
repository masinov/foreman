# PR Summary: fix/task-after-a-decision-and-while-a-task-waits-the-page

## Summary

- A task the running engine is not on reads "Waiting", not "Stopped"; "Stopped" only where no engine runs.
- A pending "Run next" is visible (`run_next`) until the engine starts the task, which now completes the `run_task` command.
- A step a task was sent back to says why; a gate's pause and decision are one attempt.
- An approval or send-back is one sentence everywhere, the server's `message` included.
- Every success sentence after an action is one shared toast; errors stay inline.

## Scope

- Engine: `ResidentEngine._complete_started_run_request`, called from `_poll_commands`, closes the `run_task` command when the engine is on the task; the end-of-pass close skips a request already closed.
- Store/services: `run_requested_task_ids`; `run_next` on `TaskService.get_task` and `SprintService.list_sprint_tasks`; `decision_sentence` for the approve/deny `message`.
- Frontend: `stageOf` and `stepRows` (Waiting, Runs next, sent back, attempts), disabled "Runs next" button, `pages/shared/decisionWords.js`, `ui/Toast` (provider, `useToast`, `useNotice`) mounted in `App`, every page's success notice moved to it.
- Docs: design README (Status, toast, approval sentence), MANUAL, CHANGELOG, sprint 62 table.

## Files changed

- `foreman/engine/resident/{base,commands}.py`, `foreman/store/commands.py`, `foreman/services/{tasks,sprints}.py`
- `frontend/src/ui/Toast.jsx` (+ test), `Icon.jsx`, `styles/{ui,tokens}.css`, `app/App.jsx`
- `frontend/src/pages/{sprint,task,shared,project,settings}/…` (notices), `shared/decisionWords.js` (+ test)
- tests: `tests/test_serve.py`, `tests/test_task_run_next.py`, `tests/test_dashboard.py`, page tests

## Migrations

- none

## Risks

- The toast's lift above the manager side bar's composer at phone width is a fixed clearance (`--toast-manager-clearance`); not checked on a device.
- A command left `acknowledged` by an older engine still shows "Runs next" until a new engine settles it (it does so on start-up).

## Tests

- Engine: a `run_task` is completed when the engine starts the task (`tests/test_serve.py`).
- Service: `run_next` true while pending/acknowledged, false once completed or rejected; the sentences (`tests/test_task_run_next.py`); the approve/deny `message` (`tests/test_dashboard.py`).
- Frontend: Waiting/Stopped/Runs next on the task page and sprint list, sent-back reasons, attempts, the approval sentence in the three places, the toast (timers, replacement, hold, close, inline error, nothing between the sprint tabs and table or above Needs you).

## Screenshots or output examples

- n/a (not checked in a browser)

## Acceptance criteria satisfied

- All five, as listed in the task.

## Follow-ups

- Look at the toast in a browser at desktop and phone width.
