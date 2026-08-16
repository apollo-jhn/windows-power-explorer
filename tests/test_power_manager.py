"""Tests for core/power_manager.py."""

import unittest
from unittest.mock import MagicMock, patch

from core.errors import PowerExplorerError, ValueOutOfBoundsError
from core.models import ControlType, SettingValueChoice
from core.power_manager import PowerManager
from core.win32_bindings import (
    ERROR_SUCCESS,
    GUID_MAX_POWER_SAVINGS,
    GUID_MIN_POWER_SAVINGS,
    GUID_TYPICAL_POWER_SAVINGS,
)


class TestPowerManager(unittest.TestCase):

    @patch("core.power_manager.powrprof")
    def test_editing_inactive_scheme_does_not_switch_active(self, mock_api):
        """PowerSetActiveScheme must NOT be called when editing an inactive scheme (REQ-2.3)."""
        mock_api.PowerWriteACValueIndex.return_value = ERROR_SUCCESS
        mock_api.PowerSetActiveScheme.return_value = ERROR_SUCCESS

        pm = PowerManager()
        with patch.object(pm, "get_active_scheme_guid", return_value="381b4222-f694-41f0-9685-ff5bb260df2e"):
            pm.write_ac_value(
                scheme_guid="8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",  # Inactive scheme
                subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
                setting_guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
                value=80,
            )

            mock_api.PowerWriteACValueIndex.assert_called_once()
            mock_api.PowerSetActiveScheme.assert_not_called()

    @patch("core.power_manager.powrprof")
    def test_editing_active_scheme_refreshes_policy(self, mock_api):
        """PowerSetActiveScheme MUST be called when editing the currently active scheme (REQ-2.3)."""
        mock_api.PowerWriteACValueIndex.return_value = ERROR_SUCCESS
        mock_api.PowerSetActiveScheme.return_value = ERROR_SUCCESS

        active_scheme = "381b4222-f694-41f0-9685-ff5bb260df2e"
        pm = PowerManager()
        with patch.object(pm, "get_active_scheme_guid", return_value=active_scheme):
            pm.write_ac_value(
                scheme_guid=active_scheme,
                subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
                setting_guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
                value=80,
            )

            mock_api.PowerWriteACValueIndex.assert_called_once()
            mock_api.PowerSetActiveScheme.assert_called_once()

    def test_bounds_validation_rejects_out_of_range(self):
        """Values outside min/max must raise ValueOutOfBoundsError before any FFI call."""
        pm = PowerManager()
        with self.assertRaises(ValueOutOfBoundsError):
            pm.write_ac_value(
                scheme_guid="381b4222-f694-41f0-9685-ff5bb260df2e",
                subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
                setting_guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
                value=-5,
                bounds=(0, 100),
            )

        with self.assertRaises(ValueOutOfBoundsError):
            pm.write_ac_value(
                scheme_guid="381b4222-f694-41f0-9685-ff5bb260df2e",
                subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
                setting_guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
                value=105,
                bounds=(0, 100),
            )

    def test_delete_built_in_scheme_rejected(self):
        """Cannot delete standard OS built-in schemes."""
        pm = PowerManager()
        built_in = "381b4222-f694-41f0-9685-ff5bb260df2e"
        with self.assertRaises(PowerExplorerError):
            pm.delete_scheme(built_in)

    def test_delete_active_scheme_rejected(self):
        """Cannot delete the currently active power scheme."""
        pm = PowerManager()
        custom_guid = "11111111-2222-3333-4444-555555555555"
        with patch.object(pm, "get_active_scheme_guid", return_value=custom_guid):
            with self.assertRaises(PowerExplorerError):
                pm.delete_scheme(custom_guid)

    def test_infer_control_type(self):
        """Verify control type inference based on bounds and enum choices."""
        choices = [SettingValueChoice(0, "Disabled", ""), SettingValueChoice(1, "Enabled", "")]
        self.assertEqual(PowerManager.infer_control_type(choices, 0, 1), ControlType.ENUM)
        self.assertEqual(PowerManager.infer_control_type([], 0, 1), ControlType.TOGGLE)
        self.assertEqual(PowerManager.infer_control_type([], 0, 100), ControlType.RANGE)
        self.assertEqual(PowerManager.infer_control_type([], None, None), ControlType.READONLY)

    def test_personality_of(self):
        """personality_of resolves personality setting index to canonical GUID."""
        pm = PowerManager()
        with patch.object(pm, "read_ac_value", return_value=0):
            self.assertEqual(pm.personality_of("381b4222-f694-41f0-9685-ff5bb260df2e"), GUID_MAX_POWER_SAVINGS)

        with patch.object(pm, "read_ac_value", return_value=1):
            self.assertEqual(pm.personality_of("381b4222-f694-41f0-9685-ff5bb260df2e"), GUID_MIN_POWER_SAVINGS)

        with patch.object(pm, "read_ac_value", return_value=2):
            self.assertEqual(pm.personality_of("381b4222-f694-41f0-9685-ff5bb260df2e"), GUID_TYPICAL_POWER_SAVINGS)

        with patch.object(pm, "read_ac_value", return_value=None):
            self.assertEqual(pm.personality_of("381b4222-f694-41f0-9685-ff5bb260df2e"), GUID_TYPICAL_POWER_SAVINGS)


if __name__ == "__main__":
    unittest.main()
