# PR Summary: docs/integrate-review-plan

## Summary

- Integrates `docs/specs/review.md` into the repo's sprint flow.
- Records that `fix/backend-correctness-hardening` has been merged to
  `origin/main` at `b396fda`.
- Promotes the remaining review Phase 0 correctness fixes ahead of the older
  queued lease-recovery sprint.

## Scope

- Update status and current sprint docs.
- Add a review-roadmap section to the backlog.
- Add a checkpoint documenting what has been merged, what is already fixed,
  and what remains open from Phase 0.

## Files changed

- `docs/STATUS.md`
- `docs/sprints/current.md`
- `docs/sprints/backlog.md`
- `docs/checkpoints/2026-06-12-review-integration.md`
- `docs/prs/docs-integrate-review-plan.md`

## Migrations

- none

## Risks

- The local checkout has no `./venv`, so validation could not be run here.
- The existing SQLite queue may still contain the older
  `sprint-47-active-run-lease-and-heartbeat-recovery`; docs now say to defer
  it until Phase 0 is fixed.

## Tests

- attempted `./venv/bin/python scripts/validate_repo_memory.py` but
  `./venv/bin/python` does not exist in this checkout.
- attempted `./venv/bin/python -m py_compile ...` but `./venv/bin/python` does
  not exist in this checkout.
- attempted `./venv/bin/python -m unittest discover -s tests -v` but
  `./venv/bin/python` does not exist in this checkout.

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- Review findings are now sequenced into current sprint and backlog docs.
- Already-fixed review Phase 0 items are separated from still-open items.
- The next branch and sprint are named explicitly for a fresh agent.

## Follow-ups

- Create or restore `./venv` before the next implementation branch.
- Implement `fix/review-phase0-correctness`.
