# Current Sprint

- Sprint: `sprint-43-backend-run-queue-activation`
- Status: done
- Branch: `fix/run-auto-activate-planned-sprint`
- Started: 2026-04-21
- Completed: 2026-04-21

## Goal

Move first-planned-sprint activation into the backend run path so Foreman can
start working queued sprints from `foreman run <project>` without depending on
the dashboard service to pre-activate the queue.

This is a backend-execution slice aimed directly at the autonomous-development
workflow: define sprints and tasks, start Foreman, let the engine consume the
queue from structured state, and stop unattended work when sprint budget limits
are reached. It also tightens failure reporting and run-time limits so backend
operators can understand and constrain live agent failures without leaving the
repo checkout stranded on task branches after routine runs. The slice now also
hardens active-run ownership so a live native task holds the sprint until it
resumes or times out, rather than letting the orchestrator start another task
into the same checkout.

## Context and rationale

After merging `fix/dashboard-run-invocation`, the real project state on `main`
showed:

```bash
./venv/bin/foreman run foreman
```

returning:

```text
Stop reason: idle
```

even though planned sprints were queued in the SQLite store. The dashboard
worked around this by activating the first planned sprint before spawning the
subprocess, but the backend run path itself still treated "no active sprint" as
"no work". That blocks the intended operator flow of setting up queued work and
then starting Foreman from the backend surface.

## Constraints

- Fix backend run semantics, not just another surface-specific shim.
- Preserve task-scoped `foreman run <project> --task <task-id>` behavior.
- Keep sprint queue ownership in durable backend logic so CLI and future
  callers share the same behavior.
- Add regression coverage for both the orchestrator and the CLI contract.
- Keep budget enforcement in the orchestrator, not the dashboard.

## Affected areas

- `foreman/orchestrator.py` — project-scoped run startup
- `foreman/orchestrator.py` — project-scoped run startup and sprint budget gate
- `foreman/orchestrator.py` — backend failure blocking semantics
- `foreman/executor.py` — project-level run time limit mapping
- `foreman/git.py` — safe worktree cleanliness check for branch restoration
- `tests/test_orchestrator.py` — queue activation regression coverage
- `tests/test_executor.py` — run timeout mapping coverage
- `tests/test_cli.py` — `foreman run` regression coverage
- `docs/STATUS.md` — active branch and slice context
- `docs/prs/fix-run-auto-activate-planned-sprint.md` — branch summary

## Implementation plan

### Task 1 — Backend queue pickup

When `run_project()` is called for a whole project and no sprint is active,
activate the first planned sprint by queue order before the selection loop
starts.

### Task 2 — Regression coverage

Cover the no-active-sprint case in:

- orchestrator tests
- CLI tests

so the backend contract stays aligned with the "define queued work, then run"
operator workflow.

### Task 3 — Sprint budget guardrail

Honor `cost_limit_per_sprint_usd` in the orchestrator before the next workflow
step runs. When the sprint's cumulative persisted run cost is already over the
limit, block the task, emit `gate.cost_exceeded` with `scope="sprint"`, and
stop unattended execution instead of continuing to burn budget.

### Task 4 — Actionable backend failures

When a native runner exhausts retries or fails preflight, preserve the actual
run error detail on the blocked task instead of replacing it with the generic
workflow fallback message. This keeps live autonomous failures diagnosable from
task history and task detail surfaces.

### Task 5 — Product-level run timeout mapping

Make the native executor honor `time_limit_per_run_minutes` from project
settings when building runner config, while keeping the older
`runner_timeout_seconds` setting as a fallback for compatibility.

### Task 6 — Checkout restoration after safe task runs

Capture the caller's original branch before a directed task switches onto its
working branch. After the task run or human-gate resume finishes, restore the
original branch when git is healthy and the worktree is clean. This reduces
checkout drift during live backend use without risking a forced branch switch
over uncommitted task work.

### Task 7 — Active-run ownership and stale-run recovery

Treat `in_progress` tasks without a persisted workflow step as live sprint
owners. While that ownership exists, `select_next_task()` should wait instead
of starting other directed work or creating autonomous placeholders. Only
persisted `running` runs that have exceeded the configured timeout window
should be failed and recovered automatically.

## Risks

- The dashboard currently performs its own pre-activation before spawning the
  subprocess, so backend activation must remain compatible with that existing
  behavior while the dashboard shim still exists.
- A queued sprint with no tasks will still activate and then immediately idle;
  this slice does not redefine empty-sprint policy.
- Sprint cost gating currently uses persisted USD totals. Backends that report
  tokens without reliable USD pricing still need separate pricing support for
  complete budget enforcement.
- Live native runs still depend on timeout-based stale detection rather than a
  stronger lease or heartbeat. This branch prevents parallel task starts in the
  same sprint and recovers stale `running` runs, but it does not yet add active
  cancellation or positive liveness confirmation.

## Validation

- `./venv/bin/python -m pytest tests/test_orchestrator.py -q`
- `./venv/bin/python -m pytest tests/test_executor.py -q`
- `./venv/bin/python -m pytest tests/test_cli.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`
