"""The policy matrix: where a person is required, decided per task.

Autonomy in Foreman is a policy, not a mode. Four decisions describe it:

``triage``
    Does work filed by another system wait for a person before it becomes
    runnable (``human``), or does it go straight to ``todo`` (``auto``)?
``plan_approval`` / ``merge_approval``
    Does the workflow gate of that name pause for a person (``human``), or
    may the engine approve it itself with an audit record (``auto``)?
``notification``
    How loudly does the project want to be told: ``none``, ``attention``
    (engine attention turns and human gates), or ``all`` (also task done)?

Each decision is resolved from three layers, most specific first:

1. the task's ``executor_overrides`` (``policy``, or the older gate-only
   ``gates`` object),
2. a per-task-type rule from the ``policy_rules`` project setting,
3. the project default setting for that decision, else the built-in default.

Resolution reports *where* the value came from as well as what it is, so the
audit trail can answer "why was a human asked?" rather than only "was one".

Reading is deliberately lenient: settings are validated at write time by
:class:`foreman.settings.ProjectSettings`, and a matrix built from a row that
predates a validator (or was edited by hand) must still yield a safe answer
rather than raise mid-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

#: The decisions the matrix answers, in the order surfaces display them.
POLICY_DECISIONS: tuple[str, ...] = (
    "triage",
    "plan_approval",
    "merge_approval",
    "notification",
)

#: Allowed values per decision.
POLICY_VALUES: dict[str, tuple[str, ...]] = {
    "triage": ("auto", "human"),
    "plan_approval": ("auto", "human"),
    "merge_approval": ("auto", "human"),
    "notification": ("none", "attention", "all"),
}

#: Built-in default per decision, used when the project sets nothing.
POLICY_DEFAULTS: dict[str, str] = {
    "triage": "human",
    "plan_approval": "human",
    "merge_approval": "auto",
    "notification": "attention",
}

#: The subset of decisions a workflow gate step may name as its ``policy``.
GATE_DECISIONS: tuple[str, ...] = ("plan_approval", "merge_approval")

#: Where a resolved value came from.
SOURCE_TASK_OVERRIDE = "task_override"
SOURCE_TASK_TYPE_RULE = "task_type_rule"
SOURCE_PROJECT_DEFAULT = "project_default"
SOURCE_BUILT_IN_DEFAULT = "built_in_default"


class PolicyError(ValueError):
    """Raised when a policy decision or value is not part of the matrix."""


def is_valid_value(decision: str, value: Any) -> bool:
    """Return whether ``value`` is an allowed value for ``decision``."""

    return isinstance(value, str) and value in POLICY_VALUES.get(decision, ())


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """One resolved decision and the layer that decided it."""

    decision: str
    value: str
    source: str
    #: The task type whose rule applied, set only for ``task_type_rule``.
    task_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"value": self.value, "source": self.source}
        if self.task_type is not None:
            payload["task_type"] = self.task_type
        return payload


@dataclass(frozen=True, slots=True)
class PolicyMatrix:
    """The project's resolved defaults plus its per-task-type rules."""

    defaults: Mapping[str, str]
    rules: Mapping[str, Mapping[str, str]]
    #: Decisions the project set explicitly; the rest fall back to built-ins.
    explicit_defaults: frozenset[str] = frozenset()

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any] | None) -> PolicyMatrix:
        """Build a matrix from a project's raw settings object.

        Unknown decisions, task types, and values are dropped rather than
        rejected: a stored setting the validator would refuse must not stop a
        run, and dropping it lands on the safer built-in default.
        """

        raw = settings if isinstance(settings, Mapping) else {}
        defaults: dict[str, str] = dict(POLICY_DEFAULTS)
        explicit: set[str] = set()
        for decision in POLICY_DECISIONS:
            value = raw.get(decision)
            if is_valid_value(decision, value):
                defaults[decision] = str(value)
                explicit.add(decision)
        return cls(
            defaults=defaults,
            rules=_clean_rules(raw.get("policy_rules")),
            explicit_defaults=frozenset(explicit),
        )

    @classmethod
    def for_project(cls, project: Any) -> PolicyMatrix:
        """Build a matrix from a :class:`foreman.models.Project`."""

        return cls.from_settings(getattr(project, "settings", None))

    def resolve(
        self,
        decision: str,
        *,
        task_type: str | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> PolicyDecision:
        """Resolve one decision for a task type and its executor overrides."""

        if decision not in POLICY_VALUES:
            raise PolicyError(
                f"Unknown policy decision {decision!r}; expected one of "
                f"{', '.join(POLICY_DECISIONS)}."
            )
        override = _override_value(decision, overrides)
        if override is not None:
            return PolicyDecision(decision, override, SOURCE_TASK_OVERRIDE)
        if task_type:
            rule = self.rules.get(task_type, {})
            value = rule.get(decision)
            if is_valid_value(decision, value):
                return PolicyDecision(
                    decision, str(value), SOURCE_TASK_TYPE_RULE, task_type=task_type
                )
        source = (
            SOURCE_PROJECT_DEFAULT
            if decision in self.explicit_defaults
            else SOURCE_BUILT_IN_DEFAULT
        )
        return PolicyDecision(decision, self.defaults[decision], source)

    def resolve_all(
        self,
        *,
        task_type: str | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, PolicyDecision]:
        """Resolve every decision for one task type and override set."""

        return {
            decision: self.resolve(decision, task_type=task_type, overrides=overrides)
            for decision in POLICY_DECISIONS
        }

    def resolve_task(self, task: Any) -> dict[str, PolicyDecision]:
        """Resolve every decision for one :class:`foreman.models.Task`."""

        return self.resolve_all(
            task_type=getattr(task, "task_type", None),
            overrides=getattr(task, "executor_overrides", None),
        )

    def describe(self) -> dict[str, Any]:
        """Serialize the project side of the matrix for the API and the UI."""

        return {
            "decisions": list(POLICY_DECISIONS),
            "values": {d: list(v) for d, v in POLICY_VALUES.items()},
            "built_in_defaults": dict(POLICY_DEFAULTS),
            "defaults": {
                decision: {
                    "value": self.defaults[decision],
                    "source": (
                        SOURCE_PROJECT_DEFAULT
                        if decision in self.explicit_defaults
                        else SOURCE_BUILT_IN_DEFAULT
                    ),
                }
                for decision in POLICY_DECISIONS
            },
            "rules": {
                task_type: dict(rule) for task_type, rule in sorted(self.rules.items())
            },
        }


def describe_resolution(resolved: Mapping[str, PolicyDecision]) -> dict[str, Any]:
    """Serialize a resolved matrix for an event payload or an API response."""

    return {
        decision: resolved[decision].as_dict()
        for decision in POLICY_DECISIONS
        if decision in resolved
    }


def _override_value(decision: str, overrides: Mapping[str, Any] | None) -> str | None:
    """Return the per-task override for one decision, if any.

    ``executor_overrides.policy`` carries any decision. ``gates`` is the older
    gate-only object and still works for the two gate decisions; ``policy``
    wins when both name the same decision.
    """

    if not isinstance(overrides, Mapping):
        return None
    policy = overrides.get("policy")
    if isinstance(policy, Mapping) and is_valid_value(decision, policy.get(decision)):
        return str(policy[decision])
    if decision in GATE_DECISIONS:
        gates = overrides.get("gates")
        if isinstance(gates, Mapping) and is_valid_value(decision, gates.get(decision)):
            return str(gates[decision])
    return None


def _clean_rules(value: Any) -> dict[str, dict[str, str]]:
    """Keep only the well-formed entries of a ``policy_rules`` object."""

    if not isinstance(value, Mapping):
        return {}
    rules: dict[str, dict[str, str]] = {}
    for task_type, rule in value.items():
        if not isinstance(task_type, str) or not isinstance(rule, Mapping):
            continue
        cleaned = {
            decision: str(decision_value)
            for decision, decision_value in rule.items()
            if isinstance(decision, str) and is_valid_value(decision, decision_value)
        }
        if cleaned:
            rules[task_type] = cleaned
    return rules
