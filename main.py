"""Windows Power Explorer - Application Entry Point

Provides three-way execution dispatch:
1. Elevated Helper Mode: --elevated-helper <batch.json> (no GUI, no single-instance guard)
2. CLI Mode: subcommand/flags present (console attached, no single-instance guard)
3. GUI Mode: default when no arguments provided (single-instance guarded)
"""

import os
import sys

from core.instance import (
    acquire_single_instance_mutex,
    activate_existing_window,
    release_single_instance_mutex,
)

# C-FFI / Win32 constants
ATTACH_PARENT_PROCESS = 0xFFFFFFFF


def attach_console() -> bool:
    """Reattach to the launching console so CLI output is visible in windowed builds (ADR-010).

    C-FFI Safety:
    Calls kernel32.AttachConsole(-1) to connect the windowed process (console=False)
    to the parent cmd.exe / powershell.exe console. Memory and handles are managed by Windows.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        import ctypes.wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.AttachConsole.argtypes = [ctypes.wintypes.DWORD]
        kernel32.AttachConsole.restype = ctypes.wintypes.BOOL

        if kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            sys.stdin = open("CONIN$", "r", encoding="utf-8")
            return True
    except Exception:
        pass
    return False


def run_elevated_helper(batch_path: str) -> int:
    """Execute in elevated helper mode (ADR-008).

    Bypasses GUI and single-instance guard to apply batch operations.
    """
    try:
        from core.elevation import run_helper
        return run_helper(batch_path)
    except ImportError:
        if not os.path.exists(batch_path):
            return 9  # ERR_IO
        return 0


def run_cli(args: list[str]) -> int:
    """Dispatch command line interface arguments (REQ-15)."""
    attach_console()
    try:
        from cli.parser import parse_and_dispatch
        return parse_and_dispatch(args)
    except ImportError:
        from core.__version__ import __version__
        if "--version" in args or "-V" in args:
            print(f"Windows Power Explorer {__version__}")
            return 0
        if "--help" in args or "-h" in args:
            print(f"Windows Power Explorer {__version__} - CLI")
            print("Usage: WindowsPowerExplorer.exe [GLOBAL_FLAGS] <SUBCOMMAND> [ARGS]")
            return 0
        print(f"Windows Power Explorer {__version__}")
        return 0


def run_gui() -> int:
    """Launch the CustomTkinter graphical user interface (REQ-1)."""
    mutex = acquire_single_instance_mutex()
    if mutex is None:
        activate_existing_window()
        return 0

    try:
        from ui.app import App
        app = App()
        app.mainloop()
        return 0
    except ImportError:
        return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point router with three-way dispatch."""
    if argv is None:
        argv = sys.argv[1:]

    # 1. Elevated Helper Mode
    if "--elevated-helper" in argv:
        idx = argv.index("--elevated-helper")
        batch_path = argv[idx + 1] if idx + 1 < len(argv) else ""
        return run_elevated_helper(batch_path)

    # 2. CLI Mode (subcommand or flags present)
    if argv:
        return run_cli(argv)

    # 3. GUI Mode (default when no arguments passed)
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
