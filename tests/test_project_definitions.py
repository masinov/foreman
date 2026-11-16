"""A project's own roles and workflows, kept in the database over the shipped ones (ADR-0024)."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from foreman.cli import main
from foreman.cli.parser import MANAGER_SESSION_COMMANDS
from foreman.data import ROLES_DIR, WORKFLOWS_DIR
from foreman.definitions import (
    DefinitionError,
    project_definitions,
    remove_definition,
    save_role,
    save_workflow,
)
from foreman.engine_control import resolve_gate_steps
from foreman.models import Project
from foreman.orchestrator import ForemanOrchestrator
from foreman.roles import RoleLoadError, load_role_text, load_roles
from foreman.store import ForemanStore


def shipped_role(role_id: str) -> str:
    return (ROLES_DIR / f"{role_id}.toml").read_text(encoding="utf-8")


def shipped_workflow(workflow_id: str) -> str:
    return (WORKFLOWS_DIR / f"{workflow_id}.toml").read_text(encoding="utf-8")


def reviewer_on(model: str) -> str:
    text = shipped_role("code_reviewer")
    assert 'model = "claude-sonnet-5-5"' in text
    return text.replace('model = "claude-sonnet-5-5"', f'model = "{model}"')


def role_called(role_id: str, *, source: str = "code_reviewer") -> str:
    text = shipped_role(source)
    assert f'id = "{source}"' in text
    return text.replace(f'id = "{source}"', f'id = "{role_id}"')


def workflow_called(workflow_id: str, *, reviewer: str = "code_reviewer") -> str:
    text = shipped_workflow("development")
    return text.replace('id = "development"', f'id = "{workflow_id}"').replace(
        'role = "code_reviewer"', f'role = "{reviewer}"'
    )


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        for project_id in ("p1", "p2"):
            self.store.save_project(
                Project(id=project_id, name=project_id, repo_path=self._temp.name, workflow_id="development")
            )

    def refused(self, message: str):
        return self.assertRaisesRegex(DefinitionError, message)


class LoadingTests(_Workspace):
    def test_a_project_with_nothing_of_its_own_runs_with_what_is_shipped(self) -> None:
        definitions = project_definitions(self.store, "p1")

        self.assertEqual(set(definitions.roles), set(load_roles()))
        self.assertIn("development", definitions.workflows)
        self.assertEqual(definitions.own_roles, {})
        self.assertEqual(definitions.own_workflows, {})

    def test_a_role_saved_under_a_shipped_id_replaces_it_for_that_project_only(self) -> None:
        save_role(self.store, "p1", reviewer_on("claude-opus-5-5"), changed_by="alice")

        self.assertEqual(project_definitions(self.store, "p1").roles["code_reviewer"].agent.model, "claude-opus-5-5")
        self.assertEqual(project_definitions(self.store, "p2").roles["code_reviewer"].agent.model, "claude-sonnet-5-5")
        self.assertIn("code_reviewer", project_definitions(self.store, "p1").own_roles)

    def test_a_new_role_and_a_workflow_that_names_it(self) -> None:
        save_role(self.store, "p1", role_called("strict_reviewer"), changed_by="alice")
        save_workflow(self.store, "p1", workflow_called("careful", reviewer="strict_reviewer"), changed_by="alice")

        definitions = project_definitions(self.store, "p1")
        self.assertIn("strict_reviewer", definitions.roles)
        self.assertEqual(
            [step.role for step in definitions.workflows["careful"].steps if step.id == "review"],
            ["strict_reviewer"],
        )
        self.assertNotIn("careful", project_definitions(self.store, "p2").workflows)

    def test_every_save_is_kept_as_a_revision(self) -> None:
        save_role(self.store, "p1", reviewer_on("claude-opus-5-5"), changed_by="alice")
        save_role(self.store, "p1", reviewer_on("claude-haiku-5-5"), changed_by="bob")

        revisions = self.store.definition_revisions("p1", "role", "code_reviewer")
        self.assertEqual([(r.revision, r.changed_by) for r in revisions], [(2, "bob"), (1, "alice")])
        self.assertIn("claude-opus-5-5", revisions[1].body)


class RefusalTests(_Workspace):
    def test_text_that_is_not_toml(self) -> None:
        with self.refused("not valid TOML"):
            save_role(self.store, "p1", "[role\nid = ", changed_by="alice")

    def test_a_tool_name_the_agent_program_does_not_have(self) -> None:
        text = shipped_role("code_reviewer").replace('allowed = ["Read", "Grep", "Glob"]', 'allowed = ["Read", "Grop"]')

        with self.refused(r"unknown tool\(s\) Grop\. Known tools: Read, Grep, Glob"):
            save_role(self.store, "p1", text, changed_by="alice")
        self.assertEqual(self.store.current_definitions("p1"), [])

    def test_a_backend_that_does_not_exist(self) -> None:
        text = shipped_role("developer").replace('backend = "claude_code"', 'backend = "claude"')

        with self.refused("agent.backend must be one of claude_code, codex"):
            save_role(self.store, "p1", text, changed_by="alice")

    def test_a_role_change_that_breaks_a_workflow_names_the_workflow(self) -> None:
        text = shipped_role("code_reviewer").replace(
            "outcomes = ['approve', 'deny', 'steer']", "outcomes = ['approve', 'deny']"
        )
        self.assertNotEqual(text, shipped_role("code_reviewer"))

        with self.refused("development.*steer"):
            save_role(self.store, "p1", text, changed_by="alice")

    def test_a_workflow_that_names_a_role_the_project_does_not_have(self) -> None:
        with self.refused("unknown role 'nobody'"):
            save_workflow(self.store, "p1", workflow_called("careful", reviewer="nobody"), changed_by="alice")

    def test_an_id_that_is_not_a_plain_name(self) -> None:
        with self.refused("lower-case letters"):
            save_role(self.store, "p1", role_called("Strict Reviewer"), changed_by="alice")

    def test_an_unknown_project(self) -> None:
        with self.refused("'nope' was not found"):
            save_role(self.store, "nope", shipped_role("developer"), changed_by="alice")


class RemovalTests(_Workspace):
    def test_resetting_a_shipped_id_goes_back_to_the_shipped_definition(self) -> None:
        save_role(self.store, "p1", reviewer_on("claude-opus-5-5"), changed_by="alice")

        self.assertTrue(remove_definition(self.store, "p1", "role", "code_reviewer", changed_by="alice"))

        definitions = project_definitions(self.store, "p1")
        self.assertEqual(definitions.roles["code_reviewer"].agent.model, "claude-sonnet-5-5")
        self.assertEqual(definitions.own_roles, {})

    def test_a_role_a_workflow_still_names_cannot_be_removed(self) -> None:
        save_role(self.store, "p1", role_called("strict_reviewer"), changed_by="alice")
        save_workflow(self.store, "p1", workflow_called("careful", reviewer="strict_reviewer"), changed_by="alice")

        with self.refused("unknown role 'strict_reviewer'"):
            remove_definition(self.store, "p1", "role", "strict_reviewer", changed_by="alice")

    def test_the_workflow_the_project_uses_cannot_be_removed(self) -> None:
        save_workflow(self.store, "p1", workflow_called("careful"), changed_by="alice")
        project = self.store.get_project("p1")
        project.workflow_id = "careful"
        self.store.save_project(project)

        with self.refused("uses workflow 'careful'"):
            remove_definition(self.store, "p1", "workflow", "careful", changed_by="alice")

    def test_removing_what_the_project_does_not_keep(self) -> None:
        with self.refused("keeps no role of its own called 'developer'"):
            remove_definition(self.store, "p1", "role", "developer", changed_by="alice")


class ShippedRoleTests(unittest.TestCase):
    def test_a_misspelt_tool_is_refused_when_a_role_is_loaded(self) -> None:
        text = shipped_role("architect").replace('"NotebookEdit"', '"NotebookEdits"')

        with self.assertRaisesRegex(RoleLoadError, "agent.tools.disallowed names unknown tool"):
            load_role_text(text, "architect")


class EngineTests(_Workspace):
    def test_the_engine_runs_a_project_with_its_own_definitions(self) -> None:
        save_role(self.store, "p1", reviewer_on("claude-opus-5-5"), changed_by="alice")
        orchestrator = ForemanOrchestrator(self.store)
        handed_out = orchestrator.roles

        orchestrator.use_project_definitions("p1")
        self.assertEqual(orchestrator.roles["code_reviewer"].agent.model, "claude-opus-5-5")
        # The same dictionary: the parts of the engine that hold it see the change.
        self.assertIs(orchestrator.roles, handed_out)

        orchestrator.use_project_definitions("p2")
        self.assertEqual(orchestrator.roles["code_reviewer"].agent.model, "claude-sonnet-5-5")

    def test_definitions_handed_to_the_engine_are_left_alone(self) -> None:
        save_role(self.store, "p1", reviewer_on("claude-opus-5-5"), changed_by="alice")
        orchestrator = ForemanOrchestrator(self.store, roles=load_roles())

        orchestrator.use_project_definitions("p1")

        self.assertEqual(orchestrator.roles["code_reviewer"].agent.model, "claude-sonnet-5-5")

    def test_gates_are_found_in_a_workflow_only_the_project_has(self) -> None:
        save_workflow(self.store, "p1", workflow_called("careful"), changed_by="alice")
        project = self.store.get_project("p1")
        project.workflow_id = "careful"
        self.store.save_project(project)

        gates = resolve_gate_steps(self.store, project)

        self.assertEqual(gates.gate_step_ids, frozenset({"merge_approval"}))


class CliTests(_Workspace):
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*argv, "--db", str(self.db_path)])
        return code, out.getvalue(), err.getvalue()

    def test_set_list_show_and_reset_a_role(self) -> None:
        path = Path(self._temp.name) / "reviewer.toml"
        path.write_text(reviewer_on("claude-opus-5-5"), encoding="utf-8")

        code, out, _ = self.run_cli("role", "set", "p1", "--file", str(path))
        self.assertEqual(code, 0)
        self.assertIn("Saved role code_reviewer for p1.", out)

        _, listing, _ = self.run_cli("role", "list", "p1")
        self.assertIn("code_reviewer | Code Reviewer | changed for this project", listing)
        self.assertIn("developer | Developer | shipped", listing)

        _, shown, _ = self.run_cli("role", "show", "p1", "code_reviewer")
        self.assertIn('model = "claude-opus-5-5"', shown)
        _, shipped, _ = self.run_cli("role", "show", "p2", "code_reviewer")
        self.assertIn('model = "claude-sonnet-5-5"', shipped)

        code, out, _ = self.run_cli("role", "reset", "p1", "code_reviewer")
        self.assertEqual(code, 0)
        self.assertIn("p1 uses the shipped role code_reviewer again.", out)

    def test_a_refused_save_says_why_and_exits_non_zero(self) -> None:
        path = Path(self._temp.name) / "wf.toml"
        path.write_text(workflow_called("careful", reviewer="nobody"), encoding="utf-8")

        code, _, err = self.run_cli("workflow", "set", "p1", "--file", str(path))

        self.assertEqual(code, 1)
        self.assertIn("Not saved:", err)
        self.assertIn("unknown role 'nobody'", err)

    def test_a_manager_session_may_read_definitions_and_not_change_them(self) -> None:
        self.assertLessEqual({"role list", "role show", "workflow list", "workflow show"}, MANAGER_SESSION_COMMANDS)
        self.assertFalse({"role set", "role reset", "workflow set", "workflow reset"} & MANAGER_SESSION_COMMANDS)


if __name__ == "__main__":
    unittest.main()
