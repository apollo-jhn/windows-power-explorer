"""Win32 C-FFI API bindings for PowrProf.dll, Kernel32.dll, and Shell32.dll.

Authoritative binding reference per docs/Win32 API Reference.md.
All bindings use stdcall convention (WinDLL) and explicit argtypes/restype.
"""

import ctypes
import re
import sys
import uuid
from contextlib import contextmanager
from ctypes import wintypes

from core.errors import PowerApiError

# ============================================================================
# 1. Constants
# ============================================================================

# POWER_DATA_ACCESSOR Access Flags
ACCESS_AC_POWER_SETTING_INDEX = 0
ACCESS_DC_POWER_SETTING_INDEX = 1
ACCESS_SCHEME = 16
ACCESS_SUBGROUP = 17
ACCESS_INDIVIDUAL_SETTING = 18
ACCESS_ACTIVE_SCHEME = 19
ACCESS_CREATE_SCHEME = 20

# Win32 Error Codes
ERROR_SUCCESS = 0
ERROR_FILE_NOT_FOUND = 2
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_DATA = 13
ERROR_INVALID_PARAMETER = 87
ERROR_ALREADY_EXISTS = 183
ERROR_MORE_DATA = 234
ERROR_NO_MORE_ITEMS = 259
ERROR_CANCELLED = 1223

# Setting Attributes
POWER_ATTRIBUTE_HIDE = 1
POWER_ATTRIBUTE_SHOW = 2

# ShellExecuteEx Flags
SEE_MASK_NOCLOSEPROCESS = 0x00000040
SEE_MASK_NO_CONSOLE = 0x00008000

# Well-Known GUID Strings
NO_SUBGROUP_GUID = "fea3413e-7e05-4911-9a71-700331f1c294"
GUID_POWERSCHEME_PERSONALITY = "245d8541-3943-4422-b025-13a784f679b7"

# Base Scheme & Personality GUIDs
GUID_MAX_POWER_SAVINGS = "a1841308-3541-4fab-bc81-f71556f20b4a"      # Power Saver (0)
GUID_MIN_POWER_SAVINGS = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"      # High Performance (1)
GUID_TYPICAL_POWER_SAVINGS = "381b4222-f694-41f0-9685-ff5bb260df2e"  # Balanced (2)
GUID_ULTIMATE_PERFORMANCE = "e9a42b02-d5df-448d-aa00-03f14749eb61"   # Ultimate Performance

BASE_SCHEMES = {
    GUID_TYPICAL_POWER_SAVINGS: "Balanced",
    GUID_MIN_POWER_SAVINGS: "High Performance",
    GUID_MAX_POWER_SAVINGS: "Power Saver",
    GUID_ULTIMATE_PERFORMANCE: "Ultimate Performance",
}

PERSONALITY_BY_INDEX = {
    0: GUID_MAX_POWER_SAVINGS,
    1: GUID_MIN_POWER_SAVINGS,
    2: GUID_TYPICAL_POWER_SAVINGS,
}

INDEX_BY_PERSONALITY = {v: k for k, v in PERSONALITY_BY_INDEX.items()}

# Windows 11 Power Mode Overlays
OVERLAY_GUID_EFFICIENCY = "961cc777-2547-4f9d-8174-7d86181b8a7a"
OVERLAY_GUID_BALANCED = "00000000-0000-0000-0000-000000000000"
OVERLAY_GUID_PERFORMANCE = "ded574b5-45a0-4f42-8737-46345c09c238"

OVERLAY_NAMES = {
    OVERLAY_GUID_EFFICIENCY: "Best power efficiency",
    OVERLAY_GUID_BALANCED: "Balanced",
    OVERLAY_GUID_PERFORMANCE: "Best performance",
}

# ============================================================================
# 2. GUID Structure & Helpers
# ============================================================================

_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class GUID(ctypes.Structure):
    """Win32 GUID structure.

    C-FFI Safety:
    Data4 MUST be c_ubyte * 8 (unsigned). Using signed c_byte causes bytes()
    to fail with ValueError on any byte >= 0x80 (ADR-001 consequence).
    """

    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),  # MUST be unsigned c_ubyte
    ]

    @classmethod
    def from_string(cls, guid_str: str) -> "GUID":
        """Parse a canonical GUID string into a C GUID struct using uuid.bytes_le."""
        raw = uuid.UUID(guid_str).bytes_le
        return cls.from_buffer_copy(raw)

    def to_string(self) -> str:
        """Convert the C GUID struct to a canonical lowercase hyphenated string."""
        return str(uuid.UUID(bytes_le=bytes(self)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GUID):
            return NotImplemented
        return bytes(self) == bytes(other)

    def __hash__(self) -> int:
        return hash(bytes(self))

    def __repr__(self) -> str:
        return f"GUID('{self.to_string()}')"


LPGUID = ctypes.POINTER(GUID)
PLPGUID = ctypes.POINTER(LPGUID)


def parse_guid(value: str) -> GUID:
    """Validate canonical hyphenated format and parse into a GUID struct."""
    if not isinstance(value, str) or not _GUID_RE.match(value):
        raise ValueError(f"Not a canonical GUID: {value!r}")
    return GUID.from_string(value)


# ============================================================================
# 3. Memory & Buffer Protocols
# ============================================================================


class SHELLEXECUTEINFOW(ctypes.Structure):
    """ShellExecuteExW parameter structure."""

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


@contextmanager
def out_guid():
    """Context manager yielding a pointer to LPGUID whose allocation is freed via LocalFree.

    C-FFI Safety:
    Guarantees kernel32.LocalFree is called on success, error, or exception path.
    The caller must copy out the GUID's value before the context manager exits.
    """
    ptr = LPGUID()
    try:
        yield ctypes.byref(ptr)
    finally:
        if ptr:
            if kernel32 is not None:
                kernel32.LocalFree(ctypes.cast(ptr, wintypes.HLOCAL))


def read_sized_string(fn, *guid_args) -> str:
    """Two-call buffer protocol helper safe against both ERROR_SUCCESS and ERROR_MORE_DATA.

    C-FFI Safety:
    Handles functions that return ERROR_SUCCESS or ERROR_MORE_DATA when the buffer is
    undersized, retrying with the size returned in BufferSize.
    """
    size = wintypes.DWORD(0)
    # First call with Buffer = None to probe required size in bytes
    fn(*guid_args, None, ctypes.byref(size))
    if size.value == 0:
        return ""

    buf = ctypes.create_string_buffer(size.value)
    rc = fn(
        *guid_args,
        ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)),
        ctypes.byref(size),
    )
    if rc != ERROR_SUCCESS or size.value > ctypes.sizeof(buf):
        raise PowerApiError(getattr(fn, "__name__", str(fn)), rc)

    # Windows power string buffers are UTF-16LE, NUL-terminated
    return buf.raw[: size.value].decode("utf-16-le", errors="replace").rstrip("\x00")


def encode_name(text: str) -> tuple[ctypes.c_void_p, wintypes.DWORD, ctypes.Array]:
    """Encode a Python string to UTF-16LE with terminating NUL for Win32 API.

    Returns (pointer, byte_length_with_nul, buffer_handle).
    Keep the returned buffer_handle alive for the duration of the C call.
    """
    if "\x00" in text:
        raise ValueError("Embedded NUL in string")
    raw = (text + "\x00").encode("utf-16-le")
    buf = ctypes.create_string_buffer(raw, len(raw))
    ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte))
    return ptr, wintypes.DWORD(len(raw)), buf


# ============================================================================
# 4. Win32 Dynamic Library Bindings
# ============================================================================

powrprof = None
kernel32 = None
advapi32 = None
shell32 = None
_OVERLAY_SUPPORTED = False

if sys.platform == "win32":
    powrprof = ctypes.WinDLL("powrprof.dll")
    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32.dll")
    shell32 = ctypes.WinDLL("shell32.dll")

    # --- Kernel32 / Memory / Synchronization ---
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE

    # --- Shell32 ---
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL

    shell32.IsUserAnAdmin.argtypes = []
    shell32.IsUserAnAdmin.restype = wintypes.BOOL

    # --- PowrProf: Enumeration ---
    powrprof.PowerEnumerate.argtypes = [
        wintypes.HANDLE,                 # RootPowerKey (always None)
        LPGUID,                          # SchemeGuid
        LPGUID,                          # SubGroupOfPowerSettingsGuid
        ctypes.c_int,                    # POWER_DATA_ACCESSOR AccessFlags
        wintypes.ULONG,                  # Index
        ctypes.POINTER(ctypes.c_ubyte),  # Buffer (UCHAR*)
        ctypes.POINTER(wintypes.DWORD),  # BufferSize
    ]
    powrprof.PowerEnumerate.restype = wintypes.DWORD

    # --- PowrProf: Active Scheme ---
    powrprof.PowerGetActiveScheme.argtypes = [wintypes.HANDLE, PLPGUID]
    powrprof.PowerGetActiveScheme.restype = wintypes.DWORD

    powrprof.PowerSetActiveScheme.argtypes = [wintypes.HANDLE, LPGUID]
    powrprof.PowerSetActiveScheme.restype = wintypes.DWORD

    # --- PowrProf: Scheme Lifecycle ---
    powrprof.PowerDuplicateScheme.argtypes = [wintypes.HANDLE, LPGUID, PLPGUID]
    powrprof.PowerDuplicateScheme.restype = wintypes.DWORD

    powrprof.PowerDeleteScheme.argtypes = [wintypes.HANDLE, LPGUID]
    powrprof.PowerDeleteScheme.restype = wintypes.DWORD

    powrprof.PowerImportPowerScheme.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, PLPGUID]
    powrprof.PowerImportPowerScheme.restype = wintypes.DWORD

    powrprof.PowerRestoreDefaultPowerSchemes.argtypes = []
    powrprof.PowerRestoreDefaultPowerSchemes.restype = wintypes.DWORD

    # --- PowrProf: Names & Descriptions ---
    _NAME_ARGS = [
        wintypes.HANDLE,                 # RootPowerKey
        LPGUID,                          # SchemeGuid
        LPGUID,                          # SubGroupOfPowerSettingsGuid
        LPGUID,                          # PowerSettingGuid
        ctypes.POINTER(ctypes.c_ubyte),  # Buffer
        ctypes.POINTER(wintypes.DWORD),  # BufferSize
    ]
    powrprof.PowerReadFriendlyName.argtypes = _NAME_ARGS
    powrprof.PowerReadFriendlyName.restype = wintypes.DWORD

    powrprof.PowerReadDescription.argtypes = _NAME_ARGS
    powrprof.PowerReadDescription.restype = wintypes.DWORD

    powrprof.PowerWriteFriendlyName.argtypes = [
        wintypes.HANDLE,
        LPGUID,
        LPGUID,
        LPGUID,
        ctypes.POINTER(ctypes.c_ubyte),
        wintypes.DWORD,  # By value
    ]
    powrprof.PowerWriteFriendlyName.restype = wintypes.DWORD

    powrprof.PowerWriteDescription.argtypes = powrprof.PowerWriteFriendlyName.argtypes
    powrprof.PowerWriteDescription.restype = wintypes.DWORD

    # --- PowrProf: AC / DC Values ---
    _READ_VALUE_ARGS = [
        wintypes.HANDLE,
        LPGUID,
        LPGUID,
        LPGUID,
        ctypes.POINTER(wintypes.DWORD),
    ]
    powrprof.PowerReadACValueIndex.argtypes = _READ_VALUE_ARGS
    powrprof.PowerReadACValueIndex.restype = wintypes.DWORD

    powrprof.PowerReadDCValueIndex.argtypes = _READ_VALUE_ARGS
    powrprof.PowerReadDCValueIndex.restype = wintypes.DWORD

    _WRITE_VALUE_ARGS = [
        wintypes.HANDLE,
        LPGUID,
        LPGUID,
        LPGUID,
        wintypes.DWORD,
    ]
    powrprof.PowerWriteACValueIndex.argtypes = _WRITE_VALUE_ARGS
    powrprof.PowerWriteACValueIndex.restype = wintypes.DWORD

    powrprof.PowerWriteDCValueIndex.argtypes = _WRITE_VALUE_ARGS
    powrprof.PowerWriteDCValueIndex.restype = wintypes.DWORD

    # --- PowrProf: Bounds & Possible Values ---
    _BOUNDS_ARGS = [
        wintypes.HANDLE,
        LPGUID,
        LPGUID,
        ctypes.POINTER(wintypes.DWORD),
    ]
    powrprof.PowerReadValueMin.argtypes = _BOUNDS_ARGS
    powrprof.PowerReadValueMin.restype = wintypes.DWORD

    powrprof.PowerReadValueMax.argtypes = _BOUNDS_ARGS
    powrprof.PowerReadValueMax.restype = wintypes.DWORD

    powrprof.PowerReadValueIncrement.argtypes = _BOUNDS_ARGS
    powrprof.PowerReadValueIncrement.restype = wintypes.DWORD

    powrprof.PowerReadValueUnitsSpecifier.argtypes = [
        wintypes.HANDLE,
        LPGUID,
        LPGUID,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.POINTER(wintypes.DWORD),
    ]
    powrprof.PowerReadValueUnitsSpecifier.restype = wintypes.DWORD

    powrprof.PowerReadPossibleValue.argtypes = [
        wintypes.HANDLE,
        LPGUID,
        LPGUID,
        ctypes.POINTER(wintypes.ULONG),  # Type
        wintypes.ULONG,                  # PossibleSettingIndex
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.POINTER(wintypes.DWORD),
    ]
    powrprof.PowerReadPossibleValue.restype = wintypes.DWORD

    powrprof.PowerReadPossibleFriendlyName.argtypes = [
        wintypes.HANDLE,
        LPGUID,
        LPGUID,
        wintypes.ULONG,                  # PossibleSettingIndex
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.POINTER(wintypes.DWORD),
    ]
    powrprof.PowerReadPossibleFriendlyName.restype = wintypes.DWORD

    # --- PowrProf: Setting Attributes ---
    powrprof.PowerReadSettingAttributes.argtypes = [LPGUID, LPGUID]
    powrprof.PowerReadSettingAttributes.restype = wintypes.DWORD

    powrprof.PowerWriteSettingAttributes.argtypes = [LPGUID, LPGUID, wintypes.DWORD]
    powrprof.PowerWriteSettingAttributes.restype = wintypes.DWORD

    # --- PowrProf: Group Policy Check ---
    powrprof.PowerSettingAccessCheck.argtypes = [ctypes.c_int, LPGUID]
    powrprof.PowerSettingAccessCheck.restype = wintypes.DWORD

    # --- PowrProf: Defaults ---
    _DEFAULT_ARGS = [
        wintypes.HANDLE,                 # RootPowerKey (None)
        LPGUID,                          # SchemePersonalityGuid
        LPGUID,                          # SubGroupGuid
        LPGUID,                          # SettingGuid
        ctypes.POINTER(wintypes.DWORD),
    ]
    powrprof.PowerReadACDefaultIndex.argtypes = _DEFAULT_ARGS
    powrprof.PowerReadACDefaultIndex.restype = wintypes.DWORD

    powrprof.PowerReadDCDefaultIndex.argtypes = _DEFAULT_ARGS
    powrprof.PowerReadDCDefaultIndex.restype = wintypes.DWORD

    # --- PowrProf: Overlays (Undocumented, defensive) ---
    try:
        powrprof.PowerGetEffectiveOverlayScheme.argtypes = [LPGUID]
        powrprof.PowerGetEffectiveOverlayScheme.restype = wintypes.DWORD
        _OVERLAY_SUPPORTED = True
    except AttributeError:
        _OVERLAY_SUPPORTED = False


def is_overlay_supported() -> bool:
    """Return True if PowerGetEffectiveOverlayScheme export is present."""
    return _OVERLAY_SUPPORTED


def is_elevated() -> bool:
    """Return True if current process has Administrator token."""
    if sys.platform != "win32" or shell32 is None:
        return False
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def verify_bindings() -> bool:
    """Verify that all required Win32 DLL functions resolve properly."""
    if sys.platform != "win32":
        return True

    required_powrprof = [
        "PowerEnumerate",
        "PowerGetActiveScheme",
        "PowerSetActiveScheme",
        "PowerDuplicateScheme",
        "PowerDeleteScheme",
        "PowerImportPowerScheme",
        "PowerRestoreDefaultPowerSchemes",
        "PowerReadFriendlyName",
        "PowerReadDescription",
        "PowerWriteFriendlyName",
        "PowerWriteDescription",
        "PowerReadACValueIndex",
        "PowerReadDCValueIndex",
        "PowerWriteACValueIndex",
        "PowerWriteDCValueIndex",
        "PowerReadValueMin",
        "PowerReadValueMax",
        "PowerReadValueIncrement",
        "PowerReadValueUnitsSpecifier",
        "PowerReadPossibleValue",
        "PowerReadPossibleFriendlyName",
        "PowerReadSettingAttributes",
        "PowerWriteSettingAttributes",
        "PowerSettingAccessCheck",
        "PowerReadACDefaultIndex",
        "PowerReadDCDefaultIndex",
    ]

    for name in required_powrprof:
        if not hasattr(powrprof, name):
            raise RuntimeError(f"Missing required export in powrprof.dll: {name}")

    # Self-test GUID round-trip
    test_guid = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
    if GUID.from_string(test_guid).to_string() != test_guid:
        raise RuntimeError("GUID roundtrip verification failed")

    return True
