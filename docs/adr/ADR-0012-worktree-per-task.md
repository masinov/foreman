# ADR-0012: One git worktree per task, and the operator's checkout is off limits

- Status: accepted
- Date: 2026-09-05
- Deciders: engine team

## Context

Until this decision the engine ran every step inside `project.repo_path`, the
operator's own checkout:

- `run_task` checked the task branch out there and restored the previous
  branch in a `finally`,
- each native role step ran with `working_dir = project.repo_path`,
- `_builtin:run_tests` ran the test command there,
- the refresh-before-develop and conflict-recovery merges happened there,
- `_builtin:merge` checked the **default branch** out there to merge into it.

That made the operator's working directory a shared mutable resource between a
person and the engine, and the live runs of sprint 54 broke on it repeatedly
(`docs/reviews/sprint-54-live-run-notes.md`, observations 7, 19, 33, 35):

- a person editing files in the repository while a task ran had their work
  swept into the task branch, or hit "you need to resolve your current index
  first" from a merge the engine left half-finished,
- an interrupted merge left the checkout on the default branch, mid-merge, and
  the next pass could not check the task branch out,
- two engines on one project could not be reasoned about at all: the second
  one's first `git checkout` silently moved the first one's tree.

None of these are bugs in a particular step. They all follow from one property:
the engine and the operator shared a working tree.

## Decision

**Every task gets its own git worktree, owned by Foreman. The engine never
changes what is checked out in the operator's repository.**

### Layout

```
<repo>/.foreman/worktrees/<task-key-or-id>/   # one per task
<repo>/.foreman/worktrees/_integration/       # shared, always on the default branch
```

`.foreman/` is already the ignored runtime-projection directory, so the trees
are invisible to `git status` in the operator's checkout. The
`worktree_root` project setting relocates the whole layout (an absolute path
puts it on another filesystem); `_integration` is reserved and a task can never
take that name.

`foreman/worktrees.py` owns the layout. `WorktreeManager` is bound to a project
and exposes `ensure(task)`, `ensure_integration()`, `remove(task)`,
`path_for(task)`, `list()`, and `preflight()`. Nothing else in the codebase
constructs a worktree path.

### Ownership

- **Everything under the worktree root belongs to Foreman.** The engine
  creates, checks out, merges in, and deletes those directories without
  asking. `remove_path` refuses any path outside the root, so a bad setting
  cannot turn removal into `rm -rf` on a real checkout.
- **The operator's checkout belongs to the operator.** Foreman reads it — refs,
  `AGENTS.md`, `git log`, `git diff` — and writes its context projection into
  the configured context directory. It never runs `checkout`, `merge`, or
  `reset` there, and it no longer restores a branch when a task ends.

Worktrees are created with `--force`. Whether the operator happens to have the
task branch (or the default branch) checked out in their own tree is not
allowed to decide whether a task can run.

### Lifecycle

A worktree is created on the task's first develop visit, from the existing task
branch or a new one cut from the default branch. It is **kept** across human
gates, quota pauses, review rounds, and engine restarts: the developer's
half-finished state is the whole point of resuming at the same step. It is
removed by `_builtin:mark_done`, by `foreman task cancel` and the dashboard's
cancel and delete, and by `foreman worktree prune`. Removing a worktree never
removes the branch.

`tasks.worktree_path` (migration 16, nullable) persists the path so the CLI,
the dashboard, and a restarted engine find the tree without recomputing the
layout. A task from before this decision simply gets a worktree on its next
visit; its branch already exists.

### The integration worktree

`_builtin:merge` cannot merge into the default branch inside the task's
worktree (that tree is on the task branch) and must not do it in the operator's
checkout. It uses `<worktree_root>/_integration`, kept checked out at the
default branch, runs the `--no-ff` merge there, and the merge preflight checks
*that* tree's cleanliness. One shared integration tree, not one per task: the
default branch can only be at one commit anyway, and merges are serialized by
the project engine lock.

The merge also refuses when the **task's** worktree is dirty. Uncommitted work
there is not on the branch, so merging would silently drop it.

### What the operator's checkout does and does not see

| | |
|---|---|
| Never changed by the engine | current branch, index, working-tree files, stash |
| Changed by the engine | refs — the default branch advances when a task merges; task branches appear and move |
| Written by the engine | the context projection under `context_dir` (default `.foreman/`), the worktrees under `worktree_root` |

An operator sitting *on* the default branch when a task merges sees the ref
move under them, exactly as `git fetch` would move a remote-tracking branch —
their files are untouched but now describe an older commit. That is the
irreducible consequence of advancing a branch someone has checked out, and it
is strictly better than the previous behaviour, which changed the files too.

### Preflight

A project whose worktree root is not ignored by git, or whose git predates
`git worktree`, fails at **run start** with a message naming the fix, not
halfway through a task. `foreman/worktrees.py::preflight` is called once from
`run_project`, before any task is leased.

### Linking local tooling

A worktree is a clean checkout, so it has none of the ignored local build state
a test command needs — `venv/`, `node_modules/`. The `worktree_link_paths`
setting names repository-relative paths symlinked from the operator's checkout
into every new worktree. It defaults to empty; this repository sets it to
`["venv"]` so `./venv/bin/python -m unittest discover -s tests` works inside a
task's tree.

## Consequences

### Positive

- A person can work in the repository while the engine works on a task.
- An interrupted merge cannot leave the operator's checkout unusable; the
  damage is confined to a Foreman-owned tree that the next pass repairs or
  `foreman worktree prune` deletes.
- Two engines on one project become a lock problem (ADR-0011) rather than a
  filesystem race.
- Every step's working directory is now explicit and inspectable:
  `foreman task show`, `foreman worktree list`, and the task drawer all name it.

### Negative / Trade-offs

- Disk: one full checkout per live task. Bounded by `mark_done` and cancel
  removing them, and by `foreman worktree prune` for anything left behind.
- A test command that depends on ignored local state needs
  `worktree_link_paths`. Silence here shows up as a failing test run in a fresh
  tree, which is a confusing first symptom; the manual calls it out.
- Advancing the default branch still disturbs an operator who has it checked
  out (see above). Not solvable while the merge is local.
- Test fixtures that fake an agent must write to the tree the engine gave them
  (`config.working_dir`, or `task.worktree_path`) rather than to the repo.

## Alternatives Considered

- **Clone per task.** Full isolation, but every task pays a clone, branches do
  not share a ref namespace, and the merge would need a push. Worktrees give
  the same isolation over one object store.
- **Keep using the operator's checkout and take a lock.** The lock already
  exists (ADR-0011) and did not help: it serializes *engines*, and the
  conflicting party in three of the four observed failures was a person.
- **Merge with `git update-ref` from a detached integration tree.** Avoids
  `--force`, but hides the merge from reflog-based recovery and still moves the
  ref under an operator on that branch. No benefit for the extra subtlety.
- **Bare repository plus per-task worktrees.** Would make the operator's
  checkout just another worktree, which is cleaner in theory, but Foreman does
  not own the repository layout of the projects it works on.
