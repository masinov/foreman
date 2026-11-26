# BRANCHING

## Principles

Foreman work should happen in small, reviewable branches with explicit scope.

Core rules:

- never work directly on `main`
- one branch per coherent sprint task or tightly scoped follow-up
- prefer reversible progress over broad, unfinished rewrites
- document paused work in the task's own record in Foreman (its guidance or its
  blocked reason); `docs/STATUS.md` is generated and is not edited

## Branch names

Allowed prefixes:

- `feat/`
- `fix/`
- `refactor/`
- `docs/`
- `spike/`
- `chore/`

Examples:

- `feat/store-project-models`
- `feat/cli-project-init`
- `fix/reviewed-codex-paths`
- `docs/architecture-runner-boundary`

## Starting work

Before creating a branch:

1. read `AGENTS.md`
2. read `docs/STATUS.md` and `docs/sprints/current.md` (Foreman writes both
   from its database)
3. read `docs/guide/` for the topic at hand
4. confirm the task belongs to the active sprint or backlog

Then:

1. create the branch
2. leave sprint and task state to Foreman: it is in its database
3. keep the branch scoped to that deliverable

## Before calling work complete

Required:

- relevant validation run
- docs updated
- `changes/<task key>.md` written (it becomes the merge commit's message)
- follow-up work recorded if anything remains
