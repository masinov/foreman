"""Unit coverage for the opt-in LLM criteria judge and heuristic fallback."""

from __future__ import annotations

import unittest
from unittest import mock

import httpx

from foreman.judge import (
    CriteriaJudgment,
    heuristic_checklist,
    judge_criteria,
    truncate_diff,
)


CRITERIA = ["Add a login button", "Persist the session token"]
JUDGE_SETTINGS = {
    "judge_base_url": "https://judge.example/api",
    "judge_model": "cheap-judge-1",
}


def _fake_response(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json={"content": [{"type": "text", "text": text}]},
        request=httpx.Request("POST", "https://judge.example/api/v1/messages"),
    )


class TruncateDiffTests(unittest.TestCase):
    def test_short_diff_unchanged(self) -> None:
        self.assertEqual(truncate_diff("abc", 100), "abc")

    def test_long_diff_head_tail_with_marker(self) -> None:
        diff = "H" * 100 + "T" * 100
        out = truncate_diff(diff, 50)
        self.assertIn("[...truncated 150 chars...]", out)
        self.assertTrue(out.startswith("H"))
        self.assertTrue(out.endswith("T"))


class HeuristicTests(unittest.TestCase):
    def test_unset_settings_returns_heuristic(self) -> None:
        result = judge_criteria(
            criteria=CRITERIA,
            diff_text="",
            agent_summary="added login button and persisted session token",
            changed_files=(),
            settings={},
        )
        self.assertEqual(result.judged_by, "heuristic")
        self.assertEqual(
            result.checklist,
            heuristic_checklist(
                CRITERIA, "added login button and persisted session token", ()
            ),
        )

    def test_empty_criteria_returns_empty_heuristic(self) -> None:
        result = judge_criteria(
            criteria=[], diff_text="x", agent_summary="y", settings=JUDGE_SETTINGS
        )
        self.assertEqual(result, CriteriaJudgment(checklist=(), judged_by="heuristic"))


class LlmJudgeTests(unittest.TestCase):
    def test_happy_path_returns_model_judgment(self) -> None:
        body = (
            '[{"criterion": "Add a login button", "status": "passed", "evidence": "button added"},'
            ' {"criterion": "Persist the session token", "status": "failed", "evidence": "no token"}]'
        )
        with mock.patch("httpx.post", return_value=_fake_response(body)) as posted:
            result = judge_criteria(
                criteria=CRITERIA,
                diff_text="diff",
                agent_summary="summary",
                settings=JUDGE_SETTINGS,
            )
        self.assertEqual(result.judged_by, "cheap-judge-1")
        self.assertEqual([c["status"] for c in result.checklist], ["passed", "failed"])
        # Anthropic Messages endpoint shape.
        self.assertTrue(posted.call_args.args[0].endswith("/v1/messages"))

    def test_fenced_json_is_parsed(self) -> None:
        body = (
            "```json\n"
            '[{"criterion": "Add a login button", "status": "partial", "evidence": "x"},'
            ' {"criterion": "Persist the session token", "status": "passed", "evidence": "y"}]'
            "\n```"
        )
        with mock.patch("httpx.post", return_value=_fake_response(body)):
            result = judge_criteria(
                criteria=CRITERIA,
                diff_text="diff",
                agent_summary="summary",
                settings=JUDGE_SETTINGS,
            )
        self.assertEqual(result.judged_by, "cheap-judge-1")
        self.assertEqual([c["status"] for c in result.checklist], ["partial", "passed"])

    def test_malformed_output_falls_back_to_heuristic(self) -> None:
        with mock.patch("httpx.post", return_value=_fake_response("not json at all")):
            result = judge_criteria(
                criteria=CRITERIA,
                diff_text="diff",
                agent_summary="summary",
                settings=JUDGE_SETTINGS,
            )
        self.assertEqual(result.judged_by, "heuristic")

    def test_wrong_item_count_falls_back(self) -> None:
        body = '[{"criterion": "only one", "status": "passed", "evidence": "x"}]'
        with mock.patch("httpx.post", return_value=_fake_response(body)):
            result = judge_criteria(
                criteria=CRITERIA,
                diff_text="diff",
                agent_summary="summary",
                settings=JUDGE_SETTINGS,
            )
        self.assertEqual(result.judged_by, "heuristic")

    def test_timeout_falls_back_to_heuristic(self) -> None:
        with mock.patch("httpx.post", side_effect=httpx.TimeoutException("slow")):
            result = judge_criteria(
                criteria=CRITERIA,
                diff_text="diff",
                agent_summary="summary",
                settings=JUDGE_SETTINGS,
            )
        self.assertEqual(result.judged_by, "heuristic")

    def test_http_error_falls_back_to_heuristic(self) -> None:
        with mock.patch("httpx.post", return_value=_fake_response("err", status=500)):
            result = judge_criteria(
                criteria=CRITERIA,
                diff_text="diff",
                agent_summary="summary",
                settings=JUDGE_SETTINGS,
            )
        self.assertEqual(result.judged_by, "heuristic")


if __name__ == "__main__":
    unittest.main()
