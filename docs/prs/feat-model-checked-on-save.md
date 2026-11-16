# PR Summary: feat/model-checked-on-save

## Summary

- A role's model is checked with the agent program when the role is saved.
  The owner typed a made-up model into "Type a model id" and asked what it
  would do: it was saved, and would have failed every task at that role.

## Scope

- `foreman/model_check.py`: one short question to Claude Code with the
  model; its refusal, in its words, refuses the save.
- `save_role(..., check_model=)`, asked only when the model or the backend
  changes; passed by the dashboard save and by `foreman role set`.
- Codex is not checked.

## Files changed

- `foreman/model_check.py` (new), `foreman/definitions.py`,
  `foreman/dashboard_definitions.py`, `foreman/cli/definitions.py`
- `tests/test_project_definitions.py`
- `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `CHANGELOG.md`

## Migrations

- none

## Risks

- A save that changes the model takes about two seconds and, for a model
  that runs, costs a fraction of a cent.
- If the program cannot be asked (not installed, no answer in 90 seconds,
  an answer that is not understood) the save goes through unchecked.

## Tests

- `ModelCheckTests` and `ModelCheckProgramTests`. The suite never calls the
  real program: run once with a stand-in on the path that logs calls, none.
- In a real browser against the real program on a database copy: "minimax"
  refused with the program's reason; "haiku" saved.

## Screenshots or output examples

- `Claude Code cannot run the model 'minimax' on this machine. It says:
  There's an issue with the selected model (minimax). It may not exist or
  you may not have access to it.`

## Acceptance criteria satisfied

- No role can be saved from the dashboard or the terminal with a Claude
  Code model that does not run on this machine.

## Follow-ups

- The same check for Codex roles.
