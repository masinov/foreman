"""Whether a route's facts hold on a task (ADR-0041 section 1).

The facts a route may name are listed in ``foreman.definitions.routes``. Here
they are read off a real task: its labels and criteria, the number of times
each step has been visited, and what its branch changed. What a change is: the
paths changed between the merge base of the task's branch with the default
branch and the branch's head. Git is asked once, and only when a route asks.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..definitions.routes import (
    CHANGED,
    CHANGED_ONLY,
    LABEL,
    NO_CRITERIA,
    VISITS,
    Fact,
    parse_fact,
)
from ..definitions.workflows import WorkflowDefinition, WorkflowTransition
from ..domain.labels import changed_in, changed_only_in, groups_of_paths
from ..domain.models import Project, Task
from ..domain.settings import settings_of
from ..repo.git import GitError, branch_changes, branch_exists


class TaskFacts:
    """The facts of one task, read when a route asks."""

    def __init__(self, project: Project, task: Task) -> None:
        self.project = project
        self.task = task
        self._groups_of_paths: dict[str, frozenset[str]] | None = None

    def holds(self, fact: Fact) -> bool:
        """Whether the fact holds, ``not:`` included."""

        return self._base(fact) != fact.negated

    def _base(self, fact: Fact) -> bool:
        if fact.kind == NO_CRITERIA:
            return not (self.task.acceptance_criteria or "").strip()
        if fact.kind == LABEL:
            return fact.names[0] in (self.task.labels or [])
        if fact.kind == VISITS:
            return int(self.task.step_visit_counts.get(fact.names[0], 0)) >= fact.count
        if fact.kind == CHANGED:
            return changed_in(self._changed(), fact.names[0])
        if fact.kind == CHANGED_ONLY:
            return changed_only_in(self._changed(), fact.names)
        raise ValueError(f"Unsupported fact {fact.text!r}.")

    def _changed(self) -> dict[str, frozenset[str]]:
        if self._groups_of_paths is None:
            paths: list[str] = []
            branch = self.task.branch_name
            if branch and branch_exists(self.project.repo_path, branch):
                try:
                    changes = branch_changes(
                        self.project.repo_path,
                        base_branch=self.project.default_branch,
                        branch_name=branch,
                    )
                except GitError as exc:
                    raise GitError(
                        f"Could not read what branch {branch!r} changed, which a route depends on: {exc}"
                    ) from exc
                paths = [change.path for change in changes]
            self._groups_of_paths = groups_of_paths(paths, settings_of(self.project).path_groups)
        return self._groups_of_paths


@dataclass(frozen=True, slots=True)
class RouteChoice:
    """The route taken, and the facts that chose it."""

    transition: WorkflowTransition
    #: Facts of the route taken that held (none for the default).
    held: tuple[str, ...]
    #: For the default: the facts of the routes before it that did not hold.
    not_held: tuple[str, ...]
    default: bool
    #: How many routes there were from the step on that trigger.
    routes: int


def choose_route(
    workflow: WorkflowDefinition, step: str, trigger: str, facts: TaskFacts
) -> RouteChoice | None:
    """The route taken from a step on a trigger, or None when there is none.

    Routes are tried in the file's order and the first whose facts all hold is
    taken; the default (no ``when``) is last, so it is taken when no other is.
    A route with no facts to choose among is returned without reading anything.
    """

    routes = workflow.routes_from(step, trigger)
    if not routes:
        return None
    not_held: list[str] = []
    for route in routes:
        parsed = [parse_fact(text) for text in route.when]
        results = [(fact, facts.holds(fact)) for fact in parsed]
        if all(holds for _, holds in results):
            return RouteChoice(
                transition=route,
                held=tuple(fact.text for fact, _ in results),
                not_held=tuple(dict.fromkeys(not_held)) if not route.when else (),
                default=not route.when,
                routes=len(routes),
            )
        not_held.extend(fact.text for fact, holds in results if not holds)
    # A workflow is validated to end in a default; if one did not, nothing is taken.
    return None
