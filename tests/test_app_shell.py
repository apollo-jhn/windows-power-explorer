"""Tests for Main Window Shell and Startup Sequence (Issue #18, REQ-1, TDD §9)."""

import unittest
from unittest.mock import MagicMock, patch

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
from core.state import AppState
from ui.app import PowerExplorerApp


class TestAppShell(unittest.TestCase):

    def setUp(self):
        self.scheme1 = PowerScheme(
            guid="381b4222-f694-41f0-9685-ff5bb260df2e",
            friendly_name="Balanced",
            description="",
            is_active=True,
            is_base_default=True,
        )
        self.setting1 = SettingCatalogEntry(
            guid="be337238-0d82-4146-a960-4f3749d470c7",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor Performance Boost",
            description="Boost mode",
            control_type=ControlType.ENUM,
            min_value=None,
            max_value=None,
            value_increment=None,
            value_units="",
            choices=(),
            is_hidden=False,
            is_policy_locked=False,
            is_degraded=False,
        )
        self.subgroup1 = SubgroupCatalogEntry(
            guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor",
            description="",
            is_hidden=False,
            settings=(self.setting1,),
        )
        self.catalog = SettingCatalog(
            subgroups=(self.subgroup1,),
            by_guid={self.setting1.guid.lower(): self.setting1},
            subgroup_by_guid={self.subgroup1.guid.lower(): self.subgroup1},
        )
        self.values = SchemeValues(
            scheme_guid=self.scheme1.guid,
            personality_guid="pers-1",
            ac={self.setting1.guid.lower(): 3},
            dc={self.setting1.guid.lower(): 0},
            ac_default={self.setting1.guid.lower(): 3},
            dc_default={self.setting1.guid.lower(): 0},
        )
        self.state = AppState(
            catalog=self.catalog,
            schemes=[self.scheme1],
            active_scheme_guid=self.scheme1.guid,
            selected_scheme_guid=self.scheme1.guid,
            values=self.values,
        )
        self.mock_pm = MagicMock()
        self.mock_pm.get_active_scheme_guid.return_value = self.scheme1.guid
        self.mock_pm.get_overlay.return_value = None
        self.mock_pm.has_battery.return_value = True

        self.controller = AppController(state=self.state, pm=self.mock_pm)

    def test_app_shell_construction_and_components(self):
        """PowerExplorerApp constructs 2-column layout, header, footer, and bindings."""
        with patch("ui.app.verify_bindings", return_value=True):
            app = PowerExplorerApp(controller=self.controller)
            app.withdraw()  # keep off screen during test

            # Check components existence
            self.assertIsNotNone(app.search_bar)
            self.assertIsNotNone(app.sidebar)
            self.assertIsNotNone(app.content_frame)
            self.assertIsNotNone(app.status_bar)

            # Check minsize
            self.assertEqual(app._min_width, 920)
            self.assertEqual(app._min_height, 600)

            # Check progressive rendering
            app._render_setting_cards()
            app.update()

            # Trigger undo and refresh shortcuts
            app._undo()
            app._toggle_modified()
            self.assertTrue(app.controller.state.show_modified_only)

            # Trigger close and verify ui-state saved
            with patch("ui.app.save_ui_state") as mock_save:
                app._on_close()
                mock_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
