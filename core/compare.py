"""Scheme comparison and modified-from-default computation.

Operates purely on in-memory SchemeValues and SettingCatalog objects without
making any foreign function calls.
"""

from core.models import (
    SchemeValues,
    SettingCatalog,
    SettingDiff,
)


def compare_schemes(
    left_values: SchemeValues,
    right_values: SchemeValues,
    catalog: SettingCatalog,
    only_differences: bool = False,
) -> list[SettingDiff]:
    """Compare two power schemes and return SettingDiff rows."""
    diffs: list[SettingDiff] = []

    for sub in catalog.subgroups:
        for setting in sub.settings:
            key = setting.guid.lower()
            ac_l = left_values.ac.get(key)
            ac_r = right_values.ac.get(key)
            dc_l = left_values.dc.get(key)
            dc_r = right_values.dc.get(key)

            diff = SettingDiff(
                setting_guid=setting.guid,
                subgroup_guid=sub.guid,
                friendly_name=setting.friendly_name or setting.guid,
                ac_left=ac_l,
                ac_right=ac_r,
                dc_left=dc_l,
                dc_right=dc_r,
            )

            if not only_differences or diff.differs:
                diffs.append(diff)

    return diffs


def get_modified_settings(
    scheme_values: SchemeValues,
    catalog: SettingCatalog,
) -> list[SettingDiff]:
    """Return all settings in a scheme whose values differ from personality defaults.

    Left side represents configured value; right side represents personality default.
    """
    diffs: list[SettingDiff] = []

    for sub in catalog.subgroups:
        for setting in sub.settings:
            key = setting.guid.lower()
            ac_val = scheme_values.ac.get(key)
            ac_def = scheme_values.ac_default.get(key)
            dc_val = scheme_values.dc.get(key)
            dc_def = scheme_values.dc_default.get(key)

            # Skip if no default is known (ERROR_FILE_NOT_FOUND)
            if ac_def is None and dc_def is None:
                continue

            diff = SettingDiff(
                setting_guid=setting.guid,
                subgroup_guid=sub.guid,
                friendly_name=setting.friendly_name or setting.guid,
                ac_left=ac_val,
                ac_right=ac_def,
                dc_left=dc_val,
                dc_right=dc_def,
            )

            if diff.differs:
                diffs.append(diff)

    return diffs
