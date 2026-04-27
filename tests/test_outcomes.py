"""Tests for outcome normalization."""

from __future__ import annotations

import unittest

from foreman.outcomes import (
    APPROVE,
    BLOCKED,
    CANCELLED,
    DENY,
    DONE,
    ERROR,
    FAILURE,
    KILLED,
    PAUSED,
    STEER,
    SUCCESS,
    CANONICAL_OUTCOMES,
    normalize_agent_outcome,
    normalize_reviewer_decision,
)


class NormalizeAgentOutcomeTests(unittest.TestCase):
    def test_done_variants(self) -> None:
        self.assertEqual(normalize_agent_outcome("completed"), DONE)
        self.assertEqual(normalize_agent_outcome("Done"), DONE)
        self.assertEqual(normalize_agent_outcome("DONE"), DONE)

    def test_error_variants(self) -> None:
        self.assertEqual(normalize_agent_outcome("error"), ERROR)
        self.assertEqual(normalize_agent_outcome("Error"), ERROR)
        self.assertEqual(normalize_agent_outcome("failed"), ERROR)

    def test_killed_variants(self) -> None:
        self.assertEqual(normalize_agent_outcome("killed"), KILLED)
        self.assertEqual(normalize_agent_outcome("terminated"), KILLED)
        self.assertEqual(normalize_agent_outcome("timeout"), KILLED)

    def test_success_variants(self) -> None:
        self.assertEqual(normalize_agent_outcome("success"), SUCCESS)
        self.assertEqual(normalize_agent_outcome("succeeded"), SUCCESS)

    def test_failure_variants(self) -> None:
        self.assertEqual(normalize_agent_outcome("failure"), FAILURE)

    def test_paused(self) -> None:
        self.assertEqual(normalize_agent_outcome("paused"), PAUSED)

    def test_unknown_passthrough(self) -> None:
        result = normalize_agent_outcome("some_custom_outcome")
        self.assertEqual(result, "some_custom_outcome")


class NormalizeReviewerDecisionTests(unittest.TestCase):
    def test_approve_variants(self) -> None:
        self.assertEqual(normalize_reviewer_decision("approve"), APPROVE)
        self.assertEqual(normalize_reviewer_decision("approved"), APPROVE)
        self.assertEqual(normalize_reviewer_decision("yes"), APPROVE)
        self.assertEqual(normalize_reviewer_decision("lgtm"), APPROVE)
        self.assertEqual(normalize_reviewer_decision("pass"), APPROVE)

    def test_deny_variants(self) -> None:
        self.assertEqual(normalize_reviewer_decision("deny"), DENY)
        self.assertEqual(normalize_reviewer_decision("denied"), DENY)
        self.assertEqual(normalize_reviewer_decision("no"), DENY)
        self.assertEqual(normalize_reviewer_decision("reject"), DENY)
        self.assertEqual(normalize_reviewer_decision("rejected"), DENY)
        self.assertEqual(normalize_reviewer_decision("needs_work"), DENY)

    def test_steer_variants(self) -> None:
        self.assertEqual(normalize_reviewer_decision("steer"), STEER)
        self.assertEqual(normalize_reviewer_decision("steering"), STEER)
        self.assertEqual(normalize_reviewer_decision("redirect"), STEER)
        self.assertEqual(normalize_reviewer_decision("revise"), STEER)

    def test_unknown_passthrough(self) -> None:
        result = normalize_reviewer_decision("some_custom_decision")
        self.assertEqual(result, "some_custom_decision")


class CanonicalOutcomesTests(unittest.TestCase):
    def test_all_outcomes_present(self) -> None:
        self.assertIn(DONE, CANONICAL_OUTCOMES)
        self.assertIn(CANCELLED, CANONICAL_OUTCOMES)
        self.assertIn(BLOCKED, CANONICAL_OUTCOMES)
        self.assertIn(SUCCESS, CANONICAL_OUTCOMES)
        self.assertIn(FAILURE, CANONICAL_OUTCOMES)
        self.assertIn(ERROR, CANONICAL_OUTCOMES)
        self.assertIn(KILLED, CANONICAL_OUTCOMES)
        self.assertIn(PAUSED, CANONICAL_OUTCOMES)
        self.assertIn(APPROVE, CANONICAL_OUTCOMES)
        self.assertIn(DENY, CANONICAL_OUTCOMES)
        self.assertIn(STEER, CANONICAL_OUTCOMES)
