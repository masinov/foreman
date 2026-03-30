# BRANCHING

## Principles

Foreman work should happen in small, reviewable branches with explicit scope.

Core rules:

- never work directly on `main`
- one branch per coherent sprint task or tightly scoped follow-up
- prefer reversible progress over broad, unfinished rewrites
- document paused work in `docs/STATUS.md` or `docs/prs/<branch-name>.md`

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
2. read `docs/STATUS.md`
3. read `docs/sprints/current.md`
4. confirm the task belongs to the active sprint or backlog

Then:

1. create the branch
2. update sprint status if the task is now `in_progress`
3. keep the branch scoped to that deliverable

## Before calling work complete

Required:

- relevant validation run
- docs updated
- `docs/prs/<branch-name>.md` written
- follow-up work recorded if anything remains
