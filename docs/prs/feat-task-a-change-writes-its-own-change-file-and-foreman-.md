# PR Summary: feat/task-a-change-writes-its-own-change-file-and-foreman-

## Summary

- ADR-0040 build item 4. A change is described in `changes/<task key>.md`; `CHANGELOG.md` is generated from those files when a sprint finishes.

## Scope

- `foreman/mutations/changelog.py`: reads change files, renders a sprint's section, folds it above the file's earlier content (after a marker line), stages the removals.
- `foreman/mutations/checkpoint.py`: the note and the changelog are one commit; a failure is `engine.checkpoint_failed` with the reason; `engine.checkpoint` gains `changelog_path`.
- Setting `generate_changelog` (default off; Settings › General › Advanced). To turn it on for Foreman's own project: `foreman config foreman --set generate_changelog=true` (not done here: it is the live database).
- `foreman changelog <project> [--sprint <id>]`.
- Developer and code reviewer prompts, `AGENTS.md`, `scripts/repo_validation.py`: change file instead of a `CHANGELOG.md` edit.

## Files changed

- `foreman/mutations/changelog.py`, `foreman/mutations/checkpoint.py`, `foreman/cli/changelog.py`, `foreman/cli/parser.py`, `foreman/cli/sprints.py`, `foreman/services/sprints.py`, `foreman/domain/settings.py`, `foreman/repo/scaffold.py`
- `foreman/data/roles/developer.toml`, `foreman/data/roles/code_reviewer.toml`, `AGENTS.md`, `scripts/repo_validation.py`, `docs/MANUAL.md`
- `frontend/src/pages/settings/*`, `changes/README.md`, `changes/FOR-67.md`, `tests/test_changelog.py`

## Migrations

- none

## Risks

- A project with the setting on and a changelog the folding cannot commit gets no tag (as with a failed note); the reason is recorded.

## Tests

- `tests/test_changelog.py`; `tests/test_sprint_checkpoint.py`.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- All five; see the developer report.

## Follow-ups

- Turn the setting on for Foreman's project once merged.
