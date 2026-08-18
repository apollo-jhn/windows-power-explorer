"""Tests for core/state.py (Centralized AppState - Issue #17)."""

import unittest

from core.models import (
    ControlType,
    OverlayInfo,
    PowerScheme,
    SchemeValues,
    SettingCatalog,
    SettingCatalogEntry,
    SettingValueChoice,
    SubgroupCatalogEntry,
    ValueChange,
)
from core.state import AppState


class TestAppState(unittest.TestCase):

    def _sample_catalog(self) -> SettingCatalog:
        choice1 = SettingValueChoice(0, "Disabled", "Disable feature")
        choice2 = SettingValueChoice(1, "Aggressive", "Aggressive boost")
        set1 = SettingCatalogEntry(
            guid="be337238-0d82-4146-a960-4f3749d470c7",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor Boost Mode",
            description="Boost processor frequencies",
            control_type=ControlType.ENUM,
            min_value=None,
            max_value=None,
            value_increment=None,
            value_units="",
            choices=(choice1, choice2),
            is_hidden=False,
            is_policy_locked=False,
            is_degraded=False,
        )
        set2 = SettingCatalogEntry(
            guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Maximum Processor State",
            description="Maximum CPU state percentage",
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
        set3 = SettingCatalogEntry(
            guid="29f6c1db-86da-48c5-9fdb-f2b67b1f44da",
            subgroup_guid="238c9fa8-0aad-41ed-83f4-97be242c8f20",
            friendly_name="Standby Timeout",
            description="Time before sleeping",
            control_type=ControlType.RANGE,
            min_value=0,
            max_value=3600,
            value_increment=60,
            value_units="Seconds",
            choices=(),
            is_hidden=False,
            is_policy_locked=False,
            is_degraded=False,
        )

        sub1 = SubgroupCatalogEntry(
            guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor",
            description="",
            is_hidden=False,
            settings=(set1, set2),
        )
        sub2 = SubgroupCatalogEntry(
            guid="238c9fa8-0aad-41ed-83f4-97be242c8f20",
            friendly_name="Sleep",
            description="",
            is_hidden=False,
            settings=(set3,),
        )

        return SettingCatalog(
            subgroups=(sub1, sub2),
            by_guid={
                set1.guid.lower(): set1,
                set2.guid.lower(): set2,
                set3.guid.lower(): set3,
            },
            subgroup_by_guid={
                sub1.guid.lower(): sub1,
                sub2.guid.lower(): sub2,
            },
        )

    def test_app_state_defaults(self):
        """AppState initializes with correct default fields."""
        state = AppState()
        self.assertIsNone(state.catalog)
        self.assertEqual(state.schemes, [])
        self.assertIsNone(state.active_scheme_guid)
        self.assertIsNone(state.selected_scheme_guid)
        self.assertIsNone(state.values)
        self.assertIsNone(state.compare_scheme_guid)

        self.assertEqual(state.selected_category, "all")
        self.assertEqual(state.search_query, "")
        self.assertFalse(state.show_modified_only)

        self.assertIsNone(state.overlay)
        self.assertTrue(state.has_battery)
        self.assertFalse(state.is_elevated)

        self.assertEqual(state.pending_visibility, {})
        self.assertIsNone(state.last_change)

        self.assertEqual(state.appearance_mode, "System")
        self.assertEqual(state.favorites, set())

        self.assertEqual(state.enumeration_generation, 0)
        self.assertEqual(state.active_worker_count, 0)
        self.assertFalse(state.is_apply_enabled)

    def test_apply_enabled_derived(self):
        """is_apply_enabled reflects whether pending_visibility has items."""
        state = AppState()
        self.assertFalse(state.is_apply_enabled)

        state.pending_visibility[("sub1", "set1")] = True
        self.assertTrue(state.is_apply_enabled)

        state.pending_visibility.clear()
        self.assertFalse(state.is_apply_enabled)

    def test_scheme_helpers(self):
        """active_scheme, selected_scheme, and compare_scheme find matching schemes."""
        scheme1 = PowerScheme(
            guid="381b4222-f694-41f0-9685-ff5bb260df2e",
            friendly_name="Balanced",
            description="",
            is_active=True,
            is_base_default=True,
        )
        scheme2 = PowerScheme(
            guid="8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
            friendly_name="High Performance",
            description="",
            is_active=False,
            is_base_default=True,
        )

        state = AppState(
            schemes=[scheme1, scheme2],
            active_scheme_guid=scheme1.guid,
            selected_scheme_guid=scheme2.guid,
            compare_scheme_guid=scheme1.guid,
        )

        self.assertEqual(state.active_scheme, scheme1)
        self.assertEqual(state.selected_scheme, scheme2)
        self.assertEqual(state.compare_scheme, scheme1)

    def test_is_setting_modified(self):
        """is_setting_modified correctly checks AC and DC values against defaults."""
        values = SchemeValues(
            scheme_guid="guid-1",
            personality_guid="pers-1",
            ac={"set1": 80, "set2": 100, "set3": 50},
            dc={"set1": 80, "set2": 100, "set3": 30},
            ac_default={"set1": 100, "set2": 100, "set3": None},
            dc_default={"set1": 80, "set2": 100, "set3": None},
        )
        state = AppState(values=values)

        # set1 AC differs (80 vs 100) -> Modified
        self.assertTrue(state.is_setting_modified("set1"))
        # set2 AC and DC match defaults (100 vs 100) -> Not modified
        self.assertFalse(state.is_setting_modified("set2"))
        # set3 has no known default (None) -> Not modified
        self.assertFalse(state.is_setting_modified("set3"))
        # unknown setting -> Not modified
        self.assertFalse(state.is_setting_modified("unknown"))

    def test_favorites_management(self):
        """is_favorite and toggle_favorite correctly manipulate favorites set."""
        state = AppState()
        sub = "54533251-82be-4824-96c1-47b60b740d00"
        setting = "be337238-0d82-4146-a960-4f3749d470c7"

        self.assertFalse(state.is_favorite(sub, setting))
        # Add to favorites
        is_fav = state.toggle_favorite(sub, setting)
        self.assertTrue(is_fav)
        self.assertTrue(state.is_favorite(sub, setting))

        # Remove from favorites
        is_fav = state.toggle_favorite(sub, setting)
        self.assertFalse(is_fav)
        self.assertFalse(state.is_favorite(sub, setting))

    def test_clear_undo(self):
        """clear_undo resets last_change (REQ-11.2)."""
        state = AppState(
            last_change=ValueChange("scheme", "sub", "set", "ac", 100, 80)
        )
        self.assertIsNotNone(state.last_change)
        state.clear_undo()
        self.assertIsNone(state.last_change)

    def test_reset_transient_filters(self):
        """reset_transient_filters resets category, search query, and modified filter."""
        state = AppState(
            selected_category="favorites",
            search_query="boost",
            show_modified_only=True,
        )
        state.reset_transient_filters()
        self.assertEqual(state.selected_category, "all")
        self.assertEqual(state.search_query, "")
        self.assertFalse(state.show_modified_only)

    def test_matches_search(self):
        """Search matches on friendly name, description, GUID, and choice text."""
        catalog = self._sample_catalog()
        boost_setting = catalog.by_guid["be337238-0d82-4146-a960-4f3749d470c7"]

        state = AppState()
        state.search_query = "boost"
        self.assertTrue(state.matches_search(boost_setting))

        state.search_query = "aggressive"  # In choice friendly_name
        self.assertTrue(state.matches_search(boost_setting))

        state.search_query = "be337238"  # In GUID
        self.assertTrue(state.matches_search(boost_setting))

        state.search_query = "nonexistent"
        self.assertFalse(state.matches_search(boost_setting))

    def test_get_filtered_settings(self):
        """get_filtered_settings returns settings matching category, search, and modified."""
        catalog = self._sample_catalog()
        values = SchemeValues(
            scheme_guid="guid-1",
            personality_guid="pers-1",
            ac={
                "be337238-0d82-4146-a960-4f3749d470c7": 0,
                "bc502fe6-701e-46c4-9826-5d42490a1e9c": 100,
                "29f6c1db-86da-48c5-9fdb-f2b67b1f44da": 1800,
            },
            dc={
                "be337238-0d82-4146-a960-4f3749d470c7": 0,
                "bc502fe6-701e-46c4-9826-5d42490a1e9c": 80,
                "29f6c1db-86da-48c5-9fdb-f2b67b1f44da": 900,
            },
            ac_default={
                "be337238-0d82-4146-a960-4f3749d470c7": 1,  # Modified! (0 != 1)
                "bc502fe6-701e-46c4-9826-5d42490a1e9c": 100,
                "29f6c1db-86da-48c5-9fdb-f2b67b1f44da": 1800,
            },
            dc_default={
                "be337238-0d82-4146-a960-4f3749d470c7": 1,
                "bc502fe6-701e-46c4-9826-5d42490a1e9c": 80,
                "29f6c1db-86da-48c5-9fdb-f2b67b1f44da": 900,
            },
        )

        state = AppState(catalog=catalog, values=values)

        # 1. "all" category -> all 3 settings
        filtered = state.get_filtered_settings()
        self.assertEqual(len(filtered), 3)

        # 2. Specific subgroup -> 2 settings in Processor
        state.selected_category = "54533251-82be-4824-96c1-47b60b740d00"
        filtered = state.get_filtered_settings()
        self.assertEqual(len(filtered), 2)

        # 3. Favorites category
        state.selected_category = "favorites"
        state.favorites.add((
            "54533251-82be-4824-96c1-47b60b740d00",
            "be337238-0d82-4146-a960-4f3749d470c7",
        ))
        filtered = state.get_filtered_settings()
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].guid, "be337238-0d82-4146-a960-4f3749d470c7")

        # 4. Modified only filter
        state.selected_category = "all"
        state.show_modified_only = True
        filtered = state.get_filtered_settings()
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].guid, "be337238-0d82-4146-a960-4f3749d470c7")

        # 5. Essentials filter
        state.show_modified_only = False
        state.selected_category = "essentials"
        essentials = {"bc502fe6-701e-46c4-9826-5d42490a1e9c"}
        filtered = state.get_filtered_settings(essentials_guids=essentials)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].guid, "bc502fe6-701e-46c4-9826-5d42490a1e9c")


if __name__ == "__main__":
    unittest.main()
