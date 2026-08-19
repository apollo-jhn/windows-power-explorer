"""Tests for UI State Persistence and Geometry Clamping (Issue #18, ADR-005 amendment, ADR-014)."""

import json
from pathlib import Path
import tempfile
import unittest

from core.ui_state import (
    DEFAULT_UI_STATE,
    clamp_window_geometry,
    load_ui_state,
    save_ui_state,
)


class TestUiState(unittest.TestCase):

    def test_clamp_window_geometry_normal(self):
        """Geometry inside screen bounds remains unchanged."""
        cx, cy, cw, ch = clamp_window_geometry(100, 100, 1150, 720, 1920, 1080)
        self.assertEqual((cx, cy, cw, ch), (100, 100, 1150, 720))

    def test_clamp_window_geometry_offscreen_right_bottom(self):
        """Window positioned off-screen to the right/bottom is clamped inside screen."""
        cx, cy, cw, ch = clamp_window_geometry(2000, 1200, 1150, 720, 1920, 1080)
        # Clamped so x + width <= 1920 and y + height <= 1080
        self.assertEqual(cx, 1920 - 1150)
        self.assertEqual(cy, 1080 - 720)
        self.assertEqual(cw, 1150)
        self.assertEqual(ch, 720)

    def test_clamp_window_geometry_negative_coords(self):
        """Window with negative coordinates (disconnected monitor) clamped to 0,0."""
        cx, cy, cw, ch = clamp_window_geometry(-500, -200, 1150, 720, 1920, 1080)
        self.assertEqual(cx, 0)
        self.assertEqual(cy, 0)
        self.assertEqual(cw, 1150)
        self.assertEqual(ch, 720)

    def test_clamp_window_geometry_min_size_enforcement(self):
        """Window smaller than minimum size is clamped to min dimensions 920x600."""
        cx, cy, cw, ch = clamp_window_geometry(50, 50, 400, 300, 1920, 1080)
        self.assertEqual(cw, 920)
        self.assertEqual(ch, 600)

    def test_load_and_save_ui_state_roundtrip(self):
        """load_ui_state and save_ui_state correctly serialize and restore state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "ui-state.json"

            custom_state = {
                "version": 2,
                "window": {"width": 1200, "height": 800, "x": 150, "y": 120, "maximized": False},
                "appearance_mode": "Dark",
                "last_selected_scheme_guid": "guid-test-123",
                "last_selected_category": "favorites",
                "show_modified_only": True,
                "favorites": [["sub1", "set1"]],
                "last_visibility_batch_hash": None,
            }

            # Save
            success = save_ui_state(custom_state, custom_path=state_path)
            self.assertTrue(success)
            self.assertTrue(state_path.exists())

            # Load
            loaded = load_ui_state(custom_path=state_path)
            self.assertEqual(loaded["version"], 2)
            self.assertEqual(loaded["appearance_mode"], "Dark")
            self.assertEqual(loaded["window"]["width"], 1200)
            self.assertEqual(loaded["favorites"], [["sub1", "set1"]])

    def test_corrupt_json_fallback(self):
        """load_ui_state returns default state when encountering unparseable JSON."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "ui-state.json"
            with open(state_path, "w", encoding="utf-8") as f:
                f.write("{ INVALID JSON DATA")

            loaded = load_ui_state(custom_path=state_path)
            self.assertEqual(loaded["version"], DEFAULT_UI_STATE["version"])
            self.assertEqual(loaded["appearance_mode"], DEFAULT_UI_STATE["appearance_mode"])


if __name__ == "__main__":
    unittest.main()
