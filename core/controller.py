"""Threading Engine and Application Controller (Issue #16).

Implements AppController with worker thread lifecycle, queue.Queue communication,
enumeration cancellation, and idle drain loop lifecycle (TDD §5, ADR-003).
"""

import logging
import queue
import threading
from typing import Any, Callable

from core.catalog import build_catalog
from core.errors import PowerExplorerError
from core.models import (
    EnumStats,
    PowerScheme,
    PowerSetting,
    PowerSubgroup,
    SchemeValues,
    SettingCatalog,
    ValueChange,
)
from core.power_manager import PowerManager
from core.state import AppState
from core.values import load_scheme_values

logger = logging.getLogger(__name__)

# Message type constants for queue communication
MSG_SUBGROUP = "subgroup"
MSG_DONE = "done"
MSG_ERROR = "error"
MSG_PROGRESS = "progress"
MSG_CATALOG = "catalog"
MSG_VALUES = "values"
MSG_SCHEMES = "schemes"


def catalog_worker(
    pm: PowerManager,
    generation: int,
    out: queue.Queue,
    cancel: threading.Event,
) -> None:
    """Background worker to build the Phase 1 scheme-invariant catalog.

    Runs off-thread. Touches no Tk objects. Catches all exceptions and posts messages.
    """
    try:
        if cancel.is_set():
            return
        catalog = build_catalog(pm)
        if cancel.is_set():
            return
        out.put((generation, MSG_CATALOG, catalog))
        out.put((generation, MSG_DONE, None))
    except Exception as exc:  # Deliberately broad per TDD §5.2
        logger.exception("Catalog enumeration worker failed")
        out.put((generation, MSG_ERROR, exc))


def values_worker(
    pm: PowerManager,
    scheme_guid: str,
    catalog: SettingCatalog,
    default_cache: dict,
    generation: int,
    out: queue.Queue,
    cancel: threading.Event,
) -> None:
    """Background worker to load Phase 2 per-scheme values.

    Runs off-thread. Touches no Tk objects.
    """
    try:
        if cancel.is_set():
            return
        values = load_scheme_values(scheme_guid, catalog, pm, default_cache)
        if cancel.is_set():
            return
        out.put((generation, MSG_VALUES, values))
        out.put((generation, MSG_DONE, None))
    except Exception as exc:  # Deliberately broad per TDD §5.2
        logger.exception("Values load worker failed")
        out.put((generation, MSG_ERROR, exc))


def schemes_worker(
    pm: PowerManager,
    generation: int,
    out: queue.Queue,
    cancel: threading.Event,
) -> None:
    """Background worker to discover all available power schemes."""
    try:
        if cancel.is_set():
            return
        schemes_data = list(pm.iter_schemes())
        if cancel.is_set():
            return
        out.put((generation, MSG_SCHEMES, schemes_data))
        out.put((generation, MSG_DONE, None))
    except Exception as exc:
        logger.exception("Schemes discovery worker failed")
        out.put((generation, MSG_ERROR, exc))


class AppController:
    """Central application controller orchestrating worker threads and state."""

    def __init__(
        self,
        state: AppState | None = None,
        pm: PowerManager | None = None,
        scheduler: Callable[[int, Callable], Any] | None = None,
        canceler: Callable[[Any], None] | None = None,
    ) -> None:
        self.state = state or AppState()
        self.pm = pm or PowerManager()
        self.queue: queue.Queue = queue.Queue()
        self.cancel_event: threading.Event = threading.Event()
        self._drain_job: Any = None
        self._scheduler = scheduler
        self._canceler = canceler
        self.default_cache: dict[tuple[str, str, str], tuple[int | None, int | None]] = {}
        self.listeners: list[Callable[[str, Any], None]] = []

    def add_listener(self, listener: Callable[[str, Any], None]) -> None:
        """Register a callback for controller/state events."""
        if listener not in self.listeners:
            self.listeners.append(listener)

    def remove_listener(self, listener: Callable[[str, Any], None]) -> None:
        """Unregister a callback."""
        if listener in self.listeners:
            self.listeners.remove(listener)

    def _notify(self, event_name: str, data: Any = None) -> None:
        """Notify all registered listeners on the main thread."""
        for listener in self.listeners:
            try:
                listener(event_name, data)
            except Exception:
                logger.exception(f"Error in controller listener for event: {event_name}")

    def start_worker(self, target: Callable, *args: Any) -> threading.Thread:
        """Launch a worker thread and manage drain loop lifecycle (TDD §5.5)."""
        self.state.active_worker_count += 1
        thread = threading.Thread(target=target, args=args, daemon=True)
        thread.start()

        if self.state.active_worker_count == 1:
            self._schedule_drain()

        return thread

    def _schedule_drain(self) -> None:
        """Schedule drain poller on the main thread."""
        if self._scheduler is not None:
            self._drain_job = self._scheduler(50, self.drain)

    def drain(self) -> None:
        """Drain incoming worker messages on the main thread.

        Stops scheduling when active_worker_count drops to 0 (0% idle CPU).
        """
        finished = 0
        try:
            while True:
                msg = self.queue.get_nowait()
                gen, kind, payload = msg

                # Discard messages from superseded generations
                if gen == self.state.enumeration_generation:
                    if kind in (MSG_DONE, MSG_ERROR):
                        finished += 1
                    self.handle_message(kind, payload)
                else:
                    if kind in (MSG_DONE, MSG_ERROR):
                        finished += 1
        except queue.Empty:
            pass

        self.state.active_worker_count = max(0, self.state.active_worker_count - finished)
        if self.state.active_worker_count > 0:
            self._schedule_drain()
        else:
            self._drain_job = None  # Idle: no scheduled callbacks

    def handle_message(self, kind: str, payload: Any) -> None:
        """Handle unpacked queue message on the main thread."""
        if kind == MSG_CATALOG:
            self.state.catalog = payload
            self._notify("catalog_loaded", payload)

        elif kind == MSG_VALUES:
            self.state.values = payload
            self._notify("values_loaded", payload)

        elif kind == MSG_SCHEMES:
            schemes_list = []
            for s_guid, name, desc, is_active, is_base in payload:
                schemes_list.append(
                    PowerScheme(
                        guid=s_guid,
                        friendly_name=name,
                        description=desc,
                        is_active=is_active,
                        is_base_default=is_base,
                    )
                )
                if is_active:
                    self.state.active_scheme_guid = s_guid
                    if not self.state.selected_scheme_guid:
                        self.state.selected_scheme_guid = s_guid
            self.state.schemes = schemes_list
            self._notify("schemes_loaded", schemes_list)

        elif kind == MSG_PROGRESS:
            self._notify("progress", payload)

        elif kind == MSG_DONE:
            self._notify("worker_done", payload)

        elif kind == MSG_ERROR:
            logger.error(f"Worker reported error: {payload}")
            self._notify("worker_error", payload)

    def cancel_current_workers(self) -> None:
        """Signal cancellation to all active workers and advance generation."""
        self.cancel_event.set()
        self.state.enumeration_generation += 1
        self.cancel_event = threading.Event()

    def load_initial_data(self) -> None:
        """Begin full startup data load (schemes + catalog + active values)."""
        self.cancel_current_workers()
        gen = self.state.enumeration_generation

        # 1. Discover schemes
        self.start_worker(schemes_worker, self.pm, gen, self.queue, self.cancel_event)

        # 2. Build catalog
        self.start_worker(catalog_worker, self.pm, gen, self.queue, self.cancel_event)

    def select_scheme(self, scheme_guid: str) -> None:
        """Switch scheme selection and load per-scheme values asynchronously."""
        if self.state.selected_scheme_guid == scheme_guid and self.state.values is not None:
            return

        self.cancel_current_workers()
        self.state.selected_scheme_guid = scheme_guid
        self.state.clear_undo()
        gen = self.state.enumeration_generation

        if self.state.catalog:
            self.start_worker(
                values_worker,
                self.pm,
                scheme_guid,
                self.state.catalog,
                self.default_cache,
                gen,
                self.queue,
                self.cancel_event,
            )
        self._notify("scheme_selected", scheme_guid)

    def refresh(self, full: bool = False) -> None:
        """Refresh power state.

        If full=True (Ctrl+R), invalidates and rebuilds the Phase 1 catalog.
        Otherwise re-reads Phase 2 values for the current scheme.
        """
        self.cancel_current_workers()
        self.state.clear_undo()
        gen = self.state.enumeration_generation

        if full or not self.state.catalog:
            self.start_worker(catalog_worker, self.pm, gen, self.queue, self.cancel_event)
        else:
            target_scheme = self.state.selected_scheme_guid or self.state.active_scheme_guid
            if target_scheme and self.state.catalog:
                self.start_worker(
                    values_worker,
                    self.pm,
                    target_scheme,
                    self.state.catalog,
                    self.default_cache,
                    gen,
                    self.queue,
                    self.cancel_event,
                )

    def write_setting_value(
        self,
        subgroup_guid: str,
        setting_guid: str,
        value: int,
        rail: str = "ac",
    ) -> None:
        """Write setting value inline on the main thread and re-read from OS (TDD §5.4)."""
        target_scheme = self.state.selected_scheme_guid or self.state.active_scheme_guid
        if not target_scheme:
            raise PowerExplorerError("No active or selected scheme to write to")

        # Capture old value for single-level undo
        old_val = None
        if self.state.values:
            key = setting_guid.lower()
            old_val = (
                self.state.values.ac.get(key)
                if rail == "ac"
                else self.state.values.dc.get(key)
            )

        # Look up bounds if catalog available
        bounds = None
        if self.state.catalog and setting_guid.lower() in self.state.catalog.by_guid:
            entry = self.state.catalog.by_guid[setting_guid.lower()]
            bounds = (entry.min_value, entry.max_value)

        # Perform Win32 write
        if rail == "ac":
            self.pm.write_ac_value(target_scheme, subgroup_guid, setting_guid, value, bounds)
            actual_val = self.pm.read_ac_value(target_scheme, subgroup_guid, setting_guid)
            if self.state.values:
                self.state.values.ac[setting_guid.lower()] = actual_val
        else:
            self.pm.write_dc_value(target_scheme, subgroup_guid, setting_guid, value, bounds)
            actual_val = self.pm.read_dc_value(target_scheme, subgroup_guid, setting_guid)
            if self.state.values:
                self.state.values.dc[setting_guid.lower()] = actual_val

        # Record undo
        if old_val is not None and old_val != value:
            self.state.last_change = ValueChange(
                scheme_guid=target_scheme,
                subgroup_guid=subgroup_guid,
                setting_guid=setting_guid,
                rail=rail,
                previous_value=old_val,
                new_value=value,
            )

        self._notify("value_changed", (setting_guid, rail, actual_val))

    def reset_setting_value(
        self,
        subgroup_guid: str,
        setting_guid: str,
        rail: str = "both",
    ) -> bool:
        """Reset a setting to its personality default (REQ-9.3).

        rail may be 'ac', 'dc', or 'both'. Returns True if at least one rail was reset.
        """
        target_scheme = self.state.selected_scheme_guid or self.state.active_scheme_guid
        if not target_scheme:
            return False

        personality = self.pm.personality_of(target_scheme)
        key = setting_guid.lower()
        reset_any = False

        if rail in ("ac", "both"):
            ac_def = (
                self.state.values.ac_default.get(key)
                if self.state.values
                else None
            )
            if ac_def is None:
                ac_def = self.pm.read_ac_default(personality, subgroup_guid, setting_guid)
            if ac_def is not None:
                self.write_setting_value(subgroup_guid, setting_guid, ac_def, rail="ac")
                reset_any = True

        if rail in ("dc", "both") and self.state.has_battery:
            dc_def = (
                self.state.values.dc_default.get(key)
                if self.state.values
                else None
            )
            if dc_def is None:
                dc_def = self.pm.read_dc_default(personality, subgroup_guid, setting_guid)
            if dc_def is not None:
                self.write_setting_value(subgroup_guid, setting_guid, dc_def, rail="dc")
                reset_any = True

        return reset_any

    def apply_setting_to_custom_schemes(
        self,
        subgroup_guid: str,
        setting_guid: str,
        ac_val: int | None = None,
        dc_val: int | None = None,
    ) -> list[str]:
        """Apply a setting value across all custom (non-built-in) schemes (REQ-11.4).

        Returns list of updated scheme GUIDs.
        """
        bounds = None
        if self.state.catalog and setting_guid.lower() in self.state.catalog.by_guid:
            entry = self.state.catalog.by_guid[setting_guid.lower()]
            bounds = (entry.min_value, entry.max_value)

        updated_schemes = []
        for s in self.state.schemes:
            if s.is_base_default:
                continue
            try:
                if ac_val is not None:
                    self.pm.write_ac_value(s.guid, subgroup_guid, setting_guid, ac_val, bounds)
                if dc_val is not None and self.state.has_battery:
                    self.pm.write_dc_value(s.guid, subgroup_guid, setting_guid, dc_val, bounds)
                updated_schemes.append(s.guid)
            except Exception as exc:
                logger.warning(f"Failed bulk applying setting to scheme {s.guid}: {exc}")

        # Update currently loaded values if the selected scheme is among them
        if self.state.values and self.state.selected_scheme_guid in updated_schemes:
            key = setting_guid.lower()
            if ac_val is not None:
                self.state.values.ac[key] = ac_val
            if dc_val is not None:
                self.state.values.dc[key] = dc_val

        return updated_schemes

    def undo(self) -> bool:
        """Restore the single previous setting value (REQ-11.1)."""
        change = self.state.last_change
        if not change:
            return False

        self.write_setting_value(
            subgroup_guid=change.subgroup_guid,
            setting_guid=change.setting_guid,
            value=change.previous_value,
            rail=change.rail,
        )
        self.state.clear_undo()
        return True

    def shutdown(self) -> None:
        """Cancel in-flight workers and pending drain jobs on exit."""
        self.cancel_event.set()
        if self._drain_job is not None and self._canceler is not None:
            self._canceler(self._drain_job)
            self._drain_job = None
