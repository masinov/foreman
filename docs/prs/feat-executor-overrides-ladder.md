# PR Summary: feat/executor-overrides-ladder

## Summary

Sprint 50 (review Phase 3 — per-task executor overrides + escalation ladder).
The manager can now differentiate dispatch per task, and the engine escalates
model tier automatically on repeated failure. A single pure function resolves
the model for every agent step and the engine records each choice as a
`workflow.model_selected` event so escalations are auditable.

Stacked on the unmerged `feat/meta-agent-persistence` (Phase 2) branch.

## Scope

- migration 12: `tasks.executor_overrides_json`, `tasks.complexity`
- `Task.executor_overrides: dict` + `Task.complexity: str | None`; store
  row-mapping, `save_task`, and additive schema-repair
- role `[agent] model_ladder` (`AgentConfig.model_ladder: tuple[str, ...]`)
- `resolve_step_model` / `resolve_step_model_selection` pure functions, wired
  into `run_workflow_from_step` and `_execute_native_runner_step`; a
  `workflow.model_selected` event per agent step
- `signal.task_created` accepts/validates optional `complexity`
- `foreman task add --complexity`; `foreman task override TASK_ID
  [--step STEP=MODEL]... [--ladder-start N] [--clear]`; overrides/complexity
  shown in `foreman task show`
- dashboard `PATCH /api/tasks/{id}` accepts a validated `executor_overrides`
  full-object replace; `executor_overrides`/`complexity` in `get_task` and
  `list_sprint_tasks` payloads
- `roles/developer_worker.toml` documents a commented `model_ladder` example
  and the per-role-per-endpoint limitation

## Files changed

- `foreman/migrations.py`, `foreman/models.py`, `foreman/store.py`
- `foreman/roles.py`, `foreman/orchestrator.py`
- `foreman/cli.py`, `foreman/dashboard_service.py`
- `roles/developer_worker.toml`
- `tests/test_orchestrator.py`, `tests/test_cli.py`, `tests/test_dashboard.py`,
  `tests/test_migrations.py`
- `docs/STATUS.md`, `docs/sprints/current.md`, `docs/sprints/backlog.md`,
  `CHANGELOG.md`

## Migrations

- migration 12 — additive `ALTER TABLE tasks ADD COLUMN` for
  `executor_overrides_json` (default `'{}'`) and `complexity` (nullable).
  Applies cleanly on fresh and existing DBs; `_repair_task_schema` adds the
  columns to long-lived local DBs whose ledger drifted.

## Model resolution precedence (resolve_step_model)

1. per-step override (`executor_overrides.models[step]`): if the override model
   appears in the role ladder, escalation resumes from its index for later
   visits; otherwise it is pinned for every visit.
2. role `model_ladder` indexed by `ladder_start + visit_count - 1`, where
   `ladder_start` = override `ladder_start`, else complexity map
   `{small:0, medium:0, large:1}`, else 0.
3. role `model`.
4. project `default_model` setting.
5. `None` (harness default).

## Risks

- Different ladder rungs share one role `[agent.env]`; rungs needing different
  endpoints must be modeled as different roles per step. Documented in the role
  TOML; per-model env maps are intentionally unimplemented.
- Existing run records created before this change keep their previously
  persisted `model`; resolution only affects new runs.

## Tests

- `tests.test_orchestrator.ResolveStepModelTests` — all five precedence
  branches + override-in-ladder resume + complexity start index
- `tests.test_orchestrator.ForemanOrchestratorTests.test_model_ladder_escalates_developer_model_across_repeated_visits`
  — A→B→C across three develop visits, with `workflow.model_selected` events
- `tests.test_orchestrator.AgentSignalPersistenceTests.test_signal_task_created_persists_valid_complexity_and_ignores_invalid`
- `tests.test_cli...test_task_override_round_trips_and_is_visible_in_show`,
  `...test_task_add_targets_explicit_sprint_with_description_and_dependencies`
- `tests.test_dashboard...test_update_task_executor_overrides_validated_and_returned`,
  `...rejects_unknown_step`
- `tests.test_migrations` (migration 12 covered by generic + meta tests)
- `./venv/bin/python -m unittest discover -s tests` — full suite (see commit)
- `./venv/bin/python scripts/validate_repo_memory.py`; `git diff --check`

## Output examples

```
$ foreman task override task-big --step develop=MiniMax-M2 --ladder-start 1
Updated task executor overrides
Overrides: {"ladder_start": 1, "models": {"develop": "MiniMax-M2"}}
```

## Acceptance criteria satisfied

- `resolve_step_model` unit tests cover all five precedence branches plus the
  override-in-ladder resume case.
- Orchestrator integration test: ladder `[A,B,C]` with repeated develop visits
  runs A, then B, then C, and `workflow.model_selected` events record it.
- `foreman task override` round-trips through the CLI and is visible in
  `foreman task show`.

## Follow-ups

- Phase 4 (sprint 51): opt-in LLM-judged criteria evidence (`foreman/judge.py`).
- Frontend affordance to display/edit per-task executor overrides and
  complexity (currently API/CLI only).
