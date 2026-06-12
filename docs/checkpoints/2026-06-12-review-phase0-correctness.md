# Checkpoint: 2026-06-12-review-phase0-correctness

## What works

- The missing local `./venv` was restored with Python 3.12 and Foreman was
  installed editable.
- A local repo `.foreman.db` was initialized and used to create/activate the
  `Review Phase 0 correctness` sprint and task through Foreman's CLI.
- Review Phase 0 fixes are implemented on `fix/review-phase0-correctness`:
  signal-created task events, merge-waiver CLI UUID generation, dashboard
  FK-safe human events, dashboard Run/Stop process registry, evidence caching
  invalidation, dashboard cancellation cleanup, and executor-path removal.
- Completion evidence is now defensive when a stored repo path cannot be
  inspected.
- Full unittest discovery passes locally: 500 tests.

## What is incomplete

- Simple Minimax M3 Claude Code calls work, and the direct Foreman
  `ClaudeCodeRunner` smoke completed. A delegated edit attempt through Claude
  Code hung without output and was not useful for implementation.

## Known regressions

- None introduced by the focused Phase 0 tests.

## Schema or migration notes

- No schema migration.

## Safe branch points

- Branch: `fix/review-phase0-correctness`
- Last clean validation point: after the full unittest discovery and
  py-compile checks listed in `docs/sprints/current.md`.
