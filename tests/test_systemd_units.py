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

    def test_units_are_given_the_installers_path(self) -> None:
        # A user unit's own PATH lacks ~/.local/bin, where `claude` usually is.
        for name in ("foreman-worker@.service", "foreman-dashboard.service"):
            self.assertEqual(_read(name)["Service"]["Environment"], '"PATH=@PATH@"', name)

    def test_restarts_outlast_the_lease_of_a_worker_killed_hard(self) -> None:
        from foreman.engine.lock import DEFAULT_LEASE_DURATION_SECONDS

        unit = _read("foreman-worker@.service")
        spacing = float(unit["Service"]["RestartSec"])
        starts = int(unit["Unit"]["StartLimitBurst"])
        window = float(unit["Unit"]["StartLimitIntervalSec"])
        # The starts left before systemd gives up reach past the dead lease.
        self.assertGreater(spacing * (starts - 1), DEFAULT_LEASE_DURATION_SECONDS)
        self.assertLessEqual(spacing * (starts - 1), window)

    def test_a_refused_schema_is_not_restarted(self) -> None:
        from foreman.cli.common import EXIT_SCHEMA_REFUSED

        for name in ("foreman-worker@.service", "foreman-dashboard.service"):
            codes = _read(name)["Service"]["RestartPreventExitStatus"].split()
            self.assertIn(str(EXIT_SCHEMA_REFUSED), codes, name)


if __name__ == "__main__":
    unittest.main()
