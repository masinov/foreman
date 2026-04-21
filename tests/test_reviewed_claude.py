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

    @patch("scripts.reviewed_claude.current_branch", return_value="main")
    def test_developer_turn_safe_rejects_main_branch(self, _current_branch: Mock) -> None:
        runner = self.make_runner()
        runner._developer_turn_safe = Mock(return_value="__MAIN_VIOLATION__")

        result = runner._developer_turn_safe("prompt")

        self.assertEqual(result, "__MAIN_VIOLATION__")
        self.assertEqual(runner.consecutive_api_failures, 0)

    def test_developer_turn_safe_rejects_main_head_change(self) -> None:
        runner = self.make_runner()
        runner._run_developer_turn = Mock(return_value="some output")

        call_count = [0]

        def main_head_mock() -> str:
            call_count[0] += 1
            return "abc123" if call_count[0] == 1 else "def456"

        with patch("scripts.reviewed_claude.main_head", side_effect=main_head_mock):
            with patch("scripts.reviewed_claude.current_branch", return_value="feat/branch"):
                result = runner._developer_turn_safe("prompt")

        self.assertEqual(result, "__MAIN_VIOLATION__")

    @patch("scripts.reviewed_claude.current_branch", return_value="feat/branch")
    @patch("scripts.reviewed_claude.main_head", return_value="abc123")
    def test_developer_turn_safe_tracks_api_failures(
        self, _main_head: Mock, _current_branch: Mock
    ) -> None:
        runner = self.make_runner()
        runner._run_developer_turn = Mock(side_effect=RuntimeError("api error"))
        runner.consecutive_api_failures = 2

        result = runner._developer_turn_safe("prompt")

        self.assertIsNone(result)
        self.assertEqual(runner.consecutive_api_failures, 3)

    @patch("scripts.reviewed_claude.current_branch", return_value="feat/branch")
    @patch("scripts.reviewed_claude.main_head", return_value="abc123")
    def test_developer_turn_safe_resets_failure_count_on_success(
        self, _main_head: Mock, _current_branch: Mock
    ) -> None:
        runner = self.make_runner()
        runner.consecutive_api_failures = 2
        runner._run_developer_turn = Mock(return_value="output text")

        result = runner._developer_turn_safe("prompt")

        self.assertEqual(result, "output text")
        self.assertEqual(runner.consecutive_api_failures, 0)

    # ─── Reviewer interaction ────────────────────────────────────────────────

    @patch("scripts.reviewed_claude.run_git")
    def test_build_review_prompt_includes_developer_output(
        self, _run_git: Mock
    ) -> None:
        runner = self.make_runner()
        runner.last_developer_output = "Developer completed task-1.\nTASK_ID: task-1"
        with patch("scripts.reviewed_claude.current_branch", return_value="feat/slice"):
            prompt = runner.build_review_prompt()
        self.assertIn("Developer completed task-1", prompt)
        self.assertIn("feat/slice", prompt)

    @patch("scripts.reviewed_claude.run_git")
    def test_build_review_prompt_shows_fallback_when_no_output(
        self, _run_git: Mock
    ) -> None:
        runner = self.make_runner()
        runner.last_developer_output = ""
        with patch("scripts.reviewed_claude.current_branch", return_value="feat/slice"):
            prompt = runner.build_review_prompt()
        self.assertIn("no completion summary", prompt)

    # ─── Finalize merge integration ──────────────────────────────────────────

    @patch("scripts.reviewed_claude.Path.exists")
    def test_finalize_supervisor_merge_returns_error_when_db_missing(
        self, mock_exists: Mock
    ) -> None:
        mock_exists.return_value = False
        result = reviewed_claude.finalize_supervisor_merge("feat/branch")
        self.assertIn("missing", result)

    @patch("scripts.reviewed_claude.terminal_report")
    @patch("scripts.reviewed_claude.ForemanStore")
    def test_finalize_supervisor_merge_reports_state_when_finalize_returns_none(
        self, mock_store_class: Mock, _terminal_report: Mock
    ) -> None:
        mock_store = Mock()
        mock_store.initialize = Mock()
        mock_store_class.return_value.__enter__ = Mock(return_value=mock_store)
        mock_store_class.return_value.__exit__ = Mock(return_value=None)

        with patch.object(
            reviewed_claude, "finalize_supervisor_merge_state", return_value=None
        ):
            result = reviewed_claude.finalize_supervisor_merge("feat/branch", task_id="task-1")
        self.assertIn("could not map", result)

    @patch("scripts.reviewed_claude.terminal_report")
    @patch("scripts.reviewed_claude.ForemanStore")
    def test_finalize_supervisor_merge_reports_success_payload(
        self, mock_store_class: Mock, mock_terminal_report: Mock
    ) -> None:
        from foreman.supervisor_state import SupervisorMergeResult

        mock_store = Mock()
        mock_store.initialize = Mock()
        mock_store_class.return_value.__enter__ = Mock(return_value=mock_store)
        mock_store_class.return_value.__exit__ = Mock(return_value=None)

        result_obj = SupervisorMergeResult(
            project_id="proj-1",
            task_id="task-1",
            sprint_id="sprint-1",
            task_status="done",
            sprint_status="completed",
            stop_reason="sprint_complete",
        )
        with patch.object(
            reviewed_claude, "finalize_supervisor_merge_state", return_value=result_obj
        ):
            result = reviewed_claude.finalize_supervisor_merge("feat/branch", task_id="task-1")
        self.assertEqual(result, "")
        mock_terminal_report.assert_called()
        call_kwargs = mock_terminal_report.call_args.kwargs
        self.assertEqual(call_kwargs["payload"]["task_status"], "done")
        self.assertEqual(call_kwargs["payload"]["sprint_status"], "completed")


if __name__ == "__main__":
    unittest.main()
