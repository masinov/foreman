# PR Summary: feat/task-a-step-s-details-show-the-reads-before-its-first

## Summary

- When an agent run ends, the engine counts the reading tool calls before its first change and records them as an `engine.step_reads` event (`{reads, edited}`), as ADR-0038 records a step's repository facts.
- The step's facts on the task page show "N reads before its first edit" or "N reads, no edit", beside the tokens it used.
- `foreman outcomes` gives the median reads before the first edit per role and model (ADR-0034).

## Scope

- One function, `reads_before_first_change`, in `foreman/domain/step_reads.py`, holds the rules (reading: `Read`, `Grep`, `Glob`, read-only shell commands; change: `Edit`, `Write`, `MultiEdit`, `apply_patch`, file-writing shell commands, `git commit`).
- The median is over runs that changed something; runs with no edit are counted separately ("N of M runs with no edit").

## Files changed

- `foreman/domain/step_reads.py` (new), `foreman/engine/workflow_runner/agent_steps.py`, `foreman/domain/outcome_numbers.py`, `foreman/cli/outcomes.py`, `foreman/services/task_models.py`, `foreman/services/task_reads.py`
- `frontend/src/pages/task/stepFacts.js`, `runWords.js`
- Tests: `tests/test_step_reads.py`, `tests/test_outcome_numbers.py`, `tests/test_dashboard_task_reads.py`, `frontend/src/pages/task/stepFacts.test.js`

## Migrations

- none (the record is an event; older runs have none and show nothing).

## Risks

- Shell classification is by command words, not a full shell parse; an unusual command line is counted as neither a read nor a change.

## Tests

- Unit tests over real-looking command lines, Claude Code, shell-only, Codex and no-edit runs, an engine run, outcome numbers, the CLI, the API, and the frontend facts.

## Screenshots or output examples

- `- developer | sonnet | runs=3 | failed=0 | reads before first edit: median 7 (1 of 3 runs with no edit) | $1.20`

## Acceptance criteria satisfied

- All four.

## Follow-ups

- none
