# ADR-0012: One git worktree per task, and the operator's checkout is off limits

- Status: accepted
- Date: 2026-09-05
- Deciders: engine team
- Amended: 2026-09-05 — added the `max_live_worktrees` disk-use policy, the
  `worktree_setup_command` per-worktree environment, and the dashboard prune
  control.

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

### Local tooling: linking versus provisioning

A worktree is a clean checkout, so it has none of the ignored local build state
a test command needs — `venv/`, `node_modules/`. There are two ways to fix
that, and they are not equivalent.

**`worktree_link_paths`** names repository-relative paths symlinked from the
operator's checkout into every new worktree. It is one symlink and no wall
clock, but the tree then *shares* the operator's environment: a task that
upgrades a dependency to make its own tests pass changes the operator's
interpreter and every other task's too. It is the escape hatch for tooling that
is genuinely expensive and genuinely read-only.

**`worktree_setup_command`** is the real answer, added by this amendment. It is
a shell command run once inside each newly created tree, before any step runs
there, with the tree as its working directory and these variables exported:

| Variable | Meaning |
|---|---|
| `FOREMAN_WORKTREE_PATH` | the tree being provisioned |
| `FOREMAN_REPO_PATH` | the operator's checkout |
| `FOREMAN_WORKTREE_BRANCH` | the branch checked out in the tree |
| `FOREMAN_DEFAULT_BRANCH` | the project's default branch |

`FOREMAN_REPO_PATH` matters: a project needs *some* base interpreter to build
an environment from, and pointing at the operator's is how a tree bootstraps
one that is thereafter its own. This repository sets:

```
"$FOREMAN_REPO_PATH/venv/bin/python" -m venv venv \
  && ./venv/bin/pip install --quiet --disable-pip-version-check setuptools wheel \
  && ./venv/bin/pip install --quiet --disable-pip-version-check -e .
```

and `worktree_link_paths` is now empty. `./venv/bin/python -m unittest discover
-s tests` inside a task's tree runs against that tree's own interpreter and its
own editable install of that tree's source, so the result describes the task's
branch and nothing else. Provisioning costs about six seconds and one venv per
tree.

Setup runs **once per tree**, tracked by a marker in the tree's git admin
directory (`<repo>/.git/worktrees/<slug>/`). That location is deliberate: a
marker inside the tree would be an untracked file, which would make the tree
dirty and block `_builtin:merge`. `git worktree remove` takes the admin
directory with the tree, so a reclaimed tree is reprovisioned when it comes
back. The marker records a hash of the command, so changing the setting
reprovisions every tree on its next visit, and clearing it drops the marker.

The integration tree is **not** provisioned: only `_builtin:merge` works
there, and it runs git and nothing else, so building an environment it would
never use would cost a full one per project.

A failing setup command fails `ensure`: the tree has no usable environment, so
running a step in it would produce a test failure that describes the
environment rather than the task. No marker is written, so the next visit
retries; the tree is left on disk to be inspected.

### Bounding disk use

One full checkout per live task is the cost of this decision, and until this
amendment nothing capped it: a project with several tasks paused at gates
accumulated a tree each, and only `mark_done`, cancel, or a manual
`foreman worktree prune` ever gave the space back.

**`max_live_worktrees` (default 4, `0` disables) caps how many task worktrees
exist at once.** It is enforced in `enforce_worktree_limit`, called from the
engine immediately *before* it creates a tree, so the cap bounds peak disk use
rather than its steady state. The reclaim order:

1. the integration tree and the tree of the task about to run are never
   candidates,
2. trees of done, cancelled, or deleted tasks go first — nothing wants them,
3. then the least recently used of the rest, measured by the tree's own git
   index mtime, which git rewrites on every checkout, commit, and status in
   that tree.

**A tree with uncommitted changes is never reclaimed.** That work is not on the
branch, so removing the tree would destroy it — which is exactly the state a
paused developer step leaves behind, and the reason the trees are kept across
gates at all. Reclaiming is safe for every *clean* tree because such a tree
holds nothing its branch does not: the task keeps its branch and its workflow
position, `worktree_path` is cleared, and the next visit recreates the checkout
(and reprovisions its environment) from the same branch.

The consequence is that the cap is a ceiling the engine reaches for, not an
invariant it can always hold. A project whose trees are all dirty stays above
its cap, and the engine records `engine.worktree_limit_exceeded` naming the
trees it refused to take. Losing an agent's unfinished work to a disk quota is
strictly worse than exceeding the quota and saying so.

| Event | Meaning |
|---|---|
| `engine.worktrees_reclaimed` | trees removed to make room, with the new count |
| `engine.worktree_limit_exceeded` | the cap could not be met; the dirty trees that blocked it |
| `engine.worktree_reclaim_failed` | reclaiming errored; the task still got its tree |

Reclaiming never fails a task. It is an optimisation on top of a correct
system, so an error is recorded and the task proceeds.

### Operator surfaces

`foreman worktree list` and `foreman worktree prune` cover the CLI. The
dashboard's Project Settings → Task working copies section shows the stored
copy count and configured storage limit separately, the worktree root under
collapsed Storage details, and a **Remove unused copies** control backed by
`GET /api/projects/{id}/worktrees` and
`POST /api/projects/{id}/worktrees/prune`. The control runs the same policy as
the CLI — done, cancelled, and unclaimed trees only — so it can never take a
tree a live task is using.

The settings placement and wording were corrected on 2026-09-08 after operator
feedback: retained checkout count is a disk-use concern, not execution
concurrency, and does not belong in the general sprint overview.

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

- Disk: one full checkout per live task, plus whatever
  `worktree_setup_command` builds inside it. Bounded by `max_live_worktrees`,
  by `mark_done` and cancel removing trees, and by `foreman worktree prune` or
  the dashboard control for anything left behind — but see above: the cap
  yields to uncommitted work, so it is a ceiling and not a guarantee.
- A test command that depends on ignored local state needs
  `worktree_setup_command` (or `worktree_link_paths`). Silence here shows up as
  a failing test run in a fresh tree, which is a confusing first symptom; the
  manual calls it out.
- A reclaimed task pays a checkout and a re-provision when it resumes. Tuning
  `max_live_worktrees` too low turns into repeated setup cost rather than
  incorrect behaviour.
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
- **Pruning the oldest paused tree unconditionally under disk pressure.** The
  original follow-up phrasing. Rejected: "paused" is precisely when a tree
  holds uncommitted work, so the policy would most often destroy exactly the
  state it was asked to preserve. Cleanliness, not age, is what makes a tree
  safe to take; age only orders the safe ones.
- **A per-task container or filesystem quota.** Real isolation and a hard
  bound, but it makes Foreman own the runtime environment of every project it
  works on, which it does not. A command the project writes stays inside the
  project's own tooling.
- **Bare repository plus per-task worktrees.** Would make the operator's
  checkout just another worktree, which is cleaner in theory, but Foreman does
  not own the repository layout of the projects it works on.

## Amendment, 2026-11-11: the default branch may move while a task runs

The orchestrator used to snapshot the default branch before each step and
block the task if the branch had moved by the step's end ("The default
branch must not be mutated during task execution"). That predates
worktrees, when an agent sharing the operator's checkout could commit to
the wrong branch. Under this ADR the operator's branch is theirs, and other
tasks merge into it; the check blocked healthy tasks whenever either
happened. It did so twice in sprint 56, on a hotfix pushed to `main` and on
an unrelated merge, each time discarding the task's resume point.

The invariant that matters is narrower: a task's own commits must not be on
the default branch before the workflow's merge step puts them there. After
every non-merge step the engine now asks git for the commits on the task
branch that were not on the default branch when the step began or when the
engine last refreshed the task branch from it, and blocks the task only if
any of those is reachable from the default branch
(`git.task_commits_on_default_branch`). On the git version in use here
(2.25) an agent can still move a branch another worktree has checked out
with `git branch -f`, `git push .` or `git update-ref`, so the check keeps
its purpose.

## Amendment, 2026-11-11: autonomous tasks get a worktree too

Branch and worktree creation was conditional on
`task_selection_mode == "directed"`, following spec §6.2 ("the orchestrator
does not create a branch; the agent creates its own branch and reports
it"). The first tests written for autonomous mode showed what that meant
under this ADR: the placeholder task had no branch, so no worktree, so
`_task_working_dir` fell back to the repository path and the agent ran in
the operator's checkout, committing to whatever branch was checked out
there. The merge step then failed with "Task branch is not set".

The engine now assigns the branch and creates the worktree for every task,
in both modes. In autonomous mode the agent still chooses the work and
names it with `signal.task_started`; a branch it reports is accepted only
when it is a valid name, exists, and is not the default branch. This
deviates from the letter of spec §6.2 and is recorded as a documented
conflict in `docs/STATUS.md`.
