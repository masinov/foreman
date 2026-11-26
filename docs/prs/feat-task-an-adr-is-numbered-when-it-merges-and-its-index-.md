# PR Summary: feat/task-an-adr-is-numbered-when-it-merges-and-its-index-

## Summary

- ADR-0040 build item 5. A branch writes `docs/adr/new-<slug>.md`; the merge numbers it, rewrites references and regenerates the index, and refuses duplicate numbers.

## Scope

- `foreman/repo/adrs.py`: reading ADRs, numbering, reference rewriting, index generation, duplicate detection.
- `foreman/repo/git.py`: `merge_branch(..., finish=)` makes the merge with `--no-commit`, lets the hook change and stage the tree or refuse, then commits.
- `foreman/engine/builtins/merge.py`: runs the hook when the merge brings a change to the ADR folder; a refusal is `engine.merge_blocked` (reason `duplicate_adr_numbers`); `engine.merge` carries `adrs` (old and new paths).
- Setting `adr_dir` (default `docs/adr`; empty: off), Settings › General.
- Where the renaming lands: the merge commit, so the tested branch is unchanged and the number is taken against the default branch's current head. See `changes/FOR-68.md`.
- `AGENTS.md`, developer prompt, `docs/adr/README.md` (index regenerated, how-to added), `docs/MANUAL.md`, `docs/ARCHITECTURE.md`.

## Files changed

- `foreman/repo/adrs.py`, `foreman/repo/git.py`, `foreman/engine/builtins/merge.py`, `foreman/domain/settings.py`, `foreman/repo/scaffold.py`
- `frontend/src/pages/settings/*`, `frontend/src/testing/settingsFixture.js`
- `tests/test_adr_numbering.py`, `changes/FOR-68.md`

## Migrations

- none

## Risks

- A duplicate number already on the default branch blocks every merge that touches the ADR folder until it is fixed by hand.
- Two branches adding the same `new-<slug>.md` slug conflict in git as add/add only if the first is not yet renamed; the first merge renames it, so the second lands as a new file.

## Tests

- `tests/test_adr_numbering.py`; merge tests in `tests/test_builtins.py`.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- All five; see the developer report.

## Follow-ups

- none
