"""Tests for CLI Subcommands and Defaults Reset (Issue #26, REQ-9.6, REQ-15)."""

import io
import json
import unittest
from unittest.mock import MagicMock, patch

from cli.parser import parse_and_dispatch
from core.models import (
    ControlType,
    SettingCatalog,
    SettingCatalogEntry,
    SubgroupCatalogEntry,
)
from core.power_manager import PowerManager


class TestCliCommands(unittest.TestCase):

    def setUp(self):
        self.mock_pm = MagicMock(spec=PowerManager)
        self.mock_pm.get_active_scheme_guid.return_value = "381b4222-f694-41f0-9685-ff5bb260df2e"
        self.mock_pm.iter_schemes.return_value = [
            ("381b4222-f694-41f0-9685-ff5bb260df2e", "Balanced", "Default", True, True),
            ("custom-guid", "Custom Game", "Custom", False, False),
        ]
        self.mock_pm.personality_of.return_value = "381b4222-f694-41f0-9685-ff5bb260df2e"

        self.set_entry = SettingCatalogEntry(
            guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Maximum processor state",
            description="",
            control_type=ControlType.RANGE,
            min_value=0,
            max_value=100,
            value_increment=1,
            value_units="%",
            choices=(),
            is_hidden=False,
            is_policy_locked=False,
            is_degraded=False,
        )
        self.sub_entry = SubgroupCatalogEntry(
            guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor Power Management",
            description="",
            is_hidden=False,
            settings=(self.set_entry,),
        )
        self.catalog = SettingCatalog(
            subgroups=(self.sub_entry,),
            by_guid={self.set_entry.guid.lower(): self.set_entry},
            subgroup_by_guid={self.sub_entry.guid.lower(): self.sub_entry},
        )

    def test_cli_list_schemes_json(self):
        """list-schemes with --json outputs structured list (REQ-15)."""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            exit_code = parse_and_dispatch(["--json", "list-schemes"], pm=self.mock_pm)
            self.assertEqual(exit_code, 0)
            data = json.loads(mock_stdout.getvalue())
            self.assertTrue(data["ok"])
            self.assertEqual(len(data["data"]), 2)

    def test_cli_list_settings_modified_only(self):
        """list-settings --modified-only filters only deviating settings (REQ-9.6)."""
        with patch("cli.commands.build_catalog", return_value=self.catalog):
            # Simulate setting is modified (AC=80 vs default=100)
            self.mock_pm.read_ac_value.return_value = 80
            self.mock_pm.read_dc_value.return_value = 50
            self.mock_pm.read_ac_default.return_value = 100
            self.mock_pm.read_dc_default.return_value = 50

            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = parse_and_dispatch(["--json", "list-settings", "--modified-only"], pm=self.mock_pm)
                self.assertEqual(exit_code, 0)
                data = json.loads(mock_stdout.getvalue())
                self.assertTrue(data["ok"])
                self.assertEqual(len(data["data"]), 1)
                self.assertTrue(data["data"][0]["is_modified"])

    def test_cli_reset_setting(self):
        """reset-setting resets AC and DC to personality default (REQ-9.6)."""
        with patch("cli.commands.build_catalog", return_value=self.catalog):
            self.mock_pm.read_ac_default.return_value = 100
            self.mock_pm.read_dc_default.return_value = 50

            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = parse_and_dispatch(
                    ["reset-setting", "--setting", "bc502fe6-701e-46c4-9826-5d42490a1e9c"],
                    pm=self.mock_pm,
                )
                self.assertEqual(exit_code, 0)
                self.mock_pm.write_ac_value.assert_called_with(
                    "381b4222-f694-41f0-9685-ff5bb260df2e",
                    "54533251-82be-4824-96c1-47b60b740d00",
                    "bc502fe6-701e-46c4-9826-5d42490a1e9c",
                    100,
                    (0, 100),
                )

    def test_cli_dry_run_flag(self):
        """--dry-run simulates mutation without executing Win32 write (REQ-15.1)."""
        with patch("cli.commands.build_catalog", return_value=self.catalog):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                exit_code = parse_and_dispatch(
                    ["--dry-run", "edit-setting", "--setting", "bc502fe6-701e-46c4-9826-5d42490a1e9c", "--ac", "90"],
                    pm=self.mock_pm,
                )
                self.assertEqual(exit_code, 0)
                self.mock_pm.write_ac_value.assert_not_called()
                self.assertIn("[DRY-RUN]", mock_stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
