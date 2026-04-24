# PR Summary: docs/task-completion-truth-contract-docs

## Summary

Documents the backend completion truth contract for Foreman via ADR-0008,
defining what evidence the engine requires before an implementation task can
be considered done, how that evidence is scored and verdicted, and what
happens when evidence is insufficient.

## Scope

- Created `docs/adr/ADR-0008-completion-truth-contract.md` as a durable
  architectural decision
- Documented: evidence dimensions (4 components), scoring formula (0–100 pts),
  verdict thresholds (strong/adequate/weak/insufficient), insufficient-evidence
  scenarios, wiring into `finalize_supervisor_merge()`, and persistence via
  `completion_evidence_json`
- Updated `docs/sprints/current.md` to mark task as done
- Corrected the shipped workflow smoke test in `tests/test_cli.py` to expect
  `transitions=9` after the explicit `completion:conflict` workflow edge was
  added, which was the repeated failure keeping this docs task from closing

## Files changed

- `docs/adr/ADR-0008-completion-truth-contract.md` — new ADR
- `docs/sprints/current.md` — updated task status
- `tests/test_cli.py` — aligned workflow smoke-test expectation with the current
  shipped `development` workflow

## Migrations

- none (ADR only)

## Risks

- Low. This branch is still primarily documentation, but it now includes a
  one-line baseline test expectation fix so the docs task can validate cleanly
  against the current workflow graph.

## Tests

- `./venv/bin/python -m pytest tests/test_cli.py -q` — passed (`41 passed`)
- `./venv/bin/python -m pytest tests/test_orchestrator.py -q` — passed
  (`89 passed`)
- `scripts/validate_repo_memory.py` — passed
- `scripts/repo_validation.py` — passed
- `scripts/reviewed_claude.py` — passed (py_compile)
- `scripts/reviewed_codex.py` — passed (py_compile)

## Screenshots or output examples

- n/a

## Acceptance criteria satisfied

- [x] Document what evidence the engine requires before a task is considered done
- [x] Document how review consumes that evidence
- [x] Document what happens when evidence is insufficient
- [x] ADR follows existing ADR format and numbering

## Follow-ups

- Wire `weak`/`insufficient` verdict into the backend guard
  (`task-backend-guard-for-weak-completions`) once unblocked
- Harden reviewer prompts with engine-produced evidence
  (`task-reviewer-prompt-hardening-with-engine-produced-evidence`)
- Update `docs/specs/engine-design-v3.md` schema to reflect `CompletionEvidence`
  model
