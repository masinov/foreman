# PR Summary: fix/task-a-merge-refused-for-lack-of-proof-says-why-in-pl

## Summary

- A merge refused for lack of proof gives a reason in plain sentences: a short heading, the facts said once with 7-character commit ids, and what the user can do.

## Scope

- `proof_refusal_text` in the completion guard; evidence reasons use 7-character ids; the decision box heads with the first sentence and shows the rest.
- The structured evidence is unchanged.

## Files changed

- `foreman/engine/builtins/completion.py`, `foreman/engine/evidence.py`
- `frontend/src/pages/task/taskWords.js`, `Decision.jsx`, `TaskPage.test.jsx`
- `tests/test_engine_completion_guard.py`, `tests/test_dashboard.py`, `tests/test_engine_evidence.py`
- `CHANGELOG.md`, `docs/sprints/current.md`

## Migrations

- none

## Risks

- Older blocked reasons keep their text and still show with a "Blocked:" prefix.

## Tests

- New cases: stale tests and review said once, failed tests, no approving review, tests not run; no internal words.
- Frontend: decision box heading and detail.
- ruff, lint-imports, full unittest suite, frontend lint, tests and build.

## Screenshots or output examples

- "Not merged: the branch changed after it was tested and reviewed. Tests and review ran on 7d8423b; the branch is now at 8fa6655. Unblock it to test and review it again."

## Acceptance criteria satisfied

- Plain reason with heading, details and next step; no internal words; tests for each case.

## Follow-ups

- none
