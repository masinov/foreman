# PR Summary: feat/task-the-reviewer-s-verdict-is-a-record-per-criterion

## Summary

- Every shipped reviewer (code, security, triage, frontier) declares a
  `review_verdict` record: each acceptance criterion as verified, not verified or
  the reviewer's judgement with the evidence it checked, and findings with a
  severity. The prompts define S1 (broken, unsafe or data-losing), S2 (an
  acceptance criterion not met), S3 (should be fixed, does not block), S4 (a nit).
- Foreman checks the verdict against the decision: deny or steer needs an S1 or
  S2; approve needs none and every criterion verified or judgement. A mismatch
  makes the step's outcome `error` with the reason, after one corrective retry.
- S3 and S4 findings of an approving review stay in the run's record and show on
  the task page; they do not become tasks (decision in ADR-0042's amendment).
- The reviewer prompts no longer mention a judge model; they describe the
  completion evidence as it is (`foreman/engine/evidence.py`).
- The task page shows the verdict per criterion and the findings with severities
  in the review step's details.

## Scope

- ADR-0040 build item 2, second half, and ADR-0041 section 2.
- Not in scope: capping review rounds (ADR-0041 section 3); comparing the
  verdict's criteria with the task's own list; turning findings into tasks.

## Files changed

- `foreman/definitions/records.py` (`choice` field type), `roles.py` (a decision
  role may declare a record), `services/definition_forms.py` (keeps the record)
- `foreman/engine/verdict.py` (new), `output_contract.py` (reads the verdict,
  checks agreement, two corrections)
- `foreman/data/roles/{code,security,triage,frontier}_reviewer.toml`
- `frontend/src/pages/task/ReviewVerdict.jsx`, `ActivityTab.jsx`, `styles/task.css`
- `docs/adr/ADR-0042-...` (amendment), `docs/ARCHITECTURE.md`
- Tests: `tests/test_review_verdict.py` (new), `ReviewVerdict.test.jsx`,
  `TaskPage.test.jsx`; scripted reviewers elsewhere use `reviewed()` from
  `tests/engine_support.py`.

## Migrations

- None (`runs.record_json` from migration 30 holds the verdict).

## Risks

- A shipped reviewer that omits a valid verdict gets one correction, then the
  step is an `error`. A project's own reviewer role in the database declares no
  record and is unaffected.
- The verdict's criteria are not compared with the task's list: an approval with
  no criteria entries passes.

## Tests

- `./venv/bin/python -m pytest tests -n auto -q`; `npx vitest run` and
  `npx eslint . --max-warnings 0` in `frontend/`.

## Screenshots or output examples

- n/a: not opened in a browser; the frontend tests cover the page.

## Acceptance criteria satisfied

- Reviewers declare the record and define S1 to S4: `ShippedRolesTests`.
- Disagreeing verdicts are `error` with the reason, each case: `AgreementTests`.
- S3 and S4 kept and shown on approval: `AgreementTests`, `ReviewVerdict.test.jsx`.
- No judge model in a shipped prompt: `ShippedRolesTests`.
- Task page shows the verdict and findings: `ReviewVerdict.test.jsx`, `TaskPage.test.jsx`.

## Follow-ups

- Compare the verdict's criteria with the task's acceptance criteria.
- Cap review rounds (ADR-0041 section 3).
