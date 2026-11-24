# PR Summary: docs/adr-method-and-workflow-model

## Summary

- **ADR-0040:** the method the agents follow, how a project's repository is
  laid out, the rules for parallel work without collisions, and the build
  order.
- **ADR-0041:** the workflow and role model that the method runs on:
  - routes that may depend on a fixed list of facts;
  - step results as records;
  - rules across steps (freeze, caps);
  - a question to a person from any step;
  - roles with a write scope, a run scope, declared inputs and a declared
    output;
  - what each step is given, in three layers.
- Both were accepted by the owner on 2026-11-25, after the proposal's six
  open questions were settled one by one.
- The proposal records the owner's decisions and stays as the evidence.
- Backlog:
  - direction 7 is marked decided;
  - direction 5 links its changed-path rule to ADR-0041;
  - direction 8 records the owner's request for a deep survey of code maps
    (Aider's repo map and the like), for later.

## Scope

Docs only. Nothing is built; the build goes through Foreman in ADR-0040's
order.

## Files changed

- `docs/adr/ADR-0040-a-method-for-the-agents-and-a-repository-without-shared-logs.md` (new)
- `docs/adr/ADR-0041-workflows-route-on-facts-and-roles-declare-what-they-touch.md` (new)
- `docs/adr/README.md`
- `docs/proposals/2026-11-24-method-repository-parallel-work.md`
- `docs/sprints/backlog.md`
- `docs/ROADMAP.md`
- `docs/STATUS.md`
- this note.

## Migrations

None.

## Risks

None in code. The ADRs change how agents will be told to work, but only as
each build item lands. Until then `AGENTS.md` and the validator are
unchanged.

## Tests

- `scripts/validate_repo_memory.py`

## Acceptance criteria

- Every decision the owner made on 2026-11-25 is recorded in an ADR, with
  its reasoning traceable to the proposal.

## Follow-ups

- The next sprint: ADR-0040's build order, filed as tasks and run through
  Foreman.
