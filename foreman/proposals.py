"""Changes the manager proposes and a person confirms (ADR-0022).

A proposal is an ordered list of operations from a fixed vocabulary, each of
which is one operation of the mutation service (``foreman.mutations``), with
a one-paragraph reason. Nothing in it happens until a person confirms it.

- ``Proposals.create`` checks the shape of every operation, that every task
  and sprint it names exists in the project, and then applies the operations
  in order inside a transaction that is always rolled back: a dry run, so an
  operation that depends on an earlier one (accept, then plan) is judged on
  the state the earlier one leaves. A refusal is reported with the
  operation's position and the reason, and nothing is stored.
- ``Proposals.confirm`` applies them again, in order, in one transaction,
  with the confirming person as the actor. If one is refused the transaction
  is rolled back, nothing is applied, and the proposal is marked ``failed``
  saying which operation and why.
- ``Proposals.decline`` records who declined it.

Surfaces translate ``ProposalError`` into their own error type. Nothing here
prints or knows about HTTP.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .errors import ForemanError
from .models import PROPOSAL_STATES, Project, Proposal
from .mutations import Mutations, MutationError
from .store import ForemanStore

#: Default page size for a project's proposals.
PROPOSAL_PAGE_LIMIT = 25

#: Set by the runner of a manager turn (``foreman.meta_agent``): the project
#: the session belongs to, and the conversation turn it is answering.
MANAGER_SESSION_ENV = "FOREMAN_MANAGER_SESSION"
MANAGER_TURN_ENV = "FOREMAN_MANAGER_TURN"

#: Who a proposal made inside a manager session is from.
MANAGER = "manager"


class ProposalError(ForemanError):
    """A proposal, or one of its operations, was refused. The message says why."""

    def __init__(self, message: str, *, index: int | None = None, kind: str | None = None) -> None:
        super().__init__(message)
        self.index = index
        self.kind = kind


class ProposalNotFound(ProposalError):
    """No proposal, project, task or sprint by that id."""


@dataclass(frozen=True)
class _Field:
    name: str
    type: str  # "id", "text", "words", "int", "bool", "ids", "new_sprint"
    required: bool = False


@dataclass(frozen=True)
class OperationKind:
    """One kind of operation: its fields, and how a person says it."""

    kind: str
    words: str
    fields: tuple[_Field, ...]
    #: At least one of these optional fields must be given.
    one_of: tuple[str, ...] = ()
    #: Exactly one of these must be given.
    exactly_one: tuple[str, ...] = ()


def _req(name: str, type_: str) -> _Field:
    return _Field(name, type_, True)


def _opt(name: str, type_: str) -> _Field:
    return _Field(name, type_, False)


_TASK_EDITS = (
    _opt("title", "words"),
    _opt("task_type", "words"),
    _opt("description", "text"),
    _opt("acceptance_criteria", "text"),
    _opt("priority", "int"),
)

#: The vocabulary, in the order the ADR lists it.
OPERATION_KINDS: dict[str, OperationKind] = {
    spec.kind: spec
    for spec in (
        OperationKind("create_sprint", "create a sprint", (_req("title", "words"), _opt("goal", "text"))),
        OperationKind(
            "edit_sprint",
            "edit a sprint",
            (_req("sprint_id", "id"), _opt("title", "words"), _opt("goal", "text")),
            one_of=("title", "goal"),
        ),
        OperationKind("activate_sprint", "activate a sprint", (_req("sprint_id", "id"),)),
        OperationKind("finish_sprint", "finish a sprint", (_req("sprint_id", "id"),)),
        OperationKind(
            "file_task",
            "file a task in the backlog",
            (
                _req("title", "words"),
                _opt("task_type", "words"),
                _opt("description", "text"),
                _opt("acceptance_criteria", "text"),
                _opt("priority", "int"),
                _opt("complexity", "words"),
                _opt("accept", "bool"),
            ),
        ),
        OperationKind("accept_task", "accept filed work", (_req("task_id", "id"),)),
        OperationKind("decline_task", "decline filed work", (_req("task_id", "id"), _opt("reason", "text"))),
        OperationKind(
            "plan_tasks",
            "plan tasks into a sprint",
            (_req("task_ids", "ids"), _opt("sprint_id", "id"), _opt("new_sprint", "new_sprint")),
            exactly_one=("sprint_id", "new_sprint"),
        ),
        OperationKind("unplan_task", "move a task back to the backlog", (_req("task_id", "id"),)),
        OperationKind(
            "edit_task",
            "edit a task",
            (_req("task_id", "id"), *_TASK_EDITS),
            one_of=tuple(field.name for field in _TASK_EDITS),
        ),
        OperationKind("block_task", "block a task", (_req("task_id", "id"), _req("reason", "words"))),
        OperationKind("unblock_task", "unblock a task", (_req("task_id", "id"),)),
        OperationKind("cancel_task", "cancel a task", (_req("task_id", "id"),)),
        OperationKind(
            "send_back", "send a task back with guidance", (_req("task_id", "id"), _req("guidance", "words"))
        ),
        OperationKind("approve_gate", "approve a waiting gate", (_req("task_id", "id"),)),
    )
}


def manager_session() -> str | None:
    """The project of the manager session this process runs in, or None."""

    return (os.environ.get(MANAGER_SESSION_ENV) or "").strip() or None


def manager_turn() -> str | None:
    """The manager turn this process runs in, or None."""

    return (os.environ.get(MANAGER_TURN_ENV) or "").strip() or None


# ── shape ────────────────────────────────────────────────────────────────


def _label(index: int, kind: str | None) -> str:
    spec = OPERATION_KINDS.get(kind or "")
    return f"Operation {index + 1}" + (f" ({spec.words})" if spec else "")


def _check_value(field: _Field, value: Any, where: str) -> Any:
    if field.type == "id" or field.type == "words":
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{where}: {field.name} must be a non-empty string.")
        return value.strip()
    if field.type == "text":
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{where}: {field.name} must be a string.")
        return value
    if field.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{where}: {field.name} must be an integer.")
        return value
    if field.type == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{where}: {field.name} must be true or false.")
        return value
    if field.type == "ids":
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) and item.strip() for item in value)
        ):
            raise ValueError(f"{where}: {field.name} must be a non-empty list of ids.")
        return [item.strip() for item in value]
    if field.type == "new_sprint":
        if not isinstance(value, Mapping):
            raise ValueError(f"{where}: new_sprint must be an object with a title.")
        unknown = sorted(set(value) - {"title", "goal"})
        if unknown:
            raise ValueError(f"{where}: new_sprint has unknown fields: {', '.join(unknown)}.")
        title = value.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"{where}: new_sprint.title must be a non-empty string.")
        goal = value.get("goal")
        if goal is not None and not isinstance(goal, str):
            raise ValueError(f"{where}: new_sprint.goal must be a string.")
        return {"title": title.strip(), **({"goal": goal} if goal is not None else {})}
    raise AssertionError(field.type)


def normalize_operations(operations: Any) -> list[dict[str, Any]]:
    """Return the operations with their shape checked, or raise ``ProposalError``."""

    if not isinstance(operations, list) or not operations:
        raise ProposalError("A proposal needs at least one operation (a non-empty list).")
    normalized: list[dict[str, Any]] = []
    for index, operation in enumerate(operations):
        if not isinstance(operation, Mapping):
            raise ProposalError(f"Operation {index + 1} must be an object.", index=index)
        kind = operation.get("kind")
        spec = OPERATION_KINDS.get(kind) if isinstance(kind, str) else None
        if spec is None:
            raise ProposalError(
                f"Operation {index + 1}: unknown kind {kind!r}. Expected one of: "
                f"{', '.join(OPERATION_KINDS)}.",
                index=index,
            )
        where = _label(index, kind)
        known = {field.name: field for field in spec.fields}
        unknown = sorted(set(operation) - set(known) - {"kind"})
        if unknown:
            raise ProposalError(
                f"{where}: unknown fields: {', '.join(unknown)}.", index=index, kind=kind
            )
        clean: dict[str, Any] = {"kind": kind}
        try:
            for field in spec.fields:
                if field.name not in operation or operation[field.name] is None and not field.required:
                    if field.required:
                        raise ValueError(f"{where}: {field.name} is required.")
                    continue
                clean[field.name] = _check_value(field, operation[field.name], where)
        except ValueError as exc:
            raise ProposalError(str(exc), index=index, kind=kind) from exc
        if spec.one_of and not any(name in clean for name in spec.one_of):
            raise ProposalError(
                f"{where}: name at least one of {', '.join(spec.one_of)} to change.",
                index=index,
                kind=kind,
            )
        if spec.exactly_one and sum(name in clean for name in spec.exactly_one) != 1:
            raise ProposalError(
                f"{where}: give exactly one of {' or '.join(spec.exactly_one)}.",
                index=index,
                kind=kind,
            )
        normalized.append(clean)
    return normalized


def _named_ids(operation: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """The task ids and sprint ids an operation names."""

    tasks = list(operation.get("task_ids") or [])
    if operation.get("task_id"):
        tasks.append(operation["task_id"])
    sprints = [operation["sprint_id"]] if operation.get("sprint_id") else []
    return tasks, sprints


# ── applying ─────────────────────────────────────────────────────────────


def _task(store: ForemanStore, project: Project, task_id: str, where: str, index: int, kind: str):
    task = store.get_task(task_id)
    if task is None or task.project_id != project.id:
        raise ProposalError(
            f"{where}: there is no task {task_id} in project {project.id}.", index=index, kind=kind
        )
    return task


def _sprint(store: ForemanStore, project: Project, sprint_id: str, where: str, index: int, kind: str):
    sprint = store.get_sprint(sprint_id)
    if sprint is None or sprint.project_id != project.id:
        raise ProposalError(
            f"{where}: there is no sprint {sprint_id} in project {project.id}.",
            index=index,
            kind=kind,
        )
    return sprint


def apply_operation(
    store: ForemanStore,
    project: Project,
    mutations: Mutations,
    operation: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    """Apply one operation through the mutation service; return what it did.

    Reads every task and sprint afresh, so it sees what earlier operations
    did. A refusal is a ``ProposalError`` naming the operation.
    """

    kind = str(operation["kind"])
    where = _label(index, kind)
    result: dict[str, Any] = {"index": index, "kind": kind}

    def task(task_id: str):
        return _task(store, project, task_id, where, index, kind)

    def sprint(sprint_id: str):
        return _sprint(store, project, sprint_id, where, index, kind)

    try:
        if kind == "create_sprint":
            created = mutations.create_sprint(project, title=operation["title"], goal=operation.get("goal"))
            result["sprint_id"] = created.id
        elif kind == "edit_sprint":
            changes = {name: operation[name] for name in ("title", "goal") if name in operation}
            result["sprint_id"] = mutations.edit_sprint(sprint(operation["sprint_id"]), changes).id
        elif kind in ("activate_sprint", "finish_sprint"):
            target = "active" if kind == "activate_sprint" else "completed"
            result["sprint_id"] = mutations.transition_sprint(sprint(operation["sprint_id"]), target).id
        elif kind == "file_task":
            filed = mutations.file_task(
                project,
                title=operation["title"],
                task_type=operation.get("task_type", "feature"),
                description=operation.get("description"),
                acceptance_criteria=operation.get("acceptance_criteria"),
                priority=operation.get("priority", 0),
                complexity=operation.get("complexity"),
                accept=bool(operation.get("accept", False)),
            )
            result["task_id"] = filed.task.id
        elif kind == "accept_task":
            result["task_id"] = mutations.accept_task(task(operation["task_id"])).id
        elif kind == "decline_task":
            result["task_id"] = mutations.decline_task(
                task(operation["task_id"]), operation.get("reason")
            ).id
        elif kind == "plan_tasks":
            tasks = [task(task_id) for task_id in operation["task_ids"]]
            new_sprint = operation.get("new_sprint")
            planned = mutations.plan_tasks(
                tasks,
                sprint=sprint(operation["sprint_id"]) if operation.get("sprint_id") else None,
                new_sprint_title=new_sprint["title"] if new_sprint else None,
                new_sprint_goal=new_sprint.get("goal") if new_sprint else None,
            )
            result["sprint_id"] = planned.sprint.id
            result["created_sprint"] = planned.created_sprint
            result["task_ids"] = [planned_task.id for planned_task in planned.tasks]
        elif kind == "unplan_task":
            result["task_id"] = mutations.unplan_task(task(operation["task_id"])).id
        elif kind == "edit_task":
            changes = {name: operation[name] for name in OPERATION_KINDS[kind].one_of if name in operation}
            target = task(operation["task_id"])
            mutations.edit_task(target, changes)
            result["task_id"] = target.id
        elif kind == "block_task":
            result["task_id"] = mutations.block_task(task(operation["task_id"]), operation["reason"]).id
        elif kind == "unblock_task":
            result["task_id"] = mutations.unblock_task(task(operation["task_id"])).id
        elif kind == "cancel_task":
            removal = mutations.cancel_task(task(operation["task_id"]))
            result["task_id"] = removal.task.id
        elif kind == "send_back":
            result["task_id"] = mutations.send_back(task(operation["task_id"]), operation["guidance"]).id
        elif kind == "approve_gate":
            target = task(operation["task_id"])
            if target.status != "blocked":
                raise MutationError(
                    f"Task {target.id} is {target.status}, not waiting at a gate."
                )
            decision = mutations.decide_gate(target, "approve")
            result["task_id"] = decision.task.id
            result["next_step"] = decision.next_step
        else:  # pragma: no cover - normalize_operations refuses unknown kinds
            raise ProposalError(f"{where}: unknown kind {kind!r}.", index=index, kind=kind)
    except MutationError as exc:
        raise ProposalError(f"{where}: {exc}", index=index, kind=kind) from exc
    return result


def _names(store: ForemanStore, project: Project, operations: Sequence[Mapping[str, Any]], leaves: Sequence[str]) -> dict[str, Any]:
    """Titles and keys of what a proposal names, as they are now."""

    tasks: dict[str, Any] = {}
    sprints: dict[str, Any] = {}
    task_ids: list[str] = list(leaves)
    sprint_ids: list[str] = []
    for operation in operations:
        named_tasks, named_sprints = _named_ids(operation)
        task_ids += named_tasks
        sprint_ids += named_sprints
    for task_id in task_ids:
        found = store.get_task(task_id)
        if found is not None and found.project_id == project.id:
            tasks[task_id] = {
                "key": found.task_key or None,
                "title": found.title,
                "status": found.status,
                "sprint_id": found.sprint_id,
            }
            sprint_ids.append(found.sprint_id)
    for sprint_id in sprint_ids:
        found = store.get_sprint(sprint_id)
        if found is not None and found.project_id == project.id:
            sprints[sprint_id] = {
                "title": found.title,
                "status": found.status,
                "backlog": found.is_backlog,
            }
    return {"tasks": tasks, "sprints": sprints}


class Proposals:
    """Create, confirm and decline proposals for the projects of one store.

    ``via`` and ``actor`` are the surface and the person deciding, recorded
    on the proposal and, through the mutation service, on every change a
    confirmation makes.
    """

    def __init__(
        self,
        store: ForemanStore,
        *,
        via: str,
        actor: str | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.via = via
        self.actor = actor
        self._now = now or (lambda: datetime.now(timezone.utc))

    def create(
        self,
        project: Project,
        *,
        reason: Any,
        operations: Any,
        leaves: Any = None,
        proposed_by: str,
        session_id: str | None = None,
        turn_id: str | None = None,
    ) -> Proposal:
        """Check a proposal by applying it in a transaction that is rolled back, then store it."""

        clean_reason = reason.strip() if isinstance(reason, str) else ""
        if not clean_reason:
            raise ProposalError("A proposal needs a reason: one paragraph saying why.")
        normalized = normalize_operations(operations)
        if leaves is None:
            leaves = []
        if not isinstance(leaves, list) or not all(isinstance(item, str) and item.strip() for item in leaves):
            raise ProposalError("leaves must be a list of task ids.")
        clean_leaves = [item.strip() for item in leaves]
        for task_id in clean_leaves:
            found = self.store.get_task(task_id)
            if found is None or found.project_id != project.id:
                raise ProposalError(f"leaves: there is no task {task_id} in project {project.id}.")

        now = self._now()
        proposal = Proposal(
            id=f"prop-{now.strftime('%Y%m%d%H%M%S%f')}-{uuid4().hex[:8]}",
            project_id=project.id,
            proposed_by=proposed_by,
            reason=clean_reason,
            operations=normalized,
            leaves=clean_leaves,
            names=_names(self.store, project, normalized, clean_leaves),
            session_id=session_id,
            turn_id=turn_id,
            created_at=now.isoformat(),
        )
        dry_run = self._mutations(proposal)
        with self.store.atomic(commit=False):
            for index, operation in enumerate(normalized):
                apply_operation(self.store, project, dry_run, operation, index)
        return self.store.save_proposal(proposal)

    def confirm(self, proposal_id: str) -> Proposal:
        """Apply a proposal, whole or not at all, as the confirming person.

        Returns it ``confirmed``, or ``failed`` with the refused operation and
        why when one was refused; then nothing was applied.
        """

        proposal = self._require_open(proposal_id)
        project = self.store.get_project(proposal.project_id)
        if project is None:
            raise ProposalNotFound(f"Project not found: {proposal.project_id}")
        mutations = self._mutations(proposal)
        total = len(proposal.operations)
        try:
            with self.store.atomic():
                # Re-read inside the transaction: two people confirming at once
                # must not both apply it.
                proposal = self._require_open(proposal_id)
                applied = [
                    apply_operation(self.store, project, mutations, operation, index)
                    for index, operation in enumerate(proposal.operations)
                ]
                self._decide(
                    proposal,
                    "confirmed",
                    {
                        "applied": applied,
                        "sentence": f"Applied {_count(total, 'operation')}.",
                    },
                )
        except ProposalError as exc:
            if exc.index is None:
                raise
            failed = self._require_open(proposal_id)
            spec = OPERATION_KINDS.get(exc.kind or "")
            self._decide(
                failed,
                "failed",
                {
                    "applied": [],
                    "failed": {
                        "index": exc.index,
                        "kind": exc.kind,
                        "reason": _reason_of(exc),
                    },
                    "sentence": (
                        f"Operation {exc.index + 1} of {total}"
                        + (f" ({spec.words})" if spec else "")
                        + f" was refused: {_reason_of(exc)} Nothing was applied."
                    ),
                },
            )
            return failed
        warnings = [warning for warning in (run() for run in mutations.deferred) if warning]
        if warnings:
            proposal.outcome["warnings"] = warnings
            self.store.save_proposal(proposal)
        return proposal

    def decline(self, proposal_id: str) -> Proposal:
        """Record that a person declined a proposal. Nothing else changes."""

        proposal = self._require_open(proposal_id)
        self._decide(proposal, "declined", {"applied": [], "sentence": "Declined. Nothing was changed."})
        return proposal

    def _decide(self, proposal: Proposal, state: str, outcome: dict[str, Any]) -> None:
        proposal.state = state
        # Who, when known; the dashboard has no identity yet, and the surface
        # is not a person, so it is kept apart in the outcome.
        proposal.decided_by = self.actor
        proposal.decided_at = self._now().isoformat()
        proposal.outcome = {"via": self.via, **outcome}
        self.store.save_proposal(proposal)

    def _require_open(self, proposal_id: str) -> Proposal:
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            raise ProposalNotFound(f"Proposal not found: {proposal_id}")
        if proposal.state != "proposed":
            raise ProposalError(
                f"Proposal {proposal_id} is already {proposal.state}"
                + (f" by {proposal.decided_by}" if proposal.decided_by else "")
                + "; only a proposed one can be confirmed or declined."
            )
        return proposal

    def _mutations(self, proposal: Proposal) -> Mutations:
        return Mutations(
            self.store,
            via=self.via,
            actor=self.actor,
            now=self._now,
            proposal_id=proposal.id,
            defer_side_effects=True,
        )


def _reason_of(exc: ProposalError) -> str:
    """The refusal without the "Operation N (...): " prefix, ending with a full stop."""

    text = str(exc)
    if exc.index is not None:
        prefix = _label(exc.index, exc.kind) + ": "
        if text.startswith(prefix):
            text = text[len(prefix) :]
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


# ── reading ──────────────────────────────────────────────────────────────


def serialize_proposal(proposal: Proposal) -> dict[str, Any]:
    """One proposal as the API and ``--json`` show it."""

    return {
        "id": proposal.id,
        "project_id": proposal.project_id,
        "state": proposal.state,
        "proposed_by": proposal.proposed_by,
        "session_id": proposal.session_id,
        "turn_id": proposal.turn_id,
        "reason": proposal.reason,
        "operations": proposal.operations,
        "leaves": proposal.leaves,
        "names": proposal.names,
        "created_at": proposal.created_at,
        "decided_by": proposal.decided_by,
        "decided_at": proposal.decided_at,
        "outcome": proposal.outcome or None,
    }


def read_proposals(
    store: ForemanStore,
    project: Project,
    *,
    states: Sequence[str] | None = None,
    limit: int | None = PROPOSAL_PAGE_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """One page of a project's proposals, newest first, and how many match."""

    unknown = sorted(set(states or ()) - set(PROPOSAL_STATES))
    if unknown:
        raise ProposalError(
            f"state: unknown {', '.join(unknown)}; expected {', '.join(PROPOSAL_STATES)}."
        )
    proposals, total = store.page_proposals(
        project.id, states=list(states or ()), limit=limit, offset=offset
    )
    return {
        "project_id": project.id,
        "proposals": [serialize_proposal(proposal) for proposal in proposals],
        "total": total,
    }
