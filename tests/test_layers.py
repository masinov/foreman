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
