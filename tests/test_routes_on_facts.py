"""Routes chosen by facts, and a routing step without an agent (ADR-0041 section 1, FOR-108).

A transition may carry ``when``; the routes of one step and trigger are tried
in the file's order and the first whose facts all hold is taken; the last is
the default. Validated before a workflow runs, evaluated on a real task and
git branch, recorded on the task with the facts that chose it.
"""

from __future__ import annotations

import unittest

from foreman.definitions.layers import save_workflow
from foreman.definitions.roles import branch_role_ids, load_roles
from foreman.definitions.routes import FactError, parse_fact, route_line
from foreman.definitions.workflows import (
    WorkflowLoadError,
    load_workflow_text,
    load_workflows,
)
from foreman.engine.errors import OrchestratorError
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.engine.results import AgentExecutionResult
from foreman.engine.route_facts import TaskFacts, choose_route
from foreman.mutations import Mutations
from foreman.mutations.projects import SettingError
from foreman.store import ForemanStore

from engine_support import OrchestratorTestCase, ScriptedAgentExecutor

OUTCOMES = {"developer": ["done"]}
BRANCH_ROLES = {"developer"}

HEAD = """
[workflow]
id = "routed"
name = "Routed"
methodology = "development"

[[steps]]
id = "route"
role = "_builtin:route"

[[steps]]
id = "plan"
role = "developer"

[[steps]]
id = "develop"
role = "developer"

[[steps]]
id = "test"
role = "_builtin:run_tests"

[[steps]]
id = "docs_test"
role = "_builtin:run_tests"

[[steps]]
id = "merge"
role = "_builtin:merge"

[[steps]]
id = "done"
role = "_builtin:mark_done"
"""

TAIL = """
[[transitions]]
from = "plan"
trigger = "completion:done"
to = "develop"

[[transitions]]
from = "test"
trigger = "completion:success"
to = "merge"

[[transitions]]
from = "test"
trigger = "completion:failure"
to = "develop"

[[transitions]]
from = "docs_test"
trigger = "completion:success"
to = "merge"

[[transitions]]
from = "docs_test"
trigger = "completion:failure"
to = "develop"

[[transitions]]
from = "merge"
trigger = "completion:success"
to = "done"

[[transitions]]
from = "merge"
trigger = "completion:failure"
to = "develop"

[[transitions]]
from = "merge"
trigger = "completion:conflict"
to = "develop"

[[transitions]]
from = "merge"
trigger = "completion:updated"
to = "test"
"""

ROUTE_PLAN = """
[[transitions]]
from = "route"
trigger = "completion:go"
to = "plan"
when = ["no_criteria"]
"""
ROUTE_DEFAULT = """
[[transitions]]
from = "route"
trigger = "completion:go"
to = "develop"
"""
DEVELOP_DOCS = """
[[transitions]]
from = "develop"
trigger = "completion:done"
to = "docs_test"
when = ["changed_only:docs"]
"""
DEVELOP_DEFAULT = """
[[transitions]]
from = "develop"
trigger = "completion:done"
to = "test"
"""
DEVELOP = DEVELOP_DOCS + DEVELOP_DEFAULT
STANDARD = ROUTE_PLAN + ROUTE_DEFAULT + DEVELOP_DOCS + DEVELOP_DEFAULT


def workflow(transitions: str = STANDARD, *, branch_roles=BRANCH_ROLES):
    return load_workflow_text(
        HEAD + transitions + TAIL,
        "routed.toml",
        role_outcomes=OUTCOMES,
        branch_roles=branch_roles,
    )


def refusal(transitions: str, *, branch_roles=BRANCH_ROLES) -> str:
    with unittest.TestCase().assertRaises(WorkflowLoadError) as caught:
        workflow(transitions, branch_roles=branch_roles)
    return str(caught.exception)


class ParsingAndValidationTests(unittest.TestCase):
    def test_when_is_parsed_and_routes_keep_the_files_order(self) -> None:
        routes = workflow().routes_from("route", "completion:go")

        self.assertEqual([r.to_step for r in routes], ["plan", "develop"])
        self.assertEqual([r.when for r in routes], [("no_criteria",), ()])

    def test_a_route_with_several_facts_keeps_them(self) -> None:
        text = ROUTE_PLAN.replace('["no_criteria"]', '["no_criteria", "not:label:ui", "visits:develop>=2"]')

        routes = workflow(text + ROUTE_DEFAULT + DEVELOP).routes_from("route", "completion:go")

        self.assertEqual(routes[0].when, ("no_criteria", "not:label:ui", "visits:develop>=2"))

    def test_a_workflow_without_when_loads_unchanged(self) -> None:
        roles = load_roles()
        workflows = load_workflows(
            available_role_ids=set(roles),
            role_outcomes={r: role.completion.outcomes for r, role in roles.items()},
            branch_roles=branch_role_ids(roles),
        )

        self.assertTrue(workflows)
        for each in workflows.values():
            self.assertTrue(all(t.when == () for t in each.transitions), each.id)
            for t in each.transitions:
                self.assertEqual(each.find_transition(t.from_step, t.trigger.removeprefix("completion:")), t)

    def test_routes_without_a_default_are_refused(self) -> None:
        message = refusal(ROUTE_PLAN + DEVELOP_DEFAULT)

        self.assertIn("none without `when`", message)
        self.assertIn("'route'", message)

    def test_a_default_that_is_not_last_is_refused(self) -> None:
        message = refusal(ROUTE_DEFAULT + ROUTE_PLAN + DEVELOP_DEFAULT)

        self.assertIn("is not last", message)

    def test_two_defaults_are_refused(self) -> None:
        message = refusal(ROUTE_DEFAULT + ROUTE_DEFAULT.replace('"develop"', '"plan"') + DEVELOP_DEFAULT)

        self.assertIn("Duplicate transition trigger", message)

    def test_a_fact_that_is_not_in_the_list_is_refused(self) -> None:
        for bad in ("nonsense", "label:", "changed", "visits:develop", "visits:develop>=x", "not:not:no_criteria", "Label:ui"):
            message = refusal(ROUTE_PLAN.replace("no_criteria", bad) + ROUTE_DEFAULT + DEVELOP_DEFAULT)
            self.assertIn(repr(bad), message)

    def test_frozen_touched_is_refused_by_name_saying_why(self) -> None:
        message = refusal(ROUTE_PLAN.replace("no_criteria", "frozen_touched") + ROUTE_DEFAULT + DEVELOP_DEFAULT)

        self.assertIn("frozen_touched", message)
        self.assertIn("write scope and frozen checks", message)

    def test_when_must_be_a_list_of_facts(self) -> None:
        for bad in ('"no_criteria"', "[]", "[1]"):
            message = refusal(ROUTE_PLAN.replace('["no_criteria"]', bad) + ROUTE_DEFAULT + DEVELOP_DEFAULT)
            self.assertIn("`when`", message)

    def test_visits_must_name_a_step_of_the_workflow(self) -> None:
        message = refusal(
            ROUTE_PLAN.replace("no_criteria", "visits:nowhere>=2") + ROUTE_DEFAULT + DEVELOP_DEFAULT
        )

        self.assertIn("unknown step 'nowhere'", message)

    def test_the_facts_of_a_change_are_refused_before_any_step_that_commits(self) -> None:
        early = ROUTE_PLAN.replace("no_criteria", "changed:docs") + ROUTE_DEFAULT + DEVELOP_DEFAULT
        for fact in ("changed:docs", "changed_only:docs", "not:changed:docs"):
            message = refusal(
                ROUTE_PLAN.replace("no_criteria", fact) + ROUTE_DEFAULT + DEVELOP_DEFAULT
            )
            self.assertIn("before any step that commits", message, fact)
        self.assertIn("'route'", refusal(early))

    def test_the_facts_of_a_change_are_allowed_after_a_step_that_commits(self) -> None:
        self.assertEqual(workflow().routes_from("develop", "completion:done")[0].when, ("changed_only:docs",))

    def test_the_change_check_needs_to_know_which_roles_commit(self) -> None:
        early = ROUTE_PLAN.replace("no_criteria", "changed:docs") + ROUTE_DEFAULT + DEVELOP

        # No roles named: nothing to check against (the project-less case).
        self.assertTrue(workflow(early, branch_roles=None).routes_from("route", "completion:go"))

    def test_route_step_outcome_is_go_only(self) -> None:
        bad = ROUTE_DEFAULT.replace("completion:go", "completion:success") + DEVELOP_DEFAULT

        self.assertIn("invalid outcome 'success'", refusal(bad))


class FactWordsTests(unittest.TestCase):
    def test_a_fact_is_said_in_words(self) -> None:
        words = {
            "no_criteria": "no criteria",
            "not:no_criteria": "criteria given",
            "label:ui": "labelled ui",
            "not:label:ui": "not labelled ui",
            "changed:docs": "docs changed",
            "changed_only:docs,tests": "only docs, tests changed",
            "visits:develop>=2": "develop visited 2 or more times",
            "not:visits:develop>=2": "develop visited fewer than 2 times",
        }
        for text, said in words.items():
            self.assertEqual(route_line(to_step="x", default=False, held=[text]), f"Took the route to x: {said}")

    def test_the_default_says_no_facts_held(self) -> None:
        self.assertEqual(
            route_line(to_step="develop", default=True, held=[]),
            "No route's facts held: the default, to develop",
        )

    def test_an_unknown_fact_does_not_parse(self) -> None:
        with self.assertRaises(FactError):
            parse_fact("changed:Docs")


class ProjectNamesTests(unittest.TestCase):
    def test_labels_and_groups_must_be_named_by_the_project(self) -> None:
        text = ROUTE_PLAN.replace('"no_criteria"', '"label:ui", "changed:docs"') + ROUTE_DEFAULT + DEVELOP
        wf = workflow(text, branch_roles=None)

        errors = wf.route_project_errors(labels={}, path_groups={})
        self.assertIn("label 'ui'", errors[0])
        self.assertTrue(any("path group 'docs'" in error for error in errors))
        self.assertEqual(
            wf.route_project_errors(labels={"ui": "x"}, path_groups={"docs": ["docs/**"]}), []
        )

    def test_a_workflow_without_such_facts_needs_nothing_named(self) -> None:
        roles = load_roles()
        shipped = load_workflows(available_role_ids=set(roles))["development"]

        self.assertEqual(shipped.route_project_errors(labels={}, path_groups={}), [])


class _Repo(OrchestratorTestCase):
    def _store(self):
        repo_path, db_path = self.create_workspace()
        self.initialize_repo(repo_path)
        store = ForemanStore(db_path)
        store.initialize()
        self.addCleanup(store.close)
        self.repo_path = repo_path
        return store, repo_path

    def _name_groups(self, store, project):
        project.settings = {
            **project.settings,
            "completion_guard_enabled": False,
            "labels": {"ui": "changes what a person sees", "other": "another"},
            "path_groups": {"docs": ["docs/**"], "frontend": ["frontend/**"], "tests": ["tests/**"]},
        }
        store.save_project(project)


class FactsOnATaskTests(_Repo):
    """Each fact, on a real task and a real branch."""

    def setUp(self) -> None:
        self.store, repo = self._store()
        self.project, _, self.task = self.seed_project(self.store, repo_path=repo)
        self._name_groups(self.store, self.project)
        self.git(repo, "checkout", "-b", "feat/t")
        self.write_text(repo / "docs" / "a.md", "a\n")
        self.write_text(repo / "frontend" / "x.js", "x\n")
        self.commit_all(repo, "feat: change")
        self.git(repo, "checkout", "main")
        # The default branch moves on after the branch left it: not the branch's change.
        self.write_text(repo / "tests" / "t.py", "t\n")
        self.commit_all(repo, "chore: on main")
        self.task.branch_name = "feat/t"
        self.task.labels = ["ui"]
        self.task.step_visit_counts = {"develop": 2}

    @staticmethod
    def _with(transitions: str):
        """The workflow's own steps with other routes, not validated: only the choosing is under test."""

        from dataclasses import replace

        parsed = load_workflow_text(
            HEAD + STANDARD + TAIL, "x.toml", role_outcomes=OUTCOMES, branch_roles=BRANCH_ROLES
        )
        import tomllib

        data = tomllib.loads(transitions)["transitions"]
        from foreman.definitions.workflows import WorkflowTransition

        routes = tuple(
            WorkflowTransition(t["from"], t["trigger"], t["to"], when=tuple(t.get("when", ())))
            for t in data
        )
        return replace(parsed, transitions=routes)

    def holds(self, text: str, task=None) -> bool:
        return TaskFacts(self.project, task or self.task).holds(parse_fact(text))

    def test_label(self) -> None:
        self.assertTrue(self.holds("label:ui"))
        self.assertFalse(self.holds("label:other"))
        self.assertFalse(self.holds("not:label:ui"))
        self.assertTrue(self.holds("not:label:other"))

    def test_no_criteria(self) -> None:
        self.assertFalse(self.holds("no_criteria"))
        self.assertTrue(self.holds("not:no_criteria"))
        for empty in (None, "", "  \n "):
            self.task.acceptance_criteria = empty
            self.assertTrue(self.holds("no_criteria"), repr(empty))
            self.assertFalse(self.holds("not:no_criteria"), repr(empty))

    def test_changed_is_what_the_branch_changed_since_it_left_the_default_branch(self) -> None:
        self.assertTrue(self.holds("changed:docs"))
        self.assertTrue(self.holds("changed:frontend"))
        self.assertFalse(self.holds("changed:tests"))  # that change is on main, not the branch
        self.assertFalse(self.holds("not:changed:docs"))
        self.assertTrue(self.holds("not:changed:tests"))

    def test_changed_only(self) -> None:
        self.assertFalse(self.holds("changed_only:docs"))
        self.assertFalse(self.holds("changed_only:frontend"))
        self.assertTrue(self.holds("changed_only:docs,frontend"))
        self.assertTrue(self.holds("not:changed_only:docs"))

    def test_a_path_in_no_group_makes_changed_only_false(self) -> None:
        self.git(self.repo_path, "checkout", "feat/t")
        self.write_text(self.repo_path / "other.txt", "o\n")
        self.commit_all(self.repo_path, "feat: more")
        self.git(self.repo_path, "checkout", "main")

        self.assertFalse(self.holds("changed_only:docs,frontend"))

    def test_visits(self) -> None:
        self.assertTrue(self.holds("visits:develop>=2"))
        self.assertTrue(self.holds("visits:develop>=1"))
        self.assertFalse(self.holds("visits:develop>=3"))
        self.assertFalse(self.holds("visits:test>=1"))
        self.assertTrue(self.holds("not:visits:develop>=3"))

    def test_a_task_with_no_branch_has_changed_nothing(self) -> None:
        self.task.branch_name = None

        self.assertFalse(self.holds("changed:docs"))
        self.assertFalse(self.holds("changed_only:docs"))
        self.assertTrue(self.holds("not:changed:docs"))

    def test_the_first_route_whose_facts_all_hold_is_taken_in_the_files_order(self) -> None:
        text = """
[[transitions]]
from = "develop"
trigger = "completion:done"
to = "docs_test"
when = ["label:other"]

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "plan"
when = ["label:ui", "changed:docs"]

[[transitions]]
from = "develop"
trigger = "completion:done"
to = "merge"
when = ["label:ui"]
"""
        wf = self._with(ROUTE_DEFAULT + text + DEVELOP_DEFAULT)

        choice = choose_route(wf, "develop", "completion:done", TaskFacts(self.project, self.task))

        # label:other fails; the next two both hold, and the earlier is taken.
        self.assertEqual(choice.transition.to_step, "plan")
        self.assertEqual(choice.held, ("label:ui", "changed:docs"))
        self.assertFalse(choice.default)

    def test_a_route_needs_every_one_of_its_facts(self) -> None:
        text = DEVELOP_DOCS.replace('["changed_only:docs"]', '["changed:docs", "label:other"]')
        wf = self._with(ROUTE_DEFAULT + text + DEVELOP_DEFAULT)

        choice = choose_route(wf, "develop", "completion:done", TaskFacts(self.project, self.task))

        self.assertTrue(choice.default)
        self.assertEqual(choice.transition.to_step, "test")
        self.assertEqual(choice.not_held, ("label:other",))


class RoutingRunTests(_Repo):
    """A task through a workflow whose routes are chosen by facts."""

    def _run(self, *, criteria, files, labels=()):
        store, repo = self._store()
        project, _, task = self.seed_project(
            store, repo_path=repo, acceptance_criteria=criteria, test_command="true"
        )
        self._name_groups(store, project)
        task.labels = list(labels)
        store.save_task(task)
        project.workflow_id = "routed"
        store.save_project(project)
        wf = workflow()
        seen: list[str] = []

        def developer(*, task, prompt, carried_output):
            seen.append(prompt)
            tree = self.work_dir(task, repo)
            for path in files if len(seen) == (2 if criteria is None else 1) else ["step.txt"]:
                self.write_text(tree / path, "x\n")
            self.commit_all(tree, "feat: work")
            return AgentExecutionResult(outcome="done", detail="Done.")

        executor = ScriptedAgentExecutor({("developer", 1): developer, ("developer", 2): developer})
        orchestrator = ForemanOrchestrator(
            store,
            roles=self.roles,
            workflows={**self.workflows, "routed": wf},
            agent_executor=executor,
        )
        orchestrator.run_project(project.id)
        return store, store.get_task(task.id)

    @staticmethod
    def _steps(store, task):
        return [
            run.workflow_step
            for run in store.list_runs(task_id=task.id)
            if run.role_id != "_builtin:orchestrator"
        ]

    @staticmethod
    def _lines(store, task):
        return [
            run.outcome_detail
            for run in store.list_runs(task_id=task.id)
            if run.role_id == "_builtin:orchestrator" and "route" in (run.outcome_detail or "")
        ]

    def test_a_task_without_criteria_goes_to_the_plan_step(self) -> None:
        store, task = self._run(criteria=None, files=["docs/a.md"])

        steps = self._steps(store, task)
        self.assertEqual(steps[:3], ["route", "plan", "develop"])
        self.assertEqual(task.status, "done", task.blocked_reason)

    def test_the_route_step_runs_no_agent_and_its_outcome_is_go(self) -> None:
        store, task = self._run(criteria=None, files=["docs/a.md"])

        run = next(r for r in store.list_runs(task_id=task.id) if r.workflow_step == "route")
        self.assertEqual((run.role_id, run.agent_backend, run.outcome), ("_builtin:route", "builtin", "go"))
        self.assertFalse(run.model)

    def test_a_task_with_criteria_takes_the_default_and_the_activity_says_so(self) -> None:
        store, task = self._run(criteria="It works.", files=["docs/a.md"])

        self.assertEqual(self._steps(store, task)[:2], ["route", "develop"])
        self.assertIn("No route's facts held: the default, to develop", self._lines(store, task))
        event = next(e for e in store.list_events(task_id=task.id) if e.event_type == "workflow.route_taken" and e.payload["from_step"] == "route")
        self.assertEqual(
            {k: event.payload[k] for k in ("to_step", "default", "held", "not_held", "routes")},
            {"to_step": "develop", "default": True, "held": [], "not_held": ["no_criteria"], "routes": 2},
        )

    def test_the_route_taken_and_its_facts_are_recorded_on_the_task(self) -> None:
        store, task = self._run(criteria=None, files=["docs/a.md"])

        self.assertIn("Took the route to plan: no criteria", self._lines(store, task))
        event = next(e for e in store.list_events(task_id=task.id) if e.event_type == "workflow.route_taken" and e.payload["from_step"] == "route")
        self.assertEqual(event.payload["to_step"], "plan")
        self.assertEqual(event.payload["held"], ["no_criteria"])
        self.assertEqual(event.payload["when"], ["no_criteria"])
        self.assertFalse(event.payload["default"])

    def test_a_change_of_one_group_only_takes_its_route_after_the_step_that_committed(self) -> None:
        store, task = self._run(criteria="It works.", files=["docs/a.md"])

        steps = self._steps(store, task)
        self.assertIn("docs_test", steps)
        self.assertNotIn("test", steps)
        self.assertIn("Took the route to docs_test: only docs changed", self._lines(store, task))

    def test_a_change_elsewhere_takes_the_default(self) -> None:
        store, task = self._run(criteria="It works.", files=["src/a.py"])

        steps = self._steps(store, task)
        self.assertIn("test", steps)
        self.assertNotIn("docs_test", steps)

    def test_a_step_without_facts_records_no_route(self) -> None:
        store, task = self._run(criteria="It works.", files=["docs/a.md"])

        taken = [e for e in store.list_events(task_id=task.id) if e.event_type == "workflow.route_taken"]
        self.assertEqual({e.payload["from_step"] for e in taken}, {"route", "develop"})


class ProjectCheckTests(_Repo):
    LABEL_ROUTE = (
        ROUTE_PLAN.replace('"no_criteria"', '"label:ui"') + ROUTE_DEFAULT + DEVELOP
    )

    def _with_workflow(self):
        store, repo = self._store()
        project, _, _ = self.seed_project(store, repo_path=repo)
        text = HEAD + self.LABEL_ROUTE + TAIL
        save_workflow(store, project.id, text, changed_by="test")
        return store, project

    def test_setting_a_workflow_that_names_a_label_the_project_does_not_is_refused(self) -> None:
        store, project = self._with_workflow()

        with self.assertRaises(SettingError) as caught:
            Mutations(store, via="cli", actor="alice").change_project(
                project, fields={"workflow_id": "routed"}, host_level=False
            )

        self.assertIn("label 'ui'", str(caught.exception))
        self.assertEqual(store.get_project(project.id).workflow_id, "development")

    def test_it_is_set_once_the_project_names_the_label(self) -> None:
        store, project = self._with_workflow()

        Mutations(store, via="cli", actor="alice").change_project(
            project,
            fields={"workflow_id": "routed"},
            settings={"labels": {"ui": "what a person sees"}, "path_groups": {"docs": ["docs/**"]}},
            host_level=False,
        )

        self.assertEqual(store.get_project(project.id).workflow_id, "routed")

    def test_the_engine_refuses_to_run_a_workflow_naming_what_the_project_no_longer_names(self) -> None:
        store, project = self._with_workflow()
        project.workflow_id = "routed"
        store.save_project(project)
        orchestrator = ForemanOrchestrator(store)

        with self.assertRaises(OrchestratorError) as caught:
            orchestrator.run_project(project.id)

        self.assertIn("label 'ui'", str(caught.exception))


class FormTests(unittest.TestCase):
    def test_the_form_does_not_save_over_routes_it_cannot_show(self) -> None:
        from foreman.definitions.layers import DefinitionError
        from foreman.services.definition_forms import workflow_text_from_fields

        text = HEAD + STANDARD + TAIL

        with self.assertRaises(DefinitionError) as caught:
            workflow_text_from_fields(text, "routed", {"name": "R", "steps": [{"id": "a", "role": "developer"}]})

        self.assertIn("Edit its text", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
