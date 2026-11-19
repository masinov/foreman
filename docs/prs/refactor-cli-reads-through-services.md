# PR Summary: refactor/cli-reads-through-services

## Summary

- Every CLI read command takes its data from a service and prints it as
  text or, with `--json`, as the document itself. Sixteen commands gained
  `--json`; the existing documents keep their shape.
- `foreman/services/reports.py` (`ReportService`): the terminal's reports
  with no API counterpart (status, board, project, sprints, tasks, history,
  transcript, cost, engine status). The board takes the sprint and its
  tasks from the sprint service.
- The worktree list, tokens and notification channels now use the same
  reads as the API (`services.worktrees`, `services.access`).
- `tests/test_layers.py`: no CLI function lists or totals rows itself
  (except `watch` and one lookup for a change), and every read command
  offers `--json`.

## Scope

- No behaviour change in text output; the CLI test suite passes unchanged.
- The sprint board's task card gains `step_visit_counts`.

## Files changed

- `foreman/services/reports.py` (new), `foreman/services/access.py`,
  `foreman/services/sprints.py`, `foreman/services/__init__.py`.
- `foreman/cli/{monitor,projects,sprints,engine,worktree,tokens,notify,catalog,definitions,db,common}.py`,
  `foreman/cli/tasks/{reads,register}.py`.
- `tests/test_layers.py`; ADR-0032, MANUAL, CHANGELOG, backlog, sprint file.

## Migrations

- none

## Risks

- Text output is rendered from dicts now; the CLI tests cover each
  command's lines.

## Tests

- Full suite, ruff, `lint-imports`.

## Screenshots or output examples

- `foreman board assay --json`, `foreman task show <id> --json`.

## Acceptance criteria satisfied

- The CLI's reads go through services; `--json` on every read command.

## Follow-ups

- Response models on the API (backlog, with the central server's API).
