# PR Summary: feat/engine-push-after-merge

## Summary

- Sprint 59, slice 5. The engine pushes the default branch after a merge
  when the project names a remote.

## Scope

- New project setting `merge_push_remote` (default empty). It must be a
  remote's name: a URL or anything starting with `-` is refused.
- It is host-level (ADR-0017): the API and the settings page cannot change
  it; the page shows it under "This machine" as "Push merges to".
- `_builtin:merge`, after a successful merge, runs `git push <remote>
  <branch>` from the integration tree with a 120 second limit and with git
  told not to prompt for credentials. Success adds an `engine.push` event;
  failure adds `engine.push_failed` with the error. Either way the step's
  outcome is `success`: a remote that is down must not send finished work
  back to develop.

## Files changed

- `foreman/settings.py`, `foreman/git.py`, `foreman/builtins.py`
- `frontend/src/pages/settings/settingsWords.js`
- `tests/test_engine_push.py` (new)
- `docs/MANUAL.md`, `docs/adr/ADR-0017-*.md`, `docs/STATUS.md`,
  `docs/sprints/current.md`, `docs/sprints/backlog.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- A failed push is only an event and a line in the merge step's detail. No
  notification is raised and nothing retries it; the next merge's push
  carries the earlier commits with it.
- The push is a plain fast-forward push. If the remote branch has moved
  (someone pushed to it), the push is rejected and recorded as failed; the
  engine does not fetch or rebase.
- Tested against a local bare repository, not a hosted remote.

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1367 tests, 5 skipped)
- frontend lint, tests and build

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- With the setting, the remote's branch equals the local one after a task
  merges. Without it nothing is pushed. With a remote that does not exist
  the task is still done and the failure is recorded.

## Follow-ups

- Pull requests through the remote (Phase 5) replace a direct push for
  projects that want review on the remote.
