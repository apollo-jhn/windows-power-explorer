# Windows Power Explorer - AI Agent Instructions

## Tech Stack
- **Language:** Python 3.10+
- **GUI Framework:** `customtkinter` 6.0.0
- **System Interop:** `ctypes` (for `PowrProf.dll`, `kernel32.dll`) and `winreg`
- **Packaging:** PyInstaller

## Project Architecture & Data
- `main.py` is the entry point.
- `core/` contains Win32 bindings and business logic.
- `ui/` contains all `customtkinter` frontend components.
- `data/` contains UI metadata ONLY (e.g. `essentials.json`). Do not store actual power values here.

## Strict Boundaries & Rules
1. **No Network Access:** The application must remain strictly offline. Do not add telemetry, updaters, or network libraries.
2. **No Kernel Overclocking:** Only use standard Win32 Power Management APIs (`PowrProf.dll`).
3. **Registry Writes:** Use `winreg` strictly for visibility attributes (`Attributes = 2` to show, `1` to hide), which requires Administrator privileges.
4. **C-FFI:** Ensure all `ctypes` bindings handle memory ownership and buffer protocols properly. Comment C-FFI boundaries extensively.
5. **UI Thread:** Win32 I/O and enumerations must run on a background worker thread. Do not block the `customtkinter` main loop.

## Commands
- **Run:** `python main.py`
- **Test:** `pytest`
