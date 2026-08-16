# Win32 C-FFI API Reference

* **Document Version:** 1.0.0
* **Target Stack:** Python 3.10+, `ctypes`
* **Related Documents:** [[Index]], [[Technical Design Document]], [[Data Flow and Configuration Schema]], [[Error Handling and Logging]], [[Architecture Decision Records]]

> [!IMPORTANT]
> This is the authoritative binding reference. Where any other document in this vault disagrees with the signatures, buffer protocols, or error semantics below, **this document wins**.

---

## 1. Loaded Libraries

```python
import ctypes
from ctypes import wintypes

powrprof = ctypes.WinDLL("powrprof.dll")
kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32.dll")
shell32  = ctypes.WinDLL("shell32.dll")
```

All power functions use the **`stdcall`** convention (`WinDLL`, not `CDLL`). Every binding MUST declare `argtypes` and `restype` explicitly — without them `ctypes` defaults to `int` returns and truncates 64-bit pointers on x64.

---

## 2. The `GUID` Structure

`Data4` MUST be `c_ubyte`, not `wintypes.BYTE`. `wintypes.BYTE` is a **signed** `c_byte`; any GUID byte `>= 0x80` becomes negative and `bytes(...)` raises `ValueError`. Roughly half of all real GUIDs contain such a byte.

```python
import uuid
import ctypes
from ctypes import wintypes


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),   # MUST be unsigned
    ]

    @classmethod
    def from_string(cls, guid_str: str) -> "GUID":
        """Parse a hyphenated GUID string into a C GUID struct.

        Uses uuid.bytes_le, whose layout is byte-identical to the Win32
        GUID struct: little-endian Data1/Data2/Data3 then 8 raw bytes.
        """
        raw = uuid.UUID(guid_str).bytes_le
        return cls.from_buffer_copy(raw)

    def to_string(self) -> str:
        """Render as a lowercase hyphenated GUID string."""
        return str(uuid.UUID(bytes_le=bytes(self)))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GUID):
            return NotImplemented
        return bytes(self) == bytes(other)

    def __hash__(self) -> int:
        return hash(bytes(self))


LPGUID = ctypes.POINTER(GUID)
PLPGUID = ctypes.POINTER(LPGUID)
```

> [!WARNING]
> Do **not** hand-assemble `Data4` from `uuid.UUID.fields`. The `fields` tuple is
> `(time_low, time_mid, time_hi_version, clock_seq_hi_variant, clock_seq_low, node)` —
> `fields[3]` and `fields[4]` are each a single byte, and `fields[5]` is the 48-bit node.
> Treating `fields[3]` as a 16-bit clock sequence produces silently wrong GUIDs that
> resolve to real-but-different power settings. `from_buffer_copy(bytes_le)` avoids the
> entire class of bug.

### 2.1 GUID Input Validation

Every GUID string crossing the CLI or JSON-import boundary MUST be validated before conversion. `uuid.UUID()` accepts braced, URN, and unhyphenated forms; we accept only the canonical hyphenated form so that log output and registry paths are unambiguous.

```python
import re

_GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def parse_guid(value: str) -> GUID:
    if not _GUID_RE.match(value):
        raise ValueError(f"Not a canonical GUID: {value!r}")
    return GUID.from_string(value)
```

---

## 3. `POWER_DATA_ACCESSOR` Enumeration

Values are positional from `0`. Only the members we call are named here; the full enum is in `powrprof.h`.

| Member | Value | Used By |
| :--- | ---: | :--- |
| `ACCESS_AC_POWER_SETTING_INDEX` | `0` | `PowerSettingAccessCheck` (AC group-policy override) |
| `ACCESS_DC_POWER_SETTING_INDEX` | `1` | `PowerSettingAccessCheck` (DC group-policy override) |
| `ACCESS_SCHEME` | `16` | `PowerEnumerate` — enumerate power schemes |
| `ACCESS_SUBGROUP` | `17` | `PowerEnumerate` — enumerate subgroups |
| `ACCESS_INDIVIDUAL_SETTING` | `18` | `PowerEnumerate` — enumerate settings in a subgroup |
| `ACCESS_ACTIVE_SCHEME` | `19` | `PowerSettingAccessCheck` (active-scheme override) |
| `ACCESS_CREATE_SCHEME` | `20` | `PowerSettingAccessCheck` (scheme-creation restriction) |

```python
ACCESS_AC_POWER_SETTING_INDEX = 0
ACCESS_DC_POWER_SETTING_INDEX = 1
ACCESS_SCHEME                 = 16
ACCESS_SUBGROUP               = 17
ACCESS_INDIVIDUAL_SETTING     = 18
ACCESS_ACTIVE_SCHEME          = 19
ACCESS_CREATE_SCHEME          = 20
```

---

## 4. Win32 Error Codes

| Constant | Value | Meaning in our context |
| :--- | ---: | :--- |
| `ERROR_SUCCESS` | `0` | Call succeeded. |
| `ERROR_FILE_NOT_FOUND` | `2` | Scheme or setting GUID does not exist. |
| `ERROR_ACCESS_DENIED` | `5` | Needs elevation, or a Group Policy override blocks the write. |
| `ERROR_INVALID_PARAMETER` | `87` | Bad GUID pointer, or value outside the setting's declared range. |
| `ERROR_MORE_DATA` | `234` | Buffer too small — retry with the size written back to `BufferSize`. |
| `ERROR_NO_MORE_ITEMS` | `259` | `PowerEnumerate` loop terminator. **Not an error.** |
| `ERROR_CANCELLED` | `1223` | User dismissed the UAC consent prompt. |

```python
ERROR_SUCCESS          = 0
ERROR_FILE_NOT_FOUND   = 2
ERROR_ACCESS_DENIED    = 5
ERROR_INVALID_PARAMETER = 87
ERROR_MORE_DATA        = 234
ERROR_NO_MORE_ITEMS    = 259
ERROR_CANCELLED        = 1223
```

---

## 5. The Buffer-Sizing Protocol

Most `PowerRead*` functions take `(UCHAR* Buffer, DWORD* BufferSize)` and are called twice: once with `Buffer = NULL` to learn the required size, then again with a right-sized buffer.

> [!CAUTION]
> **The undersized-buffer return value is not consistent across this API family.**
> `PowerReadFriendlyName` and `PowerReadDescription` return **`ERROR_SUCCESS`** when the
> buffer is too small, writing the required size into `BufferSize`. `PowerReadPossibleValue`,
> `PowerReadPossibleFriendlyName`, and `PowerEnumerate` return **`ERROR_MORE_DATA`**.
> Code that only checks for `ERROR_MORE_DATA` will silently accept a truncated string
> from the first group. Always treat "returned size > supplied size" as a retry signal,
> regardless of the return code.

```python
def read_sized_string(fn, *guid_args) -> str:
    """Two-call buffer protocol, safe against both return conventions."""
    size = wintypes.DWORD(0)
    fn(*guid_args, None, ctypes.byref(size))
    if size.value == 0:
        return ""

    buf = ctypes.create_string_buffer(size.value)
    rc = fn(*guid_args, ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)),
            ctypes.byref(size))
    if rc != ERROR_SUCCESS or size.value > ctypes.sizeof(buf):
        raise PowerApiError(fn.__name__, rc)

    # Buffers are UTF-16LE, NUL-terminated.
    return buf.raw[:size.value].decode("utf-16-le", errors="replace").rstrip("\x00")
```

All string buffers are **UTF-16LE** (`LPWSTR`), and the returned `BufferSize` is in **bytes**, not characters.

---

## 6. Function Bindings

### 6.1 Enumeration

```python
powrprof.PowerEnumerate.argtypes = [
    wintypes.HANDLE,                    # RootPowerKey — always None
    LPGUID,                             # SchemeGuid
    LPGUID,                             # SubGroupOfPowerSettingsGuid
    ctypes.c_int,                       # POWER_DATA_ACCESSOR AccessFlags
    wintypes.ULONG,                     # Index
    ctypes.POINTER(ctypes.c_ubyte),     # Buffer (UCHAR*, unsigned)
    ctypes.POINTER(wintypes.DWORD),     # BufferSize
]
powrprof.PowerEnumerate.restype = wintypes.DWORD
```

**Argument matrix** — which GUIDs are non-NULL depends entirely on `AccessFlags`:

| Goal | `AccessFlags` | `SchemeGuid` | `SubGroupGuid` |
| :--- | :--- | :--- | :--- |
| List all schemes | `ACCESS_SCHEME` | `NULL` | `NULL` |
| List subgroups in a scheme | `ACCESS_SUBGROUP` | scheme | `NULL` |
| List settings in a subgroup | `ACCESS_INDIVIDUAL_SETTING` | scheme | subgroup |

**Loop termination:** increment `Index` from `0` until the call returns `ERROR_NO_MORE_ITEMS` (`259`). Treat that as normal completion, never as a failure. Guard the loop with a sanity cap (e.g. 4096 iterations) so a driver-induced enumeration bug cannot hang a worker thread.

### 6.2 Active Scheme

```python
powrprof.PowerGetActiveScheme.argtypes = [wintypes.HANDLE, PLPGUID]
powrprof.PowerGetActiveScheme.restype  = wintypes.DWORD

powrprof.PowerSetActiveScheme.argtypes = [wintypes.HANDLE, LPGUID]
powrprof.PowerSetActiveScheme.restype  = wintypes.DWORD
```

`PowerGetActiveScheme` allocates the returned GUID with `LocalAlloc`. **The caller owns it and MUST release it with `LocalFree`.** See §7.

### 6.3 Scheme Lifecycle

```python
powrprof.PowerDuplicateScheme.argtypes = [wintypes.HANDLE, LPGUID, PLPGUID]
powrprof.PowerDuplicateScheme.restype  = wintypes.DWORD

powrprof.PowerDeleteScheme.argtypes = [wintypes.HANDLE, LPGUID]
powrprof.PowerDeleteScheme.restype  = wintypes.DWORD

powrprof.PowerImportPowerScheme.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, PLPGUID]
powrprof.PowerImportPowerScheme.restype  = wintypes.DWORD

powrprof.PowerRestoreDefaultPowerSchemes.argtypes = []
powrprof.PowerRestoreDefaultPowerSchemes.restype  = wintypes.DWORD
```

`PowerDuplicateScheme` also allocates its out-GUID via `LocalAlloc` — same ownership rule.

There is **no `PowerExportPowerScheme`**. `powrprof.dll` exports an importer but no exporter; `.pow` export exists only inside `powercfg.exe`. We therefore export our own JSON format built from API reads. See [[Architecture Decision Records]] ADR-007.

`PowerRestoreDefaultPowerSchemes` is **destructive** — it deletes every custom scheme on the machine and requires elevation. Its user-facing flow is specified in [[Recovery and Destructive Operations]].

### 6.4 Names and Descriptions

```python
_NAME_ARGS = [
    wintypes.HANDLE,                    # RootPowerKey
    LPGUID,                             # SchemeGuid
    LPGUID,                             # SubGroupOfPowerSettingsGuid
    LPGUID,                             # PowerSettingGuid
    ctypes.POINTER(ctypes.c_ubyte),     # Buffer
    ctypes.POINTER(wintypes.DWORD),     # BufferSize
]

powrprof.PowerReadFriendlyName.argtypes = _NAME_ARGS
powrprof.PowerReadFriendlyName.restype  = wintypes.DWORD

powrprof.PowerReadDescription.argtypes = _NAME_ARGS
powrprof.PowerReadDescription.restype  = wintypes.DWORD

# Write variants take BufferSize BY VALUE, not by pointer.
powrprof.PowerWriteFriendlyName.argtypes = [
    wintypes.HANDLE, LPGUID, LPGUID, LPGUID,
    ctypes.POINTER(ctypes.c_ubyte), wintypes.DWORD,
]
powrprof.PowerWriteFriendlyName.restype = wintypes.DWORD

powrprof.PowerWriteDescription.argtypes = powrprof.PowerWriteFriendlyName.argtypes
powrprof.PowerWriteDescription.restype  = wintypes.DWORD
```

**GUID selector rules** for the name/description family:

| Target | `SchemeGuid` | `SubGroupGuid` | `PowerSettingGuid` |
| :--- | :--- | :--- | :--- |
| Scheme name | scheme | `NULL` | `NULL` |
| Subgroup name | `NULL` | subgroup | `NULL` |
| Setting name | `NULL` | subgroup | setting |

**Writing names:** the buffer is UTF-16LE **including** its terminating NUL, and `BufferSize` is the byte count including that NUL.

```python
def encode_name(text: str) -> tuple:
    if "\x00" in text:
        raise ValueError("Embedded NUL in scheme name")
    raw = (text + "\x00").encode("utf-16-le")
    buf = ctypes.create_string_buffer(raw, len(raw))
    return ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)), wintypes.DWORD(len(raw)), buf
```

Keep a reference to `buf` alive for the duration of the call — returning only the cast pointer lets Python free the buffer before the DLL reads it.

### 6.5 AC / DC Value Access

```python
_READ_VALUE_ARGS = [
    wintypes.HANDLE, LPGUID, LPGUID, LPGUID,
    ctypes.POINTER(wintypes.DWORD),
]
powrprof.PowerReadACValueIndex.argtypes = _READ_VALUE_ARGS
powrprof.PowerReadACValueIndex.restype  = wintypes.DWORD
powrprof.PowerReadDCValueIndex.argtypes = _READ_VALUE_ARGS
powrprof.PowerReadDCValueIndex.restype  = wintypes.DWORD

_WRITE_VALUE_ARGS = [
    wintypes.HANDLE, LPGUID, LPGUID, LPGUID,
    wintypes.DWORD,
]
powrprof.PowerWriteACValueIndex.argtypes = _WRITE_VALUE_ARGS
powrprof.PowerWriteACValueIndex.restype  = wintypes.DWORD
powrprof.PowerWriteDCValueIndex.argtypes = _WRITE_VALUE_ARGS
powrprof.PowerWriteDCValueIndex.restype  = wintypes.DWORD
```

> [!IMPORTANT]
> **A write does not take effect until the scheme is re-applied — but only re-apply the *active* scheme.**
> `PowerSetActiveScheme(NULL, guid)` makes `guid` the system's active plan as a side effect.
> Calling it on the scheme the user happens to be *editing* silently switches their machine
> onto that plan. The correct commit sequence is:
>
> ```python
> pm.write_ac_value(scheme_guid, sub, setting, value)
> if scheme_guid == pm.get_active_scheme_guid():
>     pm.set_active_scheme(scheme_guid)   # refresh live policy only
> ```
>
> Edits to non-active schemes persist to the registry immediately and take effect the
> next time that scheme is activated. No refresh call is needed or wanted.

### 6.6 Value Bounds and Possible Values

```python
_BOUNDS_ARGS = [
    wintypes.HANDLE, LPGUID, LPGUID,        # RootPowerKey, SubGroup, Setting
    ctypes.POINTER(wintypes.DWORD),
]
for _fn in ("PowerReadValueMin", "PowerReadValueMax", "PowerReadValueIncrement"):
    getattr(powrprof, _fn).argtypes = _BOUNDS_ARGS
    getattr(powrprof, _fn).restype  = wintypes.DWORD

powrprof.PowerReadValueUnitsSpecifier.argtypes = [
    wintypes.HANDLE, LPGUID, LPGUID,
    ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(wintypes.DWORD),
]
powrprof.PowerReadValueUnitsSpecifier.restype = wintypes.DWORD

powrprof.PowerReadPossibleValue.argtypes = [
    wintypes.HANDLE, LPGUID, LPGUID,
    ctypes.POINTER(wintypes.ULONG),         # Type (REG_DWORD / REG_SZ ...)
    wintypes.ULONG,                         # PossibleSettingIndex
    ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(wintypes.DWORD),
]
powrprof.PowerReadPossibleValue.restype = wintypes.DWORD

powrprof.PowerReadPossibleFriendlyName.argtypes = [
    wintypes.HANDLE, LPGUID, LPGUID,
    wintypes.ULONG,                         # PossibleSettingIndex
    ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(wintypes.DWORD),
]
powrprof.PowerReadPossibleFriendlyName.restype = wintypes.DWORD
```

**Control-type inference.** These calls are how the UI decides which widget to render:

| Observation | Rendered control |
| :--- | :--- |
| `PowerReadPossibleValue(index=0)` succeeds | `CTkOptionMenu` — enumerate indices until `ERROR_FILE_NOT_FOUND` / `ERROR_NO_MORE_ITEMS` |
| No possible values, `min == 0` and `max == 1` | `CTkSwitch` |
| No possible values, `max > min` | `CTkSlider` with `number_of_steps = (max - min) // increment` |
| Bounds calls fail | Read-only `CTkLabel` showing the raw DWORD |

Guard against `increment == 0` before dividing — some OEM settings report it as zero.

### 6.7 Setting Attributes (Control Panel Visibility)

```python
# NOTE: returns the ATTRIBUTE VALUE, not an error code.
powrprof.PowerReadSettingAttributes.argtypes = [LPGUID, LPGUID]
powrprof.PowerReadSettingAttributes.restype  = wintypes.DWORD

powrprof.PowerWriteSettingAttributes.argtypes = [LPGUID, LPGUID, wintypes.DWORD]
powrprof.PowerWriteSettingAttributes.restype  = wintypes.DWORD
```

> [!CAUTION]
> **`PowerReadSettingAttributes` breaks the convention of every other function in this
> reference: its return value *is* the attribute bitmask, not a status code.** A return
> of `0` means "visible", not "success". There is no way to distinguish failure from a
> zero attribute value, so validate the GUIDs before calling.

**It also ORs in the subgroup's attributes.** Microsoft: *"The attribute is a combination of the attributes of the power setting and the attributes of its subgroup."* A visible setting inside a hidden subgroup still reads back as hidden. To genuinely reveal a setting you must clear the hide bit on **both** the setting and its parent subgroup (the latter by passing `PowerSettingGuid = NULL`).

**Attribute values:**

| Value | Constant | Effect |
| ---: | :--- | :--- |
| `0` | — | No attributes set. Documented as "visible" but see the warning below. |
| `1` | `POWER_ATTRIBUTE_HIDE` | Hidden from `powercfg.cpl`. The only value Microsoft documents. |
| `2` | *(undocumented)* | **Shown** in `powercfg.cpl`. This is what actually works. |

> [!WARNING]
> **Writing `0` does not reliably unhide a setting.** Microsoft documents only
> `POWER_ATTRIBUTE_HIDE = 1`, and `PowerWriteSettingAttributes` does not dependably
> persist a cleared attribute in a way `powercfg.cpl` honours. Every working unhide
> utility — and the Control Panel itself — keys off `Attributes = 2`.
>
> We therefore write the visibility attribute **directly to the registry** rather than
> through this API. See §8 and ADR-006. `PowerReadSettingAttributes` remains our *read*
> path, because it correctly folds in subgroup inheritance.

### 6.8 Group Policy and Permission Checks

```python
powrprof.PowerSettingAccessCheck.argtypes = [ctypes.c_int, LPGUID]
powrprof.PowerSettingAccessCheck.restype  = wintypes.DWORD
```

Returns `ERROR_SUCCESS` when the current user may modify the setting, and `ERROR_ACCESS_DENIED` when a Group Policy override or ACL blocks it.

Windows applies a single default ACL to all power policy objects granting **read, write, and change to Authenticated Users** — which is why scheme CRUD and AC/DC edits need no elevation. Group Policy can override any individual setting, though, and such settings must be rendered **disabled with an explanatory tooltip** rather than allowed to fail on write. Call this once per setting during enumeration and cache the result on the `PowerSetting` model.

### 6.9 Windows 11 Power Mode Overlays *(read-only)*

Windows 11's **Settings → System → Power & battery → Power mode** is a separate *overlay* layer applied on top of the active scheme. A user on "Best performance" sees behaviour that contradicts their chosen plan, which generates false "my settings don't apply" reports. We read and display the overlay; we never write it (ADR-009).

```python
# Undocumented. Exported by name from powrprof.dll on Windows 10 1809+ / 11.
# Resolve defensively — absence is not an error.
try:
    powrprof.PowerGetEffectiveOverlayScheme.argtypes = [LPGUID]
    powrprof.PowerGetEffectiveOverlayScheme.restype  = wintypes.DWORD
    _OVERLAY_SUPPORTED = True
except AttributeError:
    _OVERLAY_SUPPORTED = False
```

| Overlay GUID | Power mode |
| :--- | :--- |
| `961cc777-2547-4f9d-8174-7d86181b8a7a` | Best power efficiency |
| `00000000-0000-0000-0000-000000000000` | Balanced / recommended |
| `ded574b5-45a0-4f42-8737-46345c09c238` | Best performance |

Because these exports are undocumented, all overlay code MUST be wrapped so that a missing export, an unknown GUID, or a nonzero return degrades to hiding the overlay indicator — never to a crash or an error dialog.

### 6.10 Default Values — "Modified from Default" and Per-Setting Reset

```python
_DEFAULT_ARGS = [
    wintypes.HANDLE,        # RootPowerKey — always None
    LPGUID,                 # SchemePersonalityGuid  ← NOT a scheme GUID
    LPGUID,                 # SubGroupOfPowerSettingsGuid
    LPGUID,                 # PowerSettingGuid
    ctypes.POINTER(wintypes.DWORD),
]
powrprof.PowerReadACDefaultIndex.argtypes = _DEFAULT_ARGS
powrprof.PowerReadACDefaultIndex.restype  = wintypes.DWORD
powrprof.PowerReadDCDefaultIndex.argtypes = _DEFAULT_ARGS
powrprof.PowerReadDCDefaultIndex.restype  = wintypes.DWORD
```

> [!CAUTION]
> **The second parameter is a *personality*, not the scheme you are inspecting.**
> Passing a custom scheme's own GUID here is the obvious mistake and it returns wrong
> defaults or fails outright. Windows stores a different default per personality, and a
> custom scheme inherits whichever personality it carries.

**Correct sequence** for "is this setting modified from its default in scheme X?":

```python
GUID_POWERSCHEME_PERSONALITY = "245d8541-3943-4422-b025-13a784f679b7"

PERSONALITY_BY_INDEX = {
    0: "a1841308-3541-4fab-bc81-f71556f20b4a",  # GUID_MAX_POWER_SAVINGS (Power Saver)
    1: "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",  # GUID_MIN_POWER_SAVINGS (High Performance)
    2: "381b4222-f694-41f0-9685-ff5bb260df2e",  # GUID_TYPICAL_POWER_SAVINGS (Balanced)
}


def personality_of(scheme_guid: str) -> str:
    """A scheme's personality is itself a power setting in NO_SUBGROUP_GUID."""
    index = read_ac_value(scheme_guid, NO_SUBGROUP_GUID, GUID_POWERSCHEME_PERSONALITY)
    return PERSONALITY_BY_INDEX.get(index, PERSONALITY_BY_INDEX[2])   # default Balanced
```

Read the personality **once per scheme**, then read defaults for every setting against it. The personality GUIDs are numerically identical to the three base scheme GUIDs, which is a convenience of the Windows design, not a coincidence to rely on semantically — keep the two concepts distinct in code.

**Where defaults belong in the two-phase load** (ADR-012): defaults depend on personality, and personality depends on scheme. They therefore sit in the **value phase**, not the catalog phase — but they are cached per `(personality, subgroup, setting)`, so switching between two schemes sharing a personality reuses them at no cost.

`ERROR_FILE_NOT_FOUND` from these calls means the setting has no defined default. Treat it as "no default known", render no badge, and disable the per-setting reset control — never as an error.

### 6.11 Single-Instance Guard

Two instances writing power settings concurrently produce a UI that lies about OS state.

```python
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype  = wintypes.HANDLE

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\WindowsPowerExplorer.SingleInstance"


def acquire_single_instance() -> wintypes.HANDLE | None:
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return None          # Another instance owns it.
    return handle
```

Use the `Local\` prefix, not `Global\`: the guard is per-session, so Fast User Switching and Remote Desktop sessions each get their own instance, which is correct. A `Global\` mutex would wrongly block a second user entirely.

The handle is held for the process lifetime and released implicitly on exit. When the mutex is already held, the new process brings the existing window forward (`SetForegroundWindow` on the window found by class name) and exits `0` — it does not show an error.

**Helper mode and CLI subcommands skip this guard entirely.** They are short-lived, non-interactive, and must remain scriptable in parallel.

---

## 7. Memory Ownership

Three `powrprof` functions allocate memory the caller must free:

| Function | Allocated out-parameter |
| :--- | :--- |
| `PowerGetActiveScheme` | `GUID **ActivePolicyGuid` |
| `PowerDuplicateScheme` | `GUID **DestinationSchemeGuid` |
| `PowerImportPowerScheme` | `GUID **DestinationSchemeGuid` |

```python
kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
kernel32.LocalFree.restype  = wintypes.HLOCAL

from contextlib import contextmanager

@contextmanager
def out_guid():
    """Yield a GUID** whose allocation is always LocalFree'd."""
    ptr = LPGUID()
    try:
        yield ctypes.byref(ptr)
    finally:
        if ptr:
            kernel32.LocalFree(ctypes.cast(ptr, wintypes.HLOCAL))
```

Copy the GUID's *value* out (`GUID.from_buffer_copy(ptr.contents)`) before the context exits. Retaining `ptr.contents` past the `LocalFree` yields a use-after-free that surfaces as sporadic wrong-GUID reads rather than a clean crash.

Buffers **we** allocate (`create_string_buffer`) are owned by Python and must never be passed to `LocalFree`.

---

## 8. Direct Registry Access

Two operations bypass `powrprof` and use `winreg` directly.

### 8.1 Visibility Attributes *(requires elevation)*

```text
HKLM\SYSTEM\CurrentControlSet\Control\Power\PowerSettings
└── {SubGroup_GUID}
    ├── Attributes          REG_DWORD   ← subgroup visibility
    └── {Setting_GUID}
        └── Attributes      REG_DWORD   ← 1 = hidden, 2 = shown
```

This tree is **global and scheme-independent**. Unhiding a setting reveals it for every power plan on the machine. Bare GUID keys have no `Attributes` value at all until one is written, and `Attributes` is reset to defaults by feature updates — the app should re-read state on launch rather than caching it.

To reveal a setting, write `2` to **both** the setting key and its parent subgroup key. To re-hide, write `1` to the setting key only (leave the subgroup revealed, or you hide unrelated siblings).

### 8.2 Per-Scheme Configured Values *(read-only, diagnostics)*

```text
HKLM\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes
└── {Scheme_GUID}
    ├── FriendlyName         REG_SZ / REG_EXPAND_SZ
    ├── Description          REG_SZ
    └── {SubGroup_GUID}
        └── {Setting_GUID}
            ├── ACSettingIndex   REG_DWORD
            └── DCSettingIndex   REG_DWORD
```

Note there is **no `Attributes` value under this tree** — visibility is not per-scheme. We read this tree only for `--verbose` diagnostics; all writes go through the `PowerWrite*ValueIndex` APIs so that Windows performs its own validation and policy refresh.

`FriendlyName` on built-in schemes is frequently an indirect string reference (`@%SystemRoot%\system32\powrprof.dll,-1`). Do not parse it — use `PowerReadFriendlyName`, which resolves and localizes it for you.

---

## 9. Elevation

Only §8.1 registry writes require Administrator. Everything else runs as Standard User. Rather than relaunching the whole GUI elevated, we spawn a short-lived elevated helper that applies a batch of visibility changes and exits (ADR-008).

```python
class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize",       wintypes.DWORD),
        ("fMask",        ctypes.c_ulong),
        ("hwnd",         wintypes.HWND),
        ("lpVerb",       wintypes.LPCWSTR),
        ("lpFile",       wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory",  wintypes.LPCWSTR),
        ("nShow",        ctypes.c_int),
        ("hInstApp",     wintypes.HINSTANCE),
        ("lpIDList",     ctypes.c_void_p),
        ("lpClass",      wintypes.LPCWSTR),
        ("hkeyClass",    wintypes.HKEY),
        ("dwHotKey",     wintypes.DWORD),
        ("hIcon",        wintypes.HANDLE),
        ("hProcess",     wintypes.HANDLE),
    ]

shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
shell32.ShellExecuteExW.restype  = wintypes.BOOL

SEE_MASK_NOCLOSEPROCESS = 0x00000040
SEE_MASK_NO_CONSOLE     = 0x00008000
```

`ShellExecuteExW` is used in preference to `ShellExecuteW` because `SEE_MASK_NOCLOSEPROCESS` yields an `hProcess` we can wait on and whose exit code reports whether the batch succeeded. `ShellExecuteW` gives no such feedback, leaving the UI unable to tell success from a declined prompt.

**Elevation check** (there is no supported "am I admin" API; the registry probe below is the reliable form):

```python
def is_elevated() -> bool:
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False
```

**Argument construction rules.** The helper receives a **path to a JSON batch file**, never a caller-composed command string:

* `lpFile` is always `sys.executable`, resolved with `os.path.realpath`.
* `lpParameters` contains only our own module flag plus one quoted temp-file path that we generated.
* No user-supplied string — scheme name, description, search text — is ever interpolated into `lpParameters`.
* The batch file is written to a per-user temp directory with a randomised name and deleted after the helper exits.

A `False` return with `GetLastError() == ERROR_CANCELLED (1223)` means the user declined the UAC prompt. That is a normal outcome: revert the toggle and show a neutral status message, never an error dialog.

---

## 10. Well-Known GUIDs

### 10.1 Base Schemes

| Scheme | GUID |
| :--- | :--- |
| Balanced | `381b4222-f694-41f0-9685-ff5bb260df2e` |
| High Performance | `8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c` |
| Power Saver | `a1841308-3541-4fab-bc81-f71556f20b4a` |
| Ultimate Performance | `e9a42b02-d5df-448d-aa00-03f14749eb61` |

> [!WARNING]
> **Never assume these exist.** On Modern Standby machines Windows exposes only *Balanced*
> and hides or omits the others entirely; *Ultimate Performance* is absent until someone
> duplicates it. Populate the "clone from" dropdown from a live `PowerEnumerate(ACCESS_SCHEME)`
> pass, match against this table for display names and ordering, and omit absent entries
> rather than offering a clone that will fail with `ERROR_FILE_NOT_FOUND`.

### 10.2 Subgroups

| Subgroup | GUID |
| :--- | :--- |
| `NO_SUBGROUP_GUID` | `fea3413e-7e05-4911-9a71-700331f1c294` |
| `GUID_DISK_SUBGROUP` | `0012ee47-9041-4b5d-9b77-535fba8b1442` |
| `GUID_SYSTEM_BUTTON_SUBGROUP` | `4f971e89-eebd-4455-a8de-9e59040e7347` |
| `GUID_PROCESSOR_SETTINGS_SUBGROUP` | `54533251-82be-4824-96c1-47b60b740d00` |
| `GUID_VIDEO_SUBGROUP` | `7516b95f-f776-4464-8c53-06167f40cc99` |
| `GUID_BATTERY_SUBGROUP` | `e73a048d-bf27-4f12-9731-8b2076e8891f` |
| `GUID_SLEEP_SUBGROUP` | `238c9fa8-0aad-41ed-83f4-97be242c8f20` |
| `GUID_PCIEXPRESS_SETTINGS_SUBGROUP` | `501a4d13-42af-4429-9fd1-a8218c268e20` |

Subgroups beyond this list exist and vary by hardware and OEM. Enumerate rather than hardcode; this table only supplies our category icons and sort order.

### 10.3 The Power Plan Personality Trap

| Setting | GUID | Subgroup |
| :--- | :--- | :--- |
| Power plan personality (`GUID_POWERSCHEME_PERSONALITY`) | `245d8541-3943-4422-b025-13a784f679b7` | `NO_SUBGROUP_GUID` |

Its three legal values are themselves GUID-identified personalities, used as the second argument to the default-index reads in §6.10:

| Value | Constant | Personality | GUID |
| ---: | :--- | :--- | :--- |
| `0` | `GUID_MAX_POWER_SAVINGS` | Power Saver | `a1841308-3541-4fab-bc81-f71556f20b4a` |
| `1` | `GUID_MIN_POWER_SAVINGS` | High Performance | `8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c` |
| `2` | `GUID_TYPICAL_POWER_SAVINGS` | Balanced | `381b4222-f694-41f0-9685-ff5bb260df2e` |

> [!IMPORTANT]
> This single value **takes precedence over individual settings**. A scheme cloned from
> *Balanced* whose every processor value is copied from *High Performance* will still
> behave like Balanced until its personality changes. Values: `0` = Power Saver,
> `1` = High Performance, `2` = Balanced.
>
> The clone dialog MUST set the personality to match the chosen base template, and this
> setting deserves a prominent, plain-language card rather than being buried among the
> other hundred. See [[Product Requirements Document]] REQ-1.4.

### 10.4 Scheme-Independent vs Per-Scheme Reads

The split that drives the two-phase load in ADR-012. Note how few reads actually vary by scheme:

| Read | Scheme parameter? | Phase |
| :--- | :--- | :--- |
| `PowerEnumerate(ACCESS_SUBGROUP / ACCESS_INDIVIDUAL_SETTING)` | Accepts one, but the setting tree is identical across schemes | Catalog |
| `PowerReadFriendlyName` / `PowerReadDescription` *(setting-level)* | Passed `NULL` | Catalog |
| `PowerReadValueMin` / `Max` / `Increment` / `UnitsSpecifier` | **No scheme parameter exists** | Catalog |
| `PowerReadPossibleValue` / `PossibleFriendlyName` / `PossibleDescription` | **No scheme parameter exists** | Catalog |
| `PowerReadSettingAttributes` | **No scheme parameter exists** | Catalog |
| `PowerSettingAccessCheck` | **No scheme parameter exists** | Catalog |
| `PowerReadACValueIndex` / `PowerReadDCValueIndex` | **Yes** | Value |
| `PowerReadACDefaultIndex` / `PowerReadDCDefaultIndex` | Personality-keyed, derived from the scheme | Value *(cached per personality)* |

Six of eight read families are scheme-invariant. Re-running them on every scheme switch — as the v1.0.0 design did — repeats roughly 75% of the enumeration cost for data that cannot have changed.

---

## 11. Binding Verification

Because a wrong `argtypes` declaration fails silently rather than loudly, the binding module MUST self-verify at import in debug builds:

* Every name we bind is present on the DLL (`hasattr`), with a clear startup error naming any that is missing.
* Round-trip `GUID.from_string(s).to_string() == s` across a fixture of GUIDs including bytes above `0x7F`.
* A live read-only `PowerGetActiveScheme` call returns `ERROR_SUCCESS` and a GUID matching an enumerated scheme.

These are the Level 2 integration tests in [[Test Plan and Benchmark Targets]] §2.2.
