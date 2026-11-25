"""The reviewer's verdict is a record per criterion (ADR-0041 section 2, ADR-0042)."""

from __future__ import annotations

import json
import unittest

from foreman.definitions.records import RECORD_PROBLEM_PREFIX
from foreman.definitions.roles import default_roles_dir, load_roles
from foreman.engine.output_contract import contract_retry_reason, read_completion, with_retry_instruction
from foreman.engine.results import AgentExecutionResult
from foreman.engine.verdict import VERDICT_PROBLEM_PREFIX

REVIEWERS = ("code_reviewer", "security_reviewer", "triage_reviewer", "frontier_reviewer")


def verdict(criteria=None, findings=None) -> str:
    payload = {
        "criteria": criteria if criteria is not None else [
            {"criterion": "It works", "status": "verified", "evidence": "tests/x.py:12"},
        ],
        "findings": findings or [],
    }
    return "```foreman-record\n" + json.dumps(payload) + "\n```"


def finding(severity: str, text: str = "Something.") -> dict[str, str]:
    return {"severity": severity, "finding": text}


class ShippedRolesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roles = load_roles(default_roles_dir())

    def test_every_reviewer_declares_the_verdict_record_and_defines_the_severities(self) -> None:
        for role_id in REVIEWERS:
            with self.subTest(role_id):
                role = self.roles[role_id]
                record = role.completion.record
                assert record is not None
                self.assertEqual(record.kind, "review_verdict")
                criteria, findings = record.fields
                self.assertEqual([f.name for f in criteria.fields], ["criterion", "status", "evidence"])
                self.assertEqual(criteria.fields[1].choices, ("verified", "not_verified", "judgement"))
                self.assertEqual([f.name for f in findings.fields], ["severity", "finding"])
                self.assertEqual(findings.fields[0].choices, ("S1", "S2", "S3", "S4"))
                prompt = role.render_prompt({"developer_report": "r", "acceptance_criteria": "c"})
                for line in (
                    "- S1: broken, unsafe or data-losing.",
                    "- S2: an acceptance criterion not met.",
                    "- S3: should be fixed, but does not block.",
                    "- S4: a nit.",
                ):
                    self.assertIn(line, prompt)
                self.assertIn("```foreman-record", prompt)

    def test_no_shipped_role_prompt_mentions_a_judge_model(self) -> None:
        for role_id, role in self.roles.items():
            with self.subTest(role_id):
                self.assertNotIn("judge model", role.prompt_template.lower())


class AgreementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.role = load_roles(default_roles_dir())["code_reviewer"]

    def read(self, record: str, decision: str):
        return read_completion(self.role, f"Looked.\n\n{record}\n{decision}")

    def assert_disagrees(self, reading, *words: str) -> None:
        self.assertEqual(reading.outcome, "error")
        self.assertTrue(reading.detail.startswith(VERDICT_PROBLEM_PREFIX), reading.detail)
        for word in words:
            self.assertIn(word, reading.detail)

    def test_an_approval_with_no_serious_finding_and_every_criterion_checked_stands(self) -> None:
        record = verdict(
            criteria=[
                {"criterion": "a", "status": "verified", "evidence": "e"},
                {"criterion": "b", "status": "judgement", "evidence": "read it"},
            ],
            findings=[finding("S3"), finding("S4")],
        )
        reading = self.read(record, "APPROVE")
        self.assertEqual(reading.outcome, "approve")
        # The S3 and S4 findings are kept with the review.
        self.assertEqual(
            [f["severity"] for f in reading.record["fields"]["findings"]], ["S3", "S4"]
        )
        self.assertEqual(reading.record["kind"], "review_verdict")

    def test_an_approval_with_an_s1_or_s2_finding_is_an_error(self) -> None:
        for severity in ("S1", "S2"):
            with self.subTest(severity):
                reading = self.read(verdict(findings=[finding("S3"), finding(severity)]), "APPROVE")
                self.assert_disagrees(reading, "APPROVE", "blocking finding", severity)
                self.assertIsNotNone(reading.record)

    def test_an_approval_with_a_criterion_not_verified_is_an_error_naming_it(self) -> None:
        record = verdict(criteria=[
            {"criterion": "The page shows it", "status": "not_verified", "evidence": "not opened"},
        ])
        self.assert_disagrees(self.read(record, "APPROVE"), "not verified", "The page shows it")

    def test_a_denial_or_a_steer_with_no_s1_or_s2_finding_is_an_error(self) -> None:
        for decision in ("DENY: no.", "STEER: do this."):
            for findings in ([], [finding("S3"), finding("S4")]):
                with self.subTest(decision=decision, findings=len(findings)):
                    reading = self.read(verdict(findings=findings), decision)
                    self.assert_disagrees(reading, decision.split(":")[0], "no S1 or S2 finding")

    def test_a_denial_or_a_steer_with_a_serious_finding_stands(self) -> None:
        for decision, outcome in (("DENY: broken.", "deny"), ("STEER: fix it.", "steer")):
            for severity in ("S1", "S2"):
                with self.subTest(outcome=outcome, severity=severity):
                    reading = self.read(
                        verdict(
                            criteria=[{"criterion": "a", "status": "not_verified", "evidence": "e"}],
                            findings=[finding(severity)],
                        ),
                        decision,
                    )
                    self.assertEqual(reading.outcome, outcome)
                    # The developer is handed the reason and the findings behind it.
                    self.assertTrue(reading.detail.startswith(decision.split(": ", 1)[1]))
                    self.assertIn(f"- {severity}: Something.", reading.detail)

    def test_an_approval_listing_no_criteria_of_a_task_that_has_some_is_an_error(self) -> None:
        text = f"Looked.\n\n{verdict(criteria=[])}\nAPPROVE"
        reading = read_completion(self.role, text, task_has_criteria=True)
        self.assert_disagrees(reading, "without listing")
        # A task with no criteria may be approved with none listed.
        self.assertEqual(read_completion(self.role, text, task_has_criteria=False).outcome, "approve")

    def test_a_severity_in_lower_case_is_read_as_declared(self) -> None:
        reading = self.read(verdict(findings=[{"severity": "s3", "finding": "x"}]), "APPROVE")
        self.assertEqual(reading.outcome, "approve")
        self.assertEqual(reading.record["fields"]["findings"][0]["severity"], "S3")

    def test_the_format_example_never_shows_a_blocking_finding(self) -> None:
        instructions = self.role.completion.record.instructions("")
        self.assertNotIn('"S1"', instructions)
        self.assertNotIn('"S2"', instructions)

    def test_an_escalation_is_not_checked_against_the_findings(self) -> None:
        triage = load_roles(default_roles_dir())["triage_reviewer"]
        reading = read_completion(triage, verdict(findings=[finding("S3")]) + "\nESCALATE: unsure")
        self.assertEqual(reading.outcome, "escalate")

    def test_a_missing_or_malformed_verdict_is_an_error(self) -> None:
        reading = read_completion(self.role, "Looks fine.\nAPPROVE")
        self.assertEqual(reading.outcome, "error")
        self.assertTrue(reading.detail.startswith(RECORD_PROBLEM_PREFIX))
        self.assertIsNone(reading.record)
        bad = verdict(findings=[finding("S9")])
        reading = self.read(bad, "APPROVE")
        self.assertTrue(reading.detail.startswith(RECORD_PROBLEM_PREFIX))
        self.assertIn("`findings[1].severity` must be one of S1, S2, S3, S4", reading.detail)
        bad = verdict(criteria=[{"criterion": "a", "status": "maybe", "evidence": "e"}])
        self.assertIn("`criteria[1].status` must be one of verified", self.read(bad, "APPROVE").detail)

    def test_a_line_of_the_record_is_never_taken_for_the_decision(self) -> None:
        record = verdict(findings=[finding("S1", "Broken.\nDENY: in the text")])
        reading = self.read(record, "DENY: broken")
        self.assertEqual(reading.outcome, "deny")
        self.assertTrue(reading.detail.startswith("broken\n"))

    def test_a_decision_with_no_decision_line_is_still_the_decision_error(self) -> None:
        reading = read_completion(self.role, verdict())
        self.assertEqual(reading.outcome, "error")
        self.assertFalse(reading.detail.startswith(VERDICT_PROBLEM_PREFIX))

    def test_each_mistake_gets_its_one_correction(self) -> None:
        disagreeing = self.read(verdict(findings=[finding("S2")]), "APPROVE")
        malformed = read_completion(self.role, "Fine.\nAPPROVE")
        for reading, reason in ((disagreeing, "verdict_agreement"), (malformed, "record_format")):
            with self.subTest(reason):
                result = AgentExecutionResult(outcome=reading.outcome, detail=reading.detail)
                self.assertEqual(contract_retry_reason(self.role, result), reason)
                correction = with_retry_instruction("FIRST", self.role, reason, resumes_session=True)
                self.assertTrue(correction.startswith("### Output Correction"))
                self.assertIn("```foreman-record", correction)
                self.assertIn("DENY: <reason>", correction)

    def test_a_reviewer_with_no_record_reads_as_before(self) -> None:
        from foreman.definitions.roles import load_role_text

        text = (default_roles_dir() / "code_reviewer.toml").read_text(encoding="utf-8")
        head, _, _ = text.partition("[completion.record]")
        plain = load_role_text(head + "\n[signals]\nallowed = ['progress']\n", "plain.toml")
        reading = read_completion(plain, "APPROVE")
        self.assertEqual((reading.outcome, reading.record), ("approve", None))


if __name__ == "__main__":
    unittest.main()
