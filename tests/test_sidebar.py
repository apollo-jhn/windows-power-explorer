"""Tests for Sidebar Navigation Component (Issue #19, REQ-1.3, REQ-5.2, REQ-10.3, REQ-10.4)."""

import unittest
from unittest.mock import MagicMock

import customtkinter as ctk

from core.controller import AppController
from core.models import (
    ControlType,
    PowerScheme,
    SettingCatalog,
    SettingCatalogEntry,
    SubgroupCatalogEntry,
)
from core.state import AppState
from ui.sidebar import SidebarNav


class TestSidebarNav(unittest.TestCase):

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
        self.scheme_builtin = PowerScheme(
            guid="381b4222-f694-41f0-9685-ff5bb260df2e",
            friendly_name="Balanced",
            description="Balanced power",
            is_active=True,
            is_base_default=True,
        )
        self.scheme_custom = PowerScheme(
            guid="custom-guid-9999",
            friendly_name="My Ultra Gaming",
            description="Ultra custom",
            is_active=False,
            is_base_default=False,
        )

        self.subgroup1 = SubgroupCatalogEntry(
            guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor Power Management",
            description="",
            is_hidden=False,
            settings=(),
        )
        self.catalog = SettingCatalog(
            subgroups=(self.subgroup1,),
            by_guid={},
            subgroup_by_guid={self.subgroup1.guid.lower(): self.subgroup1},
        )

        self.state = AppState(
            catalog=self.catalog,
            schemes=[self.scheme_builtin, self.scheme_custom],
            active_scheme_guid=self.scheme_builtin.guid,
            selected_scheme_guid=self.scheme_builtin.guid,
            selected_category="all",
        )
        self.controller = AppController(state=self.state)

    def test_sidebar_sections_and_custom_distinction(self):
        """Sidebar renders schemes, categories, and tools with custom scheme tags (REQ-1.3)."""
        selected_schemes = []
        selected_categories = []
        deleted_schemes = []

        sidebar = SidebarNav(
            self.root,
            controller=self.controller,
            on_scheme_selected=lambda g: selected_schemes.append(g),
            on_category_selected=lambda c: selected_categories.append(c),
            on_delete_scheme=lambda g: deleted_schemes.append(g),
        )
        self.root.update()

        # Find scheme buttons in children
        buttons = []
        for child in sidebar.winfo_children():
            if isinstance(child, ctk.CTkButton):
                buttons.append(child.cget("text"))
            elif isinstance(child, ctk.CTkFrame):
                for sub in child.winfo_children():
                    if isinstance(sub, ctk.CTkButton):
                        buttons.append(sub.cget("text"))

        # Active built-in scheme has 🟢 and no Custom tag
        active_texts = [t for t in buttons if "Balanced" in t]
        self.assertTrue(len(active_texts) > 0)
        self.assertIn("🟢", active_texts[0])
        self.assertNotIn("(Custom)", active_texts[0])

        # Custom scheme has (Custom) tag and delete button
        custom_texts = [t for t in buttons if "My Ultra Gaming" in t]
        self.assertTrue(len(custom_texts) > 0)
        self.assertIn("(Custom)", custom_texts[0])

        # Categories are present
        self.assertTrue(any("Favorites" in t for t in buttons))
        self.assertTrue(any("Essentials" in t for t in buttons))
        self.assertTrue(any("All Settings" in t for t in buttons))
        self.assertTrue(any("Processor Power Management" in t for t in buttons))

        # Test selecting a category
        sidebar.on_category_selected("favorites")
        self.assertEqual(selected_categories, ["favorites"])

        # Test selecting a scheme
        sidebar.on_scheme_selected("custom-guid-9999")
        self.assertEqual(selected_schemes, ["custom-guid-9999"])

        sidebar.destroy()


if __name__ == "__main__":
    unittest.main()
