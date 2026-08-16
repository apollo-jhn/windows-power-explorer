"""Tests for Two-Phase Load Architecture: core/catalog.py and core/values.py (ADR-012)."""

import unittest
from unittest.mock import MagicMock

from core.catalog import build_catalog
from core.models import (
    ControlType,
    PowerScheme,
    PowerSetting,
    SchemeValues,
    SettingCatalog,
    SettingCatalogEntry,
    SubgroupCatalogEntry,
)
from core.power_manager import PowerManager
from core.values import (
    assemble_power_scheme,
    assemble_power_setting,
    load_scheme_values,
)


class TestCatalogAndValues(unittest.TestCase):

    def test_catalog_has_no_scheme_values(self):
        """SettingCatalogEntry must NOT have ac_value or dc_value fields (ADR-012 guard)."""
        self.assertFalse(hasattr(SettingCatalogEntry, "ac_value"))
        self.assertFalse(hasattr(SettingCatalogEntry, "dc_value"))

    def test_catalog_is_frozen(self):
        """Catalog entries and SettingCatalog must be frozen (immutable) for thread safety."""
        entry = SettingCatalogEntry(
            guid="be337238-0d82-4146-a960-4f3749d470c7",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor performance boost mode",
            description="Configure processor performance boost mode",
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

        with self.assertRaises(Exception):
            entry.friendly_name = "Modified"  # type: ignore

    def test_defaults_use_personality_not_scheme(self):
        """PowerReadACDefaultIndex must receive personality GUID, not scheme GUID."""
        mock_pm = MagicMock(spec=PowerManager)
        mock_pm.personality_of.return_value = "381b4222-f694-41f0-9685-ff5bb260df2e"  # Balanced personality
        mock_pm.read_ac_value.return_value = 80
        mock_pm.read_dc_value.return_value = 50
        mock_pm.read_ac_default.return_value = 100
        mock_pm.read_dc_default.return_value = 80

        sub_entry = SubgroupCatalogEntry(
            guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor",
            description="",
            is_hidden=False,
            settings=(
                SettingCatalogEntry(
                    guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
                    subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
                    friendly_name="Max CPU",
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
                ),
            ),
        )

        catalog = SettingCatalog(
            subgroups=(sub_entry,),
            by_guid={"bc502fe6-701e-46c4-9826-5d42490a1e9c": sub_entry.settings[0]},
            subgroup_by_guid={"54533251-82be-4824-96c1-47b60b740d00": sub_entry},
        )

        custom_scheme = "12345678-1234-1234-1234-1234567890ab"
        values = load_scheme_values(custom_scheme, catalog, pm=mock_pm)

        # Assert read_ac_default was called with personality GUID, not custom_scheme
        mock_pm.read_ac_default.assert_called_with(
            "381b4222-f694-41f0-9685-ff5bb260df2e",
            "54533251-82be-4824-96c1-47b60b740d00",
            "bc502fe6-701e-46c4-9826-5d42490a1e9c",
        )
        self.assertEqual(values.personality_guid, "381b4222-f694-41f0-9685-ff5bb260df2e")
        self.assertEqual(values.ac["bc502fe6-701e-46c4-9826-5d42490a1e9c"], 80)
        self.assertEqual(values.ac_default["bc502fe6-701e-46c4-9826-5d42490a1e9c"], 100)

    def test_default_cache_shared_across_personality(self):
        """Two schemes with same personality share default reads without extra FFI calls."""
        mock_pm = MagicMock(spec=PowerManager)
        mock_pm.personality_of.return_value = "381b4222-f694-41f0-9685-ff5bb260df2e"
        mock_pm.read_ac_default.return_value = 100
        mock_pm.read_dc_default.return_value = 80

        sub_entry = SubgroupCatalogEntry(
            guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor",
            description="",
            is_hidden=False,
            settings=(
                SettingCatalogEntry(
                    guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
                    subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
                    friendly_name="Max CPU",
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
                ),
            ),
        )

        catalog = SettingCatalog(
            subgroups=(sub_entry,),
            by_guid={"bc502fe6-701e-46c4-9826-5d42490a1e9c": sub_entry.settings[0]},
            subgroup_by_guid={"54533251-82be-4824-96c1-47b60b740d00": sub_entry},
        )

        shared_cache: dict = {}
        load_scheme_values("scheme-1", catalog, pm=mock_pm, default_cache=shared_cache)
        self.assertEqual(mock_pm.read_ac_default.call_count, 1)

        # Second load with same cache
        load_scheme_values("scheme-2", catalog, pm=mock_pm, default_cache=shared_cache)
        # Call count should not have increased
        self.assertEqual(mock_pm.read_ac_default.call_count, 1)

    def test_assemble_power_scheme(self):
        """assemble_power_scheme joins catalog entries and values into UI tree."""
        set_entry = SettingCatalogEntry(
            guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Max CPU",
            description="Maximum processor state",
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
        sub_entry = SubgroupCatalogEntry(
            guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor",
            description="",
            is_hidden=False,
            settings=(set_entry,),
        )
        catalog = SettingCatalog(
            subgroups=(sub_entry,),
            by_guid={set_entry.guid.lower(): set_entry},
            subgroup_by_guid={sub_entry.guid.lower(): sub_entry},
        )

        values = SchemeValues(
            scheme_guid="381b4222-f694-41f0-9685-ff5bb260df2e",
            personality_guid="381b4222-f694-41f0-9685-ff5bb260df2e",
            ac={set_entry.guid.lower(): 95},
            dc={set_entry.guid.lower(): 75},
            ac_default={set_entry.guid.lower(): 100},
            dc_default={set_entry.guid.lower(): 80},
        )

        scheme = assemble_power_scheme(
            scheme_guid="381b4222-f694-41f0-9685-ff5bb260df2e",
            friendly_name="Balanced",
            description="Standard balanced power scheme",
            is_active=True,
            is_base_default=True,
            catalog=catalog,
            values=values,
        )

        self.assertIsInstance(scheme, PowerScheme)
        self.assertTrue(scheme.is_active)
        self.assertEqual(len(scheme.subgroups), 1)
        self.assertEqual(len(scheme.subgroups[0].settings), 1)
        setting = scheme.subgroups[0].settings[0]
        self.assertEqual(setting.ac_value, 95)
        self.assertEqual(setting.dc_value, 75)


if __name__ == "__main__":
    unittest.main()
