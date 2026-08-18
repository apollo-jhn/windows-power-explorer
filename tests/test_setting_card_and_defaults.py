"""Tests for SettingCardWidget, Inferred Controls & Defaults Reset (Issues #20, #26)."""

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
    SettingValueChoice,
    SubgroupCatalogEntry,
)
from core.power_manager import PowerManager
from core.state import AppState
from ui.components.setting_card import SettingCardWidget


class TestSettingCardAndDefaults(unittest.TestCase):

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

        self.enum_choice = SettingValueChoice(value_index=1, friendly_name="Enabled", description="")
        self.enum_setting = SettingCatalogEntry(
            guid="set-enum-guid",
            subgroup_guid="sub-guid",
            friendly_name="Enum Setting",
            description="Enum description",
            control_type=ControlType.ENUM,
            min_value=None,
            max_value=None,
            value_increment=None,
            value_units="",
            choices=(self.enum_choice,),
            is_hidden=False,
            is_policy_locked=False,
            is_degraded=False,
        )

        self.toggle_setting = SettingCatalogEntry(
            guid="set-toggle-guid",
            subgroup_guid="sub-guid",
            friendly_name="Toggle Setting",
            description="",
            control_type=ControlType.TOGGLE,
            min_value=0,
            max_value=1,
            value_increment=1,
            value_units="",
            choices=(),
            is_hidden=False,
            is_policy_locked=False,
            is_degraded=False,
        )

        self.range_setting = SettingCatalogEntry(
            guid="set-range-guid",
            subgroup_guid="sub-guid",
            friendly_name="Range Setting",
            description="",
            control_type=ControlType.RANGE,
            min_value=5,
            max_value=100,
            value_increment=5,
            value_units="%",
            choices=(),
            is_hidden=False,
            is_policy_locked=False,
            is_degraded=False,
        )

        self.locked_setting = SettingCatalogEntry(
            guid="set-locked-guid",
            subgroup_guid="sub-guid",
            friendly_name="Locked Setting",
            description="",
            control_type=ControlType.RANGE,
            min_value=0,
            max_value=100,
            value_increment=1,
            value_units="%",
            choices=(),
            is_hidden=False,
            is_policy_locked=True,
            is_degraded=False,
        )

        self.catalog = SettingCatalog(
            subgroups=(
                SubgroupCatalogEntry(
                    guid="sub-guid",
                    friendly_name="Subgroup",
                    description="",
                    is_hidden=False,
                    settings=(self.enum_setting, self.toggle_setting, self.range_setting, self.locked_setting),
                ),
            ),
            by_guid={
                self.enum_setting.guid.lower(): self.enum_setting,
                self.toggle_setting.guid.lower(): self.toggle_setting,
                self.range_setting.guid.lower(): self.range_setting,
                self.locked_setting.guid.lower(): self.locked_setting,
            },
            subgroup_by_guid={},
        )

        self.state = AppState(
            catalog=self.catalog,
            schemes=[
                PowerScheme("scheme-guid", "Test Scheme", "", True, True, [])
            ],
            active_scheme_guid="scheme-guid",
            selected_scheme_guid="scheme-guid",
            has_battery=True,
            values=SchemeValues(
                scheme_guid="scheme-guid",
                personality_guid="381b4222-f694-41f0-9685-ff5bb260df2e",
                ac={"set-range-guid": 80, "set-enum-guid": 1, "set-toggle-guid": 1, "set-locked-guid": 50},
                dc={"set-range-guid": 40, "set-enum-guid": 1, "set-toggle-guid": 0, "set-locked-guid": 50},
                ac_default={"set-range-guid": 100, "set-enum-guid": 1, "set-toggle-guid": 1, "set-locked-guid": 50},
                dc_default={"set-range-guid": 50, "set-enum-guid": 1, "set-toggle-guid": 0, "set-locked-guid": 50},
            )
        )
        self.controller = AppController(state=self.state, pm=self.mock_pm)

    def test_control_type_inference_widgets(self):
        """Card constructs appropriate widgets based on ControlType (REQ-2.4)."""
        # Enum -> CTkOptionMenu
        card_enum = SettingCardWidget(self.root, self.enum_setting, self.controller)
        self.assertIsInstance(card_enum.ac_widget, ctk.CTkOptionMenu)
        card_enum.destroy()

        # Toggle -> CTkSwitch
        card_toggle = SettingCardWidget(self.root, self.toggle_setting, self.controller)
        self.assertIsInstance(card_toggle.ac_widget, ctk.CTkSwitch)
        card_toggle.destroy()

        # Range -> CTkSlider
        card_range = SettingCardWidget(self.root, self.range_setting, self.controller)
        self.assertIsInstance(card_range.ac_widget, ctk.CTkSlider)
        card_range.destroy()

    def test_modified_badge_and_reset(self):
        """Setting deviating from default shows Modified badge and allows reset (REQ-9.2, REQ-9.3)."""
        # set-range-guid: AC=80 (default=100) -> Modified
        self.assertTrue(self.state.is_setting_modified("set-range-guid"))

        card = SettingCardWidget(self.root, self.range_setting, self.controller)
        self.assertEqual(card.reset_btn.cget("state"), "normal")

        # Perform Reset
        self.mock_pm.read_ac_value.return_value = 100
        self.mock_pm.read_dc_value.return_value = 50
        card._on_reset()

        self.mock_pm.write_ac_value.assert_called_with("scheme-guid", "sub-guid", "set-range-guid", 100, (5, 100))
        self.mock_pm.write_dc_value.assert_called_with("scheme-guid", "sub-guid", "set-range-guid", 50, (5, 100))
        card.destroy()

    def test_battery_less_omits_dc_row(self):
        """On battery-less machines, the DC row is omitted entirely (REQ-2.6)."""
        self.state.has_battery = False
        card = SettingCardWidget(self.root, self.range_setting, self.controller)
        self.assertIsNone(card.dc_widget)
        card.destroy()

    def test_policy_locked_disables_controls(self):
        """Group Policy locked settings disable all controls and Reset (REQ-2.5)."""
        card = SettingCardWidget(self.root, self.locked_setting, self.controller)
        self.assertEqual(card.ac_widget.cget("state"), "disabled")
        self.assertEqual(card.reset_btn.cget("state"), "disabled")
        card.destroy()


if __name__ == "__main__":
    unittest.main()
