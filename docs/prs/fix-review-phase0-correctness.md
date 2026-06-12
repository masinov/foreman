# PR Summary: fix/review-phase0-correctness

## Summary

- Implements the remaining Phase 0 backend correctness fixes from
  `docs/specs/review.md`.
- Restores local Foreman self-use by creating a repo `.foreman.db` and using
  the Foreman CLI to track the sprint/task for this branch.

## Scope

- Fix agent-created task signal persistence.
- Fix `foreman waive-merge` UUID generation.
- Make dashboard-authored human events FK-safe.
- Share dashboard Run/Stop subprocess state across request-scoped service
  instances and expose `agent_running`.
- Restrict and invalidate completion-evidence prompt caching.
- Align dashboard task cancellation with CLI cancellation behavior.
- Remove the obsolete executor module and tests.
- Add defensive evidence handling for missing stored repo paths.

## Files changed

- `foreman/orchestrator.py`
- `foreman/cli.py`
- `foreman/dashboard_service.py`
- `tests/test_orchestrator.py`
- `tests/test_cli.py`
- `tests/test_dashboard.py`
- `foreman/executor.py`
- `tests/test_executor.py`
- `CHANGELOG.md`
- `docs/TESTING.md`
- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/checkpoints/2026-06-12-review-phase0-correctness.md`

## Migrations

- none

## Risks

- Full unittest discovery still has known non-slice blockers in this environment:
  missing optional `pytest`, read-only `.codex/run`, local DB-sensitive CLI
  discovery expectations, stale workflow transition-count expectations, and
  stale signal parser test expectations.
- A direct Minimax M3 Claude Code smoke with tools disabled produced malformed
  tool-call text, so worker-fleet delegation needs a tighter Phase 1 smoke
  before unattended use.

## Tests

- `./venv/bin/python -m unittest tests.test_orchestrator.AgentSignalPersistenceTests tests.test_orchestrator.EvidenceCachingTests -v`
- `./venv/bin/python -m unittest tests.test_dashboard.DashboardApproveDenyIntegrationTests.test_message_endpoint_creates_synthetic_run_for_runless_task tests.test_dashboard.DashboardSprintLifecycleTests.test_stop_agent_blocks_in_progress_tasks tests.test_dashboard.DashboardSprintTaskBacklogTests.test_cancel_task_sets_cancelled_status tests.test_dashboard.DashboardTier2Tests.test_start_and_stop_agent_registry_survives_service_instances -v`
- `./venv/bin/python -m unittest tests.test_cli.ForemanCLISmokeTests.test_waive_merge_creates_active_waiver -v`
- `./venv/bin/python -m unittest tests.test_supervisor_state.SupervisorStateTests.test_finalize_supervisor_merge_marks_task_done_and_completes_active_sprint tests.test_supervisor_state.SupervisorStateTests.test_finalize_supervisor_merge_prefers_explicit_task_id -v`
- `./venv/bin/python -m py_compile foreman/orchestrator.py foreman/cli.py foreman/dashboard_service.py scripts/reviewed_codex.py scripts/reviewed_claude.py scripts/repo_validation.py scripts/validate_repo_memory.py`
- `./venv/bin/foreman workflows && ./venv/bin/foreman roles`
- `./venv/bin/python -m unittest discover -s tests -v` attempted; failed on
  known non-slice blockers listed under Risks.

## Screenshots or output examples

- `./venv/bin/foreman board foreman` shows local sprint
  `sprint-review-phase-0-correctness` active with one Phase 0 task.

## Acceptance criteria satisfied

- Each remaining Phase 0 review item has implementation and focused regression
  coverage.
- The obsolete executor path is removed.
- Repo memory records the validation state and next blockers.

## Follow-ups

- Fix the full-suite blockers separately.
- Add a reliable Minimax M3 worker smoke as part of Phase 1 before depending on
  cheap-model delegation for unattended edits.
