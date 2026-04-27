"""Workflow loader support for Foreman."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._toml import load_toml_file
from .errors import ForemanError

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Role-specific valid outcome sets for workflow validation
_VALID_OUTCOMES: dict[str, set[str]] = {
    "_builtin:merge": {"success", "failure", "conflict"},
    "_builtin:run_tests": {"success", "failure"},
    "_builtin:mark_done": {"success"},
    "_builtin:human_gate": {"paused"},
    "_builtin:orchestrator": {"done", "blocked", "error"},
    "developer": {"done", "blocked", "error"},
    "code_reviewer": {"approve", "deny", "steer"},
    "security_reviewer": {"approve", "deny"},
}


class WorkflowLoadError(ForemanError):
    """Raised when a workflow definition cannot be loaded or validated."""


@dataclass(slots=True)
class WorkflowStep:
    """One named workflow step."""

    id: str
    role: str


@dataclass(slots=True)
class WorkflowTransition:
    """One directed workflow edge."""

    from_step: str
    trigger: str
    to_step: str
    carry_output: bool = False


@dataclass(slots=True)
class WorkflowGate:
    """One workflow gate declaration."""

    trigger: str
    action: str
    message: str


@dataclass(slots=True)
class WorkflowFallback:
    """Fallback behavior when no transition matches."""

    action: str
    message: str


@dataclass(slots=True)
class WorkflowDefinition:
    """One declarative workflow loaded from TOML."""

    id: str
    name: str
    methodology: str
    steps: tuple[WorkflowStep, ...]
    transitions: tuple[WorkflowTransition, ...]
    gates: tuple[WorkflowGate, ...]
    fallback: WorkflowFallback | None
    source_path: Path

    @property
    def entry_step(self) -> str:
        """Return the workflow entry step."""

        return self.steps[0].id

    def get_step(self, step_id: str) -> WorkflowStep | None:
        """Return one step by identifier."""

        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def find_transition(self, step_id: str, outcome: str) -> WorkflowTransition | None:
        """Return the completion transition for one outcome, if present."""

        return self.find_transition_by_trigger(step_id, f"completion:{outcome}")

    def validate(self) -> list[str]:
        """Validate the workflow definition and return a list of error messages.

        Validation checks:
        - builtin role steps support listed outcomes
        - reviewer role transitions include only valid reviewer outcomes
        - terminal _builtin:mark_done has no outgoing transition
        - every non-terminal step has at least one outgoing transition
        - duplicate transition triggers are rejected
        - each step only emits outcomes that match its role's contract
        """
        errors: list[str] = []
        step_ids = {step.id for step in self.steps}

        # Check all transition targets exist
        for transition in self.transitions:
            if transition.from_step not in step_ids:
                errors.append(f"Transition from unknown step {transition.from_step!r}.")
            if transition.to_step not in step_ids:
                errors.append(f"Transition to unknown step {transition.to_step!r}.")

        # Check for duplicate transition triggers
        seen_triggers: dict[str, str] = {}
        for transition in self.transitions:
            key = (transition.from_step, transition.trigger)
            if key in seen_triggers:
                errors.append(
                    f"Duplicate transition trigger {transition.trigger!r} "
                    f"from {transition.from_step!r} (first: {seen_triggers[key]!r}, "
                    f"second: {transition.to_step!r})."
                )
            seen_triggers[key] = transition.to_step

        # Group transitions by from_step for coverage checks
        outgoing: dict[str, list[WorkflowTransition]] = {}
        for transition in self.transitions:
            outgoing.setdefault(transition.from_step, []).append(transition)

        for step in self.steps:
            if step.role == "_builtin:mark_done":
                if step.id in outgoing and outgoing[step.id]:
                    errors.append(
                        f"Terminal step {step.id!r} (_builtin:mark_done) has "
                        f"{len(outgoing[step.id])} outgoing transition(s); it should be terminal."
                    )
                continue

            if step.id not in outgoing or not outgoing[step.id]:
                errors.append(
                    f"Non-terminal step {step.id!r} has no outgoing transitions."
                )
                continue

            # For builtin roles and known roles, validate outcomes against contract
            if step.role in _VALID_OUTCOMES:
                valid_outcomes = _VALID_OUTCOMES[step.role]
                for transition in outgoing[step.id]:
                    trigger_outcome = transition.trigger.removeprefix("completion:")
                    if trigger_outcome not in valid_outcomes:
                        errors.append(
                            f"Step {step.id!r} (role {step.role!r}) has transition with "
                            f"invalid outcome {trigger_outcome!r}. Expected one of {valid_outcomes}."
                        )
            elif step.role.startswith("_builtin:"):
                # Unknown builtin — allow generic outcomes
                for transition in outgoing[step.id]:
                    trigger_outcome = transition.trigger.removeprefix("completion:")
                    if trigger_outcome not in {
                        "success", "failure", "error", "blocked",
                        "done", "approve", "deny", "steer", "paused",
                        "conflict",
                    }:
                        errors.append(
                            f"Builtin step {step.id!r} has transition with "
                            f"unrecognized outcome {trigger_outcome!r}."
                        )

        return errors

    def find_transition_by_trigger(
        self,
        step_id: str,
        trigger: str,
    ) -> WorkflowTransition | None:
        """Return the transition matching one step and trigger, if present."""

        for transition in self.transitions:
            if transition.from_step == step_id and transition.trigger == trigger:
                return transition
        return None


def default_workflows_dir() -> Path:
    """Return the shipped workflows directory."""

    return _REPO_ROOT / "workflows"


def load_workflow(
    path: str | Path,
    *,
    available_role_ids: Collection[str] | None = None,
) -> WorkflowDefinition:
    """Load one workflow definition from disk."""

    workflow_path = Path(path)
    data = load_toml_file(workflow_path)

    try:
        workflow_data = _require_mapping(data, "workflow", workflow_path)
    except KeyError as exc:
        raise WorkflowLoadError(
            f"{workflow_path}: missing required section {exc.args[0]!r}."
        ) from exc

    steps_data = _require_table_array(data.get("steps"), "steps", workflow_path)
    transitions_data = _require_table_array(
        data.get("transitions"),
        "transitions",
        workflow_path,
        default=(),
    )
    gates_data = _require_table_array(data.get("gates"), "gates", workflow_path, default=())

    steps = tuple(
        WorkflowStep(
            id=_require_string(step_data, "id", workflow_path),
            role=_require_string(step_data, "role", workflow_path),
        )
        for step_data in steps_data
    )
    if not steps:
        raise WorkflowLoadError(f"{workflow_path}: workflow must declare at least one step.")

    step_ids = [step.id for step in steps]
    duplicate_step_ids = _duplicates(step_ids)
    if duplicate_step_ids:
        raise WorkflowLoadError(
            f"{workflow_path}: duplicate step ids: {', '.join(sorted(duplicate_step_ids))}."
        )

    known_roles = set(available_role_ids or ())
    if available_role_ids is not None:
        for step in steps:
            if step.role.startswith("_builtin:"):
                continue
            if step.role not in known_roles:
                raise WorkflowLoadError(
                    f"{workflow_path}: step {step.id!r} references unknown role {step.role!r}."
                )

    transitions = tuple(
        WorkflowTransition(
            from_step=_require_string(transition_data, "from", workflow_path),
            trigger=_require_string(transition_data, "trigger", workflow_path),
            to_step=_require_string(transition_data, "to", workflow_path),
            carry_output=_require_bool(
                transition_data,
                "carry_output",
                workflow_path,
                default=False,
            ),
        )
        for transition_data in transitions_data
    )
    transition_keys: set[tuple[str, str]] = set()
    valid_step_ids = set(step_ids)
    for transition in transitions:
        if transition.from_step not in valid_step_ids:
            raise WorkflowLoadError(
                f"{workflow_path}: transition from unknown step {transition.from_step!r}."
            )
        if transition.to_step not in valid_step_ids:
            raise WorkflowLoadError(
                f"{workflow_path}: transition to unknown step {transition.to_step!r}."
            )
        key = (transition.from_step, transition.trigger)
        if key in transition_keys:
            raise WorkflowLoadError(
                f"{workflow_path}: duplicate transition for step {transition.from_step!r} and trigger {transition.trigger!r}."
            )
        transition_keys.add(key)

    gates = tuple(
        WorkflowGate(
            trigger=_require_string(gate_data, "trigger", workflow_path),
            action=_require_string(gate_data, "action", workflow_path),
            message=_require_string(gate_data, "message", workflow_path),
        )
        for gate_data in gates_data
    )
    duplicate_gate_triggers = _duplicates([gate.trigger for gate in gates])
    if duplicate_gate_triggers:
        raise WorkflowLoadError(
            f"{workflow_path}: duplicate gate triggers: {', '.join(sorted(duplicate_gate_triggers))}."
        )

    fallback_data = data.get("fallback")
    fallback = None
    if fallback_data is not None:
        if not isinstance(fallback_data, dict):
            raise WorkflowLoadError(f"{workflow_path}: expected 'fallback' to be a table.")
        fallback = WorkflowFallback(
            action=_require_string(fallback_data, "action", workflow_path),
            message=_require_string(fallback_data, "message", workflow_path),
        )

    definition = WorkflowDefinition(
        id=_require_string(workflow_data, "id", workflow_path),
        name=_require_string(workflow_data, "name", workflow_path),
        methodology=_require_string(workflow_data, "methodology", workflow_path),
        steps=steps,
        transitions=transitions,
        gates=gates,
        fallback=fallback,
        source_path=workflow_path,
    )

    validation_errors = definition.validate()
    if validation_errors:
        raise WorkflowLoadError(
            f"{workflow_path}: validation errors: {'; '.join(validation_errors)}"
        )

    return definition


def load_workflows(
    directory: str | Path | None = None,
    *,
    available_role_ids: Collection[str] | None = None,
) -> dict[str, WorkflowDefinition]:
    """Load all workflow definitions from one directory."""

    workflows_dir = default_workflows_dir() if directory is None else Path(directory)
    if not workflows_dir.is_dir():
        raise WorkflowLoadError(f"{workflows_dir}: workflows directory does not exist.")

    workflows: dict[str, WorkflowDefinition] = {}
    for path in sorted(workflows_dir.glob("*.toml")):
        workflow = load_workflow(path, available_role_ids=available_role_ids)
        if workflow.id in workflows:
            raise WorkflowLoadError(
                f"{path}: duplicate workflow id {workflow.id!r}; already defined in {workflows[workflow.id].source_path}."
            )
        workflows[workflow.id] = workflow
    return workflows


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _require_mapping(data: Mapping[str, Any], key: str, path: Path) -> dict[str, Any]:
    value = data[key]
    if not isinstance(value, dict):
        raise WorkflowLoadError(f"{path}: expected {key!r} to be a table.")
    return value


def _require_table_array(
    value: Any,
    key: str,
    path: Path,
    *,
    default: tuple[()] | tuple[dict[str, Any], ...] = (),
) -> tuple[dict[str, Any], ...]:
    if value is None:
        return tuple(default)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise WorkflowLoadError(f"{path}: expected {key!r} to be an array of tables.")
    return tuple(value)


def _require_string(data: Mapping[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise WorkflowLoadError(f"{path}: expected {key!r} to be a string.")
    return value


def _require_bool(
    data: Mapping[str, Any],
    key: str,
    path: Path,
    *,
    default: bool,
) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise WorkflowLoadError(f"{path}: expected {key!r} to be a boolean.")
    return value
