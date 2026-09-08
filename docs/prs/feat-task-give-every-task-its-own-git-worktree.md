# PR Summary: feat/task-give-every-task-its-own-git-worktree

## Summary

- **The engine never changes what is checked out in the operator's
  repository.** Every task now runs in its own git worktree under
  `<repo>/.foreman/worktrees/<task-key-or-id>/`, and `_builtin:merge` lands the
  `--no-ff` merge in a shared `<worktree_root>/_integration` tree pinned to the
  default branch. The operator's checkout only ever sees refs move.
- New `foreman/worktrees.py` owns the layout and the lifecycle:
  `WorktreeManager.ensure/ensure_integration/remove/remove_path/path_for/list`
  plus `preflight()` and `prune_project_worktrees()`. It is the only module
  that constructs a working-tree path.
- Migration 16 adds the nullable `tasks.worktree_path`, so the CLI, the
  dashboard, and a restarted engine agree on where a paused task's work lives.
- New operator surfaces: `foreman worktree list|prune <project>`, the path in
  `foreman task show` and `foreman history`, and a Worktree field in the
  dashboard task drawer.
- `tests/test_cli.py` can no longer repoint the operator's virtualenv when the
  suite runs inside a worktree — which is exactly what happens when Foreman
  develops Foreman.

The sprint-54 live runs broke on the shared working tree four times
(`docs/reviews/sprint-54-live-run-notes.md`, observations 7, 19, 33, 35). All
four follow from one property — the engine and the operator shared a working
tree — and this slice removes that property rather than patching the symptoms.

## Scope

In scope: the worktree module, migration 16 and the task column, every
orchestrator and built-in call site that touched a working tree, the operator
surfaces (CLI, dashboard API, drawer), the test-harness fix, and the docs.

Out of scope: the intake endpoint and API tokens, the policy matrix, and the
per-task planner step (later sprint-54 slices). Nothing about the manager chat
changed.

## Files changed

- `foreman/worktrees.py` (new) — `WorktreeManager` bound to a project:
  `worktree_root(project)`, `task_slug(task)`, `ensure`, `ensure_integration`,
  `remove` / `remove_path` (refusing anything outside the worktree root),
  `prune_registrations`, `list`, `preflight`, and the module-level
  `prune_project_worktrees(store, project)` that the CLI's prune uses.
- `foreman/migrations.py` — migration 16, `ALTER TABLE tasks ADD COLUMN
  worktree_path TEXT`.
- `foreman/models.py` / `foreman/store.py` — `Task.worktree_path`, its
  round-trip through `save_task`/`_row_to_task`, and the narrow drift repair.
- `foreman/settings.py` — `worktree_root` and the validated
  `worktree_link_paths` (rejects absolute paths and `..`).
- `foreman/orchestrator.py` — `worktrees()`, `_ensure_task_worktree()`,
  `_task_working_dir()`, `_context_mirror_dirs()`, `_preflight_worktrees()`.
  `run_task` and `resume_human_gate` no longer `checkout_branch` in
  `project.repo_path` and no longer restore a branch; the branch invariants
  check the worktree's branch; the native runner's `working_dir`, the built-in
  executor's `working_dir`, the post-step cleanliness check, the
  refresh-before-develop merge, and the conflict-recovery merge all use the
  task's tree. `_safe_current_branch` and `_restore_branch_if_safe` are gone.
- `foreman/builtins.py` — `execute(..., working_dir=)`; `_run_tests` runs in
  the worktree and reports it on `engine.test_started`/`engine.test_run`;
  `_merge` refuses a dirty task worktree, then merges through the integration
  worktree (`engine.merge` carries `worktree`); `_mark_done` checks the task
  tree for uncommitted work and removes the worktree
  (`engine.worktree_removed` / `engine.worktree_remove_failed`);
  `_context_write` mirrors the projection into the worktree.
- `foreman/context.py` — `ProjectContextProjection.mirror_dirs`,
  `build_project_context(..., mirror_dirs=)`, `context_directory(..., root=)`,
  and a `Worktree:` line in the rendered sprint context.
- `foreman/cli.py` — `foreman worktree list|prune`, `Worktree:` in `task show`
  and `history`, `discard_task_worktree()` used by `task cancel`.
- `foreman/dashboard_service.py` — `worktree_path` on the task payload,
  worktree removal on `cancel_task`, and a `delete_task` that removes the tree
  and delegates to the store (the `DELETE /api/tasks/{id}` route previously
  called a method that did not exist).
- `frontend/src/components.jsx`, `frontend/src/styles.css`,
  `foreman/dashboard_frontend_dist/` — the drawer field and the rebuilt bundle.
- `tests/test_worktrees.py` (new), `tests/test_cli.py`,
  `tests/test_dashboard.py`, `tests/test_orchestrator.py`,
  `tests/test_output_contract.py`, `tests/test_workflow_gates.py`,
  `tests/test_engine_commands.py`.
- `docs/adr/ADR-0012-worktree-per-task.md` (new), `docs/MANUAL.md`,
  `README.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`, `CHANGELOG.md`,
  `docs/sprints/current.md`, `docs/STATUS.md`, and this note.

## Migrations

**16 — `tasks.worktree_path TEXT` (nullable).** Additive `ALTER TABLE ADD
COLUMN`, within the bundled SQLite 3.31 limits and ADR-0005's append-only
rules. Applies cleanly to a database at version 15; `foreman db version`
reports 16. Nullable by design: a task that never reached a develop step has no
worktree, and a task whose tree was removed goes back to `NULL`.

## Risks

- **Disk.** One full checkout per live task, plus one integration tree.
  Bounded by `mark_done` and cancel removing them and by
  `foreman worktree prune`, but a project that accumulates paused tasks
  accumulates checkouts.
- **`worktree_link_paths` is opt-in.** A project whose `test_command` needs
  ignored local state (`venv`, `node_modules`) fails in a fresh worktree with a
  "no such file or directory" until the setting names it. Called out in the
  manual and the troubleshooting table; **this repository needs
  `worktree_link_paths=["venv"]` set on the `foreman` project before the next
  engine-driven run**.
- **Worktrees are created with `--force`,** so a branch the operator has
  checked out can also be checked out in a Foreman tree. That is deliberate —
  the engine must not be blocked by what a person happens to have open — but it
  means two trees can be on one branch. The engine only ever writes to its own.
- **An operator sitting on the default branch** when a task merges sees the ref
  move under them, so `git status` shows their (unmodified) files as behind.
  Irreducible for a local merge; documented in §24 and the troubleshooting
  table. It is strictly better than before, when the files changed too.
- **Test fixtures** that fake an agent must write to `config.working_dir` or
  `task.worktree_path`. Every existing fixture was migrated, but a new one
  written from the old pattern will fail with "default branch moved during a
  step" rather than something obvious.

## Tests

```
./venv/bin/python -m unittest discover -s tests
Ran 802 tests — OK (skipped=1)

npm --prefix frontend test        # 29 passed
npm --prefix frontend run build   # dist rebuilt
./venv/bin/python scripts/validate_repo_memory.py
```

New coverage in `tests/test_worktrees.py`:

- **manager** — default and `worktree_root` layouts, slug from task key with
  `_integration` reserved, create from the default branch, reuse (including
  uncommitted work), reuse of an existing branch, creation while the operator
  has the branch checked out, refusal without a branch, integration tree on the
  default branch, remove (branch survives), refusal to remove outside the root,
  recreation after an operator deletes the directory, `list()`, link paths, and
  the link-path escape refusal;
- **preflight** — passes when ignored, refuses an unignored root naming
  `.gitignore`, refuses a root at the repository root, no-op outside git;
- **pruning** — finished and unclaimed trees removed, live tasks and
  `_integration` kept, dangling registrations dropped;
- **migration 16** — absent at 15, applies at 16, nullable round-trip;
- **engine** — a full task never moves the operator's checkout (and never
  writes a file into it), agent steps *and* the test command run in the task's
  tree, the projection is readable from inside that tree, the merge lands
  through the integration worktree, `mark_done` removes the tree and clears the
  column, a human gate pause and a quota pause keep it, an in-progress task
  with no recorded worktree gets one, and an unignored root fails the run
  before any task is leased.

CLI: `worktree list` (with task and branch), the empty root, `worktree prune`
(removes finished, keeps live, clears the column), an unknown project, and
`task cancel` removing the tree so `task show` stops advertising it. Dashboard:
`worktree_path` on the task payload, and cancel and delete removing the tree.

No test invokes a real `claude` or `codex` binary; every agent is a scripted
generator.

## Output examples

```
$ foreman worktree list foreman
Worktrees
Database: /repo/.foreman.db
Project: foreman | Foreman
Root: /repo/.foreman/worktrees
- FOR-102 | branch=feat/task-worktrees | task=FOR-102 | status=in_progress
  /repo/.foreman/worktrees/FOR-102
- _integration | branch=main | role=integration
  /repo/.foreman/worktrees/_integration

$ foreman task show FOR-102
Task: task-… | Give every task its own git worktree
Branch: feat/task-give-every-task-its-own-git-worktree
Worktree: /repo/.foreman/worktrees/FOR-102

$ foreman worktree prune foreman
Pruned worktrees
Root: /repo/.foreman/worktrees
Removed: 1
- FOR-101 | /repo/.foreman/worktrees/FOR-101
Kept: 2
- FOR-102 | /repo/.foreman/worktrees/FOR-102
- _integration | /repo/.foreman/worktrees/_integration

$ foreman run foreman        # in a repo whose .foreman/ is not ignored
Failed to run project: Foreman worktrees would live in '.foreman/worktrees',
which git does not ignore in /repo. Add it to .gitignore (the scaffolded
default is `.foreman/`) or point the `worktree_root` setting somewhere
ignored, then run again.
```

Dashboard drawer: a **Worktree** row under **Branch**, rendering the path in
the monospace face.

## Acceptance criteria satisfied

- Migration 16 adds `tasks.worktree_path`, applies cleanly to a version-15
  database, and `foreman db version` reports 16.
- `foreman/worktrees.py` creates, reuses, removes, prunes, and lists per-task
  worktrees under `.foreman/worktrees/` or `worktree_root`, and refuses to run
  when the root is not ignored or git lacks worktree support.
- The operator checkout's branch never changes during a task; native steps and
  `_builtin:run_tests` run in the task's worktree; the refresh and
  conflict-recovery merges happen there.
- `_builtin:merge` merges through the integration worktree; the operator
  checkout only sees the updated ref.
- Worktrees survive gate and quota pauses and review rounds, and are removed on
  `mark_done`, cancel, and delete; `foreman worktree list|prune` and
  `foreman task show` expose them.
- A suite run inside a worktree does not repoint the operator's virtualenv,
  verified by running the full suite in a real worktree of this repository and
  re-probing the virtualenv afterwards; `docs/TESTING.md` documents the
  behaviour and the check.
- The backend suite and the repo-memory validator pass.
- `docs/MANUAL.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`,
  `CHANGELOG.md`, `docs/adr/ADR-0012-worktree-per-task.md`, and this note are
  updated.

## Follow-ups

- `worktree_link_paths` was added because a worktree is a clean checkout and
  this repository's `test_command` is `./venv/bin/python …`. It is a symlink,
  which means a test run in a worktree shares the operator's virtualenv. A
  per-worktree environment (or a `test_setup_command` the engine runs once per
  new tree) would be stronger isolation; filed as a follow-up rather than
  guessed at here.
- Nothing bounds total worktree disk use. A `max_live_worktrees` cap, or
  pruning the oldest paused task's tree under pressure, is worth considering
  once several tasks are routinely paused at once.
- The dashboard shows the worktree path but offers no action on it; a
  "prune worktrees" control on the project screen is the natural surface for
  `foreman worktree prune`.
- `DashboardService.delete_task` was added here because the existing
  `DELETE /api/tasks/{id}` route called a method that did not exist and would
  have raised `AttributeError`. It is now covered, but the route's other
  neighbours deserve the same audit.
