"""Tests for core/controller.py (Threading Engine & Controller - Issue #16)."""

import queue
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from core.controller import (
    MSG_CATALOG,
    MSG_DONE,
    MSG_ERROR,
    MSG_PROGRESS,
    MSG_SCHEMES,
    MSG_VALUES,
    AppController,
    catalog_worker,
    schemes_worker,
    values_worker,
)
from core.models import (
    ControlType,
    PowerScheme,
    SchemeValues,
    SettingCatalog,
    SettingCatalogEntry,
    SubgroupCatalogEntry,
    ValueChange,
)
from core.power_manager import PowerManager
from core.state import AppState


class TestAppController(unittest.TestCase):

    def setUp(self):
        self.scheduled_jobs = []
        self.canceled_jobs = []

        def mock_scheduler(ms, callback):
            job_id = len(self.scheduled_jobs) + 1
            self.scheduled_jobs.append((job_id, ms, callback))
            return job_id

        def mock_canceler(job_id):
            self.canceled_jobs.append(job_id)

        self.mock_scheduler = mock_scheduler
        self.mock_canceler = mock_canceler
        self.mock_pm = MagicMock(spec=PowerManager)
        self.controller = AppController(
            state=AppState(),
            pm=self.mock_pm,
            scheduler=self.mock_scheduler,
            canceler=self.mock_canceler,
        )

    def test_start_worker_and_drain_loop_lifecycle(self):
        """Drain loop starts when first worker begins and stops when idle (NFR-2c)."""
        def dummy_worker(out, gen):
            out.put((gen, MSG_PROGRESS, 50))
            out.put((gen, MSG_DONE, None))

        self.assertEqual(self.controller.state.active_worker_count, 0)
        self.assertIsNone(self.controller._drain_job)

        thread = self.controller.start_worker(
            dummy_worker,
            self.controller.queue,
            self.controller.state.enumeration_generation,
        )
        thread.join(timeout=1.0)

        # Worker was active -> drain scheduled
        self.assertEqual(len(self.scheduled_jobs), 1)
        self.assertIsNotNone(self.controller._drain_job)

        # Execute drain
        self.controller.drain()

        # Work finished -> idle -> no scheduled callbacks
        self.assertEqual(self.controller.state.active_worker_count, 0)
        self.assertIsNone(self.controller._drain_job)

    def test_worker_cancellation_discards_stale_generation(self):
        """Messages with generation < current enumeration_generation are discarded."""
        old_gen = self.controller.state.enumeration_generation

        # Cancel workers and advance generation
        self.controller.cancel_current_workers()
        new_gen = self.controller.state.enumeration_generation
        self.assertGreater(new_gen, old_gen)

        # Put message from old generation
        self.controller.state.active_worker_count = 1
        self.controller.queue.put((old_gen, MSG_CATALOG, "stale catalog"))
        self.controller.queue.put((old_gen, MSG_DONE, None))

        # Drain
        self.controller.drain()

        # Stale catalog must not have been applied
        self.assertIsNone(self.controller.state.catalog)
        self.assertEqual(self.controller.state.active_worker_count, 0)

    def test_worker_exception_surfaces_as_message(self):
        """Worker exceptions are captured and delivered via queue as MSG_ERROR."""
        out = queue.Queue()
        cancel = threading.Event()

        with patch("core.controller.build_catalog", side_effect=RuntimeError("Win32 failure")):
            catalog_worker(self.mock_pm, 1, out, cancel)

        msg = out.get_nowait()
        gen, kind, payload = msg
        self.assertEqual(gen, 1)
        self.assertEqual(kind, MSG_ERROR)
        self.assertIsInstance(payload, RuntimeError)
        self.assertEqual(str(payload), "Win32 failure")

    def test_select_scheme_loads_values_and_clears_undo(self):
        """select_scheme updates selected_scheme_guid, clears undo, and launches worker."""
        set_entry = SettingCatalogEntry(
            guid="bc502fe6-701e-46c4-9826-5d42490a1e9c",
            subgroup_guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Max CPU",
            description="",
            control_type=ControlType.RANGE,
            min_value=0,
            max_value=100,
            value_increment=1,
            value_units="%",
            choices=(),
            is_hidden=False,
            is_policy_locked=False,
            is_degraded=False,
        )
        sub_entry = SubgroupCatalogEntry(
            guid="54533251-82be-4824-96c1-47b60b740d00",
            friendly_name="Processor",
            description="",
            is_hidden=False,
            settings=(set_entry,),
        )
        catalog = SettingCatalog(
            subgroups=(sub_entry,),
            by_guid={set_entry.guid.lower(): set_entry},
            subgroup_by_guid={sub_entry.guid.lower(): sub_entry},
        )
        self.controller.state.catalog = catalog
        self.controller.state.last_change = ValueChange("scheme", "sub", "set", "ac", 100, 80)

        target_scheme = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

        with patch("core.controller.load_scheme_values") as mock_load:
            mock_values = SchemeValues(
                scheme_guid=target_scheme,
                personality_guid="pers-1",
                ac={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 100},
                dc={"bc502fe6-701e-46c4-9826-5d42490a1e9c": 80},
                ac_default={},
                dc_default={},
            )
            mock_load.return_value = mock_values

            self.controller.select_scheme(target_scheme)

            # Undo buffer cleared
            self.assertIsNone(self.controller.state.last_change)
            self.assertEqual(self.controller.state.selected_scheme_guid, target_scheme)

            # Drain result from worker
            time.sleep(0.05)
            self.controller.drain()

            self.assertEqual(self.controller.state.values, mock_values)

    def test_write_setting_and_undo(self):
        """write_setting_value writes to PM, updates AppState, and undo() restores prior value."""
        scheme_guid = "381b4222-f694-41f0-9685-ff5bb260df2e"
        sub_guid = "54533251-82be-4824-96c1-47b60b740d00"
        set_guid = "bc502fe6-701e-46c4-9826-5d42490a1e9c"

        self.controller.state.active_scheme_guid = scheme_guid
        self.controller.state.selected_scheme_guid = scheme_guid
        self.controller.state.values = SchemeValues(
            scheme_guid=scheme_guid,
            personality_guid="pers",
            ac={set_guid: 100},
            dc={set_guid: 80},
            ac_default={},
            dc_default={},
        )

        self.mock_pm.read_ac_value.return_value = 85

        # 1. Write new value
        self.controller.write_setting_value(sub_guid, set_guid, 85, rail="ac")

        self.mock_pm.write_ac_value.assert_called_with(scheme_guid, sub_guid, set_guid, 85, None)
        self.assertEqual(self.controller.state.values.ac[set_guid], 85)
        self.assertIsNotNone(self.controller.state.last_change)
        self.assertEqual(self.controller.state.last_change.previous_value, 100)
        self.assertEqual(self.controller.state.last_change.new_value, 85)

        # 2. Undo
        self.mock_pm.read_ac_value.return_value = 100
        undone = self.controller.undo()
        self.assertTrue(undone)
        self.mock_pm.write_ac_value.assert_called_with(scheme_guid, sub_guid, set_guid, 100, None)
        self.assertIsNone(self.controller.state.last_change)

    def test_shutdown_cancels_worker_and_drain_job(self):
        """shutdown() cancels worker events and cancels scheduled drain job."""
        self.controller._drain_job = 42
        self.controller.shutdown()

        self.assertTrue(self.controller.cancel_event.is_set())
        self.assertIn(42, self.canceled_jobs)
        self.assertIsNone(self.controller._drain_job)


if __name__ == "__main__":
    unittest.main()
