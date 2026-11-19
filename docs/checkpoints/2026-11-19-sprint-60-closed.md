# Checkpoint: sprint 60 closed (2026-11-19)

Sprint 60, "what is there works and makes sense", is complete on `main`.
Its slices are in `docs/sprints/archive/sprint-60-what-is-there-works.md`.

## What works

- Every screen and control was audited on a copy of the database (slice 6)
  and the findings fixed or decided by the owner (slices 7, 15 to 20).
- A project has roles and workflows of its own, kept in the database and
  edited from the dashboard or `foreman role` / `foreman workflow`
  (ADR-0024). The workspace defaults are edited the same way.
- Planning is the manager's: "Plan this sprint" and "Split into smaller
  tasks" end in a proposal (slice 5). The architect role is gone.
- Two supervised runs of the engine against real agents (slices 1 and 9):
  plan, send-back with a note, a merge conflict reconciled, two tasks at
  once, push after merge.
- Assay, the first outside project, ran its first sprint through Foreman,
  and the six Foreman faults it showed are fixed (slice 12, ADR-0031).
- The backend is in layers held by `lint-imports` in CI, and every change
  goes through `foreman.mutations` (slice 14, ADR-0032).
- The owner's sprint 60 decisions: the test command is set from the
  dashboard; a note is for the developer and reviewers see it as context
  (ADR-0033); the criteria judge is removed; "Finish sprints: A person /
  Foreman"; a finished sprint can be reopened; Decline is the one way out of
  the backlog.
- Validation at close: 1570 Python tests passing, frontend tests, ESLint,
  `ruff check`, `lint-imports` and the repository validator passing, CI
  green at `b03b792`.

## What is incomplete

- Slice 10 (the manager chat off the machine) is dropped. The owner and
  Claude reopened what the manager is for; the agreed design is stage 2 of
  `docs/ROADMAP.md`.
- Seven functions are over 200 lines and the CLI reads data its own way
  (ADR-0032). Both are in sprint 61.
- The engine has not run unattended for a whole sprint since sprint 58.
- An agent process runs as the engine's user with a shell and the network.

## Known regressions

- None known.

## Schema or migration notes

- Schema version 28. No migration in the closing branch.

## Safe branch points

- `main` at the merge of `docs/close-sprint-60-and-roadmap`.

Next: sprint 61, stage 1 of the roadmap (the core proven).
