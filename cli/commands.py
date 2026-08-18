"""Subcommand implementations for Windows Power Explorer CLI (REQ-15, REQ-9.6)."""

import json
import sys
from typing import Any

from core.catalog import build_catalog
from core.errors import PowerExplorerError
from core.models import SettingCatalog
from core.power_manager import PowerManager
from core.values import load_scheme_values

# Exit codes per CLI Spec §2.3
EXIT_SUCCESS = 0
EXIT_ERR_GENERAL = 1
EXIT_ERR_SCHEME_NOT_FOUND = 2
EXIT_ERR_SETTING_NOT_FOUND = 3
EXIT_ERR_VALUE_OUT_OF_BOUNDS = 4
EXIT_ERR_ACCESS_DENIED = 5
EXIT_ERR_POLICY_LOCKED = 6


def emit_output(data: Any, is_json: bool, format_fn=None) -> None:
    """Emit structured JSON or formatted human-readable text."""
    if is_json:
        print(json.dumps({"ok": True, "data": data}, indent=2))
    else:
        if format_fn:
            print(format_fn(data))
        else:
            print(data)


def emit_error(code_name: str, exit_code: int, message: str, is_json: bool) -> int:
    """Emit uniform error envelope or human-readable stderr message."""
    if is_json:
        print(json.dumps({
            "ok": False,
            "error": {
                "code": code_name,
                "exit_code": exit_code,
                "message": message,
                "win32_code": None,
            }
        }, indent=2))
    else:
        print(f"Error: {message}", file=sys.stderr)
    return exit_code


def resolve_scheme_guid(pm: PowerManager, scheme_query: str | None) -> str | None:
    """Resolve a scheme GUID or friendly name query to a canonical GUID."""
    if not scheme_query:
        return pm.get_active_scheme_guid()

    schemes = list(pm.iter_schemes())
    # 1. Exact GUID match
    for s_guid, name, desc, active, base in schemes:
        if s_guid.lower() == scheme_query.lower():
            return s_guid

    # 2. Exact or prefix name match
    matches = [s_guid for s_guid, name, desc, active, base in schemes if name.lower() == scheme_query.lower()]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        return None  # Ambiguous

    # Partial match
    partial = [s_guid for s_guid, name, desc, active, base in schemes if scheme_query.lower() in name.lower()]
    if len(partial) == 1:
        return partial[0]

    return None


def cmd_list_schemes(args, pm: PowerManager) -> int:
    """List all power schemes (CLI Spec §2.2)."""
    schemes = list(pm.iter_schemes())
    data = [
        {
            "guid": s[0],
            "name": s[1],
            "description": s[2],
            "is_active": s[3],
            "is_base_default": s[4],
        }
        for s in schemes
    ]

    def fmt_human(items):
        lines = [
            f"{'Active':<8}{'GUID':<40}{'Name'}",
            f"{'------':<8}{'----':<40}{'----'}",
        ]
        for it in items:
            act = "* [*]" if it["is_active"] else ""
            lines.append(f"{act:<8}{it['guid']:<40}{it['name']}")
        return "\n".join(lines)

    emit_output(data, args.json, fmt_human)
    return EXIT_SUCCESS


def cmd_list_settings(args, pm: PowerManager) -> int:
    """List power settings, supporting --modified-only and filtering (REQ-9.6)."""
    scheme_guid = resolve_scheme_guid(pm, args.scheme)
    if not scheme_guid:
        return emit_error("ERR_SCHEME_NOT_FOUND", EXIT_ERR_SCHEME_NOT_FOUND, f"Scheme not found: '{args.scheme}'", args.json)

    catalog = build_catalog(pm)
    values = load_scheme_values(scheme_guid, catalog, pm)

    results = []
    for sub in catalog.subgroups:
        if args.category and args.category.lower() not in sub.friendly_name.lower() and args.category.lower() != sub.guid.lower():
            continue

        for setting in sub.settings:
            s_key = setting.guid.lower()
            if args.hidden_only and not setting.is_hidden:
                continue

            ac_val = values.ac.get(s_key)
            dc_val = values.dc.get(s_key)
            ac_def = values.ac_default.get(s_key)
            dc_def = values.dc_default.get(s_key)

            is_modified = False
            if ac_def is not None and ac_val is not None and ac_val != ac_def:
                is_modified = True
            if dc_def is not None and dc_val is not None and dc_val != dc_def:
                is_modified = True

            if args.modified_only and not is_modified:
                continue

            if args.search:
                q = args.search.lower()
                matched = (
                    q in setting.friendly_name.lower()
                    or q in setting.description.lower()
                    or q in setting.guid.lower()
                    or q in sub.friendly_name.lower()
                    or any(q in c.friendly_name.lower() for c in setting.choices)
                )
                if not matched:
                    continue

            results.append({
                "subgroup_guid": sub.guid,
                "subgroup_name": sub.friendly_name,
                "guid": setting.guid,
                "name": setting.friendly_name,
                "control_type": setting.control_type.value,
                "ac_value": ac_val,
                "dc_value": dc_val,
                "ac_default": ac_def,
                "dc_default": dc_def,
                "is_modified": is_modified,
            })

    def fmt_human(items):
        if not items:
            return "No matching settings found."
        lines = [f"{'Subgroup':<25}{'Setting Name':<35}{'AC':<10}{'DC':<10}{'Modified'}"]
        lines.append("-" * 90)
        for it in items:
            mod_str = "* Yes" if it["is_modified"] else "No"
            lines.append(f"{it['subgroup_name'][:24]:<25}{it['name'][:34]:<35}{str(it['ac_value']):<10}{str(it['dc_value']):<10}{mod_str}")
        return "\n".join(lines)

    emit_output(results, args.json, fmt_human)
    return EXIT_SUCCESS


def cmd_show_setting(args, pm: PowerManager) -> int:
    """Show details of a specific setting."""
    scheme_guid = resolve_scheme_guid(pm, args.scheme)
    if not scheme_guid:
        return emit_error("ERR_SCHEME_NOT_FOUND", EXIT_ERR_SCHEME_NOT_FOUND, f"Scheme not found: '{args.scheme}'", args.json)

    catalog = build_catalog(pm)
    target_entry = None
    subgroup_entry = None
    for sub in catalog.subgroups:
        for setting in sub.settings:
            if setting.guid.lower() == args.setting.lower():
                target_entry = setting
                subgroup_entry = sub
                break
        if target_entry:
            break

    if not target_entry:
        return emit_error("ERR_SETTING_NOT_FOUND", EXIT_ERR_SETTING_NOT_FOUND, f"Setting not found: '{args.setting}'", args.json)

    values = load_scheme_values(scheme_guid, catalog, pm)
    s_key = target_entry.guid.lower()

    data = {
        "guid": target_entry.guid,
        "name": target_entry.friendly_name,
        "description": target_entry.description,
        "subgroup_guid": subgroup_entry.guid if subgroup_entry else "",
        "subgroup_name": subgroup_entry.friendly_name if subgroup_entry else "",
        "control_type": target_entry.control_type.value,
        "min_value": target_entry.min_value,
        "max_value": target_entry.max_value,
        "value_increment": target_entry.value_increment,
        "units": target_entry.value_units,
        "ac_value": values.ac.get(s_key),
        "dc_value": values.dc.get(s_key),
        "ac_default": values.ac_default.get(s_key),
        "dc_default": values.dc_default.get(s_key),
        "choices": [{"index": c.value_index, "name": c.friendly_name} for c in target_entry.choices],
    }

    def fmt_human(d):
        lines = [
            f"Setting:     {d['name']} ({d['guid']})",
            f"Subgroup:    {d['subgroup_name']} ({d['subgroup_guid']})",
            f"Description: {d['description']}",
            f"Type:        {d['control_type']}",
            f"AC Value:    {d['ac_value']} (Default: {d['ac_default']})",
            f"DC Value:    {d['dc_value']} (Default: {d['dc_default']})",
        ]
        if d["choices"]:
            lines.append("Choices:")
            for c in d["choices"]:
                lines.append(f"  [{c['index']}] {c['name']}")
        return "\n".join(lines)

    emit_output(data, args.json, fmt_human)
    return EXIT_SUCCESS


def cmd_edit_setting(args, pm: PowerManager) -> int:
    """Edit AC/DC values for a setting (REQ-2.3)."""
    if args.ac is None and args.dc is None:
        return emit_error("ERR_GENERAL", EXIT_ERR_GENERAL, "Must specify at least one of --ac or --dc", args.json)

    scheme_guid = resolve_scheme_guid(pm, args.scheme)
    if not scheme_guid:
        return emit_error("ERR_SCHEME_NOT_FOUND", EXIT_ERR_SCHEME_NOT_FOUND, f"Scheme not found: '{args.scheme}'", args.json)

    catalog = build_catalog(pm)
    target_entry = None
    subgroup_entry = None
    for sub in catalog.subgroups:
        for setting in sub.settings:
            if setting.guid.lower() == args.setting.lower():
                target_entry = setting
                subgroup_entry = sub
                break
        if target_entry:
            break

    if not target_entry or not subgroup_entry:
        return emit_error("ERR_SETTING_NOT_FOUND", EXIT_ERR_SETTING_NOT_FOUND, f"Setting not found: '{args.setting}'", args.json)

    bounds = (target_entry.min_value, target_entry.max_value)
    if args.dry_run:
        data = {
            "dry_run": True,
            "scheme": scheme_guid,
            "setting": target_entry.guid,
            "ac_new": args.ac,
            "dc_new": args.dc,
        }
        emit_output(data, args.json, lambda d: f"[DRY-RUN] Would update setting {d['setting']} (AC={d['ac_new']}, DC={d['dc_new']})")
        return EXIT_SUCCESS

    try:
        if args.ac is not None:
            pm.write_ac_value(scheme_guid, subgroup_entry.guid, target_entry.guid, args.ac, bounds)
        if args.dc is not None:
            pm.write_dc_value(scheme_guid, subgroup_entry.guid, target_entry.guid, args.dc, bounds)
    except PowerExplorerError as exc:
        return emit_error("ERR_VALUE_OUT_OF_BOUNDS", EXIT_ERR_VALUE_OUT_OF_BOUNDS, str(exc), args.json)

    data = {
        "scheme": scheme_guid,
        "setting": target_entry.guid,
        "ac": args.ac,
        "dc": args.dc,
    }
    emit_output(data, args.json, lambda d: f"Successfully updated setting {d['setting']}")
    return EXIT_SUCCESS


def cmd_reset_setting(args, pm: PowerManager) -> int:
    """Reset setting value to default (REQ-9.6)."""
    scheme_guid = resolve_scheme_guid(pm, args.scheme)
    if not scheme_guid:
        return emit_error("ERR_SCHEME_NOT_FOUND", EXIT_ERR_SCHEME_NOT_FOUND, f"Scheme not found: '{args.scheme}'", args.json)

    catalog = build_catalog(pm)
    target_entry = None
    subgroup_entry = None
    for sub in catalog.subgroups:
        for setting in sub.settings:
            if setting.guid.lower() == args.setting.lower():
                target_entry = setting
                subgroup_entry = sub
                break
        if target_entry:
            break

    if not target_entry or not subgroup_entry:
        return emit_error("ERR_SETTING_NOT_FOUND", EXIT_ERR_SETTING_NOT_FOUND, f"Setting not found: '{args.setting}'", args.json)

    personality = pm.personality_of(scheme_guid)
    ac_def = pm.read_ac_default(personality, subgroup_entry.guid, target_entry.guid)
    dc_def = pm.read_dc_default(personality, subgroup_entry.guid, target_entry.guid)

    reset_ac = args.ac or (not args.ac and not args.dc)
    reset_dc = args.dc or (not args.ac and not args.dc)

    if args.dry_run:
        data = {
            "dry_run": True,
            "scheme": scheme_guid,
            "setting": target_entry.guid,
            "ac_default": ac_def if reset_ac else None,
            "dc_default": dc_def if reset_dc else None,
        }
        emit_output(data, args.json, lambda d: f"[DRY-RUN] Would reset setting {d['setting']} to defaults (AC={d['ac_default']}, DC={d['dc_default']})")
        return EXIT_SUCCESS

    bounds = (target_entry.min_value, target_entry.max_value)
    if reset_ac and ac_def is not None:
        pm.write_ac_value(scheme_guid, subgroup_entry.guid, target_entry.guid, ac_def, bounds)
    if reset_dc and dc_def is not None:
        pm.write_dc_value(scheme_guid, subgroup_entry.guid, target_entry.guid, dc_def, bounds)

    data = {
        "scheme": scheme_guid,
        "setting": target_entry.guid,
        "ac_reset": ac_def if reset_ac else None,
        "dc_reset": dc_def if reset_dc else None,
    }
    emit_output(data, args.json, lambda d: f"Successfully reset setting {d['setting']} to default")
    return EXIT_SUCCESS
