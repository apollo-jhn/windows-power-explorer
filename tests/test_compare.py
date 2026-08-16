"""Tests for core/compare.py."""

import unittest

from core.compare import compare_schemes, get_modified_settings
from core.models import (
    ControlType,
    SchemeValues,
    SettingCatalog,
    SettingCatalogEntry,
    SubgroupCatalogEntry,
)


class TestCompare(unittest.TestCase):

    def _sample_catalog(self) -> SettingCatalog:
        set1 = SettingCatalogEntry(
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
        )
        set2 = SettingCatalogEntry(
            guid="893dee8e-2bef-41e0-89c6-b55d0929964c",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Min CPU",
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
        )
        sub = SubgroupCatalogEntry(
            guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor",
            description="",
            is_hidden=False,
            settings=(set1, set2),
        )
        return SettingCatalog(
            subgroups=(sub,),
            by_guid={set1.guid.lower(): set1, set2.guid.lower(): set2},
            subgroup_by_guid={sub.guid.lower(): sub},
        )

    def test_compare_schemes_identical(self):
        """Comparing identical schemes with only_differences=True produces empty list."""
        catalog = self._sample_catalog()
        v1 = SchemeValues(
            scheme_guid="guid-1",
            personality_guid="pers-1",
            ac={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 100, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            dc={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 80, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            ac_default={},
            dc_default={},
        )
        v2 = SchemeValues(
            scheme_guid="guid-2",
            personality_guid="pers-1",
            ac={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 100, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            dc={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 80, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            ac_default={},
            dc_default={},
        )

        diffs = compare_schemes(v1, v2, catalog, only_differences=True)
        self.assertEqual(len(diffs), 0)

        all_rows = compare_schemes(v1, v2, catalog, only_differences=False)
        self.assertEqual(len(all_rows), 2)

    def test_compare_schemes_with_differences(self):
        """Comparing schemes with differing values returns diff records."""
        catalog = self._sample_catalog()
        v1 = SchemeValues(
            scheme_guid="guid-1",
            personality_guid="pers-1",
            ac={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 100, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            dc={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 80, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            ac_default={},
            dc_default={},
        )
        v2 = SchemeValues(
            scheme_guid="guid-2",
            personality_guid="pers-1",
            ac={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 90, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            dc={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 80, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            ac_default={},
            dc_default={},
        )

        diffs = compare_schemes(v1, v2, catalog, only_differences=True)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].setting_guid, "bc502fe6-701e-46c4-9826-5d42490a1e9c")
        self.assertEqual(diffs[0].ac_left, 100)
        self.assertEqual(diffs[0].ac_right, 90)

    def test_get_modified_settings(self):
        """get_modified_settings detects values differing from defaults."""
        catalog = self._sample_catalog()
        v = SchemeValues(
            scheme_guid="guid-1",
            personality_guid="pers-1",
            ac={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 80, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            dc={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 60, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            ac_default={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 100, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
            dc_default={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 80, "893dee8e-2bef-41e0-89c6-b55d0929964c": 5},
        )

        modified = get_modified_settings(v, catalog)
        self.assertEqual(len(modified), 1)
        self.assertEqual(modified[0].setting_guid, "bc502fe6-701e-46c4-9826-5d42490a1e9c")
        self.assertEqual(modified[0].ac_left, 80)
        self.assertEqual(modified[0].ac_right, 100)


if __name__ == "__main__":
    unittest.main()
