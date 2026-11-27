"""The systemd user units that ship with Foreman (ADR-0043, supervisor)."""

from __future__ import annotations

import configparser
import unittest
from pathlib import Path

UNITS = Path(__file__).resolve().parent.parent / "deploy" / "systemd"


def _read(name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read(UNITS / name, encoding="utf-8")
    return parser


class SystemdUnitTests(unittest.TestCase):
    def test_worker_unit_starts_at_boot_and_restarts_after_any_exit(self) -> None:
        unit = _read("foreman-worker@.service")
        self.assertEqual(unit["Service"]["Restart"], "always")
        self.assertEqual(unit["Install"]["WantedBy"], "default.target")
        self.assertTrue(unit["Service"]["ExecStart"].endswith(" serve %i"))

    def test_dashboard_unit_starts_at_boot_and_restarts_after_a_crash(self) -> None:
        unit = _read("foreman-dashboard.service")
        self.assertIn(unit["Service"]["Restart"], {"always", "on-failure"})
        self.assertEqual(unit["Install"]["WantedBy"], "default.target")
        self.assertTrue(unit["Service"]["ExecStart"].endswith(" dashboard"))


if __name__ == "__main__":
    unittest.main()
