"""Tasks carry labels, and a project names its labels and path groups
(ADR-0041 section 1, FOR-107).

The settings are validated; a task's labels are stored, set and removed by the
CLI, refused when the project does not name them, and read and changed through
the API; the path-group matching answers the facts ``changed:`` and
``changed_only:``.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from foreman.cli import main
from foreman.domain.labels import (
    LabelError,
    changed_in,
    changed_only_in,
    groups_of_paths,
    matches_pattern,
    parse_labels,
    parse_path_groups,
)
from foreman.domain.models import Project, Sprint
from foreman.domain.settings import ProjectSettings, SettingsError
from foreman.mutations import MutationError, Mutations
from foreman.services import Services
from foreman.services.errors import InvalidRequestError
from foreman.store import ForemanStore

LABELS = {"ui": "changes what a person sees", "needs-docs": "the manual changes too"}
GROUPS = {
    "frontend": ["frontend/**"],
    "docs": ["docs/**", "*.md"],
    "tests": ["tests/", "**/test_*.py"],
}


class SettingsTests(unittest.TestCase):
    def test_labels_and_path_groups_are_read_typed(self) -> None:
        settings = ProjectSettings.from_raw({"labels": LABELS, "path_groups": GROUPS})

        self.assertEqual(settings.labels, LABELS)
        self.assertEqual(settings.path_groups["docs"], ("docs/**", "*.md"))

    def test_neither_is_set_by_default(self) -> None:
        settings = ProjectSettings.from_raw({})

        self.assertEqual((settings.labels, settings.path_groups), ({}, {}))

    def test_a_name_is_lowercase_words_joined_by_dash_or_underscore(self) -> None:
        for good in ("ui", "needs-docs", "needs_docs", "v2", "a-b_c"):
            self.assertEqual(list(parse_labels({good: "m"})), [good])
        for bad in ("UI", "needs docs", "-ui", "ui-", "a--b", "", "ui/x", "ünï"):
            with self.assertRaises(LabelError, msg=bad):
                parse_labels({bad: "m"})
            with self.assertRaises(LabelError, msg=bad):
                parse_path_groups({bad: ["a/**"]})

    def test_a_label_needs_a_one_line_meaning(self) -> None:
        for bad in ("", "  ", "two\nlines", None, 3):
            with self.assertRaises(LabelError, msg=repr(bad)):
                parse_labels({"ui": bad})
        with self.assertRaises(LabelError):
            parse_labels(["ui"])

    def test_a_pattern_is_relative_and_has_no_parent_part(self) -> None:
        for bad in ("/etc/**", "~/x", "../x", "a/../b", "!docs/**", "", "  ", "a\\b", 3):
            with self.assertRaises(LabelError, msg=repr(bad)):
                parse_path_groups({"g": [bad]})
        with self.assertRaises(LabelError):
            parse_path_groups({"g": []})
        with self.assertRaises(LabelError):
            parse_path_groups({"g": 3})
        # A name that merely holds two dots is not a parent part.
        self.assertEqual(parse_path_groups({"g": ["a..b/**"]}), {"g": ("a..b/**",)})

    def test_a_bad_setting_is_a_settings_error_naming_the_setting(self) -> None:
        with self.assertRaises(SettingsError) as caught:
            ProjectSettings.from_raw({"labels": {"UI": "x"}})
        self.assertIn("labels:", str(caught.exception))
        with self.assertRaises(SettingsError) as caught:
            ProjectSettings.from_raw({"path_groups": {"fe": ["../x"]}})
        self.assertIn("path_groups:", str(caught.exception))


class PatternTests(unittest.TestCase):
    def test_a_directory_pattern_matches_everything_below_it(self) -> None:
        self.assertTrue(matches_pattern("frontend/src/App.jsx", "frontend/**"))
        self.assertTrue(matches_pattern("frontend/a.js", "frontend/**"))
        self.assertTrue(matches_pattern("frontend/src/App.jsx", "frontend/"))
        self.assertTrue(matches_pattern("frontend/src/App.jsx", "frontend"))
        self.assertFalse(matches_pattern("frontend-old/a.js", "frontend/**"))
        self.assertFalse(matches_pattern("src/frontend/a.js", "frontend/**"))

    def test_a_glob_without_a_slash_matches_at_any_depth(self) -> None:
        self.assertTrue(matches_pattern("docs/guide/a.md", "*.md"))
        self.assertTrue(matches_pattern("a.md", "*.md"))
        self.assertFalse(matches_pattern("a.mdx", "*.md"))
        self.assertTrue(matches_pattern("tests/test_labels.py", "**/test_*.py"))
        self.assertTrue(matches_pattern("test_x.py", "**/test_*.py"))
        self.assertFalse(matches_pattern("tests/helper.py", "**/test_*.py"))

    def test_a_pattern_with_a_slash_is_anchored_at_the_root(self) -> None:
        self.assertTrue(matches_pattern("docs/a.md", "docs/*.md"))
        self.assertFalse(matches_pattern("docs/guide/a.md", "docs/*.md"))
        self.assertFalse(matches_pattern("x/docs/a.md", "docs/*.md"))
        self.assertTrue(matches_pattern("docs/guide/a.md", "docs/**/a.md"))
        self.assertTrue(matches_pattern("docs/a.md", "docs/**/a.md"))

    def test_a_file_at_the_root_is_matched_by_its_name(self) -> None:
        self.assertTrue(matches_pattern("pyproject.toml", "pyproject.toml"))
        self.assertTrue(matches_pattern("pyproject.toml", "*.toml"))
        self.assertFalse(matches_pattern("pyproject.toml", "frontend/**"))

    def test_a_question_mark_and_a_class_stay_within_one_part(self) -> None:
        self.assertTrue(matches_pattern("a1.py", "a?.py"))
        self.assertFalse(matches_pattern("a/.py", "a?.py"))
        self.assertTrue(matches_pattern("b.py", "[ab].py"))
        self.assertFalse(matches_pattern("c.py", "[ab].py"))

    def test_a_path_is_taken_as_relative_to_the_repository(self) -> None:
        self.assertTrue(matches_pattern("./docs/a.md", "docs/**"))
        self.assertTrue(matches_pattern("/docs/a.md", "docs/**"))


class PathGroupTests(unittest.TestCase):
    def groups(self, *paths: str) -> dict[str, frozenset[str]]:
        return groups_of_paths(paths, GROUPS)

    def test_each_path_is_given_the_groups_it_falls_in(self) -> None:
        found = self.groups("frontend/a.js", "README.md", "docs/x.md", "tests/test_a.py", "setup.cfg")

        self.assertEqual(found["frontend/a.js"], {"frontend"})
        self.assertEqual(found["README.md"], {"docs"})
        self.assertEqual(found["docs/x.md"], {"docs"})
        self.assertEqual(found["tests/test_a.py"], {"tests"})
        self.assertEqual(found["setup.cfg"], frozenset())

    def test_a_path_may_fall_in_several_groups(self) -> None:
        self.assertEqual(self.groups("docs/README.md")["docs/README.md"], {"docs"})
        both = groups_of_paths(["docs/a.md"], {"one": ["docs/**"], "two": ["*.md"]})
        self.assertEqual(both["docs/a.md"], {"one", "two"})

    def test_changed_is_any_path_in_the_group(self) -> None:
        found = self.groups("frontend/a.js", "setup.cfg")

        self.assertTrue(changed_in(found, "frontend"))
        self.assertFalse(changed_in(found, "docs"))
        self.assertFalse(changed_in(found, "unnamed"))

    def test_changed_only_is_every_path_in_the_listed_groups(self) -> None:
        docs_and_tests = self.groups("docs/a.md", "README.md", "tests/test_a.py")

        self.assertTrue(changed_only_in(docs_and_tests, ["docs", "tests"]))
        self.assertFalse(changed_only_in(docs_and_tests, ["docs"]))
        self.assertTrue(changed_only_in(self.groups("docs/a.md"), ["docs"]))

    def test_a_path_in_no_group_defeats_changed_only(self) -> None:
        found = self.groups("docs/a.md", "setup.cfg")

        self.assertFalse(changed_only_in(found, ["docs", "frontend", "tests"]))
        self.assertTrue(changed_in(found, "docs"))

    def test_a_change_of_nothing_is_not_only_anything(self) -> None:
        self.assertFalse(changed_only_in(self.groups(), ["docs"]))
        self.assertFalse(changed_in(self.groups(), "docs"))


class _Project(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.db_path = Path(self._temp.name) / "foreman.db"
        self.store = ForemanStore(self.db_path)
        self.addCleanup(self.store.close)
        self.store.initialize()
        self.project = Project(
            id="p1",
            name="P",
            repo_path=self._temp.name,
            workflow_id="development",
            settings={"labels": dict(LABELS)},
        )
        self.store.save_project(self.project)
        self.store.save_sprint(Sprint(id="s1", project_id="p1", title="S", status="active"))
        self.mutations = Mutations(self.store, via="cli", actor="alice")

    def stored(self, task_id: str):
        task = self.store.get_task(task_id)
        assert task is not None
        return task

    def name_labels(self, labels: dict[str, str]) -> None:
        project = self.store.get_project("p1")
        project.settings = {**project.settings, "labels": labels}
        self.store.save_project(project)


class StoreTests(_Project):
    def test_labels_are_stored_and_read_back_in_order(self) -> None:
        task = self.mutations.add_task(
            self.store.get_sprint("s1"), title="T", labels=["needs-docs", "ui", "ui"]
        )

        self.assertEqual(self.stored(task.id).labels, ["needs-docs", "ui"])

    def test_a_task_made_without_labels_carries_none(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T")

        self.assertEqual(self.stored(task.id).labels, [])

    def test_the_migration_gives_an_existing_task_none(self) -> None:
        from test_migrations import IncrementalUpgradeTests

        # The labels column came with migration 37: start just before it, not
        # before whatever the latest migration is.
        before = 36
        old = IncrementalUpgradeTests()._apply_migrations_up_to(before)
        connection = old._connection
        try:
            stamp = "2026-01-01T00:00:00+00:00"
            connection.execute(
                "INSERT INTO projects (id, name, repo_path, workflow_id, created_at, updated_at)"
                " VALUES ('p', 'P', '/tmp/x', 'development', ?, ?)",
                (stamp, stamp),
            )
            connection.execute(
                "INSERT INTO sprints (id, project_id, title, status, created_at)"
                " VALUES ('s', 'p', 'S', 'active', ?)",
                (stamp,),
            )
            connection.execute(
                "INSERT INTO tasks (id, sprint_id, project_id, title, created_at)"
                " VALUES ('t', 's', 'p', 'Old', ?)",
                (stamp,),
            )
            old.migrate()
            task = old.get_task("t")
        finally:
            connection.close()

        self.assertEqual(task.labels, [])


class MutationTests(_Project):
    def test_a_label_the_project_does_not_name_is_refused_with_the_names_it_does(self) -> None:
        with self.assertRaises(MutationError) as caught:
            self.mutations.add_task(self.store.get_sprint("s1"), title="T", labels=["ui", "backend"])

        message = str(caught.exception)
        self.assertIn("'backend'", message)
        self.assertIn("needs-docs, ui", message)
        self.assertEqual(self.store.list_tasks(sprint_id="s1"), [])
        with self.assertRaises(MutationError):
            self.mutations.file_task(self.project, title="T", labels=["backend"])
        self.assertEqual(self.store.list_tasks(project_id="p1"), [])

    def test_a_project_that_names_none_refuses_every_label_and_says_so(self) -> None:
        self.name_labels({})

        with self.assertRaises(MutationError) as caught:
            self.mutations.add_task(self.store.get_sprint("s1"), title="T", labels=["ui"])
        self.assertIn("It names: none", str(caught.exception))

    def test_file_task_carries_labels_into_the_backlog(self) -> None:
        filed = self.mutations.file_task(self.project, title="T", labels=["ui"])

        self.assertEqual(self.stored(filed.task.id).labels, ["ui"])

    def test_edit_task_sets_and_removes_them_and_records_the_change(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T", labels=["ui"])

        changed = self.mutations.edit_task(task, {"labels": ["ui", "needs-docs"]})
        self.assertEqual(changed, {"labels": ["ui", "needs-docs"]})
        changed = self.mutations.edit_task(task, {"labels": []})
        self.assertEqual(changed, {"labels": []})
        self.assertEqual(self.stored(task.id).labels, [])
        self.assertEqual(self.mutations.edit_task(task, {"labels": []}), {})

    def test_edit_task_refuses_a_new_label_the_project_does_not_name(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T", labels=["ui"])

        with self.assertRaises(MutationError):
            self.mutations.edit_task(task, {"labels": ["ui", "backend"]})
        self.assertEqual(self.stored(task.id).labels, ["ui"])

    def test_removing_a_label_from_the_setting_leaves_the_task_with_it(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T", labels=["ui", "needs-docs"])
        self.name_labels({"needs-docs": "the manual changes too"})

        self.assertEqual(self.stored(task.id).labels, ["ui", "needs-docs"])
        # An edit that keeps the unknown label is not refused; one that adds it again is.
        self.mutations.edit_task(task, {"labels": ["ui", "needs-docs"], "priority": 2})
        self.mutations.edit_task(task, {"labels": ["ui"]})
        with self.assertRaises(MutationError):
            self.mutations.edit_task(task, {"labels": ["ui", "needs-docs", "backend"]})
        self.assertEqual(self.stored(task.id).labels, ["ui"])
        with self.assertRaises(MutationError):
            self.mutations.edit_task(self.stored(task.id), {"labels": ["ui", "ui2"]})

    def test_a_malformed_list_is_refused(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T")

        with self.assertRaises(MutationError):
            self.mutations.edit_task(task, {"labels": {"ui": 1}})
        with self.assertRaises(MutationError):
            self.mutations.edit_task(task, {"labels": [3]})


class ApiTests(_Project):
    def test_a_task_is_created_changed_and_read_with_its_labels(self) -> None:
        api = Services(self.store)

        created = api.tasks.create_task("s1", title="T", labels=["ui"])
        self.assertEqual(created["labels"], ["ui"])
        detail = api.tasks.update_task_fields(created["id"], updates={"labels": ["ui", "needs-docs"]})
        self.assertEqual(detail["labels"], ["ui", "needs-docs"])
        self.assertEqual(detail["unknown_labels"], [])
        self.assertEqual(api.tasks.get_task(created["id"])["labels"], ["ui", "needs-docs"])

    def test_a_label_the_project_no_longer_names_is_returned_as_unknown(self) -> None:
        api = Services(self.store)
        created = api.tasks.create_task("s1", title="T", labels=["ui", "needs-docs"])
        self.name_labels({"ui": "changes what a person sees"})

        detail = api.tasks.get_task(created["id"])

        self.assertEqual(detail["labels"], ["ui", "needs-docs"])
        self.assertEqual(detail["unknown_labels"], ["needs-docs"])

    def test_an_unnamed_label_is_an_invalid_request_naming_the_known_ones(self) -> None:
        api = Services(self.store)

        with self.assertRaises(InvalidRequestError) as caught:
            api.tasks.create_task("s1", title="T", labels=["backend"])
        self.assertIn("needs-docs, ui", str(caught.exception))
        created = api.tasks.create_task("s1", title="T")
        with self.assertRaises(InvalidRequestError):
            api.tasks.update_task_fields(created["id"], updates={"labels": ["backend"]})
        with self.assertRaises(InvalidRequestError):
            api.backlog.file_backlog_task("p1", title="T", labels=["backend"])

    def test_a_backlog_task_carries_them(self) -> None:
        filed = Services(self.store).backlog.file_backlog_task("p1", title="T", labels=["ui"])

        self.assertEqual(filed["labels"], ["ui"])


class CliTests(_Project):
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*argv, "--db", str(self.db_path)])
        return code, out.getvalue(), err.getvalue()

    def test_config_sets_validates_and_shows_both_settings(self) -> None:
        code, out, err = self.run_cli(
            "config", "p1", "--set", 'path_groups={"frontend": ["frontend/**"], "docs": ["*.md"]}'
        )
        self.assertEqual(code, 0, err)
        self.assertIn("path_groups=", out)
        code, out, _ = self.run_cli("config", "p1")
        self.assertIn('- labels={"needs-docs": "the manual changes too", "ui": "changes what a person sees"}', out)
        self.assertIn('"frontend": ["frontend/**"]', out)
        code, _, err = self.run_cli("config", "p1", "--set", 'path_groups={"Front": ["x/**"]}')
        self.assertEqual(code, 1)
        self.assertIn("Invalid setting path_groups", err)
        code, _, err = self.run_cli("config", "p1", "--set", 'path_groups={"fe": ["../x"]}')
        self.assertEqual(code, 1)
        code, _, err = self.run_cli("config", "p1", "--set", 'labels={"ui": ""}')
        self.assertEqual(code, 1)
        self.assertIn("Invalid setting labels", err)

    def test_neither_setting_is_host_level(self) -> None:
        from foreman.domain.settings import HOST_LEVEL_SETTINGS

        self.assertFalse({"labels", "path_groups"} & HOST_LEVEL_SETTINGS)

    def test_task_add_sets_labels_and_refuses_an_unnamed_one(self) -> None:
        code, out, err = self.run_cli(
            "task", "add", "p1", "--title", "T", "--criteria", "C", "--label", "ui", "--label", "needs-docs"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Labels: ui, needs-docs", out)
        code, _, err = self.run_cli("task", "add", "p1", "--title", "U", "--criteria", "C", "--label", "backend")
        self.assertEqual(code, 1)
        self.assertIn("It names: needs-docs, ui", err)
        self.assertEqual(len(self.store.list_tasks(sprint_id="s1")), 1)

    def test_task_edit_adds_and_removes_one_label_at_a_time(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T", labels=["ui"])

        code, out, err = self.run_cli("task", "edit", task.id, "--label", "needs-docs")
        self.assertEqual(code, 0, err)
        self.assertIn("Labels: ui -> ui, needs-docs", out)
        code, out, err = self.run_cli("task", "edit", task.id, "--remove-label", "ui")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.stored(task.id).labels, ["needs-docs"])
        code, _, err = self.run_cli("task", "edit", task.id, "--remove-label", "ui")
        self.assertEqual(code, 1)
        self.assertIn("does not carry the label ui", err)
        code, _, err = self.run_cli("task", "edit", task.id, "--label", "backend")
        self.assertEqual(code, 1)
        self.assertIn("does not name", err)
        code, _, err = self.run_cli("task", "edit", task.id, "--label", "ui", "--remove-label", "ui")
        self.assertEqual(code, 1)
        self.assertIn("not both", err)
        self.assertEqual(self.stored(task.id).labels, ["needs-docs"])

    def test_task_edit_removes_a_label_the_project_no_longer_names(self) -> None:
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T", labels=["ui"])
        self.name_labels({"needs-docs": "x"})

        code, _, err = self.run_cli("task", "edit", task.id, "--remove-label", "ui")

        self.assertEqual(code, 0, err)
        self.assertEqual(self.stored(task.id).labels, [])

    def test_backlog_add_sets_labels_and_refuses_an_unnamed_one(self) -> None:
        code, out, err = self.run_cli("backlog", "add", "p1", "--title", "T", "--label", "ui")
        self.assertEqual(code, 0, err)
        self.assertIn("Labels: ui", out)
        code, _, err = self.run_cli("backlog", "add", "p1", "--title", "U", "--label", "backend")
        self.assertEqual(code, 1)
        self.assertIn("It names: needs-docs, ui", err)
        self.assertEqual(len(self.store.list_tasks(project_id="p1")), 1)


if __name__ == "__main__":
    unittest.main()


class ReviewFixTests(_Project):
    """Sprint 69 review of FOR-107."""

    def test_patterns_that_would_crash_or_never_match_are_refused(self) -> None:
        for bad in ("[!]x", "[z-a].py", "./docs/**", "docs//a", "docs/./a",
                    "[[:alpha:]]", "C:/x", "docs/ ..", ".. /x"):
            with self.subTest(bad=bad), self.assertRaises(LabelError):
                parse_path_groups({"g": [bad]})

    def test_a_trailing_slash_names_a_directory_at_any_depth(self) -> None:
        self.assertTrue(matches_pattern("docs/a.md", "docs/"))
        self.assertTrue(matches_pattern("tools/docs/a.md", "docs/"))
        self.assertFalse(matches_pattern("docs", "docs/"))
        self.assertFalse(matches_pattern("tools/docs", "docs/"))
        # Without the trailing slash a file of that name is matched too.
        self.assertTrue(matches_pattern("docs", "docs"))

    def test_a_task_without_labels_is_added_whatever_the_other_settings_say(self) -> None:
        self.project.settings["max_step_visits"] = "lots"
        self.store.save_project(self.project)
        task = self.mutations.add_task(self.store.get_sprint("s1"), title="T")
        self.assertEqual(self.stored(task.id).labels, [])
