"""Regression tests for the reviewed Claude supervisor flow."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import Mock, patch

from scripts import reviewed_claude


class ReviewedClaudeFlowTests(unittest.TestCase):
    """Verify post-review control flow for the Claude supervisor."""

    def make_runner(self) -> reviewed_claude.ReviewedClaude:
        runner = reviewed_claude.ReviewedClaude.__new__(reviewed_claude.ReviewedClaude)
        runner.reviewer_config = reviewed_claude.ReviewerConfig(
            model="claude-sonnet-4-6",
            effort="high",
            instructions="",
        )
        runner.dev_session_id = None
        runner.last_developer_output = ""
        runner.consecutive_api_failures = 0
        runner._pre_turn_branch = ""
        runner._pre_turn_main_head = ""
        return runner

    # ─── Completion marker detection ─────────────────────────────────────────

    def test_task_complete_marker_is_detected(self) -> None:
        text = f"slice summary\n{reviewed_claude.TASK_COMPLETE_MARKER}\n"
        self.assertTrue(reviewed_claude.developer_declared_completion(text))
        self.assertFalse(reviewed_claude.developer_declared_completion("not complete"))

    def test_spec_complete_marker_is_detected(self) -> None:
        text = f"slice summary\n{reviewed_claude.SPEC_COMPLETE_MARKER}\n"
        self.assertTrue(reviewed_claude.developer_declared_spec_complete(text))
        self.assertFalse(reviewed_claude.developer_declared_spec_complete("not complete"))

    # ─── Task ID extraction ───────────────────────────────────────────────────

    def test_extract_task_id_reads_uppercase_task_id_line(self) -> None:
        text = "Summary\nTASK_ID: sprint-45-t1\nREVIEWED_CLAUDE_TASK_COMPLETE\n"
        self.assertEqual(reviewed_claude.extract_task_id(text), "sprint-45-t1")

    def test_extract_task_id_reads_bold_task_id_format(self) -> None:
        text = "Summary\n**Task ID**: sprint-45-t1\nREVIEWED_CLAUDE_TASK_COMPLETE\n"
        self.assertEqual(reviewed_claude.extract_task_id(text), "sprint-45-t1")

    def test_extract_task_id_returns_none_when_absent(self) -> None:
        text = "Summary\nREVIEWED_CLAUDE_TASK_COMPLETE\n"
        self.assertIsNone(reviewed_claude.extract_task_id(text))

    # ─── Reviewer decision parsing ────────────────────────────────────────────

    def test_split_reviewer_decision_parses_approve(self) -> None:
        kind, detail = reviewed_claude.split_reviewer_decision("APPROVE")
        self.assertEqual(kind, "APPROVE")
        self.assertEqual(detail, "")

    def test_split_reviewer_decision_parses_deny(self) -> None:
        kind, detail = reviewed_claude.split_reviewer_decision("DENY: work is incomplete")
        self.assertEqual(kind, "DENY")
        self.assertEqual(detail, "work is incomplete")

    def test_split_reviewer_decision_parses_steer(self) -> None:
        kind, detail = reviewed_claude.split_reviewer_decision("STEER: add more tests")
        self.assertEqual(kind, "STEER")
        self.assertEqual(detail, "add more tests")

    def test_normalize_decision_picks_last_decision_line(self) -> None:
        text = "some output\nAPPROVE\nbut also some noise"
        self.assertEqual(reviewed_claude.normalize_decision(text), "APPROVE")

    def test_normalize_decision_handles_malformed_output(self) -> None:
        text = "something went wrong"
        result = reviewed_claude.normalize_decision(text)
        self.assertTrue(result.startswith("STEER:"))

    # ─── Git helpers ──────────────────────────────────────────────────────────

    @patch("scripts.reviewed_claude.run_git")
    def test_current_branch_calls_git_rev_parse(self, run_git: Mock) -> None:
        run_git.return_value = "feat/my-branch"
        self.assertEqual(reviewed_claude.current_branch(), "feat/my-branch")
        run_git.assert_called_once_with(["rev-parse", "--abbrev-ref", "HEAD"])

    @patch("scripts.reviewed_claude.run_git")
    def test_main_head_returns_rev_parse_of_main(self, run_git: Mock) -> None:
        run_git.return_value = "abc123def"
        self.assertEqual(reviewed_claude.main_head(), "abc123def")
        run_git.assert_called_once_with(["rev-parse", "main"])

    @patch("scripts.reviewed_claude.run_git")
    def test_git_status_returns_status_output(self, run_git: Mock) -> None:
        run_git.return_value = "## main...origin/main"
        self.assertIn("main", reviewed_claude.git_status())

    # ─── Main violation detection ─────────────────────────────────────────────

    def test_main_head_returns_empty_string_when_main_not_found(self) -> None:
        with patch("scripts.reviewed_claude.run_git", return_value=""):
            result = reviewed_claude.main_head()
            self.assertEqual(result, "")

    def test_developer_turn_safe_returns_main_violation_when_on_main(self) -> None:
        runner = self.make_runner()
        runner._run_developer_turn = Mock(return_value="committed directly to main")
        runner.consecutive_api_failures = 0

        with patch("scripts.reviewed_claude.current_branch", return_value="main"):
            with patch("scripts.reviewed_claude.main_head", return_value="abc123"):
                result = runner._developer_turn_safe("prompt")

        self.assertEqual(result, "__MAIN_VIOLATION__")
        self.assertEqual(runner.consecutive_api_failures, 0)  # not an API error

    def test_developer_turn_safe_returns_main_violation_when_main_head_changed(self) -> None:
        runner = self.make_runner()
        runner._run_developer_turn = Mock(return_value="some output")
        runner.consecutive_api_failures = 0

        call_count = [0]

        def main_head_mock() -> str:
            call_count[0] += 1
            return "abc123" if call_count[0] == 1 else "def456"

        with patch("scripts.reviewed_claude.main_head", side_effect=main_head_mock):
            with patch("scripts.reviewed_claude.current_branch", return_value="feat/branch"):
                result = runner._developer_turn_safe("prompt")

        self.assertEqual(result, "__MAIN_VIOLATION__")

    def test_developer_turn_safe_increments_api_failure_on_runtime_error(self) -> None:
        runner = self.make_runner()
        runner._run_developer_turn = Mock(side_effect=RuntimeError("api error"))
        runner.consecutive_api_failures = 2

        with patch("scripts.reviewed_claude.current_branch", return_value="feat/branch"):
            with patch("scripts.reviewed_claude.main_head", return_value="abc123"):
                result = runner._developer_turn_safe("prompt")

        self.assertIsNone(result)
        self.assertEqual(runner.consecutive_api_failures, 3)

    def test_developer_turn_safe_resets_api_failure_on_success(self) -> None:
        runner = self.make_runner()
        runner._run_developer_turn = Mock(return_value="output text")
        runner.consecutive_api_failures = 2

        with patch("scripts.reviewed_claude.current_branch", return_value="feat/branch"):
            with patch("scripts.reviewed_claude.main_head", return_value="abc123"):
                result = runner._developer_turn_safe("prompt")

        self.assertEqual(result, "output text")
        self.assertEqual(runner.consecutive_api_failures, 0)

    # ─── Task ID extraction edge cases ─────────────────────────────────────────

    def test_extract_task_id_empty_colon_value_returns_none(self) -> None:
        text = "Summary\nTASK_ID:\nREVIEWED_CLAUDE_TASK_COMPLETE\n"
        self.assertIsNone(reviewed_claude.extract_task_id(text))

    def test_extract_task_id_bold_header_next_line_value(self) -> None:
        text = "Summary\n**Task ID**\nsprint-45-t1\nREVIEWED_CLAUDE_TASK_COMPLETE\n"
        self.assertEqual(reviewed_claude.extract_task_id(text), "sprint-45-t1")

    def test_extract_task_id_not_recognized_when_only_in_body_text(self) -> None:
        text = "Summary\nThe task-id was sprint-45-t1 according to our tracking.\nREVIEWED_CLAUDE_TASK_COMPLETE\n"
        self.assertIsNone(reviewed_claude.extract_task_id(text))

    def test_extract_task_id_empty_text_returns_none(self) -> None:
        self.assertIsNone(reviewed_claude.extract_task_id(""))
        self.assertIsNone(reviewed_claude.extract_task_id("   \n  "))

    def test_extract_task_id_returns_first_match(self) -> None:
        text = "Summary\nTASK_ID: first-id\nSomething else\n**Task ID**: last-id\n"
        self.assertEqual(reviewed_claude.extract_task_id(text), "first-id")

    # ─── Reviewer decision parsing edge cases ─────────────────────────────────

    def test_split_reviewer_decision_empty_string_returns_steer(self) -> None:
        kind, detail = reviewed_claude.split_reviewer_decision("")
        self.assertEqual(kind, "STEER")
        self.assertEqual(detail, "")

    def test_normalize_decision_whitespace_only_returns_steer(self) -> None:
        result = reviewed_claude.normalize_decision("   \n  ")
        self.assertTrue(result.startswith("STEER:"))
        self.assertIn("malformed", result)

    def test_normalize_decision_just_deny_without_colon_returns_steer(self) -> None:
        result = reviewed_claude.normalize_decision("DENY")
        self.assertTrue(result.startswith("STEER:"))
        self.assertIn("DENY", result)

    def test_normalize_decision_empty_string_returns_steer(self) -> None:
        result = reviewed_claude.normalize_decision("")
        self.assertTrue(result.startswith("STEER:"))

    def test_normalize_decision_steer_preserved(self) -> None:
        result = reviewed_claude.normalize_decision("some noise\nSTEER: do this\nmore noise")
        self.assertEqual(result, "STEER: do this")

    def test_normalize_decision_deny_preserved(self) -> None:
        result = reviewed_claude.normalize_decision("some noise\nDENY: reason here\nmore noise")
        self.assertEqual(result, "DENY: reason here")

    # ─── Developer completion declaration edge cases ─────────────────────────

    def test_developer_declared_completion_false_without_marker(self) -> None:
        self.assertFalse(reviewed_claude.developer_declared_completion("TASK_COMPLETE wrong format"))
        self.assertFalse(reviewed_claude.developer_declared_completion(""))

    def test_developer_declared_spec_complete_false_without_marker(self) -> None:
        self.assertFalse(reviewed_claude.developer_declared_spec_complete("SPEC_COMPLETE wrong format"))
        self.assertFalse(reviewed_claude.developer_declared_spec_complete(""))

    # ─── SQLite reconciliation integration ─────────────────────────────────────

    def test_finalize_supervisor_merge_passes_explicit_task_id(self) -> None:
        from foreman.supervisor_state import SupervisorMergeResult

        mock_store = Mock()
        mock_store.initialize = Mock()
        with patch("scripts.reviewed_claude.ForemanStore") as mock_store_class:
            mock_store_class.return_value.__enter__ = Mock(return_value=mock_store)
            mock_store_class.return_value.__exit__ = Mock(return_value=None)
            with patch("scripts.reviewed_claude.finalize_supervisor_merge_state") as mock_finalize:
                result_obj = SupervisorMergeResult(
                    project_id="proj-1",
                    task_id="explicit-task",
                    sprint_id="sprint-1",
                    task_status="done",
                    sprint_status="active",
                    stop_reason=None,
                )
                mock_finalize.return_value = result_obj
                with patch("scripts.reviewed_claude.terminal_report"):
                    result = reviewed_claude.finalize_supervisor_merge(
                        "feat/branch", task_id="explicit-task"
                    )

        self.assertEqual(result, "")
        mock_finalize.assert_called_once()
        _, kwargs = mock_finalize.call_args
        self.assertEqual(kwargs["task_id"], "explicit-task")
        self.assertEqual(kwargs["branch_name"], "feat/branch")

    def test_finalize_supervisor_merge_db_absent_returns_meaningful_error(self) -> None:
        with patch("scripts.reviewed_claude.Path.exists", return_value=False):
            result = reviewed_claude.finalize_supervisor_merge("feat/branch")
        self.assertIn("missing", result)
        self.assertIn(".foreman.db", result)

    @patch("scripts.reviewed_claude.ForemanStore")
    @patch("scripts.reviewed_claude.terminal_report")
    def test_finalize_supervisor_merge_none_result_gives_recovery_prompt(
        self, _terminal_report: Mock, _mock_store_class: Mock
    ) -> None:
        with patch.object(reviewed_claude, "finalize_supervisor_merge_state", return_value=None):
            result = reviewed_claude.finalize_supervisor_merge("feat/branch", task_id="task-1")

        self.assertIn("could not map", result)

    # ─── Reviewer interaction ────────────────────────────────────────────────
