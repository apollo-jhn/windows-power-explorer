"""Tests for core/models.py and core/errors.py."""

import unittest

from core.errors import (
    ElevationDeclinedError,
    ElevationRequiredError,
    PolicyLockedError,
    PowerApiError,
    PowerExplorerError,
    PresetValidationError,
    SchemeNotFoundError,
    SettingNotFoundError,
    ValueOutOfBoundsError,
    user_message,
)
from core.models import (
    ControlType,
    EnumStats,
    OverlayInfo,
    SettingDiff,
    SettingValueChoice,
    ValueChange,
)


class TestModelsAndErrors(unittest.TestCase):

    def test_user_message_mappings(self):
        """user_message correctly formats Win32 error codes according to specification."""
        self.assertEqual(user_message(2), "That power scheme or setting no longer exists.")
        self.assertEqual(user_message(5), "This change needs Administrator permission.")
        self.assertEqual(user_message(13), "Windows rejected that value for this setting.")
        self.assertEqual(user_message(87), "Windows rejected that value for this setting.")
        self.assertEqual(user_message(1223), "Change cancelled.")

        # Unknown code falls back to generic message
        msg = user_message(999, action="saving custom scheme")
        self.assertIn("code 999", msg)
        self.assertIn("saving custom scheme", msg)

    def test_power_api_error_message(self):
        """PowerApiError integrates function name, code, and user message."""
        err = PowerApiError("PowerWriteACValueIndex", 87, context="Setting 123")
        self.assertIn("PowerWriteACValueIndex", str(err))
        self.assertIn("87", str(err))
        self.assertIn("rejected", str(err))
        self.assertIn("Setting 123", str(err))

    def test_exception_hierarchy(self):
        """All custom exceptions inherit from PowerExplorerError."""
        self.assertTrue(issubclass(PowerApiError, PowerExplorerError))
        self.assertTrue(issubclass(ElevationRequiredError, PowerExplorerError))
        self.assertTrue(issubclass(ElevationDeclinedError, PowerExplorerError))
        self.assertTrue(issubclass(ValueOutOfBoundsError, PowerExplorerError))
        self.assertTrue(issubclass(PolicyLockedError, PowerExplorerError))
        self.assertTrue(issubclass(SchemeNotFoundError, PowerExplorerError))
        self.assertTrue(issubclass(SettingNotFoundError, PowerExplorerError))
        self.assertTrue(issubclass(PresetValidationError, PowerExplorerError))

    def test_value_change_frozen(self):
        """ValueChange dataclass must be frozen (immutable)."""
        vc = ValueChange(
            scheme_guid="381b4222-f694-41f0-9685-ff5bb260df2e",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            setting_guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
            rail="ac",
            previous_value=100,
            new_value=80,
        )
        with self.assertRaises(Exception):
            vc.new_value = 50  # type: ignore

    def test_setting_diff_differs(self):
        """SettingDiff.differs property returns True only when left != right on any rail."""
        same = SettingDiff(
            setting_guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Max CPU",
            ac_left=100,
            ac_right=100,
            dc_left=80,
            dc_right=80,
        )
        self.assertFalse(same.differs)

        ac_diff = SettingDiff(
            setting_guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Max CPU",
            ac_left=90,
            ac_right=100,
            dc_left=80,
            dc_right=80,
        )
        self.assertTrue(ac_diff.differs)

        dc_diff = SettingDiff(
            setting_guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Max CPU",
            ac_left=100,
            ac_right=100,
            dc_left=70,
            dc_right=80,
        )
        self.assertTrue(dc_diff.differs)


if __name__ == "__main__":
    unittest.main()
