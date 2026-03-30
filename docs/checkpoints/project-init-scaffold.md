# Checkpoint: project-init-scaffold

## What works

- `foreman init --db <path>` can scaffold a target repository with
  `AGENTS.md`, `docs/adr/`, `.foreman/`, and `.gitignore` updates
- initialized projects are persisted or updated in SQLite with workflow,
  default-branch, and test-command settings
- scaffold generation is idempotent and preserves a user-owned `AGENTS.md` on
  subsequent initialization runs

## What is incomplete

- `.foreman/context.md` and `.foreman/status.md` are not projected yet
- human-gate approve and deny resume commands are still pending
- native Claude Code and Codex runner backends do not exist yet

## Known regressions

- none known from the scaffold slice itself

## Schema or migration notes

- no schema migration was required
- the store gained a repo-path lookup helper so `foreman init` can update an
  existing project record in place

## Safe branch points

- `feat/init-scaffold-generator` after scaffold, CLI, and full unittest
  validation pass
- repo memory rolled forward to `sprint-04-context-projection`
