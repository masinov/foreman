# PR Summary: refactor/one-implementation-per-change

## Summary

- Every change the CLI and the services make to a project, sprint, task,
  decision gate or merge waiver goes through `foreman.mutations`. A test
  holds it. This follows ADR-0032's "What the layers do not settle yet".

## Scope

- `mutations/projects.py` (new): `register_project`, `reregister_project`,
  `change_project` (fields and settings checked together, with
  `host_level`, ADR-0017), `allocate_project_id`, `SettingError`,
  `HostLevelSettingError`.
- `mutations/decision_gates.py` (new): `raise_decision_gate`,
  `resolve_decision_gate`.
- `mutations/tasks.py`: `add_task`, which `foreman task add`, the
  dashboard's add task and a new sprint's first tasks all use.
- `mutations/gates.py`: `waive_merge` and `MERGE_WAIVER_TYPES`.
- `repo/worktrees.prune_project_worktrees` forgets the removed paths
  itself. The CLI and the service each did it.
- The dashboard's Run activates the next sprint with `transition_sprint`.
- `foreman sprint add` uses `create_sprint`; `foreman task override` uses
  `edit_task`; `foreman init` and `foreman config` use the project
  mutations.
- Deleted, no longer used: `allocate_entity_id`, `allocate_project_id` and
  `next_order_index` in `cli/common.py`, and `stable_slug` in
  `services/views.py`. One slug function is left (`mutations.base.slug_id`).
- `tests/test_layers.py`: no module of `cli/`, `api/` or `services/` calls
  a store's `save_*` or builds a `Project`, `Sprint`, `Task`,
  `DecisionGate` or `MergeWaiver`. It fails on the code before this branch.

## Behaviour that changes

- `foreman sprint add` refuses an empty title and strips the goal, as the
  dashboard did.
- `foreman task override` checks the overrides as an edit does
  (`validate_executor_overrides`). An edit to a task in progress or blocked
  is recorded as `human.task_edited`.
- An id made from a title uses `slug_id` everywhere. The CLI's old helper
  went through the project-id slugifier. For ordinary titles both give the
  same id.

## Migrations

- none

## Risks

- The CLI's reads are still its own (ADR-0032).

## Tests

- full Python suite (1,570), ruff, `lint-imports`, repo-memory validation.
  The suite took 556 s instead of about 250 s because two training jobs of
  another project held most of the machine's cores. Every module also
  passed when run on its own.

## Follow-ups

- The five long modules (ADR-0032).
