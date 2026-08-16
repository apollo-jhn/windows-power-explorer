"""Phase-2 Per-Scheme Values and Defaults Loader (ADR-012).

Reads per-scheme AC/DC configured values (~150 FFI calls) and resolves defaults
keyed by scheme personality, reusing the default cache when schemes share a personality.
Assembles UI models on demand.
"""

from core.models import (
    PowerScheme,
    PowerSetting,
    PowerSubgroup,
    SchemeValues,
    SettingCatalog,
    SettingCatalogEntry,
)
from core.power_manager import PowerManager


def load_scheme_values(
    scheme_guid: str,
    catalog: SettingCatalog,
    pm: PowerManager | None = None,
    default_cache: dict[tuple[str, str, str], tuple[int | None, int | None]] | None = None,
) -> SchemeValues:
    """Load per-scheme configured values and personality defaults (Phase 2 of ADR-012).

    Defaults are keyed by personality GUID (not scheme GUID) and shared across schemes.
    """
    if pm is None:
        pm = PowerManager()

    if default_cache is None:
        default_cache = {}

    personality_guid = pm.personality_of(scheme_guid)

    ac_values: dict[str, int | None] = {}
    dc_values: dict[str, int | None] = {}
    ac_defaults: dict[str, int | None] = {}
    dc_defaults: dict[str, int | None] = {}

    for sub in catalog.subgroups:
        for setting in sub.settings:
            s_guid_key = setting.guid.lower()

            # Read configured AC and DC values
            ac_val = pm.read_ac_value(scheme_guid, sub.guid, setting.guid)
            dc_val = pm.read_dc_value(scheme_guid, sub.guid, setting.guid)
            ac_values[s_guid_key] = ac_val
            dc_values[s_guid_key] = dc_val

            # Resolve defaults keyed by personality
            cache_key = (personality_guid.lower(), sub.guid.lower(), s_guid_key)
            if cache_key in default_cache:
                ac_def, dc_def = default_cache[cache_key]
            else:
                ac_def = pm.read_ac_default(personality_guid, sub.guid, setting.guid)
                dc_def = pm.read_dc_default(personality_guid, sub.guid, setting.guid)
                default_cache[cache_key] = (ac_def, dc_def)

            ac_defaults[s_guid_key] = ac_def
            dc_defaults[s_guid_key] = dc_def

    return SchemeValues(
        scheme_guid=scheme_guid,
        personality_guid=personality_guid,
        ac=ac_values,
        dc=dc_values,
        ac_default=ac_defaults,
        dc_default=dc_defaults,
    )


def assemble_power_setting(
    catalog_entry: SettingCatalogEntry,
    values: SchemeValues,
) -> PowerSetting:
    """Assemble a flattened PowerSetting UI model from a catalog entry and values."""
    key = catalog_entry.guid.lower()
    return PowerSetting(
        guid=catalog_entry.guid,
        subgroup_guid=catalog_entry.subgroup_guid,
        friendly_name=catalog_entry.friendly_name,
        description=catalog_entry.description,
        control_type=catalog_entry.control_type,
        is_hidden=catalog_entry.is_hidden,
        is_policy_locked=catalog_entry.is_policy_locked,
        is_degraded=catalog_entry.is_degraded,
        has_friendly_name=bool(catalog_entry.friendly_name),
        value_units=catalog_entry.value_units,
        min_value=catalog_entry.min_value,
        max_value=catalog_entry.max_value,
        value_increment=catalog_entry.value_increment,
        ac_value=values.ac.get(key),
        dc_value=values.dc.get(key),
        choices=list(catalog_entry.choices),
    )


def assemble_power_scheme(
    scheme_guid: str,
    friendly_name: str,
    description: str,
    is_active: bool,
    is_base_default: bool,
    catalog: SettingCatalog,
    values: SchemeValues,
) -> PowerScheme:
    """Assemble a complete PowerScheme UI tree from catalog and values."""
    subgroups: list[PowerSubgroup] = []
    for sub_entry in catalog.subgroups:
        settings: list[PowerSetting] = [
            assemble_power_setting(set_entry, values)
            for set_entry in sub_entry.settings
        ]
        subgroups.append(
            PowerSubgroup(
                guid=sub_entry.guid,
                friendly_name=sub_entry.friendly_name,
                description=sub_entry.description,
                is_hidden=sub_entry.is_hidden,
                settings=settings,
            )
        )

    return PowerScheme(
        guid=scheme_guid,
        friendly_name=friendly_name,
        description=description,
        is_active=is_active,
        is_base_default=is_base_default,
        subgroups=subgroups,
    )
