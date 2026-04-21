"""Regression tests for the reviewed Codex supervisor flow."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import Mock, patch

from scripts import reviewed_codex


class ReviewedCodexFlowTests(unittest.TestCase):
    """Verify post-review control flow for the Codex supervisor."""

    def make_runner(self) -> reviewed_codex.ReviewedCodex:
        runner = reviewed_codex.ReviewedCodex.__new__(reviewed_codex.ReviewedCodex)
        runner.dev_thread_id = "dev-thread"
        runner.dev_turn_id = None
        runner.last_supervisor_merge_main_head = None
        return runner

    def test_spec_complete_marker_is_detected(self) -> None:
        text = f"slice summary\n{reviewed_codex.SPEC_COMPLETE_MARKER}\n"
        self.assertTrue(reviewed_codex.developer_declared_spec_complete(text))
        self.assertFalse(reviewed_codex.developer_declared_spec_complete("not complete"))

    @patch("scripts.reviewed_codex.terminal_report")
    def test_continue_developer_turn_can_allow_spec_completion(self, _terminal_report: Mock) -> None:
        runner = self.make_runner()
        runner.start_turn = Mock(return_value="turn-2")

        runner.continue_developer_turn("continue with next slice", allow_spec_complete=True)

        runner.start_turn.assert_called_once()
        prompt = runner.start_turn.call_args.args[1]
        self.assertIn(reviewed_codex.SPEC_COMPLETE_MARKER, prompt)
        self.assertIn(reviewed_codex.TASK_COMPLETE_MARKER, prompt)

    @patch("scripts.reviewed_codex.terminal_report")
    @patch("scripts.reviewed_codex.run_git_command")
    @patch("scripts.reviewed_codex.current_head", return_value="abc123")
    @patch("scripts.reviewed_codex.current_branch", return_value="feat/slice")
    def test_handle_approved_completion_continues_after_successful_merge(
        self,
        _current_branch: Mock,
        _current_head: Mock,
        run_git_command: Mock,
        _terminal_report: Mock,
    ) -> None:
        run_git_command.side_effect = [
            subprocess.CompletedProcess(["git", "switch", "main"], 0, stdout="ok", stderr=""),
            subprocess.CompletedProcess(["git", "merge"], 0, stdout="merged", stderr=""),
        ]
        runner = self.make_runner()
        runner.continue_developer_turn = Mock()

        runner.handle_approved_completion()

        self.assertEqual(run_git_command.call_args_list[0].args[0], ["switch", "main"])
        self.assertEqual(
            run_git_command.call_args_list[1].args[0],
            ["merge", "--no-ff", "feat/slice", "-m", "merge: feat/slice into main"],
        )
        self.assertEqual(runner.last_supervisor_merge_main_head, "abc123")
        runner.continue_developer_turn.assert_called_once()
        reason = runner.continue_developer_turn.call_args.args[0]
        self.assertIn("Branch `feat/slice` has been merged into `main`.", reason)
        self.assertTrue(runner.continue_developer_turn.call_args.kwargs["allow_spec_complete"])

    @patch("scripts.reviewed_codex.terminal_report")
    @patch("scripts.reviewed_codex.run_git_command")
    @patch("scripts.reviewed_codex.current_branch", return_value="feat/slice")
    def test_handle_approved_completion_recovers_from_merge_failure(
        self,
        _current_branch: Mock,
        run_git_command: Mock,
        _terminal_report: Mock,
    ) -> None:
        run_git_command.side_effect = [
            subprocess.CompletedProcess(["git", "switch", "main"], 1, stdout="", stderr="local changes would be overwritten"),
        ]
        runner = self.make_runner()
        runner.continue_developer_turn = Mock()

        runner.handle_approved_completion()

        runner.continue_developer_turn.assert_called_once()
        reason = runner.continue_developer_turn.call_args.args[0]
        self.assertIn("automatic merge of `feat/slice` into `main` failed", reason)
        self.assertIn("Finalize the approved slice", reason)
        self.assertTrue(runner.continue_developer_turn.call_args.kwargs["allow_spec_complete"])

    @patch("scripts.reviewed_codex.terminal_report")
    @patch("scripts.reviewed_codex.current_branch", return_value="main")
    def test_handle_approved_completion_detects_main_violation(
        self,
        _current_branch: Mock,
        _terminal_report: Mock,
    ) -> None:
        runner = self.make_runner()
        runner.continue_developer_turn = Mock()

        runner.handle_approved_completion()

        runner.continue_developer_turn.assert_called_once()
        reason = runner.continue_developer_turn.call_args.args[0]
        self.assertIn("approved work is currently on `main`", reason)
        self.assertTrue(runner.continue_developer_turn.call_args.kwargs["allow_spec_complete"])

    @patch("scripts.reviewed_codex.current_branch", return_value="main")
    @patch("scripts.reviewed_codex.current_head", return_value="def456")
    @patch("scripts.reviewed_codex.worktree_dirty", return_value=False)
    def test_post_merge_main_violation_detects_new_commits(
        self,
        _worktree_dirty: Mock,
        _current_head: Mock,
        _current_branch: Mock,
    ) -> None:
        runner = self.make_runner()
        runner.last_supervisor_merge_main_head = "abc123"

        reason = runner.post_merge_main_violation_reason()

        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("new commits were created on `main` afterward", reason)

    @patch("scripts.reviewed_codex.current_branch", return_value="main")
    @patch("scripts.reviewed_codex.current_head", return_value="abc123")
    @patch("scripts.reviewed_codex.worktree_dirty", return_value=True)
    def test_post_merge_main_violation_detects_dirty_worktree(
        self,
        _worktree_dirty: Mock,
        _current_head: Mock,
        _current_branch: Mock,
    ) -> None:
        runner = self.make_runner()
        runner.last_supervisor_merge_main_head = "abc123"

        reason = runner.post_merge_main_violation_reason()

        self.assertIsNotNone(reason)
        assert reason is not None
        self.assertIn("uncommitted changes on `main`", reason)

    @patch("scripts.reviewed_codex.current_branch", return_value="main")
    @patch("scripts.reviewed_codex.current_head", return_value="abc123")
    @patch("scripts.reviewed_codex.worktree_dirty", return_value=False)
    def test_post_merge_main_violation_allows_clean_merged_main(
        self,
        _worktree_dirty: Mock,
        _current_head: Mock,
        _current_branch: Mock,
    ) -> None:
        runner = self.make_runner()
        runner.last_supervisor_merge_main_head = "abc123"

        reason = runner.post_merge_main_violation_reason()

        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
