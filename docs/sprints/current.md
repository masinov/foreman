# Current Sprint

- Sprint: `sprint-46-completion-truth-hardening`
- Status: in_progress
- Branch: none
- Started: 2026-04-22

## Goal

Harden Foreman's backend completion evaluation so developer completion markers
and reviewer approval alone are not enough to count implementation work as
done when the evidence is too weak for the task intent.

## Context and rationale

This sprint was chosen after checking the real Foreman runtime rather than the
legacy example supervisors.

What the code currently does:

- directed task selection simply executes the next runnable `todo` task in the
  active sprint
- developer completion is primarily accepted through completion-marker parsing
- reviewer approval is prompt-driven and sees acceptance criteria plus git
  context, but Foreman does not yet enforce a first-class backend evidence
  threshold for "this task was actually completed"

That means the real backend gap is completion-truth hardening, not selector
priority or legacy-script scope enforcement.

## Constraints

- backend only
- do not manually edit `.foreman.db`
- do not target `scripts/reviewed_claude.py` or `scripts/reviewed_codex.py`
  as product work
- preserve the existing development workflow shape:
  `develop -> review -> test -> merge -> done`

## Affected areas

- `foreman/orchestrator.py`
- `foreman/context.py`
- `roles/developer.toml`
- `roles/code_reviewer.toml`
- orchestrator and workflow regression tests
- repo-memory docs for the completion-truth contract

## Tasks

- [done] Completion evidence model in orchestrator (task-completion-evidence-model-in-orchestrator)
  - added `CompletionEvidence` and `build_completion_evidence()` in
    `foreman/orchestrator.py`
  - persist evidence to `tasks.completion_evidence_json` and emit
    `engine.completion_evidence` during supervisor merge finalization
  - repaired known local schema drift in `ForemanStore.initialize()` when the
    migration ledger and `tasks` table shape diverge around
    `completion_evidence_json`
  - raised shipped role and executor cost caps to `$1000.00` so native runs do
    not stop early under monthly-plan environments
- [todo] Backend guard for weak completions (task-backend-guard-for-weak-completions)
  - block or steer tasks when completion evidence is too weak for the stated
    task intent
- [todo] Reviewer prompt hardening with engine-produced evidence (task-reviewer-prompt-hardening-with-engine-produced-evidence)
  - feed explicit engine-produced evidence into the real Foreman review path
- [todo] False-positive completion regression coverage (task-false-positive-completion-regression-coverage)
  - prove docs-only or tests-only changes are not enough for implementation
    tasks when evidence does not support completion
- [todo] Completion truth contract docs (task-completion-truth-contract-docs)
  - document what Foreman now requires before a task can be considered done

## Validation

- `./venv/bin/python -m pytest tests/test_roles.py tests/test_executor.py -q`
- `./venv/bin/python -m pytest tests/test_migrations.py tests/test_orchestrator.py -q`
- `./venv/bin/python -m pytest tests/test_store.py tests/test_cli.py -q`
- `./venv/bin/python scripts/validate_repo_memory.py`
