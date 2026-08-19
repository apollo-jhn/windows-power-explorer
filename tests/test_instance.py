"""Tests for Single-Instance Guard (Issue #30, REQ-14)."""

import sys
import unittest
from unittest.mock import MagicMock, patch

from core.instance import (
    ERROR_ALREADY_EXISTS,
    MUTEX_NAME,
    acquire_single_instance_mutex,
    activate_existing_window,
    release_single_instance_mutex,
)
import main


class TestSingleInstanceGuard(unittest.TestCase):

    def test_session_scoped_mutex_name(self):
        """Mutex name must start with Local\\ for session scoping (REQ-14.2)."""
        self.assertTrue(
            MUTEX_NAME.startswith(r"Local\\") or MUTEX_NAME.startswith("Local\\"),
            f"Mutex name '{MUTEX_NAME}' must be session-scoped with Local\\ prefix",
        )
        self.assertIn("WindowsPowerExplorer", MUTEX_NAME)

    @patch("main.run_gui")
    def test_cli_bypasses_instance_guard(self, mock_run_gui):
        """CLI subcommands and flags bypass single-instance guard entirely (REQ-14.3)."""
        with patch("main.attach_console", return_value=True):
            exit_code = main.main(["--version"])
            self.assertEqual(exit_code, 0)
            mock_run_gui.assert_not_called()

        with patch("main.run_elevated_helper", return_value=0) as mock_helper:
            exit_code = main.main(["--elevated-helper", "test.json"])
            self.assertEqual(exit_code, 0)
            mock_helper.assert_called_once_with("test.json")
            mock_run_gui.assert_not_called()

    @patch("main.acquire_single_instance_mutex")
    @patch("main.activate_existing_window")
    def test_second_instance_activates_first(self, mock_activate, mock_acquire):
        """A second GUI launch activates existing window and exits 0 (REQ-14.1)."""
        # Simulate mutex already held by another instance
        mock_acquire.return_value = None

        exit_code = main.run_gui()

        # Must attempt window activation and return exit code 0
        mock_activate.assert_called_once()
        self.assertEqual(exit_code, 0)

    def test_acquire_and_release_mutex_lifecycle(self):
        """Acquiring and releasing single-instance mutex executes without errors."""
        handle = acquire_single_instance_mutex()
        self.assertIsNotNone(handle)
        release_single_instance_mutex(handle)


if __name__ == "__main__":
    unittest.main()
