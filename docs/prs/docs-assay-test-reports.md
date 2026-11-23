# PR Summary: docs/assay-test-reports

## Summary

- `docs/STATUS.md` records Assay's state after 2026-11-23.
  - Its `main` is pushed to its GitLab at `d64947e`, with sprints 1 and 2
    (owner: "Update Assay and push").
  - Its tests write JUnit reports, so its test step counts them (ADR-0035).
  - Its engine and API are down since the reboot.
- In Assay itself (pushed):
  - `requirements.txt` gains unittest-xml-reporting;
  - `tests/test_serve.py` pins the API host, as it pins the port. The
    operator's `.env` had bound the API to the LAN address since
    2026-11-20, so the launcher test failed.

## Scope

- Docs only, in Foreman.

## Files changed

- `docs/STATUS.md`

## Migrations

- None.

## Risks

- None.

## Tests

- Assay's 186 tests, run with `python -m xmlrunner`. The report was read
  back as 186.

## Acceptance criteria satisfied

- `docs/STATUS.md` says where Assay is.

## Follow-ups

- Restart Assay's engine and API when the owner asks.
