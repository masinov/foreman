"""Acceptance-criteria judging for completion evidence.

A task's acceptance criteria are checked by a machine only when a project
configures a judge model (``judge_base_url`` and ``judge_model``):
``judge_criteria`` then issues one direct HTTP call to an Anthropic-compatible
Messages endpoint and returns a passed / partial / failed checklist.

Without a judge, or when the call fails, every criterion is reported as
``unverified`` and ``judged_by`` is ``"none"``. Nothing here guesses: an
earlier keyword-overlap heuristic compared the criteria with the developer's
own summary and called that a pass, which is not a check (ADR-0018).
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
    judged_by: str  # model id, or NOT_JUDGED when no judge ran


NOT_JUDGED = "none"
UNVERIFIED = "unverified"


def unverified_checklist(criteria: list[str]) -> tuple[dict[str, str], ...]:
    """Return the checklist for criteria no judge looked at."""

    return tuple(
        {
            "criterion": criterion,
            "status": UNVERIFIED,
            "evidence": "Not checked by a judge model.",
        }
        for criterion in criteria
    )


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
    """Judge acceptance criteria with the configured model.

    Returns an all-``unverified`` checklist when the judge is not configured or
    on any HTTP / timeout / parse error, so evidence building never crashes
    and never reports a check that did not run.
    """

    if not criteria:
        return CriteriaJudgment(checklist=(), judged_by=NOT_JUDGED)

    base_url = str(settings.get("judge_base_url") or "").strip()
    model = str(settings.get("judge_model") or "").strip()

    def _not_judged() -> CriteriaJudgment:
        return CriteriaJudgment(checklist=unverified_checklist(criteria), judged_by=NOT_JUDGED)

    if not base_url or not model:
        return _not_judged()

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
    except Exception:  # noqa: BLE001 - any failure means the criteria were not judged
        return _not_judged()
