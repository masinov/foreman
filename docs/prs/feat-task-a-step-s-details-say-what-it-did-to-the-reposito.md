# PR Summary: feat/task-a-step-s-details-say-what-it-did-to-the-reposito

## Summary

- A step's panel on a task's Activity tab says what it did to the repository: Session, Changed, and for a merge Main before, Brought in and Changed (sprint 62 slice 4, ADR-0038).

## Scope

- `repo/git.py` (`commit_changes`, `commits_between`, `is_ancestor`), `engine/repo_facts.py`, the agent step and the merge step record the facts, `services/task_reads.py` and `task_models.py` return them on `GET /runs/{id}/output`, `ActivityTab.jsx` and `stepFacts.js` show them.

## Files changed

- `foreman/repo/git.py`, `foreman/engine/repo_facts.py`, `foreman/engine/workflow_runner/agent_steps.py`, `foreman/engine/builtins/merge.py`, `foreman/services/task_reads.py`, `foreman/services/task_models.py`
- `frontend/src/pages/task/ActivityTab.jsx`, `stepFacts.js`, `runWords.js`, `TaskPage.test.jsx`, `frontend/src/styles/task.css`
- `tests/test_step_repository_facts.py`, `tests/test_dashboard_task_reads.py`
- `docs/adr/ADR-0038-...`, spec, MANUAL, ARCHITECTURE, design README, CHANGELOG, STATUS, sprint files

## Migrations

- none (events are free-form JSON)

## Risks

- Steps run before this change have no facts, so their panels show only Session.
- A session id that a backend changes on resume would show "New".

## Tests

- Git helper, engine (commit, no commit, sync not counted, caps, failed read), service and API, and the frontend rows, wording, five-then-all, order, "added", picking the continued attempt, no Changed without the event, the merge's rows and no Branch row.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- All of the task's, see the tests above.

## Follow-ups

- Open the Changes tab at a file, so a path in Changed can be a link.
