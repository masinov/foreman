# PR Summary: fix/engine-review-evidence-fresh

## Summary

- **A reviewer is shown the evidence as it is now.** It used to see a copy
  saved earlier on the task.
- **What happened on FOR-52 (2026-11-24):**
  - The merge step refused at 16:36 and saved evidence for commit 8fa6655,
    saying "tests ran on 7d8423b".
  - The tests then ran again on 8fa6655. The branch head did not move, and
    the saved copy counted as stale only when the head moved, so the
    reviewer at 17:23 was shown "Tests ran on 7d8423b5".
  - It sent the task back to re-run checks that had already passed: one
    more develop pass and one more test run.
- **The change:** `PromptBuilder` builds the evidence every time it renders a
  reviewer's prompt, which costs a few git reads, and still saves it on the
  task. `CompletionEvidenceBuilder.is_stale`, used only for that copy, is
  removed.
- Found and fixed by Claude while managing sprint 62 for the owner.

## Scope

- `foreman/engine/prompts.py`
- `foreman/engine/evidence.py`

## Files changed

- The two files above.
- `tests/test_engine_prompts.py`: a test run made again on the same commit
  shows in the next reviewer prompt.
- `tests/test_engine_evidence.py`: the test that required the evidence be
  reused now requires that it is built for every reviewer prompt.
- This note.

`CHANGELOG.md` and `docs/sprints/` are left alone while sprint 62's queued
tasks edit them. They are updated when the queue is empty.

## Migrations

None.

## Risks

None found. The evidence is now built once per review instead of once per
task until the head moves.

## Tests

- `tests.test_engine_prompts`: the new test passes, and fails on the old
  code.
- The whole Python suite, ruff, lint-imports.

## Acceptance criteria

- A reviewer never sees test or review facts older than those recorded.

## Follow-ups

- A CHANGELOG line when the queue is empty.
