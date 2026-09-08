"""Tests for the policy matrix: resolution order, validation, and defaults.

Nothing here runs an agent step. The matrix is a pure function of project
settings and one task, so the suite never reaches a ``claude`` or ``codex``
binary.
"""

from __future__ import annotations

import unittest

from foreman.models import Task, validate_executor_overrides
from foreman.policy import (
    GATE_DECISIONS,
    POLICY_DECISIONS,
    POLICY_DEFAULTS,
    POLICY_VALUES,
    PolicyError,
    PolicyMatrix,
    describe_resolution,
    is_valid_value,
)
from foreman.settings import ProjectSettings, SettingsError


def _task(**kwargs) -> Task:
    defaults = dict(id="task-1", sprint_id="sprint-1", project_id="project-1", title="T")
    defaults.update(kwargs)
    return Task(**defaults)


class PolicyDefaultsTests(unittest.TestCase):
    """A project that configures nothing gets the documented defaults."""

    def test_built_in_defaults_are_the_documented_ones(self) -> None:
        matrix = PolicyMatrix.from_settings({})
        resolved = matrix.resolve_all(task_type="feature")

        self.assertEqual(resolved["triage"].value, "human")
        self.assertEqual(resolved["plan_approval"].value, "human")
        self.assertEqual(resolved["merge_approval"].value, "auto")
        self.assertEqual(resolved["notification"].value, "attention")
        for decision in POLICY_DECISIONS:
            self.assertEqual(resolved[decision].source, "built_in_default", decision)

    def test_every_decision_has_a_default_and_a_value_set(self) -> None:
        self.assertEqual(set(POLICY_DEFAULTS), set(POLICY_DECISIONS))
        self.assertEqual(set(POLICY_VALUES), set(POLICY_DECISIONS))
        for decision, value in POLICY_DEFAULTS.items():
            self.assertIn(value, POLICY_VALUES[decision])

    def test_the_gate_decisions_are_a_subset_of_the_matrix(self) -> None:
        self.assertTrue(set(GATE_DECISIONS) <= set(POLICY_DECISIONS))

    def test_a_project_default_is_reported_as_explicitly_set(self) -> None:
        matrix = PolicyMatrix.from_settings({"merge_approval": "human"})
        decision = matrix.resolve("merge_approval")

        self.assertEqual(decision.value, "human")
        self.assertEqual(decision.source, "project_default")
        # A decision the project left alone still reads as a built-in.
        self.assertEqual(matrix.resolve("plan_approval").source, "built_in_default")

    def test_an_unknown_decision_is_refused(self) -> None:
        with self.assertRaises(PolicyError):
            PolicyMatrix.from_settings({}).resolve("deploy_approval")


class PolicyResolutionOrderTests(unittest.TestCase):
    """Override beats task-type rule beats project default."""

    matrix = PolicyMatrix.from_settings(
        {
            "merge_approval": "human",
            "notification": "all",
            "policy_rules": {
                "docs": {"merge_approval": "auto", "notification": "none"},
                "fix": {"triage": "auto"},
            },
        }
    )

    def test_a_task_type_rule_beats_the_project_default(self) -> None:
        decision = self.matrix.resolve("merge_approval", task_type="docs")

        self.assertEqual(decision.value, "auto")
        self.assertEqual(decision.source, "task_type_rule")
        self.assertEqual(decision.task_type, "docs")

    def test_a_task_type_without_a_rule_falls_back_to_the_default(self) -> None:
        decision = self.matrix.resolve("merge_approval", task_type="feature")

        self.assertEqual(decision.value, "human")
        self.assertEqual(decision.source, "project_default")

    def test_a_rule_only_covers_the_decisions_it_names(self) -> None:
        # `fix` names triage only, so notification still comes from the project.
        self.assertEqual(self.matrix.resolve("triage", task_type="fix").value, "auto")
        self.assertEqual(
            self.matrix.resolve("notification", task_type="fix").source,
            "project_default",
        )

    def test_a_task_override_beats_a_task_type_rule(self) -> None:
        decision = self.matrix.resolve(
            "merge_approval",
            task_type="docs",
            overrides={"policy": {"merge_approval": "human"}},
        )

        self.assertEqual(decision.value, "human")
        self.assertEqual(decision.source, "task_override")

    def test_the_legacy_gates_object_still_overrides_a_gate(self) -> None:
        decision = self.matrix.resolve(
            "merge_approval",
            task_type="docs",
            overrides={"gates": {"merge_approval": "human"}},
        )

        self.assertEqual(decision.value, "human")
        self.assertEqual(decision.source, "task_override")

    def test_policy_wins_over_gates_when_both_name_a_decision(self) -> None:
        decision = self.matrix.resolve(
            "merge_approval",
            overrides={
                "gates": {"merge_approval": "human"},
                "policy": {"merge_approval": "auto"},
            },
        )

        self.assertEqual(decision.value, "auto")

    def test_gates_never_overrides_a_non_gate_decision(self) -> None:
        # `gates` is the gate-only form; a stray key in it must not silently
        # start deciding triage.
        decision = self.matrix.resolve("triage", overrides={"gates": {"triage": "auto"}})

        self.assertEqual(decision.value, "human")
        self.assertEqual(decision.source, "built_in_default")

    def test_resolve_task_reads_the_tasks_type_and_overrides(self) -> None:
        task = _task(task_type="docs", executor_overrides={"policy": {"triage": "auto"}})

        resolved = self.matrix.resolve_task(task)

        self.assertEqual(resolved["triage"].value, "auto")
        self.assertEqual(resolved["triage"].source, "task_override")
        self.assertEqual(resolved["merge_approval"].value, "auto")
        self.assertEqual(resolved["merge_approval"].source, "task_type_rule")


class PolicyLenientReadTests(unittest.TestCase):
    """Reading settings never raises; a bad stored value lands on the default."""

    def test_an_invalid_stored_value_falls_back_to_the_built_in(self) -> None:
        matrix = PolicyMatrix.from_settings({"merge_approval": "sometimes"})

        decision = matrix.resolve("merge_approval")
        self.assertEqual(decision.value, "auto")
        self.assertEqual(decision.source, "built_in_default")

    def test_malformed_rules_are_dropped_entry_by_entry(self) -> None:
        matrix = PolicyMatrix.from_settings(
            {
                "policy_rules": {
                    "docs": {"merge_approval": "auto", "triage": "maybe"},
                    "fix": "not-an-object",
                }
            }
        )

        self.assertEqual(matrix.rules, {"docs": {"merge_approval": "auto"}})

    def test_settings_that_are_not_an_object_yield_the_defaults(self) -> None:
        matrix = PolicyMatrix.from_settings(None)

        self.assertEqual(
            {d: matrix.resolve(d).value for d in POLICY_DECISIONS}, POLICY_DEFAULTS
        )

    def test_an_invalid_override_value_is_ignored(self) -> None:
        decision = PolicyMatrix.from_settings({}).resolve(
            "notification", overrides={"policy": {"notification": "shout"}}
        )

        self.assertEqual(decision.source, "built_in_default")


class PolicySerializationTests(unittest.TestCase):
    def test_describe_reports_defaults_rules_and_the_vocabulary(self) -> None:
        described = PolicyMatrix.from_settings(
            {"triage": "auto", "policy_rules": {"docs": {"merge_approval": "auto"}}}
        ).describe()

        self.assertEqual(described["decisions"], list(POLICY_DECISIONS))
        self.assertEqual(described["built_in_defaults"], POLICY_DEFAULTS)
        self.assertEqual(
            described["defaults"]["triage"], {"value": "auto", "source": "project_default"}
        )
        self.assertEqual(described["rules"], {"docs": {"merge_approval": "auto"}})
        self.assertEqual(described["values"]["notification"], ["none", "attention", "all"])

    def test_describe_resolution_keeps_the_source_and_the_rule_type(self) -> None:
        matrix = PolicyMatrix.from_settings(
            {"policy_rules": {"docs": {"merge_approval": "human"}}}
        )

        payload = describe_resolution(matrix.resolve_all(task_type="docs"))

        self.assertEqual(list(payload), list(POLICY_DECISIONS))
        self.assertEqual(
            payload["merge_approval"],
            {"value": "human", "source": "task_type_rule", "task_type": "docs"},
        )
        self.assertEqual(payload["triage"], {"value": "human", "source": "built_in_default"})


class PolicySettingsValidationTests(unittest.TestCase):
    """`ProjectSettings` is strict where the matrix reader is lenient."""

    def test_the_new_defaults_land_on_the_settings_object(self) -> None:
        settings = ProjectSettings.from_raw({})

        self.assertEqual(settings.triage, "human")
        self.assertEqual(settings.notification, "attention")
        self.assertEqual(settings.policy_rules, {})

    def test_valid_rules_round_trip(self) -> None:
        rules = {"docs": {"merge_approval": "auto"}, "fix": {"triage": "auto"}}

        self.assertEqual(ProjectSettings.from_raw({"policy_rules": rules}).policy_rules, rules)

    def test_an_invalid_decision_value_is_refused(self) -> None:
        for raw in ({"triage": "yes"}, {"notification": "loud"}, {"merge_approval": True}):
            with self.subTest(raw=raw), self.assertRaises(SettingsError):
                ProjectSettings.from_raw(raw)

    def test_rules_are_checked_key_by_key(self) -> None:
        bad = [
            {"policy_rules": []},
            {"policy_rules": {"not-a-task-type": {"triage": "auto"}}},
            {"policy_rules": {"docs": "auto"}},
            {"policy_rules": {"docs": {"deploy_approval": "auto"}}},
            {"policy_rules": {"docs": {"triage": "maybe"}}},
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(SettingsError):
                ProjectSettings.from_raw(raw)

    def test_is_valid_value_matches_the_vocabulary(self) -> None:
        self.assertTrue(is_valid_value("notification", "all"))
        self.assertFalse(is_valid_value("notification", "auto"))
        self.assertFalse(is_valid_value("triage", None))


class PolicyOverrideValidationTests(unittest.TestCase):
    """`executor_overrides` accepts the new `policy` object and the old `gates`."""

    def test_policy_and_gates_both_survive_validation(self) -> None:
        value = validate_executor_overrides(
            {
                "gates": {"merge_approval": "human"},
                "policy": {"triage": "auto", "notification": "all"},
            }
        )

        self.assertEqual(value["gates"], {"merge_approval": "human"})
        self.assertEqual(value["policy"], {"triage": "auto", "notification": "all"})

    def test_an_unknown_decision_or_value_is_refused(self) -> None:
        for value in (
            {"policy": {"deploy_approval": "auto"}},
            {"policy": {"triage": "maybe"}},
            {"policy": ["triage"]},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_executor_overrides(value)

    def test_an_empty_policy_object_is_dropped(self) -> None:
        self.assertEqual(validate_executor_overrides({"policy": {}}), {})


if __name__ == "__main__":
    unittest.main()
