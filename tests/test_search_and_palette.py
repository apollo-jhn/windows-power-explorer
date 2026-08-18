"""Tests for Search Filtering & Command Palette (Issue #21, REQ-5.1, REQ-10.1, REQ-10.2)."""

import time
import unittest
from unittest.mock import MagicMock

import customtkinter as ctk

from core.controller import AppController
from core.models import (
    ControlType,
    PowerScheme,
    SettingCatalog,
    SettingCatalogEntry,
    SettingValueChoice,
    SubgroupCatalogEntry,
)
from core.state import AppState
from ui.dialogs.command_palette import CommandPalette
from ui.search_bar import SearchBar


class TestSearchAndPalette(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create a hidden CTk root for widget tests
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        # Build dummy catalog with choice options
        self.choice1 = SettingValueChoice(value_index=0, friendly_name="Disabled", description="")
        self.choice2 = SettingValueChoice(value_index=3, friendly_name="Aggressive Boost", description="")

        self.setting1 = SettingCatalogEntry(
            guid="be337238-0d82-4146-a960-4f3749d470c7",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor Performance Boost",
            description="Controls boost policy",
            control_type=ControlType.ENUM,
            min_value=0,
            max_value=3,
            value_increment=1,
            value_units="",
            choices=(self.choice1, self.choice2),
            is_hidden=False,
            is_policy_locked=False,
            is_degraded=False,
        )
        self.subgroup1 = SubgroupCatalogEntry(
            guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor Power Management",
            description="",
            is_hidden=False,
            settings=(self.setting1,),
        )
        self.catalog = SettingCatalog(
            subgroups=(self.subgroup1,),
            by_guid={self.setting1.guid.lower(): self.setting1},
            subgroup_by_guid={self.subgroup1.guid.lower(): self.subgroup1},
        )

        self.state = AppState(catalog=self.catalog)
        self.controller = AppController(state=self.state)

    def test_search_matches_choice_names(self):
        """Search query matches choice option friendly names (REQ-10.2)."""
        # 1. Matches setting friendly name
        self.state.search_query = "Processor"
        self.assertTrue(self.state.matches_search(self.setting1))

        # 2. Matches choice name 'Aggressive'
        self.state.search_query = "Aggressive"
        self.assertTrue(self.state.matches_search(self.setting1))

        # 3. Matches GUID
        self.state.search_query = "be337238"
        self.assertTrue(self.state.matches_search(self.setting1))

        # 4. Non-matching query
        self.state.search_query = "NonExistentValue"
        self.assertFalse(self.state.matches_search(self.setting1))

    def test_search_debounce(self):
        """SearchBar debounces fast keystrokes to a single dispatched callback (TDD §7)."""
        dispatched_queries = []
        search_bar = SearchBar(
            self.root,
            on_query_changed=lambda q: dispatched_queries.append(q),
            on_modified_toggle=lambda _: None,
            debounce_ms=50,
        )

        # Simulate typing 'B', 'o', 'o', 's', 't' rapidly
        search_bar.entry.insert(0, "Boost")
        mock_event = MagicMock()
        mock_event.keysym = "t"

        for _ in range(5):
            search_bar._on_key_release(mock_event)

        # Immediately before debounce delay, callback must not have fired
        self.assertEqual(len(dispatched_queries), 0)

        # Run main loop briefly to allow after callback to fire
        self.root.update()
        time.sleep(0.08)
        self.root.update()

        # Should fire once with the complete query
        self.assertEqual(len(dispatched_queries), 1)
        self.assertEqual(dispatched_queries[0], "Boost")
        search_bar.destroy()

    def test_command_palette_keyboard_only(self):
        """Command palette supports 100% keyboard-only navigation: Up, Down, Enter (REQ-10.1)."""
        executed_actions = []

        palette = CommandPalette(
            self.root,
            controller=self.controller,
            on_select_category=lambda cat: executed_actions.append(f"cat:{cat}"),
            on_select_setting=lambda sg, st: executed_actions.append(f"set:{st}"),
        )
        self.root.update()

        # Check items were generated
        self.assertGreater(len(palette.filtered_items), 0)
        initial_index = palette.selected_index
        self.assertEqual(initial_index, 0)

        # 1. Down arrow moves index down
        palette._on_arrow_down(MagicMock())
        self.assertEqual(palette.selected_index, 1)

        # 2. Up arrow moves index back up
        palette._on_arrow_up(MagicMock())
        self.assertEqual(palette.selected_index, 0)

        # 3. Enter executes currently selected item
        selected_item = palette.filtered_items[0]
        palette._on_enter(MagicMock())

        palette.destroy()


if __name__ == "__main__":
    unittest.main()
