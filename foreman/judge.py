"""Acceptance-criteria judging for completion evidence.

Two ways to turn a task's acceptance criteria into a pass/partial/fail
checklist:

1. the zero-config keyword heuristic (``heuristic_checklist``), kept as the
   default so the engine never depends on a network call, and
2. an opt-in cheap-model LLM judge (``judge_criteria``) that issues a single
   direct HTTP call to an Anthropic-compatible Messages endpoint.

The judge is strictly opt-in: when ``judge_base_url`` / ``judge_model`` project
settings are unset, or on any error, ``judge_criteria`` returns the heuristic
result so evidence building can never crash the workflow.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CriteriaJudgment:
    """The per-criterion checklist plus the judge that produced it."""

    checklist: tuple[dict[str, str], ...]  # {criterion, status, evidence}
    judged_by: str  # model id, or "heuristic"


# ---------------------------------------------------------------------------
# Heuristic fallback (the single owner of the keyword logic)
# ---------------------------------------------------------------------------

def _criterion_addressed(
    criterion: str,
    output_text: str,
    changed_files: tuple[str, ...],
) -> tuple[bool, bool]:
    """Return (addressed, partially_addressed) for one acceptance criterion.

    A criterion is addressed when the output text or changed files contain
    substantive references to its key terms. Partial coverage is when only a
    subset of the relevant terms appear.
    """

    key_terms = [
        t.strip().rstrip(".,;:!?()[]{}'\"").strip()
        for t in re.findall(r"\b\w{4,}\b", criterion.lower())
    ]
    if not key_terms:
        return (False, False)

    matching_terms = sum(
        1
        for term in key_terms
        if term in output_text or any(term in f.lower() for f in changed_files)
    )
    coverage_ratio = matching_terms / len(key_terms)

    if coverage_ratio >= 0.7:
        return (True, False)
    if coverage_ratio >= 0.3:
        return (False, True)
    return (False, False)


def heuristic_checklist(
    criteria: list[str],
    output_text: str,
    changed_files: tuple[str, ...],
) -> tuple[dict[str, str], ...]:
    """Build the keyword-overlap criteria checklist (zero-config fallback)."""

    checklist: list[dict[str, str]] = []
    for criterion in criteria:
        addressed, partial = _criterion_addressed(criterion, output_text, changed_files)
        if addressed:
            status = "passed"
            evidence = "Addressed in agent output or changed files."
        elif partial:
            status = "partial"
            evidence = "Partially addressed — some key terms missing."
        else:
            status = "unknown"
            evidence = "No substantive coverage found in output or changed files."
        checklist.append(
            {"criterion": criterion, "status": status, "evidence": evidence}
        )
    return tuple(checklist)


# ---------------------------------------------------------------------------
# Diff truncation
# ---------------------------------------------------------------------------

def truncate_diff(diff_text: str, max_chars: int) -> str:
    """Head+tail truncate a diff, keeping the first 70% and last 30%."""

    if max_chars <= 0 or len(diff_text) <= max_chars:
        return diff_text
    head_len = int(max_chars * 0.7)
    tail_len = max_chars - head_len
    removed = len(diff_text) - max_chars
    return (
        diff_text[:head_len]
        + f"\n[...truncated {removed} chars...]\n"
        + diff_text[len(diff_text) - tail_len:]
    )


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = (
    "You are a strict software acceptance-criteria judge. Given a unified diff, "
    "a short developer summary, and a list of acceptance criteria, decide for "
    "each criterion whether the change satisfies it. Respond with ONLY a JSON "
    "array, no prose, of objects shaped exactly: "
    '[{"criterion": "<verbatim criterion>", "status": "passed|partial|failed", '
    '"evidence": "<one line>"}]. Use \"passed\" only when the diff clearly '
    "satisfies the criterion, \"partial\" when partially satisfied, and "
    '"failed" otherwise.'
)


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        # Drop the opening fence (optionally ```json) and the trailing fence.
        stripped = re.sub(r"^```[a-zA-Z0-9_]*\s*", "", stripped)
        if stripped.endswith("```"):
            stripped = stripped[: -3]
    return stripped.strip()


def _parse_checklist(text: str, criteria: list[str]) -> tuple[dict[str, str], ...]:
    """Parse the model JSON array into a normalized checklist, or raise."""

    data = json.loads(_strip_json_fence(text))
    if not isinstance(data, list):
        raise ValueError("Judge response was not a JSON array.")
    valid = {"passed", "partial", "failed"}
    checklist: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("Judge array item was not an object.")
        status = str(item.get("status", "")).strip().lower()
        if status not in valid:
            raise ValueError(f"Invalid judge status: {item.get('status')!r}.")
        checklist.append(
            {
                "criterion": str(item.get("criterion", "")).strip(),
                "status": status,
                "evidence": str(item.get("evidence", "")).strip()[:300],
            }
        )
    if len(checklist) != len(criteria):
        raise ValueError(
            f"Judge returned {len(checklist)} items for {len(criteria)} criteria."
        )
    return tuple(checklist)


def judge_criteria(
    *,
    criteria: list[str],
    diff_text: str,
    agent_summary: str,
    changed_files: tuple[str, ...] = (),
    settings: Mapping[str, Any],
    timeout_seconds: float = 60.0,
) -> CriteriaJudgment:
    """Judge acceptance criteria, preferring the configured LLM, else heuristic.

    Falls back to ``heuristic_checklist`` when the judge is not configured or on
    any HTTP / timeout / parse error, so evidence building never crashes.
    """

    if not criteria:
        return CriteriaJudgment(checklist=(), judged_by="heuristic")

    base_url = str(settings.get("judge_base_url") or "").strip()
    model = str(settings.get("judge_model") or "").strip()

    def _heuristic() -> CriteriaJudgment:
        return CriteriaJudgment(
            checklist=heuristic_checklist(criteria, agent_summary, changed_files),
            judged_by="heuristic",
        )

    if not base_url or not model:
        return _heuristic()

    max_diff = settings.get("judge_max_diff_chars", 24000)
    try:
        max_diff = int(max_diff)
    except (TypeError, ValueError):
        max_diff = 24000
    capped_diff = truncate_diff(diff_text, max_diff)

    api_key_env = str(settings.get("judge_api_key_env") or "").strip()
    api_key = ""
    if api_key_env:
        import os

        api_key = os.environ.get(api_key_env, "")

    user_block = (
        "## Acceptance criteria\n"
        + "\n".join(f"- {c}" for c in criteria)
        + "\n\n## Developer summary\n"
        + (agent_summary or "(none)")
        + "\n\n## Unified diff\n"
        + (capped_diff or "(empty)")
    )

    try:
        import httpx

        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if api_key:
            headers["x-api-key"] = api_key
        response = httpx.post(
            base_url.rstrip("/") + "/v1/messages",
            headers=headers,
            json={
                "model": model,
                "max_tokens": 1024,
                "system": _JUDGE_SYSTEM,
                "messages": [{"role": "user", "content": user_block}],
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        # Anthropic Messages API: content is a list of blocks; concat text.
        text_parts = [
            str(block.get("text", ""))
            for block in body.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "".join(text_parts) if text_parts else ""
        checklist = _parse_checklist(text, criteria)
        return CriteriaJudgment(checklist=checklist, judged_by=model)
    except Exception:  # noqa: BLE001 - any failure must fall back to heuristic
        return _heuristic()
