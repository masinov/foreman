"""Response models for a task's changes, checks and runs (sprint 58).

Facts are what the engine measured; claims are what an agent reported
(ADR-0018). The two never share a list, so a screen can say which is which.
"""

from __future__ import annotations

from typing import Literal

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


class TestsFact(BaseModel):
    __test__ = False  # not a test class, whatever pytest thinks of the name

    status: Literal["passed", "failed", "not_run", "stale"]
    exit_code: int | None = None
    duration_seconds: float | None = None
    command: str | None = None
    #: The last line of the test output, which is where runners print totals.
    result_line: str | None = None
    #: The commit the tests ran on, and the branch head now.
    commit: str | None = None
    head_sha: str | None = None


class BranchFact(BaseModel):
    name: str | None = None
    default_branch: str
    ahead: int | None = None
    behind: int | None = None
    #: ``current`` (nothing new on the default branch), ``behind``, or
    #: ``no_branch`` when there is nothing to compare.
    state: Literal["current", "behind", "no_branch"]


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
    #: ``none`` when no judge model looked at the criteria.
    judged_by: str
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
    commit_sha: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    cost_usd: float
    tokens: int
    token_usage: dict[str, int]


class TaskRuns(BaseModel):
    """``GET /tasks/{id}/runs``, newest first."""

    runs: list[RunItem]
    total: int
    limit: int
    offset: int


class TranscriptEntry(BaseModel):
    at: str
    kind: str
    stream: str | None = None
    text: str


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
    cap_chars: int
