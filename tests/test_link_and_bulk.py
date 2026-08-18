"""Tests for Link AC/DC Toggle and Bulk Custom Scheme Editing (Issue #28, REQ-11.3, REQ-11.4)."""

import unittest
from unittest.mock import MagicMock

import customtkinter as ctk

from core.controller import AppController
from core.models import (
    ControlType,
    PowerScheme,
    SchemeValues,
    SettingCatalog,
    SettingCatalogEntry,
    SubgroupCatalogEntry,
)
from core.power_manager import PowerManager
from core.state import AppState
from ui.components.setting_card import SettingCardWidget


class TestLinkAndBulk(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.mock_pm = MagicMock(spec=PowerManager)
        self.mock_pm.personality_of.return_value = "381b4222-f694-41f0-9685-ff5bb260df2e"

        self.setting = SettingCatalogEntry(
            guid="set-link-guid",
            subgroup_guid="sub-guid",
            friendly_name="Linkable Setting",
            description="",
            control_type=ControlType.RANGE,
            min_value=0,
            max_value=100,
            value_increment=5,
            value_units="%",
            choices=(),
            is_hidden=False,
            is_policy_locked=False,
            is_degraded=False,
        )

        self.catalog = SettingCatalog(
            subgroups=(
                SubgroupCatalogEntry(
                    guid="sub-guid",
                    friendly_name="Subgroup",
                    description="",
                    is_hidden=False,
                    settings=(self.setting,),
                ),
            ),
            by_guid={self.setting.guid.lower(): self.setting},
            subgroup_by_guid={},
        )

        self.state = AppState(
            catalog=self.catalog,
            schemes=[
                PowerScheme("base-scheme", "Balanced", "", True, True, []),
                PowerScheme("custom-1", "Custom Gaming", "", False, False, []),
                PowerScheme("custom-2", "Custom Quiet", "", False, False, []),
            ],
            active_scheme_guid="base-scheme",
            selected_scheme_guid="base-scheme",
            has_battery=True,
            values=SchemeValues(
                scheme_guid="base-scheme",
                personality_guid="381b4222-f694-41f0-9685-ff5bb260df2e",
                ac={"set-link-guid": 50},
                dc={"set-link-guid": 30},
                ac_default={},
                dc_default={},
            ),
        )
        self.controller = AppController(state=self.state, pm=self.mock_pm)

    def test_link_ac_dc_mirrors_values(self):
        """When Link AC/DC toggle is active, changing AC writes to DC and vice versa (REQ-11.3)."""
        card = SettingCardWidget(self.root, self.setting, self.controller)

        # Toggle Link Mode on
        card._toggle_link()
        self.assertTrue(card.is_linked)

        # Modify AC value to 75
        self.mock_pm.read_ac_value.return_value = 75
        self.mock_pm.read_dc_value.return_value = 75
        card._on_user_value_change(75, "ac")

        # Both AC and DC must have been written with value 75
        self.mock_pm.write_ac_value.assert_called_with("base-scheme", "sub-guid", "set-link-guid", 75, (0, 100))
        self.mock_pm.write_dc_value.assert_called_with("base-scheme", "sub-guid", "set-link-guid", 75, (0, 100))
        card.destroy()

    def test_apply_to_all_custom_schemes(self):
        """Bulk applying a setting writes to all custom schemes but skips built-in schemes (REQ-11.4)."""
        updated = self.controller.apply_setting_to_custom_schemes(
            subgroup_guid="sub-guid",
            setting_guid="set-link-guid",
            ac_val=90,
            dc_val=60,
        )

        # Should update custom-1 and custom-2, not base-scheme
        self.assertEqual(set(updated), {"custom-1", "custom-2"})
        self.mock_pm.write_ac_value.assert_any_call("custom-1", "sub-guid", "set-link-guid", 90, (0, 100))
        self.mock_pm.write_dc_value.assert_any_call("custom-1", "sub-guid", "set-link-guid", 60, (0, 100))
        self.mock_pm.write_ac_value.assert_any_call("custom-2", "sub-guid", "set-link-guid", 90, (0, 100))
        self.mock_pm.write_dc_value.assert_any_call("custom-2", "sub-guid", "set-link-guid", 60, (0, 100))


if __name__ == "__main__":
    unittest.main()
