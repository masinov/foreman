# refactor/cli-package

## Summary

Sprint 57 slice 5. `foreman/cli.py` becomes the package `foreman/cli/`.

## Scope

- Handlers moved text-exact into a module per command group. Helpers they
  share are in `common.py` under public names.
- The parser builder was cut at each top-level command into
  `register_<command>(subparsers)` functions living next to their handlers;
  `parser.build_parser` calls them in the original order, so `--help` is
  unchanged (a test pins the order).
- `main` wraps the handler: `ForemanError` and `sqlite3.Error` print one
  line and exit 1; any other exception prints a line saying it is a bug and
  exits 70, or re-raises under `FOREMAN_DEBUG`; `KeyboardInterrupt` exits
  130.
- `--json` on `projects`, `sprint list`, `task list`, `engine status`.
- The entry point `foreman.cli:main` and `python -m foreman` are unchanged.

## Files changed

`foreman/cli.py` removed; `foreman/cli/` (14 modules) added;
`tests/test_cli_package.py` (new); one import in `tests/test_cli.py`; docs.

## Migrations

None.

## Risks

- Handlers that already printed their own error and returned 1 behave as
  before. An exception that used to escape as a traceback is now one line;
  the traceback needs `FOREMAN_DEBUG=1`.
- The JSON shapes are new and unversioned.

## Tests

Full Python suite (1088 tests) and `ruff check`.

## Acceptance criteria satisfied

Slice 5 as written in `docs/sprints/current.md`; `--json` on four of the
read commands.

## Follow-ups

`--json` on the remaining read commands.
