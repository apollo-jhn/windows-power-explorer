"""Phase-1 Scheme-Invariant Setting Catalog Builder (ADR-012).

Builds an immutable, scheme-invariant catalog containing the setting tree,
names, descriptions, bounds, units, possible values, visibility attributes,
and policy locks. Holds NO per-scheme AC/DC values.
"""

from core.models import (
    ControlType,
    SettingCatalog,
    SettingCatalogEntry,
    SettingValueChoice,
    SubgroupCatalogEntry,
)
from core.power_manager import PowerManager
from core.win32_bindings import (
    ACCESS_AC_POWER_SETTING_INDEX,
    POWER_ATTRIBUTE_HIDE,
)


def build_catalog(
    pm: PowerManager | None = None,
    scheme_guid: str | None = None,
) -> SettingCatalog:
    """Build the scheme-invariant setting catalog (Phase 1 of ADR-012).

    Traverses all subgroups and settings to gather immutable metadata.
    This operation performs ~700 FFI calls and is cached for the session.
    """
    if pm is None:
        pm = PowerManager()

    subgroups_list: list[SubgroupCatalogEntry] = []
    by_guid: dict[str, SettingCatalogEntry] = {}
    subgroup_by_guid: dict[str, SubgroupCatalogEntry] = {}

    for sub_guid in pm.iter_subgroups(scheme_guid):
        sub_name = pm.read_friendly_name(None, sub_guid, None)
        sub_desc = pm.read_description(None, sub_guid, None)
        sub_attr = pm.read_setting_attributes(sub_guid, None)
        sub_is_hidden = bool(sub_attr & POWER_ATTRIBUTE_HIDE)

        settings_list: list[SettingCatalogEntry] = []

        for set_guid in pm.iter_settings(scheme_guid, sub_guid):
            set_name = pm.read_friendly_name(None, sub_guid, set_guid)
            set_desc = pm.read_description(None, sub_guid, set_guid)
            min_val, max_val, inc_val, units = pm.read_bounds(sub_guid, set_guid)
            choices_list = pm.read_possible_values(sub_guid, set_guid)
            choices_tuple = tuple(choices_list)

            ctrl_type = pm.infer_control_type(choices_list, min_val, max_val)
            set_attr = pm.read_setting_attributes(sub_guid, set_guid)
            set_is_hidden = bool(set_attr & POWER_ATTRIBUTE_HIDE)

            is_policy_locked = not pm.check_policy(ACCESS_AC_POWER_SETTING_INDEX, set_guid)
            is_degraded = not bool(set_name) and (min_val is None and max_val is None and not choices_list)

            entry = SettingCatalogEntry(
                guid=set_guid,
                subgroup_guid=sub_guid,
                friendly_name=set_name,
                description=set_desc,
                control_type=ctrl_type,
                min_value=min_val,
                max_value=max_val,
                value_increment=inc_val,
                value_units=units,
                choices=choices_tuple,
                is_hidden=set_is_hidden,
                is_policy_locked=is_policy_locked,
                is_degraded=is_degraded,
            )

            settings_list.append(entry)
            by_guid[set_guid.lower()] = entry

        subgroup_entry = SubgroupCatalogEntry(
            guid=sub_guid,
            friendly_name=sub_name,
            description=sub_desc,
            is_hidden=sub_is_hidden,
            settings=tuple(settings_list),
        )

        subgroups_list.append(subgroup_entry)
        subgroup_by_guid[sub_guid.lower()] = subgroup_entry

    return SettingCatalog(
        subgroups=tuple(subgroups_list),
        by_guid=by_guid,
        subgroup_by_guid=subgroup_by_guid,
    )
