"""The workflow reads and the settings errors the project settings page uses."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from foreman.dashboard.app import create_dashboard_app
from foreman.models import Project
from foreman.store import ForemanStore


class WorkflowApiCase(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = str(Path(self._temp.name) / "foreman.db")
        self.store = ForemanStore(self.db_path)
        self.store.initialize()
        self.addCleanup(self.store.close)
        self.app = create_dashboard_app(self.db_path, auth_token=None)

    def call(self, method: str, path: str, **kwargs) -> httpx.Response:
        async def run():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(run())

    def project(self, pid: str, workflow: str = "development", **settings) -> None:
        self.store.save_project(
            Project(id=pid, name=pid, repo_path=self._temp.name, workflow_id=workflow, settings=settings)
        )


class ProjectWorkflowTests(WorkflowApiCase):
    def test_steps_transitions_roles_and_source(self) -> None:
        self.project("p1")
        body = self.call("GET", "/api/v1/projects/p1/workflow").json()
        self.assertEqual(body["id"], "development")
        self.assertEqual(
            [step["id"] for step in body["steps"]],
            ["develop", "test", "review", "merge_approval", "merge", "done"],
        )
        self.assertTrue(body["source_path"].endswith("development.toml"))
        self.assertTrue(Path(body["source_path"]).is_file())
        by_edge = {(t["from"], t["outcome"]): t for t in body["transitions"]}
        self.assertEqual(by_edge[("test", "failure")]["to"], "develop")
        self.assertTrue(by_edge[("test", "failure")]["carry_output"])
        self.assertEqual(by_edge[("test", "success")]["to"], "review")
        self.assertEqual(by_edge[("merge_approval", "approve")]["to"], "merge")
        gate = next(step for step in body["steps"] if step["id"] == "merge_approval")
        self.assertEqual(gate["policy"], "merge_approval")

    def test_roles_are_the_ones_the_steps_use_with_backend_and_model(self) -> None:
        self.project("p1")
        roles = {r["id"]: r for r in self.call("GET", "/api/v1/projects/p1/workflow").json()["roles"]}
        self.assertEqual(set(roles), {"developer", "code_reviewer"})
        self.assertEqual(roles["developer"]["backend"], "claude_code")
        self.assertEqual(roles["developer"]["model"], "")
        self.assertTrue(roles["code_reviewer"]["model"])
        self.assertTrue(roles["code_reviewer"]["description"])

    def test_requirements_are_facts_and_claims_read_from_the_steps(self) -> None:
        self.project("p1")
        requirements = self.call("GET", "/api/v1/projects/p1/workflow").json()["requirements"]
        kinds = {r["id"]: r["kind"] for r in requirements}
        self.assertEqual(
            kinds, {"tests": "fact", "code-review": "claim", "acceptance-criteria": "claim"}
        )

    def test_another_workflow_has_other_steps_and_requirements(self) -> None:
        self.project("p1")
        self.project("p2", workflow="development_secure")
        first = self.call("GET", "/api/v1/projects/p1/workflow").json()
        second = self.call("GET", "/api/v1/projects/p2/workflow").json()
        self.assertEqual(second["id"], "development_secure")
        self.assertNotEqual([s["id"] for s in first["steps"]], [s["id"] for s in second["steps"]])
        self.assertIn("security-review", {r["id"] for r in second["requirements"]})
        self.assertNotIn("security-review", {r["id"] for r in first["requirements"]})

    def test_says_whether_requirements_are_enforced(self) -> None:
        self.project("p1")
        self.project("p2", completion_guard_enabled=False)
        self.assertTrue(self.call("GET", "/api/v1/projects/p1/workflow").json()["requirements_enforced"])
        self.assertFalse(self.call("GET", "/api/v1/projects/p2/workflow").json()["requirements_enforced"])

    def test_unknown_project_is_not_found(self) -> None:
        self.assertEqual(self.call("GET", "/api/v1/projects/nope/workflow").status_code, 404)


class WorkflowListTests(WorkflowApiCase):
    def test_lists_every_workflow_described_like_a_project_workflow(self) -> None:
        self.project("p1")
        listed = self.call("GET", "/api/v1/workflows").json()["workflows"]
        ids = {w["id"] for w in listed}
        self.assertIn("development", ids)
        self.assertIn("development_secure", ids)
        mine = self.call("GET", "/api/v1/projects/p1/workflow").json()
        development = next(w for w in listed if w["id"] == "development")
        for key in ("name", "steps", "transitions", "roles", "requirements", "source_path"):
            self.assertEqual(development[key], mine[key])


class ChangeWorkflowTests(WorkflowApiCase):
    def test_changes_the_projects_workflow(self) -> None:
        self.project("p1")
        response = self.call("PATCH", "/api/v1/projects/p1/settings", json={"workflow_id": "development_secure"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.get_project("p1").workflow_id, "development_secure")
        self.assertEqual(self.call("GET", "/api/v1/projects/p1/workflow").json()["id"], "development_secure")

    def test_refuses_a_workflow_that_does_not_exist(self) -> None:
        self.project("p1")
        response = self.call("PATCH", "/api/v1/projects/p1/settings", json={"workflow_id": "nope"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["field"], "workflow_id")
        self.assertEqual(self.store.get_project("p1").workflow_id, "development")


class SettingsFieldErrorTests(WorkflowApiCase):
    def test_a_refusal_names_the_setting_it_is_about(self) -> None:
        self.project("p1")
        response = self.call(
            "PATCH",
            "/api/v1/projects/p1/settings",
            json={"settings": {"max_step_visits": 3, "cost_limit_per_task_usd": -1}},
        )
        body = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(body["code"], "invalid_request")
        self.assertEqual(body["field"], "cost_limit_per_task_usd")
        self.assertIn("non-negative", body["error"])
        # Nothing was saved.
        self.assertNotIn("max_step_visits", self.store.get_project("p1").settings)

    def test_an_error_without_a_field_has_no_field_key(self) -> None:
        self.project("p1")
        body = self.call("PATCH", "/api/v1/projects/p1/settings", json={"unknown_field": 1}).json()
        self.assertNotIn("field", body)


if __name__ == "__main__":
    unittest.main()
