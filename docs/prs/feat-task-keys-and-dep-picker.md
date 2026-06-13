# PR Summary: feat/task-keys-and-dep-picker

## Summary

Adds Jira-style per-project task keys (`FOR-102`) and replaces the dependency
checkbox list with a Jira/Linear-style search-to-add picker. Motivated by the
dependency picker being unstyled and unscalable (a checkbox wall of full titles)
and the lack of any compact, linkable task handle.

## Scope

### Backend — task keys (migration 13)
- `migrations.py` migration 13: `projects.task_key_prefix`, `tasks.task_key`,
  `idx_tasks_task_key`. Mirrored in `_repair_known_schema_drift` for older DBs.
- `models.py`: `Project.task_key_prefix`, `Task.task_key`.
- `store.py`:
  - `derive_task_key_prefix(name)` — "Foreman" → `FOR`, "My Project" → `MP`,
    fallback `TASK`.
  - `save_task` assigns a **write-once** key to brand-new tasks
    (`PREFIX-N`, per-project max+1); the key is set on INSERT and never changed
    by updates (excluded from the upsert SET).
  - `_ensure_project_key_prefix` / `_next_task_key` helpers; one-time
    `_backfill_task_keys()` run from `initialize()` for pre-existing tasks.
  - Centralizing key assignment in the store means every creation path (CLI,
    dashboard, agent `signal.task_created`) gets keys automatically.
- `dashboard_service.py`: `task_key` added to `get_task`, `list_sprint_tasks`,
  `create_task` / `create_sprint` responses, and the active-sprint task rows.

### Frontend — keys + dependency picker
- `DependencyPicker`: type to filter by key or title, up to 6 matches; selected
  deps render as removable chips (key shown, full title on hover). Replaces the
  scrolling checkbox list; flows through the shared `TaskFormFields`, so all
  three creation surfaces get it.
- Keys surfaced on the task card, the detail drawer header, the active-sprint
  mini-list, and the drawer's dependency chips.

## Migrations

- 13 (additive). Backfill assigns keys to existing tasks on first
  `initialize()`; prefix derived from the project name and persisted.

## Risks

- Per-project sequence is max-existing + 1 (not a stored counter), so a key is
  not reused while its task exists; a deleted task's number can be reused. Fine
  for display/linking. Keys are unique within a project, not globally.

## Tests

- `tests/test_store.py` — round-trip updated for the derived prefix / assigned
  key (write-once verified by smoke).
- `tests/test_dashboard.py` — `create_task` assigns a sequential `PREFIX-N` key,
  surfaced in board + detail payloads (+1).
- Full suite: **585** backend; frontend **12**. `validate_repo_memory` clean.

## Follow-ups

- Optional: show keys in the CLI (`task show`, `board`) and let the manager
  reference `FOR-102` in chat.
- Optional: editable project key prefix in settings.
