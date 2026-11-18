# PR Summary: fix/checkout-follows-merges

## Summary

- Found on Assay. A project folder registered while on `main` showed none of
  the merged code: the engine moved `main` under it and left its files
  behind, so git listed the merged work as staged deletions. After a merge,
  that checkout is now brought along when nothing of the person's would be
  lost (ADR-0031, amends ADR-0012).

## Scope

- `foreman/git.py`: `follow_branch_in_checkout`, `CheckoutFollow`.
- `foreman/builtins.py`: the merge step calls it and records
  `engine.checkout_updated` or `engine.checkout_behind`.
- `frontend/src/pages/task/runWords.js`: words for the two events.

## Files changed

- `foreman/git.py`, `foreman/builtins.py`
- `frontend/src/pages/task/runWords.js`
- tests: `tests/test_git.py` (new `FollowBranchInCheckoutTests`),
  `tests/test_worktrees.py` (the end-to-end operator-checkout tests),
  `frontend/src/pages/task/runWords.test.js`
- `docs/adr/ADR-0031-…`, `docs/adr/README.md`, `docs/adr/ADR-0012-…`,
  `docs/MANUAL.md` §24, `CHANGELOG.md`

## Migrations

- none

## Risks

- A person editing on the default branch sees files change under them at
  each merge. Their edits are kept, or the update is refused.

## Tests

- ruff, the full Python suite, frontend lint, tests and build.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- A clean checkout on `main`, even several merges behind, shows the merge
  and has an empty `git status`.
- Untracked files and unstaged edits survive. An update that would
  overwrite one changes nothing and is reported.
- A checkout on another branch is not touched.

## Follow-ups

- none
