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

## Files changed

- `docs/adr/ADR-0008-completion-truth-contract.md` — new ADR
- `docs/sprints/current.md` — updated task status

## Migrations

- none (ADR only)

## Risks

- None. Document only; no implementation change.

## Tests

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