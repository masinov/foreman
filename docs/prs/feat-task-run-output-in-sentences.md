# PR Summary: feat/task-run-output-in-sentences

## Summary

- Sprint 59, slice 9. A run's output on the task Activity tab is a story in
  sentences, with the raw stream one level down.

## Scope

- API: `GET /api/v1/runs/{id}/output` returns, per event, `kind`, `at`,
  `text` (only for lines of test output) and `data` (the event's facts,
  long strings clipped to 4,000 characters). The agent's raw stream
  (`agent.raw_output`) is no longer in the default transcript; its line
  count is `raw_entries`, and `?raw=true` returns it alone.
- Page: `runWords.js` turns an entry into `{ says, mono, body, tone }` and
  `narrate` builds the story (test output gathered, a closing message that
  repeats the one before it dropped). `ActivityTab` renders it as rows of
  time and sentence; a line naming the day appears where the day changes.
- Left out as bookkeeping: context writes, session ids, cost updates, the
  resolved policy, and the duplicate of a filed task.
- An event kind the page does not know is shown by name with its facts.

## Files changed

- `foreman/dashboard_task_reads.py`, `foreman/dashboard/task_models.py`,
  `foreman/dashboard/routers/tasks.py`
- `frontend/src/pages/task/runWords.js` (new), `ActivityTab.jsx`,
  `frontend/src/api/tasks.js`, `frontend/src/ui/format.js`,
  `frontend/src/styles/task.css`, `tokens.css`,
  `frontend/src/testing/taskFixture.js`
- `tests/test_dashboard_task_reads.py`,
  `frontend/src/pages/task/runWords.test.js` (new), `TaskPage.test.jsx`
- `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/sprints/current.md`,
  `docs/sprints/backlog.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- A client that read `text` for every entry gets an empty string for
  events now; the dashboard is the only client.
- The wording covers the event kinds recorded so far (58 in Foreman's own
  database). A new kind shows by name until it is given words.

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1389 tests, 5 skipped)
- `npm --prefix frontend run lint`, `test` (378 tests), `run build`
- Looked at with `scripts/dashboard_shot.mjs` on a copy of Foreman's own
  database: a develop run, a test run, a review run and a run a person
  closed by hand, at 1440 wide; the review run at 390 wide.

## Screenshots or output examples

- Review run: "Model: claude-sonnet-5-5, named by the role / May use every
  tool except Bash, Write, Edit, NotebookEdit / Started Review / Searched
  for head_sha|GitError in foreman/engine/workflow_runner.py / APPROVE /
  Finished in 9.4 s · 445 tokens · $0.11 / Review recorded: Approved at
  c52648d".

## Acceptance criteria satisfied

- No raw JSON in a run's story; nothing recorded is hidden without a way to
  see it (the raw stream and the prompt are each behind a disclosure).

## Follow-ups

- The project and sprint Activity tabs list milestones and were already in
  sentences; nothing to do there.
