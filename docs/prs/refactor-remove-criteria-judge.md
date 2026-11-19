# PR Summary: refactor/remove-criteria-judge

## Summary

- Sprint 60, decision 1: the criteria judge is removed (ADR-0010
  amendment). An approving code review of the branch head covers a task's
  acceptance criteria.

## Scope

- Deleted: `foreman/engine/judge.py`, `tests/test_judge.py`, the settings
  `judge_base_url`, `judge_model`, `judge_api_key_env`,
  `judge_max_diff_chars`, and `CompletionEvidence.judged_by` (and its place
  in the API, the digest and the task page).
- `engine/evidence.py`: each criterion is `covered` when code review
  approved the head commit, with that commit as its evidence, and
  `unverified` otherwise. The proof is pending until then, as before.
  `truncate_diff`, which the reviewer's diff still uses, moved here.
- The merge waiver for partly met criteria (`incomplete_criteria`) is gone,
  since nothing produces that failure any more. The CLI's waiver choices
  come from `MERGE_WAIVER_TYPES`.
- Task page: "Covered by review" and "Not reviewed yet"; "2 acceptance
  criteria, covered by the approving review". The settings page has no
  judge rows.
- Evidence recorded by the judge still loads: `from_mapping` skips
  `judged_by`, and the old statuses keep their words.
- Docs: README, MANUAL, ARCHITECTURE, STATUS, ADR-0010, ADR-0032, the
  backlog's sprint-workflow direction (global roles at the end of a sprint).

## Migrations

- none. Projects that stored judge settings keep the keys. Nothing reads
  them.

## Tests

- new evidence tests: an approving review of the head covers the criteria;
  an approval of an older commit does not; they wait for a review; old
  judge evidence loads. Updated settings, safety, dashboard, task-read and
  prompt tests. Frontend 451. Full Python suite.
