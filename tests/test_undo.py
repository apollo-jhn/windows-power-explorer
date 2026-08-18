"""Tests for Single-Level Undo (Issue #27, REQ-11.1, REQ-11.2)."""

import unittest
from unittest.mock import MagicMock, patch

from core.controller import AppController
from core.models import PowerScheme, SchemeValues, ValueChange
from core.power_manager import PowerManager
from core.state import AppState


class TestUndo(unittest.TestCase):

    def setUp(self):
        self.mock_pm = MagicMock(spec=PowerManager)
        self.scheme_guid = "381b4222-f694-41f0-9685-ff5bb260df2e"
        self.sub_guid = "54533251-82be-4824-96c1-47b60b740d00"
        self.set_guid = "bc502fe6-701e-46c4-9826-5d42490a1e9c"

        self.state = AppState(
            schemes=[
                PowerScheme(self.scheme_guid, "Balanced", "", True, True, [])
            ],
            active_scheme_guid=self.scheme_guid,
            selected_scheme_guid=self.scheme_guid,
            values=SchemeValues(
                scheme_guid=self.scheme_guid,
                personality_guid="pers",
                ac={self.set_guid: 100},
                dc={self.set_guid: 80},
                ac_default={},
                dc_default={},
            ),
        )
        self.controller = AppController(state=self.state, pm=self.mock_pm)

    def test_undo_restores_previous_value(self):
        """Writing a value records it in AppState.last_change; undo() restores it (REQ-11.1)."""
        self.mock_pm.read_ac_value.return_value = 85

        # 1. Modify value
        self.controller.write_setting_value(self.sub_guid, self.set_guid, 85, rail="ac")
        self.assertIsNotNone(self.state.last_change)
        self.assertEqual(self.state.last_change.previous_value, 100)
        self.assertEqual(self.state.last_change.new_value, 85)

        # 2. Undo
        self.mock_pm.read_ac_value.return_value = 100
        result = self.controller.undo()

        self.assertTrue(result)
        self.mock_pm.write_ac_value.assert_called_with(self.scheme_guid, self.sub_guid, self.set_guid, 100, None)
        self.assertIsNone(self.state.last_change)

        # 3. Subsequent undo returns False (single level only)
        self.assertFalse(self.controller.undo())

    def test_undo_cleared_on_scheme_switch(self):
        """Undo buffer is invalidated on scheme switch, refresh, or import (REQ-11.2)."""
        self.state.last_change = ValueChange(
            scheme_guid=self.scheme_guid,
            subgroup_guid=self.sub_guid,
            setting_guid=self.set_guid,
            rail="ac",
            previous_value=100,
            new_value=85,
        )

        with patch("core.controller.values_worker"):
            self.controller.select_scheme("other-scheme-guid")
            self.assertIsNone(self.state.last_change)


if __name__ == "__main__":
    unittest.main()
