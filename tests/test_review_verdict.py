"""The reviewer's verdict is a record per criterion (ADR-0041 section 2, ADR-0042)."""

from __future__ import annotations

import json
import unittest

from foreman.definitions.records import RECORD_PROBLEM_PREFIX
from foreman.definitions.roles import default_roles_dir, load_roles
from foreman.engine.output_contract import contract_retry_reason, read_completion, with_retry_instruction
from foreman.engine.results import AgentExecutionResult
from foreman.definitions.roles import APPROVE_NEEDS_RULES
from foreman.engine.verdict import VERDICT_PROBLEM_PREFIX, command_was_run, criteria_items, missing_criteria

REVIEWERS = ("code_reviewer", "security_reviewer", "triage_reviewer", "frontier_reviewer")


def basis(entry: dict) -> dict:
    """A criterion with the basis fields it must carry, empty unless it names them."""

    return {"ran": [], "read": [], "from_report": False, **entry}


def verdict(criteria=None, findings=None) -> str:
    if criteria is None:
        criteria = [{"criterion": "It works", "status": "verified", "evidence": "tests/x.py:12", "read": ["tests/x.py"]}]
    payload = {
        "criteria": [basis(entry) for entry in criteria],
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
                self.assertEqual([f.name for f in criteria.fields], ["criterion", "status", "evidence", "ran", "read", "from_report"])
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


def with_needs(role, needs: str):
    """The role with its ``approve_needs`` set."""

    from dataclasses import replace

    output = replace(role.completion.output, approve_needs=needs)
    return replace(role, completion=replace(role.completion, output=output))


class BasisTests(unittest.TestCase):
    """How each criterion was verified, and what an approval needs of it (ADR-0041 section 2)."""

    def setUp(self) -> None:
        self.role = load_roles(default_roles_dir())["code_reviewer"]

    def approve(self, criteria, needs=None, commands=None, decision="APPROVE"):
        role = with_needs(self.role, needs) if needs else self.role
        return read_completion(role, f"Looked.\n\n{verdict(criteria)}\n{decision}", commands=commands)

    def test_every_shipped_reviewer_asks_for_checked_and_carries_the_basis_fields(self) -> None:
        for role_id in REVIEWERS:
            with self.subTest(role_id):
                role = load_roles(default_roles_dir())[role_id]
                self.assertEqual(role.completion.output.approve_needs, "checked")
                entry = role.completion.record.fields[0]
                self.assertEqual(
                    [(f.name, f.type) for f in entry.fields[3:]],
                    [("ran", "text_list"), ("read", "text_list"), ("from_report", "bool")],
                )
                prompt = role.render_prompt({"developer_report": "r", "acceptance_criteria": "c"})
                for word in ("`ran`", "`read`", "`from_report`"):
                    self.assertIn(word, prompt)
                # The reviewer is told its own role's rule, not a list of all three.
                self.assertIn(APPROVE_NEEDS_RULES["checked"], prompt)
                self.assertNotIn("`stated`: your word", prompt)

    def test_a_command_the_review_did_not_run_disagrees_with_the_outcome(self) -> None:
        criteria = [
            {"criterion": "a", "status": "verified", "evidence": "e", "ran": ["pytest tests/test_a.py"]},
            {"criterion": "b", "status": "verified", "evidence": "e", "ran": ["pytest tests/test_x.py"]},
        ]
        recorded = ["cd /w && pytest   tests/test_a.py -q"]
        reading = self.approve(criteria, commands=recorded)
        self.assertEqual(reading.outcome, "error")
        self.assertTrue(reading.detail.startswith(VERDICT_PROBLEM_PREFIX))
        self.assertIn("criterion 2 cites `pytest tests/test_x.py`, which the review did not run", reading.detail)
        self.assertNotIn("criterion 1", reading.detail)
        # The record stays, and the correction is the verdict one.
        self.assertIsNotNone(reading.record)
        result = AgentExecutionResult(outcome=reading.outcome, detail=reading.detail)
        self.assertEqual(contract_retry_reason(self.role, result), "verdict_agreement")

    def test_a_denial_is_checked_the_same_way(self) -> None:
        criteria = [{"criterion": "a", "status": "not_verified", "evidence": "e", "ran": ["make x"]}]
        text = f"Looked.\n\n{verdict(criteria, findings=[finding('S2')])}\nDENY: no"
        reading = read_completion(self.role, text, commands=[])
        self.assertIn("cites `make x`", reading.detail)
        self.assertEqual(read_completion(self.role, text, commands=["make x"]).outcome, "deny")

    def test_commands_that_were_run_are_confirmed_and_unknown_commands_are_not_checked(self) -> None:
        criteria = [{"criterion": "a", "status": "verified", "evidence": "e", "ran": ["pytest -q"]}]
        self.assertEqual(self.approve(criteria, commands=["pytest -q"]).outcome, "approve")
        # A caller that does not know the commands (a resumed session) skips the lookup.
        self.assertEqual(self.approve(criteria, commands=None).outcome, "approve")

    def test_checked_needs_a_command_or_a_file_or_a_judgement(self) -> None:
        ran = {"criterion": "a", "status": "verified", "evidence": "e", "ran": ["t"]}
        read = {"criterion": "b", "status": "verified", "evidence": "e", "read": ["f.py"]}
        judged = {"criterion": "c", "status": "judgement", "evidence": "a reason", "from_report": True}
        self.assertEqual(self.approve([ran, read, judged], "checked", ["t"]).outcome, "approve")
        report = {"criterion": "d", "status": "verified", "evidence": "the report says so", "from_report": True}
        reading = self.approve([ran, report], "checked", ["t"])
        self.assertEqual(reading.outcome, "error")
        self.assertIn("a command it ran or a file it read", reading.detail)
        self.assertIn("d", reading.detail)

    def test_ran_needs_a_command_or_a_judgement(self) -> None:
        ran = {"criterion": "a", "status": "verified", "evidence": "e", "ran": ["t"]}
        read = {"criterion": "b", "status": "verified", "evidence": "e", "read": ["f.py"]}
        judged = {"criterion": "c", "status": "judgement", "evidence": "a reason"}
        self.assertEqual(self.approve([ran, judged], "ran", ["t"]).outcome, "approve")
        reading = self.approve([ran, read], "ran", ["t"])
        self.assertEqual(reading.outcome, "error")
        self.assertIn("a command it ran, or judgement with its reason", reading.detail)
        self.assertIn("b", reading.detail)

    def test_stated_is_the_reviewers_word(self) -> None:
        report = {"criterion": "d", "status": "verified", "evidence": "the report", "from_report": True}
        self.assertEqual(self.approve([report], "stated").outcome, "approve")
        # A cited command is still looked for.
        cited = {"criterion": "d", "status": "verified", "evidence": "e", "ran": ["x"]}
        self.assertEqual(self.approve([cited], "stated", commands=[]).outcome, "error")

    def test_a_role_names_what_an_approval_needs_or_gets_the_default(self) -> None:
        from foreman.definitions.roles import RoleLoadError, load_role_text

        text = (default_roles_dir() / "code_reviewer.toml").read_text(encoding="utf-8")
        for needs in ("checked", "ran", "stated"):
            role = load_role_text(text.replace('approve_needs = "checked"', f'approve_needs = "{needs}"'), "r.toml")
            self.assertEqual(role.completion.output.approve_needs, needs)
        bare = load_role_text(text.replace('approve_needs = "checked"\n', ""), "r.toml")
        self.assertEqual(bare.completion.output.approve_needs, "checked")
        with self.assertRaises(RoleLoadError):
            load_role_text(text.replace('approve_needs = "checked"', 'approve_needs = "trust"'), "r.toml")


class RecordedCommandsTests(unittest.TestCase):
    """The commands Foreman recorded during the review run are what ``ran`` is checked against."""

    def tally(self, session_id=None):
        from foreman.engine.agent_step import _NativeRunTally

        role = load_roles(default_roles_dir())["code_reviewer"]
        return _NativeRunTally(role=role, session_id=session_id, task_criteria=1)

    def finish(self, tally, cited, ran):
        for command in ran:
            tally.absorb("agent.command", {"command": command, "cwd": "/w"})
        criteria = [{"criterion": "a", "status": "verified", "evidence": "e", "ran": cited}]
        message = f"Looked.\n\n{verdict(criteria)}\nAPPROVE"
        tally.absorb("agent.message", {"text": message, "phase": "final_answer"})
        tally.absorb("agent.completed", {})
        return tally

    def test_a_command_the_run_made_is_confirmed(self) -> None:
        tally = self.finish(self.tally(), ["./venv/bin/python -m pytest tests/test_x.py"], ["ls", "./venv/bin/python -m pytest tests/test_x.py -q"])
        self.assertEqual(tally.outcome, "approve")

    def test_a_command_the_run_did_not_make_ends_the_step_as_a_disagreement(self) -> None:
        tally = self.finish(self.tally(), ["pytest tests/test_x.py"], ["ls"])
        self.assertEqual(tally.outcome, "error")
        self.assertIn("criterion 1 cites `pytest tests/test_x.py`, which the review did not run", tally.detail)

    def test_a_run_that_resumes_a_session_is_checked_against_the_whole_session(self) -> None:
        from foreman.engine.agent_step import _NativeRunTally

        role = load_roles(default_roles_dir())["code_reviewer"]
        # The retry ran nothing itself; the run before it, in the same session, did.
        earlier = _NativeRunTally(role=role, session_id="s1", task_criteria=1, earlier_commands=["pytest tests/test_x.py"])
        self.assertEqual(self.finish(earlier, ["pytest tests/test_x.py"], []).outcome, "approve")
        # A retry is never taken unchecked: nothing in the session ran it.
        fabricated = self.finish(self.tally(session_id="s1"), ["pytest tests/test_x.py"], [])
        self.assertEqual(fabricated.outcome, "error")
        self.assertIn("which the review did not run", fabricated.detail)


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
                {"criterion": "a", "status": "verified", "evidence": "e", "read": ["f.py"]},
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
        reading = read_completion(self.role, text, task_criteria=2)
        self.assert_disagrees(reading, "without listing")
        # A task with no criteria may be approved with none listed.
        self.assertEqual(read_completion(self.role, text, task_criteria=0).outcome, "approve")

    def test_a_verdict_that_leaves_out_one_of_the_tasks_criteria_is_refused(self) -> None:
        text = f"Looked.\n\n{verdict()}\nAPPROVE"
        reading = read_completion(self.role, text, task_criteria=2)
        self.assert_disagrees(reading, "lists 1 of the task's 2")
        self.assertEqual(read_completion(self.role, text, task_criteria=1).outcome, "approve")

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


class CommandMatchTests(unittest.TestCase):
    """A cited command counts only when it ran as a whole command (review of sprint 66)."""

    def test_a_substring_or_a_neighbour_is_not_the_command(self) -> None:
        for cited, ran in (
            ("pytest", "cat pytest.ini"),
            ("ls", "false"),
            ("pytest tests/test_x.py", "echo pytest tests/test_x.py"),
            ("make test", "make test-unit"),
            ("ruff check foreman", "ruff check foreman/engine/verdict.py"),
            ("pytest tests/test_x.py", "pytest tests/test_x.pyc_missing"),
            ("./venv/bin/python -m pytest tests -q", "grep -rn './venv/bin/python -m pytest tests -q' docs/"),
            ("pytest tests", "pytest tests/test_x.py"),
        ):
            with self.subTest(cited=cited, ran=ran):
                self.assertFalse(command_was_run(cited, [ran]))

    def test_the_same_command_however_it_was_wrapped(self) -> None:
        for cited, ran in (
            ("pytest tests/test_x.py", "cd /w && pytest   tests/test_x.py -q"),
            ("pytest tests/test_x.py", "pytest tests/test_x.py 2>&1 | tail -20"),
            ("pytest tests/test_x.py", "pytest tests/test_x.py < /dev/null"),
            ("grep -n 'def check' foreman/engine/verdict.py",
             "/bin/bash -lc 'grep -n '\"'\"'def check'\"'\"' foreman/engine/verdict.py'"),
            ('grep -n "x y" f.py', "grep -n 'x y' f.py"),
            ("ruff check foreman && lint-imports", "ruff check foreman; lint-imports"),
        ):
            with self.subTest(cited=cited, ran=ran):
                self.assertTrue(command_was_run(cited, [ran]))
        self.assertTrue(command_was_run("a && b", ["a", "b"]))
        self.assertFalse(command_was_run("a && b", ["a"]))


class JudgementAndOldRolesTests(unittest.TestCase):
    setUp = BasisTests.setUp
    approve = BasisTests.approve
    def test_a_judgement_says_why(self) -> None:
        # The record itself refuses a blank evidence, whatever the role asks.
        bare = {"criterion": "It works", "status": "judgement", "evidence": "  "}
        for needs in ("checked", "ran", "stated"):
            with self.subTest(needs):
                reading = self.approve([bare], needs)
                self.assertEqual(reading.outcome, "error")
                self.assertIn("evidence", reading.detail)

    def test_a_reviewer_written_before_the_basis_is_taken_on_its_word(self) -> None:
        from foreman.definitions.roles import load_role_text

        text = (default_roles_dir() / "code_reviewer.toml").read_text(encoding="utf-8")
        start = text.index('[[completion.record.fields.fields]]\nname = "ran"')
        end = text.index("[[completion.record.fields]]", start)
        old = load_role_text(text[:start] + text[end:], "old.toml")
        record = "```foreman-record\n" + json.dumps({
            "criteria": [{"criterion": "a", "status": "verified", "evidence": "read the code"}],
            "findings": [],
        }) + "\n```"
        reading = read_completion(old, f"Looked.\n\n{record}\nAPPROVE", task_criteria=["a"])
        self.assertEqual(reading.outcome, "approve", reading.detail)

    def test_a_role_that_cannot_run_commands_cannot_ask_for_ran(self) -> None:
        from foreman.definitions.roles import RoleLoadError, load_role_text

        text = (default_roles_dir() / "triage_reviewer.toml").read_text(encoding="utf-8")
        with self.assertRaises(RoleLoadError) as caught:
            load_role_text(text.replace('approve_needs = "checked"', 'approve_needs = "ran"'), "t.toml")
        self.assertIn("could never approve", str(caught.exception))

    def test_the_prompt_says_the_roles_own_rule(self) -> None:
        from foreman.definitions.roles import load_role_text

        text = (default_roles_dir() / "code_reviewer.toml").read_text(encoding="utf-8")
        role = load_role_text(text.replace('approve_needs = "checked"', 'approve_needs = "ran"'), "r.toml")
        prompt = role.render_prompt({"developer_report": "r", "acceptance_criteria": "c"})
        self.assertIn(APPROVE_NEEDS_RULES["ran"], prompt)


class CriteriaTextTests(unittest.TestCase):
    def test_a_bullet_that_wraps_is_one_criterion(self) -> None:
        text = "- The first one,\n  which wraps.\n- The second.\n"
        self.assertEqual(criteria_items(text), ["The first one, which wraps.", "The second."])
        self.assertEqual(criteria_items("one\ntwo"), ["one", "two"])

    def test_each_criterion_must_be_listed_once(self) -> None:
        items = ["The loader rejects a bad declaration", "The page shows the report"]
        fields = {"criteria": [{"criterion": items[0]}, {"criterion": items[0]}]}
        self.assertEqual(missing_criteria(fields, items), [items[1]])
        fields = {"criteria": [{"criterion": "the loader rejects a bad declaration."}, {"criterion": "The page shows the report"}]}
        self.assertEqual(missing_criteria(fields, items), [])


if __name__ == "__main__":
    unittest.main()
