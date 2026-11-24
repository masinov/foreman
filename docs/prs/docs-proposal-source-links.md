# PR Summary: docs/proposal-source-links

## Summary

- Two source links in the method proposal were wrong: SWE-agent's
  interface page had moved (404), and Uber's blog page refuses automated
  requests. They now point to the SWE-agent docs and to the paper's DOI.
  The other 35 links were checked and resolve.

## Scope

Docs only.

## Files changed

- `docs/proposals/2026-11-24-method-repository-parallel-work.md`
- this note.

## Migrations

None.

## Risks

None.

## Tests

- `scripts/validate_repo_memory.py`; every link fetched with curl.

## Acceptance criteria

- Every source link in the proposal resolves.

## Follow-ups

- None.
