"""Response models for a task's changes, checks and runs (sprint 58).

Facts are what the engine measured; claims are what an agent reported
(ADR-0018). The two never share a list, so a screen can say which is which.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

#: Most characters of one file's diff the API returns before truncating.
DIFF_CAP_CHARS = 200_000
#: Most characters of a run's prompt, and of its transcript, one response holds.
OUTPUT_CAP_CHARS = 200_000


class CommitRef(BaseModel):
    """One side of a comparison: a branch and the commit it was at."""

    branch: str
    sha: str | None = None


class FileChangeItem(BaseModel):
    path: str
    status: Literal["added", "modified", "deleted", "renamed"]
    added: int
    deleted: int
    binary: bool = False
    #: Where a renamed file came from.
    old_path: str | None = None


class ChangeTotals(BaseModel):
    files: int
    added: int
    deleted: int


class TaskChanges(BaseModel):
    """``GET /tasks/{id}/changes``."""

    task_id: str
    files: list[FileChangeItem]
    totals: ChangeTotals
    #: The commit the task branch left the default branch at, and the branch
    #: head: the two commits the diff compares. Null when there is no branch.
    base: CommitRef | None = None
    head: CommitRef | None = None
    #: Why ``files`` is empty when the task has no comparable branch.
    empty_reason: str | None = None
    #: The commit the task landed as, once merged; the files are then what it landed.
    merged_as: str | None = None


class FileDiff(BaseModel):
    """``GET /tasks/{id}/changes/diff``."""

    task_id: str
    path: str
    status: str
    old_path: str | None = None
    diff: str
    #: True when the diff was longer than ``cap_chars`` and was cut.
    truncated: bool
    cap_chars: int
    total_chars: int


class TaskDocument(BaseModel):
    """``GET /tasks/{id}/documents``: a document the task rests on, as it was
    at the commit it was named at."""

    task_id: str
    path: str
    heading: str
    commit: str
    text: str
    truncated: bool
    cap_chars: int
    total_chars: int


class TaskDocumentChange(BaseModel):
    """``GET /tasks/{id}/documents/diff``: what changed in a document the task
    rests on, from the commit it was named at to the merge that changed it."""

    task_id: str
    path: str
    from_commit: str
    to_commit: str
    task_key: str | None
    diff: str
    truncated: bool
    cap_chars: int
    total_chars: int


class FailedTest(BaseModel):
    """A test that failed: its suite (class or file) and its name."""

    suite: str = ""
    name: str = ""


class TestCounts(BaseModel):
    """How many tests ran and how they ended, from the test command's JUnit reports."""

    __test__ = False  # not a test class, whatever pytest thinks of the name

    tests: int
    passed: int
    failed: int
    skipped: int
    #: The failed tests the report named, at most 50; ``failed`` is how many there were.
    failed_tests: list[FailedTest] = []


def test_counts(report: Any) -> TestCounts | None:
    """The counts a test run recorded, or None when it recorded none."""

    if not isinstance(report, dict):
        return None
    try:
        return TestCounts(
            tests=int(report["tests"]),
            passed=int(report.get("passed", 0)),
            failed=int(report.get("failed", 0)),
            skipped=int(report.get("skipped", 0)),
            failed_tests=[
                FailedTest(suite=str(item.get("suite") or ""), name=str(item.get("name") or ""))
                for item in report.get("failed_tests") or []
                if isinstance(item, dict)
            ],
        )
    except (KeyError, TypeError, ValueError):
        return None


class TestsFact(BaseModel):
    __test__ = False  # not a test class, whatever pytest thinks of the name

    status: Literal["passed", "failed", "not_run", "stale"]
    exit_code: int | None = None
    duration_seconds: float | None = None
    command: str | None = None
    #: The last line of the test output, which is where runners print totals.
    result_line: str | None = None
    #: How many tests ran, when the test command wrote a report.
    counts: TestCounts | None = None
    #: The commit the tests ran on, and the branch head now.
    commit: str | None = None
    head_sha: str | None = None


class BranchFact(BaseModel):
    name: str | None = None
    default_branch: str
    ahead: int | None = None
    behind: int | None = None
    #: ``current`` (nothing new on the default branch), ``behind``,
    #: ``merged`` (it is in the default branch, as ``merged_as``), or
    #: ``no_branch`` when there is nothing to compare.
    state: Literal["current", "behind", "merged", "no_branch"]
    merged_as: str | None = None


class SizeFact(BaseModel):
    files: int
    added: int
    deleted: int


class ChecksFacts(BaseModel):
    tests: TestsFact
    branch: BranchFact
    size: SizeFact


class ReviewClaim(BaseModel):
    kind: Literal["code", "security"] | str
    decision: str | None = None
    model: str | None = None
    role_id: str | None = None
    duration_seconds: float | None = None
    commit: str | None = None
    summary: str | None = None
    run_id: str | None = None
    #: Whether ``commit`` is still the branch head.
    current: bool | None = None


class CriterionClaim(BaseModel):
    criterion: str
    status: str
    evidence: str | None = None


class ChecksClaims(BaseModel):
    reviews: list[ReviewClaim]
    criteria: list[CriterionClaim]


class EvidenceFile(BaseModel):
    """A file an agent attached as evidence. Phase 5 captures them; until
    then ``evidence_files`` is always empty."""

    name: str
    path: str
    media_type: str | None = None
    size_bytes: int | None = None
    run_id: str | None = None
    captured_at: str | None = None


class TaskChecks(BaseModel):
    """``GET /tasks/{id}/checks``."""

    task_id: str
    proof_status: str | None = None
    #: What the evidence says is still missing.
    outstanding: list[str]
    built_at: str | None = None
    facts: ChecksFacts
    claims: ChecksClaims
    evidence_files: list[EvidenceFile]


class RunItem(BaseModel):
    id: str
    step: str
    role_id: str
    model: str | None = None
    backend: str
    status: str
    outcome: str | None = None
    #: Why it ended as it did, in the run's own words: a reviewer's reason for
    #: sending a task back, a failure's message, how a gate was decided.
    outcome_detail: str | None = None
    commit_sha: str | None = None
    #: The record the step's role declared and the step returned (ADR-0042):
    #: its ``kind`` and its ``fields``; None for a role that declares none.
    record: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    cost_usd: float
    tokens: int
    token_usage: dict[str, int]
    #: Which attempt at its step this run was: 1 for the first.
    attempt: int = 1
    #: The commit the step was about: the one it made or reviewed, the one
    #: the tests ran on, or the merge commit.
    step_commit: str | None = None
    #: How many tests a test step ran, when the test command wrote a report.
    tests: TestCounts | None = None


class TaskRuns(BaseModel):
    """``GET /tasks/{id}/runs``, newest first: the task's own steps.

    Left out: the step that closes a task after its merge, and the
    engine's records that do not name the task (``domain.activity``).
    """

    runs: list[RunItem]
    total: int
    limit: int
    offset: int


class SprintActivityItem(BaseModel):
    """One row of a sprint's activity: a run of one of its tasks, or what a person did to one by hand."""

    #: ``run``, or ``event`` for what a person did by hand.
    source: str
    id: str
    task_id: str
    task_key: str | None = None
    task_title: str
    at: str | None = None
    step: str | None = None
    role_id: str | None = None
    backend: str | None = None
    model: str | None = None
    status: str | None = None
    #: A run's outcome; for a person's act, ``closed``, ``cancelled`` or ``unblocked``.
    outcome: str | None = None
    #: Why: a reviewer's reason, a failure's message, a person's reason.
    outcome_detail: str | None = None
    commit_sha: str | None = None
    duration_ms: int | None = None
    cost_usd: float = 0.0
    #: Who, for a person's act.
    actor: str | None = None
    #: Who did it, as the By filter names them: ``user``, ``foreman`` or an agent's role id.
    who: str | None = None


class SprintActivity(BaseModel):
    """``GET /sprints/{id}/activity``: what happened to the sprint's tasks, newest first."""

    items: list[SprintActivityItem]
    total: int
    limit: int
    offset: int
    #: Every ``who`` in the sprint's activity, whatever the filters: what the By filter offers.
    who: list[str] = []


class TranscriptEntry(BaseModel):
    at: str
    kind: str
    stream: str | None = None
    #: Text to show as it is: a line of raw or test output. Empty for an
    #: event whose facts are in ``data``.
    text: str
    #: What the event recorded, for the page to say in words. Long strings
    #: are clipped. None for raw and test output lines.
    data: dict[str, Any] | None = None


class SessionFact(BaseModel):
    """Whether an agent run started a session or resumed an earlier run's.

    Two runs with the same stored session id are one session.
    """

    #: The earlier run of the same role on the task whose session this one
    #: resumed; None for a new session.
    continued_from: str | None = None
    #: That run's attempt at its step.
    continued_attempt: int | None = None


class StepFile(BaseModel):
    path: str
    #: None for a binary file.
    added: int | None = None
    removed: int | None = None
    status: Literal["added", "modified", "deleted", "renamed"] = "modified"


class ChangedAgainst(BaseModel):
    """What a step's changes are counted against.

    ``attempt``: the commit an earlier run of the task left (``run_id``,
    ``attempt``); ``default_branch``: a commit on the default branch, where the
    branch began; ``commit``: only the commit.
    """

    kind: Literal["attempt", "default_branch", "commit"]
    sha: str
    run_id: str | None = None
    attempt: int | None = None
    branch: str | None = None


class StepReads(BaseModel):
    """How many reading tool calls an agent step made before its first change (ADR-0041)."""

    reads: int
    #: False when the step changed nothing: ``reads`` is then all of its reads.
    edited: bool


class StepChanges(BaseModel):
    """What an agent step changed on the task branch, as recorded when it ended."""

    from_sha: str
    to_sha: str
    files: list[StepFile]
    #: How many files changed; ``files`` is capped.
    files_total: int
    added: int
    removed: int
    against: ChangedAgainst


class MergeCommit(BaseModel):
    sha: str
    subject: str = ""


class MergeChanges(BaseModel):
    files: list[StepFile]
    files_total: int
    added: int
    removed: int


class MergeFacts(BaseModel):
    """What a landed merge brought in, as recorded when it landed. Each field is
    present only when it was recorded."""

    target_before: str | None = None
    commits: list[MergeCommit] | None = None
    commits_total: int | None = None
    changes: MergeChanges | None = None


class RunOutput(BaseModel):
    """``GET /runs/{id}/output``."""

    run_id: str
    task_id: str
    prompt: str | None = None
    prompt_truncated: bool
    transcript: list[TranscriptEntry]
    #: True when later entries were dropped to stay under ``cap_chars``.
    transcript_truncated: bool
    total_entries: int
    #: How many lines of the agent's raw stream the run recorded. They are in
    #: ``transcript`` only when asked for with ``?raw=true``.
    raw_entries: int = 0
    raw_included: bool = False
    cap_chars: int
    #: Agent runs only: a new session, or the earlier run's it resumed.
    session: SessionFact | None = None
    #: What the step changed on the branch, when it recorded that.
    changes: StepChanges | None = None
    #: The reads the step made before its first change, when it recorded them.
    reads: StepReads | None = None
    #: A landed merge's facts, when it recorded them.
    merge: MergeFacts | None = None
    #: A review's verdict: the commands its criteria cite under ``ran`` that
    #: Foreman found among the commands the run made (ADR-0041 section 2).
    confirmed_commands: list[str] = []
