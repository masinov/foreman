# RELEASES

## Current state

Foreman is pre-release. The repository is still being bootstrapped from spec
and mockup into an executable product.

The first runnable CLI checkpoint is recorded in
`docs/checkpoints/first-runnable-foreman-cli.md`.

The first persisted SQLite store checkpoint is recorded in
`docs/checkpoints/sqlite-store-baseline.md`.

The declarative loader checkpoint is recorded in
`docs/checkpoints/role-workflow-loaders.md`.

The first orchestrator workflow execution checkpoint is recorded in
`docs/checkpoints/orchestrator-main-loop.md`.

The first project-initialization checkpoint is recorded in
`docs/checkpoints/project-init-scaffold.md`.

The first runtime-context projection checkpoint is recorded in
`docs/checkpoints/context-projection-runtime.md`.

The first human-gate resume checkpoint is recorded in
`docs/checkpoints/human-gate-resume.md`.

The first native Claude runner checkpoint is recorded in
`docs/checkpoints/claude-code-runner.md`.

The first native Codex runner checkpoint is recorded in
`docs/checkpoints/codex-runner.md`.

## Near-term policy

While the monitoring and dashboard milestones are still incomplete:

- use tags only for meaningful checkpoints,
- prefer sprint-completion checkpoints over frequent versioning,
- pair every notable tag with a checkpoint note in `docs/checkpoints/`.

## What should trigger a checkpoint

- first runnable `foreman` CLI
- first persisted SQLite project state
- first project initialization and repo scaffold generation
- first orchestrator workflow execution
- first runtime `.foreman` context projection
- first persisted human-gate resume path
- first native Claude runner
- first native Codex runner
- first dashboard implementation milestone

## Before creating a release tag

Confirm:

1. relevant tests pass
2. `docs/STATUS.md` is current
3. sprint state is current
4. `CHANGELOG.md` is updated
5. open risks are documented
6. a checkpoint note exists if the milestone matters long-term
