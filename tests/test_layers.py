"""What the layers contract cannot see (ADR-0032).

``.importlinter`` says which package may import which. It cannot say that a
surface which may import the store must not write rows with it. That is how
the CLI and the dashboard came to have their own copies of the same change
(adding a task, creating a sprint, changing a setting), with rules that had
drifted apart. Every change to a project, sprint, task, decision gate or
merge waiver goes through ``foreman.mutations``, and these tests hold that
for the CLI, the HTTP API and the services.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "foreman"
SURFACES = ("cli", "api", "services")

#: Rows only ``foreman.mutations`` creates.
RECORDS = frozenset({"Project", "Sprint", "Task", "DecisionGate", "MergeWaiver"})


def _surface_modules():
    for surface in SURFACES:
        for path in sorted((ROOT / surface).rglob("*.py")):
            yield path, ast.parse(path.read_text())


def _receiver(node: ast.AST) -> str:
    """The dotted name a method is called on (``self.store``), or ``""``."""

    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


class SurfacesWriteThroughMutationsTests(unittest.TestCase):
    def test_no_surface_saves_a_row_itself(self) -> None:
        found = []
        for path, tree in _surface_modules():
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr.startswith("save_")
                    and "store" in _receiver(node.func.value).split(".")[-1]
                ):
                    found.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.func.attr}")
        self.assertEqual(found, [], "a surface writes a row; use foreman.mutations")

    def test_no_surface_makes_a_record_mutations_own(self) -> None:
        found = []
        for path, tree in _surface_modules():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in RECORDS:
                        found.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.func.id}")
        self.assertEqual(found, [], "a surface builds a row; use foreman.mutations")


if __name__ == "__main__":
    unittest.main()


#: Store reads that list or total rows. A CLI read command takes its data
#: from a service instead, so the terminal and the API show the same thing.
LISTING_READS = ("list_", "count_", "task_counts", "run_totals", "task_run_totals")

#: The CLI code that may still read rows itself, and why.
CLI_OWN_READS = {
    # `foreman watch` follows the event table as rows arrive; it is a tail,
    # not a report.
    ("monitor.py", "_build_run_watch_plan"),
    ("monitor.py", "_build_sprint_watch_plan"),
    ("monitor.py", "_build_project_watch_plan"),
    # Which sprint a new task goes into: a lookup that serves a change.
    ("common.py", "select_task_creation_sprint"),
}


class CliReadsThroughServicesTests(unittest.TestCase):
    def test_no_cli_read_command_lists_rows_itself(self) -> None:
        found = []
        for path in sorted((ROOT / "cli").rglob("*.py")):
            tree = ast.parse(path.read_text())
            for function in ast.walk(tree):
                if not isinstance(function, ast.FunctionDef):
                    continue
                if (path.name, function.name) in CLI_OWN_READS:
                    continue
                for node in ast.walk(function):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr.startswith(LISTING_READS)
                        and _receiver(node.func.value).split(".")[-1] == "store"
                    ):
                        found.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.func.attr}")
        self.assertEqual(sorted(set(found)), [], "a CLI command reads rows itself; use a service")

    def test_every_read_command_offers_json(self) -> None:
        from foreman.cli.parser import MANAGER_SESSION_COMMANDS, build_parser

        def leaves(parser, path=()):
            nested = [a for a in parser._actions if isinstance(getattr(a, "choices", None), dict)]
            if not nested:
                yield path, parser
                return
            for action in nested:
                for name, child in action.choices.items():
                    yield from leaves(child, (*path, name))

        missing = [
            " ".join(path)
            for path, parser in leaves(build_parser())
            if " ".join(path) in MANAGER_SESSION_COMMANDS
            # A live tail prints events as they come; there is no one document.
            and " ".join(path) != "watch"
            and not any("--json" in action.option_strings for action in parser._actions)
        ]
        self.assertEqual(missing, [])
