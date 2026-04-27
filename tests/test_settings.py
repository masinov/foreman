"""Tests for project settings validation."""

from __future__ import annotations

import unittest

from foreman.settings import (
    SettingsError,
    ProjectSettings,
    _validate_non_negative_float,
    _validate_non_negative_int,
    _validate_positive_int,
    _validate_task_selection_mode,
)


class ValidateTaskSelectionModeTests(unittest.TestCase):
    def test_defaults_to_directed(self) -> None:
        self.assertEqual(_validate_task_selection_mode(None), "directed")

    def test_accepts_directed(self) -> None:
        self.assertEqual(_validate_task_selection_mode("directed"), "directed")

    def test_accepts_autonomous(self) -> None:
        self.assertEqual(_validate_task_selection_mode("autonomous"), "autonomous")

    def test_rejects_invalid(self) -> None:
        with self.assertRaises(SettingsError):
            _validate_task_selection_mode("invalid")

    def test_rejects_non_string(self) -> None:
        with self.assertRaises(SettingsError):
            _validate_task_selection_mode(123)


class ValidatePositiveIntTests(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(_validate_positive_int(None, default=5), 5)

    def test_accepts_positive_int(self) -> None:
        self.assertEqual(_validate_positive_int(10, default=5), 10)

    def test_rejects_zero(self) -> None:
        with self.assertRaises(SettingsError):
            _validate_positive_int(0, default=5)

    def test_rejects_negative(self) -> None:
        with self.assertRaises(SettingsError):
            _validate_positive_int(-1, default=5)

    def test_rejects_float(self) -> None:
        with self.assertRaises(SettingsError):
            _validate_positive_int(3.14, default=5)


class ValidateNonNegativeIntTests(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(_validate_non_negative_int(None, default=0), 0)

    def test_accepts_zero(self) -> None:
        self.assertEqual(_validate_non_negative_int(0, default=5), 0)

    def test_accepts_positive(self) -> None:
        self.assertEqual(_validate_non_negative_int(10, default=0), 10)

    def test_rejects_negative(self) -> None:
        with self.assertRaises(SettingsError):
            _validate_non_negative_int(-1, default=0)


class ValidateNonNegativeFloatTests(unittest.TestCase):
    def test_defaults(self) -> None:
        self.assertEqual(_validate_non_negative_float(None, default=0.0), 0.0)

    def test_accepts_zero(self) -> None:
        self.assertEqual(_validate_non_negative_float(0.0, default=100.0), 0.0)

    def test_accepts_positive(self) -> None:
        self.assertEqual(_validate_non_negative_float(50.0, default=0.0), 50.0)

    def test_rejects_negative(self) -> None:
        with self.assertRaises(SettingsError):
            _validate_non_negative_float(-0.01, default=0.0)


class ProjectSettingsFromRawTests(unittest.TestCase):
    def test_empty_raw(self) -> None:
        settings = ProjectSettings.from_raw({})
        self.assertEqual(settings.task_selection_mode, "directed")
        self.assertEqual(settings.max_autonomous_tasks, 5)
        self.assertEqual(settings.max_step_visits, 5)
        self.assertEqual(settings.test_command, "")
        self.assertEqual(settings.time_limit_per_run_minutes, 0)
        self.assertEqual(settings.cost_limit_per_task_usd, 0.0)
        self.assertEqual(settings.cost_limit_per_sprint_usd, 0.0)

    def test_full_valid_raw(self) -> None:
        raw = {
            "task_selection_mode": "autonomous",
            "max_autonomous_tasks": 3,
            "max_step_visits": 10,
            "test_command": "pytest",
            "time_limit_per_run_minutes": 60,
            "cost_limit_per_task_usd": 50.0,
            "cost_limit_per_sprint_usd": 500.0,
            "time_limit_per_task_ms": 3600000,
            "completion_guard_enabled": False,
        }
        settings = ProjectSettings.from_raw(raw)
        self.assertEqual(settings.task_selection_mode, "autonomous")
        self.assertEqual(settings.max_autonomous_tasks, 3)
        self.assertEqual(settings.max_step_visits, 10)
        self.assertEqual(settings.test_command, "pytest")
        self.assertEqual(settings.time_limit_per_run_minutes, 60)
        self.assertEqual(settings.cost_limit_per_task_usd, 50.0)
        self.assertEqual(settings.cost_limit_per_sprint_usd, 500.0)
        self.assertEqual(settings.time_limit_per_task_ms, 3600000)
        self.assertFalse(settings.completion_guard_enabled)

    def test_invalid_mode(self) -> None:
        with self.assertRaises(SettingsError):
            ProjectSettings.from_raw({"task_selection_mode": "invalid"})

    def test_negative_max_visits(self) -> None:
        with self.assertRaises(SettingsError):
            ProjectSettings.from_raw({"max_step_visits": -1})
