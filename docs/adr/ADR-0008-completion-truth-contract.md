# ADR-0008: Completion Truth Contract

- Status: accepted
- Date: 2026-04-23
- Sprint: sprint-46-completion-truth-hardening

## Context

Foreman's orchestrator relies on two signals to mark a task done: the
developer's `TASK_COMPLETE` marker and the reviewer's merge approval. Sprint-46
identified that neither signal is sufficient on its own for implementation-oriented
tasks — a developer can mark a task done without writing code, and a reviewer
can approve a merge without verifying that the implementation actually satisfies
the task's intent.

The risk is false-positive completions: tasks that advance to `done` without
adequate evidence, eroding trust in the sprint record and making regression
harder to detect.

This ADR defines the backend **completion truth contract**: what evidence the
engine must gather before a task can be considered done, how that evidence is
scored, and what happens when the evidence is insufficient.

## Decision

### 1. Evidence is mandatory for all implementation tasks

For every task where `task_type` is `implementation` (or is not `docs`, `research`,
or `review`), the orchestrator must gather completion evidence before the task
can transition to `done`.

Evidence is not required for `docs`, `research`, and `review` task types, where
textual output is the primary deliverable.

### 2. The CompletionEvidence model

The `CompletionEvidence` dataclass (`foreman/models.py`) bundles four evidence
dimensions:

| Field | Description |
|---|---|
| `criteria_count` | Number of acceptance criteria defined |
| `criteria_addressed` | Criteria fully addressed by evidence |
| `criteria_partially_addressed` | Criteria partially addressed |
| `changed_files` | Files modified on the task branch (from git diff) |
| `diff_context_lines` | Total lines in the diff (proxy for implementation breadth) |
| `agent_outputs` | Structured snippets from agent run logs |
| `builtin_test_passed` | Whether the built-in test suite passed |
| `builtin_test_detail` | Test output text |
| `score` | 0–100 composite score (see §3) |
| `score_breakdown` | Human-readable point breakdown |
| `verdict` | One of `strong`, `adequate`, `weak`, `insufficient` |
| `verdict_reasons` | Plain-language reasons for the verdict |

### 3. Scoring: four components, 100 points max

The evidence score is computed as the sum of four independent components:

| Component | Max points | Basis |
|---|---|---|
| Acceptance criteria coverage | 40 | Share of criteria fully or partially addressed |
| Code change breadth | 20 | Files changed on the branch (5 pts/file, cap at 20) |
| Diff context | 10 | Total lines in the diff (0.5 pts/line, cap at 10) |
| Built-in test result | 30 | Passed = 30, failed/absent = 0 |

The built-in test component is binary: a passing test earns the full 30 points;
a failing test earns 0. An absent test result earns 0. This means a passing test
is a meaningful signal but is not sufficient on its own — it can only add up to
30 of the 100 required points.

### 4. Verdict thresholds

The verdict is derived from the score and the criteria-addressed count:

| Verdict | Condition |
|---|---|
| `strong` | score ≥ 75 AND all criteria addressed |
| `adequate` | score ≥ 60 AND at least half of criteria addressed |
| `weak` | score ≥ 40 |
| `insufficient` | score < 40 |

Verdicts below `adequate` cannot be overridden by developer markers or reviewer
approval alone. The engine must surface the weak/insufficient verdict before the
task advances.

### 5. Acceptance criterion coverage detection

A criterion is **addressed** when ≥ 70% of its key terms appear in either the
agent output text or the names of the changed files.

A criterion is **partially addressed** when ≥ 30% but < 70% of its key terms
appear.

Key terms are extracted as all words in the criterion with 4 or more characters,
case-insensitively.

This is a heuristic — it is not a semantic proof. It is designed to detect
absence of evidence, not presence of correctness.

### 6. Evidence assembly: build_completion_evidence()

The orchestrator's `build_completion_evidence()` method (`foreman/orchestrator.py`)
gathers evidence in this order:

1. Run list from the store filtered to `completed | failed | killed | timeout` status
2. Git diff against the target branch (`{target_branch}...{branch_name}`, falling
   back to two-dot diff if the three-dot diff fails)
3. Test events from the store (`engine.test_run`, `engine.test_output`)
4. Acceptance criteria from the task record, split on newlines

The method returns `None` when there are no completed runs for the task.

### 7. Insufficient evidence scenarios

The following scenarios must produce `weak` or `insufficient` verdicts:

| Scenario | Minimum verdict |
|---|---|
| Docs-only changes, no code | `insufficient` |
| Tests-only changes, no implementation | `weak` or `insufficient` |
| Approval without any code changes | `insufficient` |
| Passed tests but zero criteria addressed and no files changed | `weak` |
| Passing tests with no implementation behind them | `weak` (not `adequate`) |

The regression suite (`tests/test_orchestrator.py`, `CompletionEvidenceTests`)
encodes these expectations as assertions, not as comments. If these scenarios
produce `adequate` or `strong` verdicts, the regression tests fail.

### 8. Persistence

`CompletionEvidence` is serialized to JSON and stored in the `tasks` table
column `completion_evidence_json`. It is persisted:

- When the task transitions to `done`
- At the point `finalize_supervisor_merge()` is called

The schema migration adds the column as:

```sql
ALTER TABLE tasks ADD COLUMN completion_evidence_json TEXT NOT NULL DEFAULT '';
```

### 9. Wiring into the orchestrator

`build_completion_evidence()` is a method on `ForemanOrchestrator`
(`foreman/orchestrator.py`). `finalize_supervisor_merge()` is the canonical
orchestrator entry point at which a supervisor-approved merge transitions a
task to `done`; the evidence wiring at that point is pending the backend guard
(task-004). Until the guard lands, evidence is built and persisted via the
same method when called directly by the guard implementation.

The `CompletionEvidence` record is stored on the task via
`completion_evidence_json` before the status transition is persisted. This
means every `done` task has an evidence record in the database, enabling
post-hoc audit and regression analysis.

## Consequences

- Developer `TASK_COMPLETE` markers and reviewer approval are no longer
  sufficient, alone, to mark an implementation task done. Both signals remain
  necessary but the engine must also see sufficient evidence.
- The verdict is advisory until the backend guard (task-004) is implemented.
  The evidence is gathered and persisted, but the orchestrator does not yet
  block task completion on a `weak` verdict. The guard task adds the blocking
  behavior.
- The evidence model does not prove correctness — it detects absence of
  evidence. A task can earn a strong verdict through coverage without having
  a correct implementation. Human review remains the final authority.
- The scoring thresholds are deliberate: a score of 75 with all criteria
  addressed is the minimum for `strong`. This prevents a high score with
  partial criteria coverage from claiming strong completion.
- The binary built-in test component means tests are a safety signal, not a
  primary path to a high verdict. A passing test earns 30 points; the remaining
  70 must come from criteria coverage and code change evidence.

## Open questions

- Should the backend guard apply a hard block for `insufficient` verdicts while
  surfacing a warning for `weak`? Decision deferred to task-004.
- Should evidence gathering be retried on transient failures (e.g. a failing
  git command that succeeds on retry)? Not in scope for v1.
- Should non-implementation tasks (docs, research, review) have a separate
  evidence model or is the current `None` return correct? Deferred.

## References

- `foreman/models.py` — `CompletionEvidence` dataclass
- `foreman/orchestrator.py` — `build_completion_evidence()`, `_score_evidence()`,
  `_verdict_from_score()`, `finalize_supervisor_merge()`
- `foreman/store.py` — `_serialize_evidence()`, `_row_to_task()`, `save_task()`
- `foreman/migrations.py` — `completion_evidence_json` column migration
- `tests/test_orchestrator.py` — `CompletionEvidenceTests` (14 regression cases)
- `docs/sprints/current.md` — sprint-46 definition
- `docs/adr/ADR-0001-runner-session-backend-contract.md`