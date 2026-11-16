# fix: a resolved sprint stays active until a person finishes it (ADR-0025)

## Summary
`SprintFlow.resolve` looks at the autonomy level first. Autonomous: unchanged.
Directed/supervised: the sprint stays `active`, the pass stops `sprint_resolved`,
and `engine.sprint_ready` plus one `sprint_resolved` attention turn are recorded
once per resolution.

## Scope
foreman/engine/sprints.py, foreman/orchestrator.py, foreman/digest.py, tests, docs.

## Risks
Callers that expected `idle`/`sprint_complete` for non-autonomous projects now see `sprint_resolved`.

## Tests
`./venv/bin/python -m unittest discover -s tests`; `./venv/bin/ruff check .`

## Follow-ups
Spec 6.4 checkpoint actions; reopening a completed sprint.
