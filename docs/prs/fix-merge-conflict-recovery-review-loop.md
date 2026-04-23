## Summary

Fix Foreman's merge-conflict recovery loop for long-lived task branches.

Merge conflicts are now a first-class workflow outcome instead of a generic
merge failure, and conflict-resolution passes keep the normal
`develop -> review -> test -> merge` shape so the developer's conflict
resolution is reviewed again before the task can merge.

## Scope

- detect merge conflicts explicitly in `foreman/git.py`
- carry merge-conflict guidance back into `develop`
- refresh stale existing task branches against current `main` before a
  conflict-recovery develop pass when that refresh is clean
- add regression coverage for both the conflict-review loop and branch refresh

## Files changed

- `foreman/git.py`
- `foreman/builtins.py`
- `foreman/orchestrator.py`
- `workflows/development.toml`
- `tests/test_orchestrator.py`
- `docs/STATUS.md`
- `docs/sprints/current.md`

## Risks

- automatic base-branch refresh during conflict recovery creates a merge commit
  on the task branch when the refresh is clean
- generic non-conflict merge failures still route back through the existing
  `completion:failure -> develop` edge

## Tests

- targeted orchestrator conflict-recovery regressions
- full `tests/test_orchestrator.py`

## Acceptance criteria satisfied

- merge conflicts are no longer indistinguishable from generic merge failures
- conflict-resolution returns to `develop` with explicit guidance
- the next developer pass is re-reviewed before merge
- stale existing task branches can be refreshed against latest `main` instead
  of being silently reused unchanged

## Follow-ups

- consider narrowing generic `merge completion:failure -> develop` so
  deterministic non-conflict merge failures do not spin the loop indefinitely
- consider a dedicated persisted flag for "conflict resolution required" if the
  carried-output heuristic becomes too implicit
