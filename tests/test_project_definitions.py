"""A project's own roles and workflows, kept in the database over the shipped ones (ADR-0024)."""

from __future__ import annotations

import asyncio
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import httpx

from foreman.cli import main
from foreman.cli.parser import MANAGER_SESSION_COMMANDS
from foreman.api.app import create_dashboard_app
from foreman.services.definition_forms import (
    describe_project_definitions,
    role_text_from_fields,
    workflow_text_from_fields,
)
from foreman.data import ROLES_DIR, WORKFLOWS_DIR
from foreman.definitions.layers import (
    DefinitionError,
    project_definitions,
    remove_definition,
    save_role,
    save_workflow,
)
from foreman.definitions.gate_steps import resolve_gate_steps
from foreman.domain.models import Project
from foreman.engine.orchestrator import ForemanOrchestrator
from foreman.definitions.roles import RoleLoadError, load_role_text, load_roles
from foreman.definitions.workflows import load_workflow_text
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
        # No test asks the real agent program about a model; `asked` records what would be.
        self.asked: list[tuple[str, str]] = []
        self.unknown_models: set[str] = set()

        def check_model(backend: str, model: str) -> str | None:
            self.asked.append((backend, model))
            return f"Claude Code cannot run the model {model!r}." if model in self.unknown_models else None

        for target in ("foreman.services.definition_forms.check_model", "foreman.cli.definitions.check_model"):
            patcher = mock.patch(target, check_model)
            patcher.start()
            self.addCleanup(patcher.stop)
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
        text = shipped_role("code_reviewer").replace('allowed = ["Read", "Grep", "Glob", "Bash"]', 'allowed = ["Read", "Grop"]')

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
        text = shipped_role("code_reviewer").replace('"NotebookEdit"', '"NotebookEdits"')

        with self.assertRaisesRegex(RoleLoadError, "agent.tools.disallowed names unknown tool"):
            load_role_text(text, "code_reviewer")


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

    def test_the_workspace_form_of_each_role_command(self) -> None:
        path = Path(self._temp.name) / "reviewer.toml"
        path.write_text(reviewer_on("claude-opus-5-5"), encoding="utf-8")

        code, out, _ = self.run_cli("role", "set", "--workspace", "--file", str(path))
        self.assertEqual(code, 0)
        self.assertIn("Saved role code_reviewer for the workspace.", out)
        self.assertEqual(project_definitions(self.store, "p1").roles["code_reviewer"].agent.model, "claude-opus-5-5")
        self.assertIn(("claude_code", "claude-opus-5-5"), self.asked)

        _, listing, _ = self.run_cli("role", "list", "--workspace")
        self.assertIn("Roles of the workspace", listing)
        self.assertIn("code_reviewer | Code Reviewer | changed for the workspace", listing)
        self.assertIn("developer | Developer | shipped", listing)

        _, shown, _ = self.run_cli("role", "show", "--workspace", "code_reviewer")
        self.assertIn('model = "claude-opus-5-5"', shown)

        code, out, _ = self.run_cli("role", "reset", "--workspace", "code_reviewer")
        self.assertEqual(code, 0)
        self.assertIn("The workspace uses the shipped role code_reviewer again.", out)
        self.assertEqual(self.store.current_definitions(None), [])

    def test_the_workspace_form_of_each_workflow_command(self) -> None:
        path = Path(self._temp.name) / "wf.toml"
        path.write_text(workflow_called("house"), encoding="utf-8")

        code, out, _ = self.run_cli("workflow", "set", "--workspace", "--file", str(path))
        self.assertEqual(code, 0)
        self.assertIn("Saved workflow house for the workspace.", out)

        _, listing, _ = self.run_cli("workflow", "list", "--workspace")
        self.assertIn("house | ", listing)
        self.assertIn("the workspace's own", listing)
        _, shown, _ = self.run_cli("workflow", "show", "--workspace", "house")
        self.assertIn('id = "house"', shown)
        _, p1, _ = self.run_cli("workflow", "list", "p1")
        self.assertIn("house | ", p1)

        code, out, _ = self.run_cli("workflow", "reset", "--workspace", "house")
        self.assertEqual(code, 0)
        self.assertIn("Removed workflow house from the workspace.", out)
        self.assertEqual(self.store.current_definitions(None), [])

    def test_a_refused_workspace_save_says_why_and_exits_non_zero(self) -> None:
        self.unknown_models.add("minimax")
        path = Path(self._temp.name) / "reviewer.toml"
        path.write_text(reviewer_on("minimax"), encoding="utf-8")

        code, _, err = self.run_cli("role", "set", "--workspace", "--file", str(path))

        self.assertEqual(code, 1)
        self.assertIn("Not saved:", err)
        self.assertIn("minimax", err)
        self.assertEqual(self.store.current_definitions(None), [])

    def test_a_refused_workspace_reset_exits_non_zero(self) -> None:
        code, _, err = self.run_cli("role", "reset", "--workspace", "code_reviewer")
        self.assertEqual(code, 1)
        self.assertIn("The workspace keeps no role of its own", err)

    def test_a_project_and_the_workspace_are_not_both_given_or_both_left_out(self) -> None:
        for argv in (("role", "list"), ("role", "list", "p1", "--workspace")):
            code, _, err = self.run_cli(*argv)
            self.assertEqual(code, 1)
            self.assertIn("--workspace", err)

    def test_a_manager_session_may_read_definitions_and_not_change_them(self) -> None:
        self.assertLessEqual({"role list", "role show", "workflow list", "workflow show"}, MANAGER_SESSION_COMMANDS)
        self.assertFalse({"role set", "role reset", "workflow set", "workflow reset"} & MANAGER_SESSION_COMMANDS)


ROLE_FIELDS = ("name", "description", "model", "tools", "ends", "decisions", "timeout_minutes", "max_cost_usd", "prompt")


def fields_of(described: dict) -> dict:
    return {key: described[key] for key in ROLE_FIELDS}


class FormTests(_Workspace):
    """The editor's form and the stored text say the same thing, both ways."""

    def test_every_shipped_role_survives_the_form_unchanged(self) -> None:
        described = describe_project_definitions(self.store, "p1")
        shipped = load_roles()

        for role in described["roles"]:
            with self.subTest(role=role["id"]):
                text = role_text_from_fields(role["text"], role["id"], fields_of(role))
                again = load_role_text(text, role["id"])
                before = shipped[role["id"]]
                self.assertEqual(again.completion, before.completion)
                self.assertEqual(again.prompt_template, before.prompt_template)
                self.assertEqual(again.agent.model, before.agent.model)
                self.assertEqual(again.agent.flags, before.agent.flags)
                self.assertEqual(again.signals, before.signals)

    def test_a_role_with_no_tool_stays_without_tools(self) -> None:
        described = describe_project_definitions(self.store, "p1")
        triage = next(role for role in described["roles"] if role["id"] == "triage_reviewer")
        self.assertEqual(triage["tools"], {"every": False, "chosen": []})

        again = load_role_text(role_text_from_fields(triage["text"], "triage_reviewer", fields_of(triage)), "t")

        self.assertTrue(again.agent.tools.none)
        self.assertEqual(list(again.agent.tools.allowed), [])

    def test_choosing_a_tool_for_a_role_that_had_none(self) -> None:
        described = describe_project_definitions(self.store, "p1")
        triage = next(role for role in described["roles"] if role["id"] == "triage_reviewer")
        fields = fields_of(triage)
        fields["tools"] = {"every": False, "chosen": ["Read"]}

        again = load_role_text(role_text_from_fields(triage["text"], "triage_reviewer", fields), "t")

        self.assertFalse(again.agent.tools.none)
        self.assertEqual(list(again.agent.tools.allowed), ["Read"])

    def test_every_shipped_workflow_survives_the_form_unchanged(self) -> None:
        described = describe_project_definitions(self.store, "p1")
        roles = load_roles()
        outcomes = {role_id: role.completion.outcomes for role_id, role in roles.items()}

        for workflow in described["workflows"]:
            with self.subTest(workflow=workflow["id"]):
                text = workflow_text_from_fields(
                    workflow["text"], workflow["id"], {"name": workflow["name"], "steps": workflow["steps"]}
                )
                again = load_workflow_text(text, "w", available_role_ids=set(roles), role_outcomes=outcomes)
                before = project_definitions(self.store, "p1").workflows[workflow["id"]]
                self.assertEqual(again.steps, before.steps)
                self.assertEqual(
                    sorted(again.transitions, key=lambda tr: (tr.from_step, tr.trigger)),
                    sorted(before.transitions, key=lambda tr: (tr.from_step, tr.trigger)),
                )
                self.assertEqual(again.gates, before.gates)
                self.assertEqual(again.fallback, before.fallback)


class ApiTests(_Workspace):
    def request(self, method: str, path: str, **kwargs):
        async def send():
            app = create_dashboard_app(str(self.db_path))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                return await client.request(method, f"/api/v1{path}", **kwargs)

        return asyncio.run(send())

    def role(self, role_id: str, project: str = "p1") -> dict:
        payload = self.request("GET", f"/projects/{project}/definitions").json()
        return next(role for role in payload["roles"] if role["id"] == role_id)

    def test_the_editor_is_given_roles_workflows_and_the_words_to_choose_from(self) -> None:
        response = self.request("GET", "/projects/p1/definitions")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        reviewer = next(role for role in payload["roles"] if role["id"] == "code_reviewer")
        self.assertEqual(reviewer["origin"], "shipped")
        self.assertEqual(reviewer["ends"], "decides")
        self.assertEqual(reviewer["decisions"], ["approve", "deny", "steer"])
        self.assertEqual(reviewer["tools"], {"every": False, "chosen": ["Read", "Grep", "Glob", "Bash"]})
        self.assertIn("Standard Development", reviewer["used_by"])
        development = next(w for w in payload["workflows"] if w["id"] == "development")
        self.assertTrue(development["used"])
        self.assertEqual(development["steps"][1]["then"]["failure"], {"to": "develop", "carry_output": True})
        self.assertIn("Read", payload["vocabulary"]["tools"]["claude_code"])
        tests = next(entry for entry in payload["vocabulary"]["done_by"] if entry["role"] == "_builtin:run_tests")
        self.assertEqual(tests["outcomes"], ["success", "failure"])

    def test_saving_the_form_changes_the_role_for_this_project(self) -> None:
        fields = fields_of(self.role("code_reviewer"))
        fields["model"] = "claude-opus-5-5"
        fields["tools"] = {"every": False, "chosen": ["Read", "Grep", "Glob", "Bash"]}
        fields["timeout_minutes"] = 20

        response = self.request("PUT", "/projects/p1/roles/code_reviewer", json={"fields": fields})

        self.assertEqual(response.status_code, 200, response.text)
        saved = project_definitions(self.store, "p1").roles["code_reviewer"]
        self.assertEqual(saved.agent.model, "claude-opus-5-5")
        self.assertEqual(list(saved.agent.tools.allowed), ["Read", "Grep", "Glob", "Bash"])
        self.assertEqual(list(saved.agent.tools.disallowed), [])
        self.assertEqual(saved.completion.timeout_minutes, 20)
        self.assertTrue(saved.completion.output.approve_needs_reading)
        self.assertEqual(self.role("code_reviewer")["origin"], "changed")
        self.assertEqual(self.role("code_reviewer", "p2")["origin"], "shipped")

    def test_a_decision_the_prompt_never_mentions_is_refused(self) -> None:
        fields = fields_of(self.role("security_reviewer"))
        fields["decisions"] = ["approve", "deny", "steer"]

        response = self.request("PUT", "/projects/p1/roles/security_reviewer", json={"fields": fields})

        self.assertEqual(response.status_code, 400)
        self.assertIn("may decide STEER but its prompt never says so", response.text)
        self.assertEqual(self.store.current_definitions("p1"), [])

    def test_a_new_role_starts_as_a_copy(self) -> None:
        fields = fields_of(self.role("code_reviewer"))
        fields["name"] = "Strict Reviewer"

        refused = self.request("PUT", "/projects/p1/roles/strict_reviewer", json={"fields": fields})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("starts as a copy", refused.text)

        response = self.request(
            "PUT", "/projects/p1/roles/strict_reviewer", json={"fields": fields, "copy_of": "code_reviewer"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = self.role("strict_reviewer")
        self.assertEqual((created["name"], created["origin"], created["used_by"]), ("Strict Reviewer", "own", []))

    def test_a_workflow_saved_from_its_steps(self) -> None:
        payload = self.request("GET", "/projects/p1/definitions").json()
        development = next(w for w in payload["workflows"] if w["id"] == "development")
        steps = [step for step in development["steps"] if step["id"] != "review"]
        for step in steps:
            if step["id"] == "test":
                step["then"]["success"] = {"to": "merge_approval", "carry_output": False}

        response = self.request(
            "PUT",
            "/projects/p1/workflows/no_review",
            json={"fields": {"name": "Without review", "steps": steps}, "copy_of": "development"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        saved = project_definitions(self.store, "p1").workflows["no_review"]
        self.assertEqual([step.id for step in saved.steps], ["develop", "test", "merge_approval", "merge", "done"])
        self.assertEqual(saved.find_transition("test", "success").to_step, "merge_approval")
        self.assertEqual(len(saved.gates), 2)

    def test_a_step_that_goes_to_a_step_that_is_gone_is_refused(self) -> None:
        payload = self.request("GET", "/projects/p1/definitions").json()
        development = next(w for w in payload["workflows"] if w["id"] == "development")
        steps = [step for step in development["steps"] if step["id"] != "review"]

        response = self.request(
            "PUT", "/projects/p1/workflows/development", json={"fields": {"name": "Broken", "steps": steps}}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("unknown step 'review'", response.text)

    def test_text_whose_id_is_another_is_refused(self) -> None:
        response = self.request(
            "PUT", "/projects/p1/roles/code_reviewer", json={"text": shipped_role("developer")}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("An id is not changed by editing", response.text)

    def test_reset_goes_back_to_the_shipped_role(self) -> None:
        self.request("PUT", "/projects/p1/roles/code_reviewer", json={"text": reviewer_on("claude-opus-5-5")})
        self.assertEqual(self.role("code_reviewer")["model"], "claude-opus-5-5")

        response = self.request("DELETE", "/projects/p1/roles/code_reviewer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.role("code_reviewer")["model"], "claude-sonnet-5-5")
        self.assertEqual(self.role("code_reviewer")["origin"], "shipped")

    def test_an_unknown_project_is_not_found(self) -> None:
        self.assertEqual(self.request("GET", "/projects/nope/definitions").status_code, 404)

    def test_the_route_that_wrote_into_shipped_role_files_is_gone(self) -> None:
        response = self.request("PATCH", "/roles/code_reviewer", json={"model": "x"})

        self.assertIn(response.status_code, (404, 405))


if __name__ == "__main__":
    unittest.main()


class WorkspaceDefaultTests(ApiTests):
    """The workspace's own definitions: the defaults every project starts from."""

    def model(self, project: str | None) -> str:
        return project_definitions(self.store, project).roles["code_reviewer"].agent.model

    def test_a_default_reaches_every_project_that_keeps_no_version_of_its_own(self) -> None:
        save_role(self.store, "p2", reviewer_on("claude-haiku-5-5"), changed_by="bob")

        save_role(self.store, None, reviewer_on("claude-opus-5-5"), changed_by="alice")

        self.assertEqual(self.model(None), "claude-opus-5-5")
        self.assertEqual(self.model("p1"), "claude-opus-5-5")
        self.assertEqual(self.model("p2"), "claude-haiku-5-5")
        # For p1 the role is the default, not something of its own.
        self.assertEqual(project_definitions(self.store, "p1").own_roles, {})
        self.assertEqual(self.role("code_reviewer")["origin"], "shipped")

    def test_a_project_that_drops_its_own_goes_back_to_the_workspaces_default(self) -> None:
        save_role(self.store, None, reviewer_on("claude-opus-5-5"), changed_by="alice")
        save_role(self.store, "p1", reviewer_on("claude-haiku-5-5"), changed_by="bob")

        remove_definition(self.store, "p1", "role", "code_reviewer", changed_by="bob")

        self.assertEqual(self.model("p1"), "claude-opus-5-5")

    def test_a_default_that_would_break_a_project_is_refused_and_names_it(self) -> None:
        # p1 keeps a workflow that routes the reviewer's "steer".
        save_workflow(self.store, "p1", workflow_called("careful"), changed_by="bob")
        no_steer = shipped_role("code_reviewer").replace(
            "outcomes = ['approve', 'deny', 'steer']", "outcomes = ['approve', 'deny']"
        )
        with self.refused("steer"):
            save_role(self.store, None, no_steer, changed_by="alice")
        self.assertEqual(self.store.current_definitions(None), [])

    def test_a_workflow_added_to_the_workspace_can_be_used_and_then_not_removed(self) -> None:
        save_workflow(self.store, None, workflow_called("house"), changed_by="alice")
        self.assertIn("house", project_definitions(self.store, "p2").workflows)
        project = self.store.get_project("p2")
        project.workflow_id = "house"
        self.store.save_project(project)

        with self.refused("p2.*uses workflow 'house'"):
            remove_definition(self.store, None, "workflow", "house", changed_by="alice")

    def test_going_back_to_what_is_shipped(self) -> None:
        save_role(self.store, None, reviewer_on("claude-opus-5-5"), changed_by="alice")

        left = remove_definition(self.store, None, "role", "code_reviewer", changed_by="alice")

        self.assertTrue(left)
        self.assertEqual(self.model("p1"), "claude-sonnet-5-5")
        self.assertEqual(len(self.store.definition_revisions(None, "role", "code_reviewer")), 2)

    def test_the_dashboard_reads_and_saves_the_defaults(self) -> None:
        payload = self.request("GET", "/definitions").json()
        development = next(w for w in payload["workflows"] if w["id"] == "development")
        self.assertEqual(development["used_by"], ["p1", "p2"])
        reviewer = next(role for role in payload["roles"] if role["id"] == "code_reviewer")
        fields = fields_of(reviewer)
        fields["model"] = "claude-opus-5-5"

        response = self.request("PUT", "/roles/code_reviewer", json={"fields": fields})

        self.assertEqual(response.status_code, 200, response.text)
        saved = next(role for role in response.json()["roles"] if role["id"] == "code_reviewer")
        self.assertEqual((saved["model"], saved["origin"]), ("claude-opus-5-5", "changed"))
        self.assertEqual(self.model("p1"), "claude-opus-5-5")
        # A project's editor starts from the default's text, not the shipped file's.
        self.assertIn("claude-opus-5-5", self.role("code_reviewer")["text"])
        # The plain lists read the defaults too.
        listed = self.request("GET", "/roles").json()["roles"]
        self.assertEqual(next(r for r in listed if r["id"] == "code_reviewer")["model"], "claude-opus-5-5")

        response = self.request("DELETE", "/roles/code_reviewer")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.model("p1"), "claude-sonnet-5-5")

    def test_a_refused_default_is_a_400_with_the_reason(self) -> None:
        response = self.request("PUT", "/roles/code_reviewer", json={"text": "not toml ["})

        self.assertEqual(response.status_code, 400)

    def test_a_new_role_or_workflow_may_start_empty(self) -> None:
        payload = self.request("GET", "/projects/p1/definitions").json()
        blank = payload["blank"]
        self.assertEqual((blank["role"]["id"], blank["workflow"]["id"]), ("_blank", "_blank"))
        self.assertIn("{completion_marker}", blank["role"]["prompt"])
        self.assertIn("claude-haiku-5-5", payload["vocabulary"]["models"])
        fields = fields_of(blank["role"])
        fields["name"] = "Doc Writer"

        response = self.request("PUT", "/projects/p1/roles/doc_writer", json={"fields": fields, "copy_of": "_blank"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(project_definitions(self.store, "p1").roles["doc_writer"].name, "Doc Writer")
        response = self.request(
            "PUT",
            "/projects/p1/workflows/tiny",
            json={"fields": {"name": "Tiny", "steps": blank["workflow"]["steps"]}, "copy_of": "_blank"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            [s.id for s in project_definitions(self.store, "p1").workflows["tiny"].steps],
            ["develop", "test", "review", "merge", "done"],
        )


class ModelCheckTests(ApiTests):
    """A role is not saved with a model the agent program cannot run."""

    def save_with(self, model: str):
        fields = fields_of(self.role("code_reviewer"))
        fields["model"] = model
        return self.request("PUT", "/projects/p1/roles/code_reviewer", json={"fields": fields})

    def test_a_model_the_program_cannot_run_is_refused_with_its_reason(self) -> None:
        self.unknown_models.add("minimax")

        response = self.save_with("minimax")

        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot run the model 'minimax'", response.json()["error"])
        self.assertEqual(project_definitions(self.store, "p1").roles["code_reviewer"].agent.model, "claude-sonnet-5-5")
        self.assertEqual(self.store.current_definitions("p1"), [])

    def test_a_model_it_can_run_is_saved_after_asking(self) -> None:
        self.assertEqual(self.save_with("claude-opus-5-5").status_code, 200)
        self.assertEqual(self.asked, [("claude_code", "claude-opus-5-5")])

    def test_it_is_not_asked_again_when_the_model_did_not_change(self) -> None:
        self.save_with("claude-opus-5-5")
        self.asked.clear()

        fields = fields_of(self.role("code_reviewer"))
        fields["timeout_minutes"] = 25
        response = self.request("PUT", "/projects/p1/roles/code_reviewer", json={"fields": fields})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.asked, [])

    def test_no_model_means_the_projects_default_and_nothing_to_ask(self) -> None:
        self.assertEqual(self.save_with("").status_code, 200)
        self.assertEqual(self.asked, [])

    def test_the_terminal_command_asks_too(self) -> None:
        self.unknown_models.add("minimax")
        path = Path(self._temp.name) / "role.toml"
        path.write_text(reviewer_on("minimax"), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["role", "set", "p1", "--file", str(path), "--db", str(self.db_path)])

        self.assertNotEqual(code, 0)
        self.assertIn("cannot run the model 'minimax'", out.getvalue() + err.getvalue())


class ModelCheckProgramTests(unittest.TestCase):
    """What is asked of the agent program, and how its answer is read."""

    def answer(self, stdout: str, *, found: bool = True):
        from foreman.runner import model_check

        done = mock.Mock(stdout=stdout)
        with (
            mock.patch.object(model_check.shutil, "which", return_value="/bin/claude" if found else None),
            mock.patch.object(model_check.subprocess, "run", return_value=done) as run,
            mock.patch.dict(model_check.os.environ, {}, clear=False),
        ):
            model_check.os.environ.pop(model_check.SWITCH, None)
            return model_check.check_model("claude_code", "minimax"), run

    def test_the_programs_refusal_is_passed_on_in_its_words(self) -> None:
        problem, run = self.answer('{"is_error": true, "result": "It may not exist or you may not have access to it."}')

        self.assertIn("cannot run the model 'minimax'", problem)
        self.assertIn("It may not exist or you may not have access to it.", problem)
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["/bin/claude", "--model", "minimax"])
        # It is asked one question and given no tools to answer it with.
        self.assertEqual(command[command.index("--tools") + 1], "")

    def test_an_answer_is_no_problem(self) -> None:
        self.assertIsNone(self.answer('{"is_error": false, "result": "ok"}')[0])

    def test_what_cannot_be_asked_or_read_refuses_nothing(self) -> None:
        self.assertIsNone(self.answer("not json")[0])
        problem, run = self.answer("{}", found=False)
        self.assertIsNone(problem)
        run.assert_not_called()

    def test_another_backend_is_not_asked(self) -> None:
        from foreman.runner import model_check

        with mock.patch.object(model_check.subprocess, "run") as run:
            self.assertIsNone(model_check.check_model("codex", "o3"))
        run.assert_not_called()

