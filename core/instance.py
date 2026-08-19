"""Single-Instance Guard for Windows Power Explorer (REQ-14, Issue #30).

Ensures only a single GUI instance runs per user session.
A second GUI launch activates the existing window and exits 0 (REQ-14.1).
Uses a session-scoped Local\\ named mutex (REQ-14.2).
CLI subcommands and elevated helper bypass the guard (REQ-14.3).
"""

import sys
from typing import Any

# Win32 Constants
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
MUTEX_NAME = r"Local\WindowsPowerExplorer.SingleInstance"
WINDOW_TITLE_PREFIX = "Windows Power Explorer"


def acquire_single_instance_mutex() -> Any | None:
    """Acquire the session-scoped single-instance named mutex.

    C-FFI Safety:
    Calls kernel32.CreateMutexW with Local\\ prefix for session isolation (REQ-14.2).
    Returns the handle if acquired, or None if another instance already holds it.
    The handle should be retained for the process lifetime and released on exit.
    """
    if sys.platform != "win32":
        return True

    try:
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.wintypes.BOOL,
            ctypes.wintypes.LPCWSTR,
        ]
        kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE

        # Create or open mutex with initial ownership
        handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        if not handle:
            return None

        # Check if mutex already existed prior to this call
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return None

        return handle
    except Exception:
        # Graceful fallback if ctypes or API fails
        return True


def activate_existing_window(title_prefix: str = WINDOW_TITLE_PREFIX) -> bool:
    """Bring the existing application window to the foreground when a second instance launches.

    C-FFI Safety:
    Uses user32.FindWindowW and user32.SetForegroundWindow to focus the running GUI (REQ-14.1).
    Returns True if an existing window was found and brought to foreground.
    """
    if sys.platform != "win32":
        return False

    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32
        user32.FindWindowW.argtypes = [ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR]
        user32.FindWindowW.restype = ctypes.wintypes.HWND

        user32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
        user32.SetForegroundWindow.restype = ctypes.wintypes.BOOL

        user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = ctypes.wintypes.BOOL

        # Find window with exact or prefix title
        hwnd = user32.FindWindowW(None, title_prefix)
        if hwnd:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            return True

        # Fallback: enumerate top-level windows if title contains prefix
        found_hwnd = ctypes.wintypes.HWND(0)
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

        def enum_cb(h: int, _: int) -> bool:
            nonlocal found_hwnd
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                if buf.value.startswith(title_prefix):
                    found_hwnd = h
                    return False  # stop enumeration
            return True

        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        if found_hwnd:
            user32.ShowWindow(found_hwnd, SW_RESTORE)
            user32.SetForegroundWindow(found_hwnd)
            return True

    except Exception:
        pass

    return False


def release_single_instance_mutex(handle: Any) -> None:
    """Safely release and close the single-instance mutex handle."""
    if sys.platform != "win32" or handle is None or isinstance(handle, bool):
        return

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.CloseHandle(handle)
    except Exception:
        pass
