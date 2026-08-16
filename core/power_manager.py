"""High-level Power Manager interface wrapping Win32 Power Management APIs.

Handles scheme CRUD, value read/write, bounds validation, policy checks,
and critical active-scheme write safety (REQ-2.3).
"""

import ctypes
from ctypes import wintypes
from typing import Iterator

from core.errors import (
    PowerApiError,
    PowerExplorerError,
    SchemeNotFoundError,
    ValueOutOfBoundsError,
)
from core.models import (
    ControlType,
    SettingValueChoice,
)
from core.win32_bindings import (
    ACCESS_AC_POWER_SETTING_INDEX,
    ACCESS_DC_POWER_SETTING_INDEX,
    ACCESS_INDIVIDUAL_SETTING,
    ACCESS_SCHEME,
    ACCESS_SUBGROUP,
    BASE_SCHEMES,
    ERROR_ACCESS_DENIED,
    ERROR_FILE_NOT_FOUND,
    ERROR_MORE_DATA,
    ERROR_NO_MORE_ITEMS,
    ERROR_SUCCESS,
    GUID,
    GUID_POWERSCHEME_PERSONALITY,
    GUID_TYPICAL_POWER_SAVINGS,
    NO_SUBGROUP_GUID,
    PERSONALITY_BY_INDEX,
    encode_name,
    out_guid,
    parse_guid,
    powrprof,
    read_sized_string,
)


class PowerManager:
    """High-level API for scheme lifecycle management and setting values."""

    def __init__(self) -> None:
        self._active_guid: str | None = None

    def get_active_scheme_guid(self) -> str:
        """Retrieve the currently active power scheme GUID."""
        if powrprof is None:
            return self._active_guid or GUID_TYPICAL_POWER_SAVINGS

        with out_guid() as out_ptr:
            rc = powrprof.PowerGetActiveScheme(None, out_ptr)
            if rc != ERROR_SUCCESS:
                raise PowerApiError("PowerGetActiveScheme", rc)
            ptr = out_ptr._obj
            guid_obj = GUID.from_buffer_copy(ptr.contents)
            active = guid_obj.to_string()
            self._active_guid = active
            return active

    def set_active_scheme(self, scheme_guid: str) -> None:
        """Set the active power scheme on the system."""
        c_guid = parse_guid(scheme_guid)
        if powrprof is not None:
            rc = powrprof.PowerSetActiveScheme(None, ctypes.byref(c_guid))
            if rc != ERROR_SUCCESS:
                raise PowerApiError("PowerSetActiveScheme", rc, context=f"Scheme: {scheme_guid}")
        self._active_guid = scheme_guid

    def iter_schemes(self) -> Iterator[tuple[str, str, str, bool, bool]]:
        """Enumerate all available power schemes.

        Yields (guid, friendly_name, description, is_active, is_base_default).
        """
        if powrprof is None:
            return

        active_guid = self.get_active_scheme_guid()
        buf_size = wintypes.DWORD(ctypes.sizeof(GUID))
        buf = (ctypes.c_ubyte * ctypes.sizeof(GUID))()

        for index in range(4096):
            buf_size.value = ctypes.sizeof(GUID)
            rc = powrprof.PowerEnumerate(
                None,
                None,
                None,
                ACCESS_SCHEME,
                index,
                ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)),
                ctypes.byref(buf_size),
            )
            if rc == ERROR_NO_MORE_ITEMS:
                break
            if rc != ERROR_SUCCESS:
                raise PowerApiError("PowerEnumerate(ACCESS_SCHEME)", rc)

            guid_obj = GUID.from_buffer_copy(buf)
            s_guid = guid_obj.to_string()
            name = self.read_friendly_name(s_guid, None, None)
            desc = self.read_description(s_guid, None, None)
            is_active = (s_guid.lower() == active_guid.lower())
            is_base = s_guid.lower() in {k.lower(): v for k, v in BASE_SCHEMES.items()}

            if not name and s_guid.lower() in {k.lower(): v for k, v in BASE_SCHEMES.items()}:
                name = BASE_SCHEMES.get(s_guid, s_guid)

            yield s_guid, name, desc, is_active, is_base

    def iter_subgroups(self, scheme_guid: str | None = None) -> Iterator[str]:
        """Enumerate all power subgroups for a scheme (or global tree)."""
        if powrprof is None:
            return

        c_scheme = ctypes.byref(parse_guid(scheme_guid)) if scheme_guid else None
        buf_size = wintypes.DWORD(ctypes.sizeof(GUID))
        buf = (ctypes.c_ubyte * ctypes.sizeof(GUID))()

        for index in range(4096):
            buf_size.value = ctypes.sizeof(GUID)
            rc = powrprof.PowerEnumerate(
                None,
                c_scheme,
                None,
                ACCESS_SUBGROUP,
                index,
                ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)),
                ctypes.byref(buf_size),
            )
            if rc == ERROR_NO_MORE_ITEMS:
                break
            if rc != ERROR_SUCCESS:
                break

            guid_obj = GUID.from_buffer_copy(buf)
            yield guid_obj.to_string()

    def iter_settings(self, scheme_guid: str | None, subgroup_guid: str) -> Iterator[str]:
        """Enumerate all power settings within a specific subgroup."""
        if powrprof is None:
            return

        c_scheme = ctypes.byref(parse_guid(scheme_guid)) if scheme_guid else None
        c_subgroup = ctypes.byref(parse_guid(subgroup_guid))
        buf_size = wintypes.DWORD(ctypes.sizeof(GUID))
        buf = (ctypes.c_ubyte * ctypes.sizeof(GUID))()

        for index in range(4096):
            buf_size.value = ctypes.sizeof(GUID)
            rc = powrprof.PowerEnumerate(
                None,
                c_scheme,
                c_subgroup,
                ACCESS_INDIVIDUAL_SETTING,
                index,
                ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)),
                ctypes.byref(buf_size),
            )
            if rc == ERROR_NO_MORE_ITEMS:
                break
            if rc != ERROR_SUCCESS:
                break

            guid_obj = GUID.from_buffer_copy(buf)
            yield guid_obj.to_string()

    def read_friendly_name(
        self,
        scheme_guid: str | None = None,
        subgroup_guid: str | None = None,
        setting_guid: str | None = None,
    ) -> str:
        """Read localized friendly name for a scheme, subgroup, or setting."""
        if powrprof is None:
            return ""

        c_scheme = ctypes.byref(parse_guid(scheme_guid)) if scheme_guid else None
        c_sub = ctypes.byref(parse_guid(subgroup_guid)) if subgroup_guid else None
        c_set = ctypes.byref(parse_guid(setting_guid)) if setting_guid else None

        try:
            return read_sized_string(powrprof.PowerReadFriendlyName, None, c_scheme, c_sub, c_set)
        except Exception:
            return ""

    def read_description(
        self,
        scheme_guid: str | None = None,
        subgroup_guid: str | None = None,
        setting_guid: str | None = None,
    ) -> str:
        """Read localized description for a scheme, subgroup, or setting."""
        if powrprof is None:
            return ""

        c_scheme = ctypes.byref(parse_guid(scheme_guid)) if scheme_guid else None
        c_sub = ctypes.byref(parse_guid(subgroup_guid)) if subgroup_guid else None
        c_set = ctypes.byref(parse_guid(setting_guid)) if setting_guid else None

        try:
            return read_sized_string(powrprof.PowerReadDescription, None, c_scheme, c_sub, c_set)
        except Exception:
            return ""

    def write_friendly_name(
        self,
        scheme_guid: str | None,
        subgroup_guid: str | None,
        setting_guid: str | None,
        name: str,
    ) -> None:
        """Write friendly name for a scheme, subgroup, or setting."""
        if powrprof is None:
            return

        c_scheme = ctypes.byref(parse_guid(scheme_guid)) if scheme_guid else None
        c_sub = ctypes.byref(parse_guid(subgroup_guid)) if subgroup_guid else None
        c_set = ctypes.byref(parse_guid(setting_guid)) if setting_guid else None

        ptr, size, _buf = encode_name(name)
        rc = powrprof.PowerWriteFriendlyName(None, c_scheme, c_sub, c_set, ptr, size)
        if rc != ERROR_SUCCESS:
            raise PowerApiError("PowerWriteFriendlyName", rc)

    def write_description(
        self,
        scheme_guid: str | None,
        subgroup_guid: str | None,
        setting_guid: str | None,
        description: str,
    ) -> None:
        """Write description for a scheme, subgroup, or setting."""
        if powrprof is None:
            return

        c_scheme = ctypes.byref(parse_guid(scheme_guid)) if scheme_guid else None
        c_sub = ctypes.byref(parse_guid(subgroup_guid)) if subgroup_guid else None
        c_set = ctypes.byref(parse_guid(setting_guid)) if setting_guid else None

        ptr, size, _buf = encode_name(description)
        rc = powrprof.PowerWriteDescription(None, c_scheme, c_sub, c_set, ptr, size)
        if rc != ERROR_SUCCESS:
            raise PowerApiError("PowerWriteDescription", rc)

    def read_ac_value(self, scheme_guid: str, subgroup_guid: str, setting_guid: str) -> int | None:
        """Read configured AC (plugged-in) setting index."""
        if powrprof is None:
            return None

        c_scheme = ctypes.byref(parse_guid(scheme_guid))
        c_sub = ctypes.byref(parse_guid(subgroup_guid))
        c_set = ctypes.byref(parse_guid(setting_guid))
        val = wintypes.DWORD(0)

        rc = powrprof.PowerReadACValueIndex(None, c_scheme, c_sub, c_set, ctypes.byref(val))
        if rc == ERROR_SUCCESS:
            return val.value
        return None

    def read_dc_value(self, scheme_guid: str, subgroup_guid: str, setting_guid: str) -> int | None:
        """Read configured DC (on-battery) setting index."""
        if powrprof is None:
            return None

        c_scheme = ctypes.byref(parse_guid(scheme_guid))
        c_sub = ctypes.byref(parse_guid(subgroup_guid))
        c_set = ctypes.byref(parse_guid(setting_guid))
        val = wintypes.DWORD(0)

        rc = powrprof.PowerReadDCValueIndex(None, c_scheme, c_sub, c_set, ctypes.byref(val))
        if rc == ERROR_SUCCESS:
            return val.value
        return None

    def write_ac_value(
        self,
        scheme_guid: str,
        subgroup_guid: str,
        setting_guid: str,
        value: int,
        bounds: tuple[int | None, int | None] | None = None,
    ) -> None:
        """Write AC power setting value with bounds validation and active scheme guard.

        CRITICAL REQ-2.3:
        PowerSetActiveScheme MUST only be called if scheme_guid matches the active scheme!
        """
        if bounds:
            min_val, max_val = bounds
            if min_val is not None and value < min_val:
                raise ValueOutOfBoundsError(f"Value {value} below minimum {min_val}")
            if max_val is not None and value > max_val:
                raise ValueOutOfBoundsError(f"Value {value} above maximum {max_val}")

        c_scheme = ctypes.byref(parse_guid(scheme_guid))
        c_sub = ctypes.byref(parse_guid(subgroup_guid))
        c_set = ctypes.byref(parse_guid(setting_guid))

        if powrprof is not None:
            rc = powrprof.PowerWriteACValueIndex(None, c_scheme, c_sub, c_set, wintypes.DWORD(value))
            if rc != ERROR_SUCCESS:
                raise PowerApiError("PowerWriteACValueIndex", rc, context=f"Setting: {setting_guid}")

            # REQ-2.3: Refresh policy live ONLY if the edited scheme is active
            active = self.get_active_scheme_guid()
            if scheme_guid.lower() == active.lower():
                self.set_active_scheme(scheme_guid)

    def write_dc_value(
        self,
        scheme_guid: str,
        subgroup_guid: str,
        setting_guid: str,
        value: int,
        bounds: tuple[int | None, int | None] | None = None,
    ) -> None:
        """Write DC power setting value with bounds validation and active scheme guard.

        CRITICAL REQ-2.3:
        PowerSetActiveScheme MUST only be called if scheme_guid matches the active scheme!
        """
        if bounds:
            min_val, max_val = bounds
            if min_val is not None and value < min_val:
                raise ValueOutOfBoundsError(f"Value {value} below minimum {min_val}")
            if max_val is not None and value > max_val:
                raise ValueOutOfBoundsError(f"Value {value} above maximum {max_val}")

        c_scheme = ctypes.byref(parse_guid(scheme_guid))
        c_sub = ctypes.byref(parse_guid(subgroup_guid))
        c_set = ctypes.byref(parse_guid(setting_guid))

        if powrprof is not None:
            rc = powrprof.PowerWriteDCValueIndex(None, c_scheme, c_sub, c_set, wintypes.DWORD(value))
            if rc != ERROR_SUCCESS:
                raise PowerApiError("PowerWriteDCValueIndex", rc, context=f"Setting: {setting_guid}")

            # REQ-2.3: Refresh policy live ONLY if the edited scheme is active
            active = self.get_active_scheme_guid()
            if scheme_guid.lower() == active.lower():
                self.set_active_scheme(scheme_guid)

    def read_bounds(
        self, subgroup_guid: str, setting_guid: str
    ) -> tuple[int | None, int | None, int | None, str]:
        """Read Min, Max, Increment, and UnitsSpecifier for a setting.

        Returns (min_value, max_value, value_increment, units_str).
        """
        if powrprof is None:
            return None, None, None, ""

        c_sub = ctypes.byref(parse_guid(subgroup_guid))
        c_set = ctypes.byref(parse_guid(setting_guid))

        min_val = wintypes.DWORD(0)
        max_val = wintypes.DWORD(0)
        inc_val = wintypes.DWORD(0)

        min_res = powrprof.PowerReadValueMin(None, c_sub, c_set, ctypes.byref(min_val))
        max_res = powrprof.PowerReadValueMax(None, c_sub, c_set, ctypes.byref(max_val))
        inc_res = powrprof.PowerReadValueIncrement(None, c_sub, c_set, ctypes.byref(inc_val))

        min_out = min_val.value if min_res == ERROR_SUCCESS else None
        max_out = max_val.value if max_res == ERROR_SUCCESS else None
        inc_out = inc_val.value if inc_res == ERROR_SUCCESS else None

        # Coerce increment to 1 if reported as 0 by buggy OEM drivers
        if inc_out == 0:
            inc_out = 1

        # Read Units Specifier
        units = ""
        try:
            units = read_sized_string(powrprof.PowerReadValueUnitsSpecifier, None, c_sub, c_set)
        except Exception:
            units = ""

        return min_out, max_out, inc_out, units

    def read_possible_values(
        self, subgroup_guid: str, setting_guid: str
    ) -> list[SettingValueChoice]:
        """Enumerate discrete possible values (enum choices) for a setting."""
        if powrprof is None:
            return []

        c_sub = ctypes.byref(parse_guid(subgroup_guid))
        c_set = ctypes.byref(parse_guid(setting_guid))
        choices: list[SettingValueChoice] = []

        for index in range(256):
            val_type = wintypes.ULONG(0)
            size = wintypes.DWORD(0)

            # Probe size
            rc = powrprof.PowerReadPossibleValue(
                None, c_sub, c_set, ctypes.byref(val_type), index, None, ctypes.byref(size)
            )
            if rc in (ERROR_FILE_NOT_FOUND, ERROR_NO_MORE_ITEMS):
                break
            if rc not in (ERROR_SUCCESS, ERROR_MORE_DATA):
                break

            buf = ctypes.create_string_buffer(max(size.value, 4))
            rc = powrprof.PowerReadPossibleValue(
                None,
                c_sub,
                c_set,
                ctypes.byref(val_type),
                index,
                ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)),
                ctypes.byref(size),
            )
            if rc != ERROR_SUCCESS:
                break

            # Read choice integer value (usually DWORD)
            val_int = int.from_bytes(buf.raw[:4], byteorder="little") if size.value >= 4 else index

            # Read choice friendly name
            name = ""
            name_size = wintypes.DWORD(0)
            powrprof.PowerReadPossibleFriendlyName(None, c_sub, c_set, index, None, ctypes.byref(name_size))
            if name_size.value > 0:
                name_buf = ctypes.create_string_buffer(name_size.value)
                rc_name = powrprof.PowerReadPossibleFriendlyName(
                    None,
                    c_sub,
                    c_set,
                    index,
                    ctypes.cast(name_buf, ctypes.POINTER(ctypes.c_ubyte)),
                    ctypes.byref(name_size),
                )
                if rc_name == ERROR_SUCCESS:
                    name = name_buf.raw[: name_size.value].decode("utf-16-le", errors="replace").rstrip("\x00")

            if not name:
                name = f"Option {val_int}"

            choices.append(SettingValueChoice(value_index=val_int, friendly_name=name, description=""))

        return choices

    def read_setting_attributes(self, subgroup_guid: str, setting_guid: str | None = None) -> int:
        """Read visibility attributes bitmask for a setting or subgroup."""
        if powrprof is None:
            return 0

        c_sub = ctypes.byref(parse_guid(subgroup_guid))
        c_set = ctypes.byref(parse_guid(setting_guid)) if setting_guid else None

        # PowerReadSettingAttributes returns the bitmask DWORD directly
        return int(powrprof.PowerReadSettingAttributes(c_sub, c_set))

    def check_policy(self, access_flags: int, setting_guid: str) -> bool:
        """Check if Group Policy or ACL permits modifying this setting."""
        if powrprof is None:
            return True

        c_set = ctypes.byref(parse_guid(setting_guid))
        rc = powrprof.PowerSettingAccessCheck(access_flags, c_set)
        return rc == ERROR_SUCCESS

    def duplicate_scheme(self, source_scheme_guid: str, new_name: str | None = None) -> str:
        """Duplicate an existing power scheme and optionally set its friendly name."""
        if powrprof is None:
            raise PowerExplorerError("Win32 API not available")

        c_src = ctypes.byref(parse_guid(source_scheme_guid))
        with out_guid() as out_ptr:
            rc = powrprof.PowerDuplicateScheme(None, c_src, out_ptr)
            if rc != ERROR_SUCCESS:
                raise PowerApiError("PowerDuplicateScheme", rc)
            ptr = out_ptr._obj
            guid_obj = GUID.from_buffer_copy(ptr.contents)
            new_guid = guid_obj.to_string()

        if new_name:
            self.write_friendly_name(new_guid, None, None, new_name)

        return new_guid

    def delete_scheme(self, scheme_guid: str) -> None:
        """Delete a custom power scheme."""
        if powrprof is None:
            return

        if scheme_guid.lower() in {k.lower(): v for k, v in BASE_SCHEMES.items()}:
            raise PowerExplorerError(f"Cannot delete built-in Windows scheme: {scheme_guid}")

        active = self.get_active_scheme_guid()
        if scheme_guid.lower() == active.lower():
            raise PowerExplorerError(f"Cannot delete currently active power scheme: {scheme_guid}")

        c_scheme = ctypes.byref(parse_guid(scheme_guid))
        rc = powrprof.PowerDeleteScheme(None, c_scheme)
        if rc != ERROR_SUCCESS:
            raise PowerApiError("PowerDeleteScheme", rc)

    def personality_of(self, scheme_guid: str) -> str:
        """Determine the base personality GUID of a power scheme."""
        val = self.read_ac_value(scheme_guid, NO_SUBGROUP_GUID, GUID_POWERSCHEME_PERSONALITY)
        if val is not None and val in PERSONALITY_BY_INDEX:
            return PERSONALITY_BY_INDEX[val]
        return GUID_TYPICAL_POWER_SAVINGS

    def read_ac_default(self, personality_guid: str, subgroup_guid: str, setting_guid: str) -> int | None:
        """Read default AC setting index for a personality."""
        if powrprof is None:
            return None

        c_pers = ctypes.byref(parse_guid(personality_guid))
        c_sub = ctypes.byref(parse_guid(subgroup_guid))
        c_set = ctypes.byref(parse_guid(setting_guid))
        val = wintypes.DWORD(0)

        rc = powrprof.PowerReadACDefaultIndex(None, c_pers, c_sub, c_set, ctypes.byref(val))
        if rc == ERROR_SUCCESS:
            return val.value
        return None

    def read_dc_default(self, personality_guid: str, subgroup_guid: str, setting_guid: str) -> int | None:
        """Read default DC setting index for a personality."""
        if powrprof is None:
            return None

        c_pers = ctypes.byref(parse_guid(personality_guid))
        c_sub = ctypes.byref(parse_guid(subgroup_guid))
        c_set = ctypes.byref(parse_guid(setting_guid))
        val = wintypes.DWORD(0)

        rc = powrprof.PowerReadDCDefaultIndex(None, c_pers, c_sub, c_set, ctypes.byref(val))
        if rc == ERROR_SUCCESS:
            return val.value
        return None

    @staticmethod
    def infer_control_type(
        choices: list[SettingValueChoice],
        min_val: int | None,
        max_val: int | None,
    ) -> ControlType:
        """Infer UI ControlType from metadata."""
        if choices:
            return ControlType.ENUM
        if min_val == 0 and max_val == 1:
            return ControlType.TOGGLE
        if min_val is not None and max_val is not None and max_val > min_val:
            return ControlType.RANGE
        return ControlType.READONLY
