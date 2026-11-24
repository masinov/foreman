# PR Summary: docs/proposal-method-repository-parallel

## Summary

- **A proposal for the owner to correct** (roadmap stage 3, moved before
  stage 2 on 2026-11-24): the method the agents follow, how a project's
  repository is organised, and the rules for parallel work without
  collisions.
- Written from four surveys: the methods already used in the company's
  projects, published practice on agentic coding, repository organisation,
  and parallel work. Sources are listed in the proposal.
- It ends with six open questions. Nothing is built until the owner has
  answered them; an ADR follows, then the build through Foreman.

## Scope

Docs only: a new `docs/proposals/` file and a pointer in the roadmap.

## Files changed

- `docs/proposals/2026-11-24-method-repository-parallel-work.md` (new)
- `docs/ROADMAP.md`: points to the proposal.
- this note.

## Migrations

None.

## Risks

None. Docs only; no behaviour changes.

## Tests

- `scripts/validate_repo_memory.py`

## Acceptance criteria

- The proposal is in the repository with its evidence, its build order and
  its open questions.

## Follow-ups

- The owner's corrections, then the ADR, then the build in the proposal's
  Part 4 order.
