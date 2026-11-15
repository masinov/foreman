# PR Summary: feat/reviewer-must-read-before-approving

## Summary

- Sprint 59, slice 6. An approval of a change the reviewer was shown only
  part of, with no file opened, does not count.

## Scope

- What happened (2026-11-12): the reviewer approved a 1,310-line change in
  seven seconds. The diff in its prompt had been cut at the cap and it
  opened no file. The prompt was reworded then; nothing checked.
- New role option `[completion.output] approve_needs_reading` (default
  false; true in `code_reviewer`, `security_reviewer`, `frontier_reviewer`
  and `triage_reviewer`).
- With it, an `approve` is checked: if the prompt carries the line a cut
  diff leaves (`[...truncated N chars...]`) and the run has no Read, Grep
  or Glob (or, for a backend with a shell, no command), the engine records
  `engine.output_contract_retry` with reason `approved_unread` and asks
  again in the same session: read the changed files, then decide.
- A second unread approval becomes outcome `error` with the reason. The
  workflow has no transition for it, so the task is blocked and appears in
  Needs you. The first run keeps its `approve` in history; no review is
  recorded as evidence and nothing merges.

## Files changed

- `foreman/roles.py`, `foreman/engine/output_contract.py`,
  `foreman/engine/workflow_runner.py`
- `foreman/data/roles/{code,security,frontier,triage}_reviewer.toml`
- `tests/test_engine_review_reading.py` (new)
- `docs/STATUS.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`, `docs/MANUAL.md`

## Migrations

- none

## Risks

- It checks that something was opened, not that the right things were read
  or understood. One Read of any file satisfies it.
- A reviewer shown the whole diff may still approve without opening
  anything; that is allowed on purpose.
- A project with its own reviewer role file does not get the option until
  it adds the line.
- Run against scripted runners only.

## Tests

- `ruff check foreman tests scripts`
- `./venv/bin/python -m unittest discover -s tests` (1371 tests, 5 skipped)
- frontend lint, tests and build (unchanged code)

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Unread approval of a cut diff: sent back, then accepted once a file is
  read. Two unread approvals: task blocked, nothing merged. A search counts
  as reading. A whole diff can be approved as read.

## Follow-ups

- none
