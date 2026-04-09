# Current Sprint

- Sprint: `sprint-42-dashboard-run-invocation`
- Status: done
- Branch: `fix/dashboard-run-invocation`
- Started: 2026-04-10
- Completed: 2026-04-10

## Goal

Align the dashboard's background `Run` subprocess invocation with the shipped
CLI contract so dashboard-triggered runs actually launch the orchestrator
instead of failing immediately on an unrecognized argument.

This slice is intentionally narrow: fix the invocation path, add regression
coverage for the exact argv, and remove the now-closed repo-memory risk.

## Context and rationale

During the repo-memory reconciliation pass, the dashboard service was found to
spawn:

```bash
foreman run --project <project_id> --db <path>
```

The actual CLI parser exposes:

```bash
foreman run <project_id> [--task ...] [--db ...]
```

This means the dashboard's Run control can report success from the API layer
while the child process exits immediately with `unrecognized arguments:
--project`. The code path needs a direct regression test because previous
coverage only asserted that a subprocess was spawned, not that its argv was
valid.

## Constraints

- Fix the invocation shape only; do not broaden this slice into dashboard UX or
  orchestrator refactors.
- Preserve the existing `./venv/bin/foreman` subprocess entrypoint rather than
  changing the dashboard to a different runtime contract.
- Add regression coverage for both project-scope and task-scope start paths.
- Leave unrelated local frontend edits untouched.

## Affected areas

- `foreman/dashboard_service.py` — `start_agent` subprocess argv
- `tests/test_dashboard.py` — `start_agent` regression coverage
- `docs/STATUS.md` — closed risk and completed-sprint record
- `docs/sprints/backlog.md` — remove closed follow-up
- `docs/prs/fix-dashboard-run-invocation.md` — branch summary

## Implementation plan

---

### Task 1 — Fix the subprocess argv

Change the dashboard service from:

```bash
foreman run --project <project_id> --db <path>
```

to:

```bash
foreman run <project_id> --db <path>
```

---

### Task 2 — Lock the contract down with tests

Extend dashboard tests so they assert the exact argv passed to
`subprocess.Popen`, including:

- project-scope start: positional `project_id`
- task-scope start: positional `project_id` plus `--task <task_id>`

---

## Risks

- The current tests patch `subprocess.Popen`, so they validate argv shape but do
  not execute a real background run.
- This does not address broader dashboard process-lifecycle concerns beyond the
  CLI argument mismatch.

## Validation

- `./venv/bin/foreman run --help`
- `./venv/bin/foreman run --project demo --db /tmp/demo.db` (expected parser
  failure before the fix; confirms the mismatch exists)
- `./venv/bin/python -m pytest tests/test_dashboard.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`
