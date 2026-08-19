"""UI State Persistence and Window Geometry Clamping (ADR-005 amendment, ADR-014, REQ-13.1, REQ-13.3).

Persists UI preferences, window geometry, selected scheme, and favorites to ui-state.json.
Contains NO power data (ADR-005). Read defensively with silent fallback to defaults.
"""

import json
import os
from pathlib import Path
import sys
from typing import Any

DEFAULT_UI_STATE: dict[str, Any] = {
    "version": 2,
    "window": {
        "width": 1150,
        "height": 720,
        "x": 100,
        "y": 100,
        "maximized": False,
    },
    "appearance_mode": "System",
    "last_selected_scheme_guid": None,
    "last_selected_category": "all",
    "show_modified_only": False,
    "favorites": [],
    "last_visibility_batch_hash": None,
}


def get_data_directory() -> Path:
    """Resolve data directory considering portable mode (ADR-014, REQ-13.3, REQ-13.4)."""
    # Check for portable.txt beside executable or main script
    base_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    portable_sentinel = base_dir / "portable.txt"

    if portable_sentinel.exists():
        portable_data_dir = base_dir / "data"
        try:
            portable_data_dir.mkdir(parents=True, exist_ok=True)
            # Test writability
            test_file = portable_data_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            return portable_data_dir
        except Exception:
            # Fall back silently to %LOCALAPPDATA% if portable dir is read-only (REQ-13.4)
            pass

    # Standard Windows LocalAppData location
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        app_dir = Path(local_app_data) / "WindowsPowerExplorer"
    else:
        app_dir = Path.home() / ".windows_power_explorer"

    try:
        app_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return app_dir


def get_ui_state_path() -> Path:
    """Return path to ui-state.json."""
    return get_data_directory() / "ui-state.json"


def load_ui_state(custom_path: Path | None = None) -> dict[str, Any]:
    """Read ui-state.json defensively, falling back to defaults on any error."""
    path = custom_path or get_ui_state_path()
    if not path.exists():
        return dict(DEFAULT_UI_STATE)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict) or data.get("version") != 2:
            return dict(DEFAULT_UI_STATE)

        # Merge with defaults for missing keys
        merged = dict(DEFAULT_UI_STATE)
        merged.update(data)
        if isinstance(data.get("window"), dict):
            win = dict(DEFAULT_UI_STATE["window"])
            win.update(data["window"])
            merged["window"] = win

        return merged
    except Exception:
        return dict(DEFAULT_UI_STATE)


def save_ui_state(state: dict[str, Any], custom_path: Path | None = None) -> bool:
    """Safely persist UI state to disk."""
    path = custom_path or get_ui_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        tmp_path.replace(path)
        return True
    except Exception:
        return False


def clamp_window_geometry(
    x: int,
    y: int,
    width: int,
    height: int,
    screen_w: int,
    screen_h: int,
    min_w: int = 920,
    min_h: int = 600,
) -> tuple[int, int, int, int]:
    """Clamp window position and dimensions to visible display bounds.

    Guarantees the window is visible and meets minimum size constraints.
    """
    width = max(min_w, min(width, screen_w))
    height = max(min_h, min(height, screen_h))

    max_x = max(0, screen_w - width)
    max_y = max(0, screen_h - height)

    clamped_x = max(0, min(x, max_x))
    clamped_y = max(0, min(y, max_y))

    return clamped_x, clamped_y, width, height
