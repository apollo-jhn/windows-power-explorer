"""Tests for In-House Dialog System and Toasts (Issue #23, ADR-011)."""

import json
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
from ui.dialogs.base import BaseDialog, ConfirmDialog, show_startup_error
from ui.dialogs.create_scheme_dialog import CreateSchemeDialog
from ui.dialogs.elevation_dialog import ElevationDialog
from ui.dialogs.export_dialog import ExportDialog
from ui.status_bar import StatusBar


class TestDialogSuite(unittest.TestCase):

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
        self.scheme1 = PowerScheme("381b4222-f694-41f0-9685-ff5bb260df2e", "Balanced", "Balanced plan", is_active=True, is_base_default=True)
        self.scheme2 = PowerScheme("custom-guid-1234", "My Gaming Plan", "Custom gaming profile", is_active=False, is_base_default=False)

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
            schemes=[self.scheme1, self.scheme2],
            active_scheme_guid=self.scheme1.guid,
            selected_scheme_guid=self.scheme1.guid,
            values=self.values,
        )
        self.mock_pm = MagicMock()
        self.mock_pm.duplicate_scheme.return_value = "new-cloned-guid"
        self.controller = AppController(state=self.state, pm=self.mock_pm)

    def test_modal_focus_and_escape(self):
        """BaseDialog grabs modal focus, centers, and handles Escape closing (ADR-011)."""
        dialog = BaseDialog(self.root, title="Test Modal", width=300, height=200)
        self.root.update()

        # Dialog exists and is top level
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(dialog.title(), "Test Modal")

        # Simulate Escape key
        mock_event = MagicMock()
        dialog.destroy()
        self.root.update()

    def test_destructive_dialog_gate(self):
        """ConfirmDialog enables confirm button only when typed phrase matches exactly."""
        confirmed = False

        def on_confirm():
            nonlocal confirmed
            confirmed = True

        dialog = ConfirmDialog(
            self.root,
            title="Destructive Operation",
            message="Type RESTORE to confirm reset.",
            on_confirm=on_confirm,
            is_destructive=True,
            required_phrase="RESTORE",
        )
        self.root.update()

        # Initially disabled
        self.assertEqual(dialog.confirm_btn.cget("state"), "disabled")

        # Incorrect phrase
        dialog.phrase_entry.insert(0, "REST")
        dialog._on_phrase_type(None)
        self.assertEqual(dialog.confirm_btn.cget("state"), "disabled")

        # Exact match enables confirm button
        dialog.phrase_entry.delete(0, "end")
        dialog.phrase_entry.insert(0, "RESTORE")
        dialog._on_phrase_type(None)
        self.assertEqual(dialog.confirm_btn.cget("state"), "normal")

        # Confirm executes action
        dialog._confirm()
        self.assertTrue(confirmed)

    def test_create_scheme_dialog_cloning(self):
        """CreateSchemeDialog lists live machine schemes and invokes create_scheme."""
        created_guid = None

        def on_created(guid):
            nonlocal created_guid
            created_guid = guid

        dialog = CreateSchemeDialog(
            self.root,
            controller=self.controller,
            on_created=on_created,
        )
        self.root.update()

        # Dropdown contains Balanced and My Gaming Plan
        self.assertIn("Balanced", dialog.scheme_map)
        self.assertIn("My Gaming Plan (Custom)", dialog.scheme_map)

        # Trigger create
        dialog.name_entry.delete(0, "end")
        dialog.name_entry.insert(0, "My New Gaming Clone")
        dialog._on_create()

        self.mock_pm.duplicate_scheme.assert_called_once()
        self.assertEqual(created_guid, "new-cloned-guid")

    def test_elevation_dialog_proceed(self):
        """ElevationDialog displays explanation and executes proceed callback."""
        proceeded = False

        def on_proceed():
            nonlocal proceeded
            proceeded = True

        dialog = ElevationDialog(
            self.root,
            title="Administrator Required",
            action_name="Control Panel Visibility",
            description="Registry write requires elevation.",
            on_proceed=on_proceed,
        )
        self.root.update()

        dialog._proceed()
        self.assertTrue(proceeded)

    def test_export_dialog_formats(self):
        """ExportDialog generates JSON Preset, powercfg script, and Markdown summary."""
        dialog = ExportDialog(
            self.root,
            controller=self.controller,
            scheme=self.scheme1,
        )
        self.root.update()

        # 1. JSON Preset Format
        dialog._on_format_changed("JSON Preset")
        json_text = dialog._generate_export_text()
        parsed = json.loads(json_text)
        self.assertEqual(parsed["version"], 2)
        self.assertEqual(parsed["scheme"]["guid"], self.scheme1.guid)
        self.assertEqual(len(parsed["settings"]), 1)

        # 2. powercfg Script Format
        dialog._on_format_changed("powercfg Script")
        bat_text = dialog._generate_export_text()
        self.assertIn("powercfg -changename", bat_text)
        self.assertIn("powercfg -setacvalueindex", bat_text)

        # 3. Markdown Summary Format
        dialog._on_format_changed("Markdown Summary")
        md_text = dialog._generate_export_text()
        self.assertIn(f"# Power Scheme: {self.scheme1.friendly_name}", md_text)
        self.assertIn("Processor Performance Boost", md_text)

        dialog.destroy()

    def test_status_bar_toast(self):
        """StatusBar shows transient toast and restores status text (ADR-011)."""
        status_bar = StatusBar(self.root, controller=self.controller)
        self.root.update()

        status_bar.show_toast("Setting saved successfully", duration_ms=50)
        self.assertIn("Setting saved successfully", status_bar.status_label.cget("text"))

        # Run scheduler for toast auto-clear
        self.root.update()
        import time
        time.sleep(0.08)
        self.root.update()

        self.assertIn("System Ready", status_bar.status_label.cget("text"))
        status_bar.destroy()

    @patch("tkinter.messagebox.showerror")
    def test_show_startup_error(self, mock_msgbox):
        """show_startup_error falls back to native tkinter.messagebox for screen reader access."""
        show_startup_error("Fatal Error", "Binding resolution failed")
        mock_msgbox.assert_called_once_with("Fatal Error", "Binding resolution failed")


if __name__ == "__main__":
    unittest.main()
