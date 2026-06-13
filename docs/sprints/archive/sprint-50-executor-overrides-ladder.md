# Sprint 50 — Review Phase 3 Executor Overrides + Escalation Ladder

- **Branch:** `feat/executor-overrides-ladder` (stacked on
  `feat/meta-agent-persistence`)
- **Merged:** 2026-06-13 (fast-forward to `main` at `2ca7b49`)
- **Status:** done

## Goal

Add per-task executor overrides, task complexity, role `model_ladder`,
deterministic per-step model resolution, `workflow.model_selected` events,
CLI/API override surfaces, and architect-created complexity persistence.

## Tasks completed

| # | Task | Deliverable |
|---|------|-------------|
| 1 | Migration 12 | `tasks.executor_overrides_json` + `tasks.complexity` with additive schema-repair fallbacks; `Task.executor_overrides: dict`, `Task.complexity: str\|None`; row mapping + `save_task` updated |
| 2 | Role ladder | `AgentConfig.model_ladder`; when present it supersedes `model` for tier selection |
| 3 | Model resolution | `resolve_step_model` / `resolve_step_model_selection` (pure) — five-branch precedence: per-step override (ladder-resume if the override is in the ladder, else pinned) → role ladder indexed by `ladder_start + visit_count - 1` (`ladder_start` from override, else a complexity map, else 0) → role `model` → project `default_model` → None. Wired into the workflow loop and native runner; a `workflow.model_selected` event records `{step, model, visit_count, source}` per agent step |
| 4 | Complexity signal | `signal.task_created` validates + persists optional `complexity` (`small\|medium\|large`) |
| 5 | CLI | `foreman task add --complexity`; new `foreman task override TASK_ID [--step STEP=MODEL]... [--ladder-start N] [--clear]` (step ids validated against the project workflow); overrides/complexity in `task show` |
| 6 | Dashboard | `PATCH /api/tasks/{id}` accepts a validated full-object `executor_overrides`; task payloads expose `executor_overrides` + `complexity` |
| 7 | Example role | `roles/developer_worker.toml` documents a commented `model_ladder` example and the per-role-per-endpoint limitation |

## Files changed

`foreman/migrations.py`, `foreman/models.py`, `foreman/roles.py`,
`foreman/orchestrator.py`, `foreman/cli.py`, `foreman/dashboard_service.py`,
`roles/developer_worker.toml`, and the matching tests in
`tests/test_orchestrator.py`, `tests/test_cli.py`, `tests/test_dashboard.py`.

## Test results

- `ResolveStepModelTests`, ladder integration test, complexity signal test, CLI
  override round-trip, dashboard PATCH validation
- Full suite passed
- `scripts/validate_repo_memory.py`

## Follow-ups

- Stacked-on by Sprint 51 (token economy: LLM judge + tiered review).
