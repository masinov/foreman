# fix: make the manager operating contract list commands that exist

## Summary

The manager operating contract (`build_operating_contract` in
`foreman/meta_agent.py`) gave the manager chat agent wrong or missing CLI
syntax. Two lines were incorrect and several real commands were absent. The
contract now lists only commands that the CLI parser accepts, and a test keeps
it that way.

## Scope

- Fix `foreman history` to take `<task-id>`.
- Fix `foreman task override` to use `--step <step>=<model>` (no `--model`).
- Add `foreman task accept|block|unblock|cancel` (block/unblock/cancel were
  previously one malformed line).
- Add an Engine section: `foreman engine status|pause|resume|run-task|stop-task`.
- Add `foreman worktree list`, `foreman notify list`, and
  `foreman notify deliveries` under Inspect.
- Rename the state header column `model_override` to `assigned_role`, which is
  what the column prints.
- The Hard rules section is unchanged.

## Files changed

- `foreman/meta_agent.py`: contract text and state-header column heading.
- `tests/test_meta_agent.py`: drift test that parses every `foreman ...` line in
  the contract and checks its command and subcommand against
  `foreman.cli.build_parser()`; assertions for the corrected history and
  override syntax; assertion for the `assigned_role` heading.
- `docs/prs/fix-task-make-the-manager-operating-contract-list-commands-that-exist.md`:
  this summary.

## Migrations

None.

## Risks

- `foreman/digest.py` (around line 106) still prints
  `foreman task override <task-id> --step ... --model ...`. That is the same
  wrong syntax, but it is outside this task's scope and is left for a follow-up.
- The drift test checks command and subcommand only. It does not validate flags
  or argument counts.

## Tests

- `./venv/bin/python -m unittest tests.test_meta_agent`: 9 tests OK.
- `./venv/bin/python -m unittest discover -s tests`: 1040 tests, OK (1 skipped).
- `./venv/bin/ruff check foreman tests scripts`: passed.

## Acceptance criteria

1. The contract shows `foreman history <task-id>` and
   `foreman task override <task-id> --step <step>=<model>`, and has no
   `--model`.
2. The contract lists task accept, engine status/pause/resume/run-task/stop-task,
   worktree list, and notify list and deliveries.
3. The drift test checks every contract command against the argparse parser.
4. The state header column is headed `assigned_role`.
5. The full suite and ruff pass.

## Follow-ups

- Fix the `--model` line in `foreman/digest.py`.
