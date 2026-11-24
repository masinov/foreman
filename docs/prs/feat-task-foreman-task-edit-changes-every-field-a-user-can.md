# PR Summary: feat/task-foreman-task-edit-changes-every-field-a-user-can

## Summary

- `foreman task edit` now changes type, description and acceptance criteria through `Mutations.edit_task` (`via="cli"`), as text, from a file or stdin, or in the user's editor.
- Every command that takes a task accepts its key (`FOR-56`) as well as its id.
- The manager's operating contract names the options and keys.

## Scope

- Options: `--type`, `--description`, `--criteria`, `--description-file`, `--criteria-file` (`-` is stdin), `--edit description|criteria`.
- `--edit` opens `$VISUAL`, else `$EDITOR`, else `nano`, else `vi`, only with `--edit` and only on a terminal; unchanged or emptied text changes nothing ("Description unchanged."); the temporary file is removed.
- Refused: a text and its `-file` form, `--edit` with an option for the same field, two texts from stdin, `--edit` off a terminal. An empty `--description ""` clears the text, as the dashboard allows.
- Keys: `resolve_task_or_print` tries the id, then the key (within the project when the command knows it); a key in several projects is refused, naming them.

## Files changed

- `foreman/cli/tasks/texts.py` (new), `foreman/cli/tasks/changes.py`, `register.py`
- `foreman/cli/common.py`, `gates.py`, `monitor.py`, `backlog.py`, `engine.py`, `tasks/reads.py`
- `foreman/store/tasks.py` (`find_tasks_by_key`), `foreman/manager/agent.py`
- `tests/test_task_edit_texts.py`; `docs/MANUAL.md`, `CHANGELOG.md`, `docs/sprints/current.md`

## Migrations

- none

## Risks

- The manager session refuses `task edit` (it proposes `edit_task` instead); the contract says so.
- Key matching ignores case.

## Tests

- `tests/test_task_edit_texts.py`: three ways, `--edit` (rewrite, unchanged, emptied, no terminal), refusals, `human.task_edited` via cli, keys (show, edit, block, history, ambiguous), contract text.

## Screenshots or output examples

- `Description: changed (412 characters)`, `Type: feature -> fix`, `Description unchanged.`

## Acceptance criteria satisfied

- All three; see Scope.

## Follow-ups

- none
