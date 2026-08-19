"""Main Graphical User Interface Shell (customtkinter) for Windows Power Explorer (Issue #18, REQ-1, TDD §9).

Orchestrates:
- 2-Column responsive split layout (Sidebar + Content + Header + Footer)
- Complete TDD §9 startup sequence with early Win32 binding verification
- Geometry persistence and off-screen clamping via ui-state.json
- Three-mode appearance system (Light / Dark / System)
- In-house dialogs: CreateSchemeDialog, ExportDialog, ElevationDialog, ConfirmDialog, CommandPalette
- Live debounced search and progressive catalog rendering
- Single-level undo (Ctrl+Z) and full keyboard shortcuts (CLI and UX spec §1.4)
"""

import logging
import os
from pathlib import Path
import sys
import tkinter as tk
from typing import Any

import customtkinter as ctk

from core.controller import AppController
from core.models import SettingCatalogEntry
from core.presentational_data import (
    load_doc_links,
    load_essentials_guids,
    load_reboot_required,
)
from core.ui_state import (
    clamp_window_geometry,
    get_data_directory,
    load_ui_state,
    save_ui_state,
)
from core.win32_bindings import verify_bindings
from ui.components.setting_card import SettingCardWidget
from ui.dialogs.base import ConfirmDialog, show_startup_error
from ui.dialogs.command_palette import CommandPalette
from ui.dialogs.create_scheme_dialog import CreateSchemeDialog
from ui.dialogs.elevation_dialog import ElevationDialog
from ui.dialogs.export_dialog import ExportDialog
from ui.search_bar import SearchBar
from ui.sidebar import SidebarNav
from ui.status_bar import StatusBar
from ui.theme import (
    COLOR_APP_BG,
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_SURFACE_CARD,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_BODY,
    FONT_SUBTITLE,
    apply_appearance_mode,
)

logger = logging.getLogger(__name__)


class PowerExplorerApp(ctk.CTk):
    """Main Application Window implementing the full UI lifecycle."""

    def __init__(self, controller: AppController | None = None) -> None:
        # 1. Early Win32 binding verification (TDD §9 step 4)
        if not verify_bindings():
            show_startup_error(
                "Windows Power Explorer - Startup Error",
                "Failed to initialize Win32 Power Management APIs (PowrProf.dll / Kernel32.dll).\n"
                "Please verify that this application is running on Windows 10/11 with valid system privileges.",
            )
            sys.exit(1)

        super().__init__()

        # 2. Read ui-state.json and configure appearance mode (TDD §9 steps 5 & 6)
        self.ui_state = load_ui_state()
        app_mode = self.ui_state.get("appearance_mode", "System")
        apply_appearance_mode(app_mode)

        # 3. Setup window properties, title, min size, and clamped geometry
        self.title("Windows Power Explorer")
        self.minsize(920, 600)
        self.configure(fg_color=COLOR_APP_BG)
        self._apply_initial_geometry()

        # 4. Initialize Controller with GUI schedulers
        self.controller = controller or AppController(
            scheduler=self.after,
            canceler=self.after_cancel,
        )
        self.controller.add_listener(self._on_controller_event)

        # Restore preferences from ui_state into controller state
        if self.ui_state.get("favorites"):
            self.controller.state.favorites = {
                (pair[0], pair[1]) for pair in self.ui_state["favorites"] if len(pair) == 2
            }
        if self.ui_state.get("last_selected_category"):
            self.controller.state.selected_category = self.ui_state["last_selected_category"]
        if self.ui_state.get("show_modified_only"):
            self.controller.state.show_modified_only = bool(self.ui_state["show_modified_only"])

        # Load presentational metadata (safely degraded if missing)
        self.essentials_guids = load_essentials_guids()
        self.reboot_guids = load_reboot_required()
        self.doc_links = load_doc_links()

        self._active_palette: CommandPalette | None = None

        # 5. Build Shell Layout and Bind Shortcuts
        self._build_shell()
        self._bind_shortcuts()

        # 6. Read initial inline context and trigger worker startup (TDD §9 steps 8 & 9)
        self._init_inline_context()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self.controller.load_initial_data)

    def _apply_initial_geometry(self) -> None:
        """Apply window geometry from saved state with display bounds clamping."""
        win_info = self.ui_state.get("window", {})
        w = win_info.get("width", 1150)
        h = win_info.get("height", 720)
        x = win_info.get("x", 100)
        y = win_info.get("y", 100)
        is_max = win_info.get("maximized", False)

        try:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            cx, cy, cw, ch = clamp_window_geometry(x, y, w, h, screen_w, screen_h)
            self.geometry(f"{cw}x{ch}+{cx}+{cy}")
            if is_max:
                self.after(100, lambda: self.state("zoomed"))
        except Exception:
            self.geometry(f"{w}x{h}")

    def _init_inline_context(self) -> None:
        """Read cheap system context inline (active scheme, overlay, battery presence)."""
        try:
            active_guid = self.controller.pm.get_active_scheme_guid()
            if active_guid:
                self.controller.state.active_scheme_guid = active_guid
                if not self.controller.state.selected_scheme_guid:
                    saved_scheme = self.ui_state.get("last_selected_scheme_guid")
                    self.controller.state.selected_scheme_guid = saved_scheme or active_guid

            self.controller.state.overlay = self.controller.pm.get_overlay()
            self.controller.state.has_battery = self.controller.pm.has_battery()
        except Exception as exc:
            logger.warning(f"Failed reading inline context: {exc}")

    def _build_shell(self) -> None:
        """Construct top-level layout grid."""
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # 1. Header (Search & Actions)
        self.search_bar = SearchBar(
            self,
            on_query_changed=self._on_search_query,
            on_modified_toggle=self._on_modified_toggle,
            on_create_scheme=self._open_create_scheme,
        )
        self.search_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        if self.controller.state.show_modified_only:
            self.search_bar.mod_switch.select()

        # 2. Sidebar Navigation (Left column)
        self.sidebar = SidebarNav(
            self,
            controller=self.controller,
            on_scheme_selected=self._on_scheme_selected,
            on_category_selected=self._on_category_selected,
            on_open_compare=self._open_compare,
            on_open_visibility=self._open_visibility,
            on_restore_defaults=self._open_restore_defaults,
            on_delete_scheme=self._on_delete_scheme,
        )
        self.sidebar.grid(row=1, column=0, sticky="nsew")

        # 3. Main Content Container (Right column)
        self.content_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
        )
        self.content_frame.grid(row=1, column=1, sticky="nsew", padx=16, pady=12)
        self.content_frame.grid_columnconfigure(0, weight=1)

        # Show initial loading indicator before enumeration finishes (TDD §9)
        self._show_loading_indicator()

        # 4. Status Bar (Footer)
        self.status_bar = StatusBar(self, controller=self.controller)
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")

    def _show_loading_indicator(self) -> None:
        """Render immediate loading placeholder."""
        for child in self.content_frame.winfo_children():
            child.destroy()

        loading_box = ctk.CTkFrame(self.content_frame, fg_color=COLOR_SURFACE_CARD, corner_radius=8)
        loading_box.pack(fill="x", pady=40, padx=20)

        ctk.CTkLabel(
            loading_box,
            text="⚡ Discovering Windows Power Settings...",
            font=FONT_SUBTITLE,
            text_color=COLOR_PRIMARY,
        ).pack(pady=(24, 6))

        ctk.CTkLabel(
            loading_box,
            text="Building scheme catalog and reading live values from OS...",
            font=FONT_BODY,
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(pady=(0, 24))

    def _bind_shortcuts(self) -> None:
        """Register global keyboard shortcuts (CLI and UX spec §1.4)."""
        self.bind("<Control-f>", lambda _: self.search_bar.focus())
        self.bind("<Control-k>", lambda _: self._open_command_palette())
        self.bind("<Control-n>", lambda _: self._open_create_scheme())
        self.bind("<Control-e>", lambda _: self._open_export())
        self.bind("<Control-d>", lambda _: self._open_compare())
        self.bind("<Control-z>", lambda _: self._undo())
        self.bind("<Control-r>", lambda _: self._refresh())
        self.bind("<Control-m>", lambda _: self._toggle_modified())
        self.bind("<Escape>", lambda _: self.search_bar.clear())
        self.bind("<F1>", lambda _: self._open_log_folder())

    def _on_controller_event(self, event_name: str, payload: Any) -> None:
        """Handle notifications from AppController on the main thread."""
        if event_name in ("catalog_loaded", "values_loaded", "schemes_loaded", "scheme_selected", "value_changed", "scheme_created", "scheme_deleted"):
            self.sidebar.refresh()
            self.status_bar.refresh()
            self._render_setting_cards()

        elif event_name == "worker_done":
            self.status_bar.set_status("Ready", is_busy=False)

        elif event_name == "progress":
            self.status_bar.set_status("Loading settings...", is_busy=True)

        elif event_name == "worker_error":
            self.status_bar.set_status(f"Error: {payload}", is_busy=False)

    def _render_setting_cards(self) -> None:
        """Render setting cards for current filters into content area (Spike #41)."""
        for child in self.content_frame.winfo_children():
            child.destroy()

        if not self.controller.state.catalog:
            self._show_loading_indicator()
            return

        settings = self.controller.state.get_filtered_settings(self.essentials_guids)

        if not settings:
            # Empty state (REQ-5.4)
            empty_box = ctk.CTkFrame(self.content_frame, fg_color=COLOR_SURFACE_CARD, corner_radius=8)
            empty_box.pack(fill="x", pady=20, padx=10)

            ctk.CTkLabel(
                empty_box,
                text="🔍 No settings match the current filter",
                font=FONT_SUBTITLE,
                text_color=COLOR_TEXT_PRIMARY,
            ).pack(pady=(20, 6))

            ctk.CTkLabel(
                empty_box,
                text="Try clearing the search query or changing the selected category in the sidebar.",
                font=FONT_BODY,
                text_color=COLOR_TEXT_SECONDARY,
            ).pack(pady=(0, 20))
            return

        # Render setting cards sequentially
        for setting in settings:
            s_key = setting.guid.lower()
            doc_url = self.doc_links.get(s_key)
            reboot = (s_key in self.reboot_guids)

            card = SettingCardWidget(
                self.content_frame,
                setting=setting,
                controller=self.controller,
                doc_url=doc_url,
                reboot_required=reboot,
                on_refresh=self._on_card_value_changed,
            )
            card.pack(fill="x", pady=6)

    def _on_card_value_changed(self) -> None:
        """Card modified; refresh summary elements."""
        self.sidebar.refresh()
        self.status_bar.refresh()

    def _on_search_query(self, query: str) -> None:
        self.controller.state.search_query = query
        self._render_setting_cards()

    def _on_modified_toggle(self, modified_only: bool) -> None:
        self.controller.state.show_modified_only = modified_only
        self._render_setting_cards()

    def _on_scheme_selected(self, scheme_guid: str) -> None:
        self.status_bar.set_status("Loading scheme values...", is_busy=True)
        self.controller.select_scheme(scheme_guid)

    def _on_category_selected(self, category_guid: str) -> None:
        self.controller.state.selected_category = category_guid
        self.sidebar.refresh()
        self._render_setting_cards()

    def _on_delete_scheme(self, scheme_guid: str) -> None:
        try:
            self.controller.delete_scheme(scheme_guid)
            self.status_bar.show_toast("Custom power scheme deleted")
        except Exception as exc:
            self.status_bar.set_status(f"Delete failed: {exc}")

    def _open_create_scheme(self) -> None:
        """Open create custom scheme modal (REQ-1.1)."""
        CreateSchemeDialog(
            self,
            controller=self.controller,
            on_created=lambda guid: self.status_bar.show_toast("Custom scheme created successfully"),
        )

    def _open_export(self) -> None:
        """Open export scheme dialog (REQ-4.1)."""
        ExportDialog(
            self,
            controller=self.controller,
            scheme=self.controller.state.selected_scheme or self.controller.state.active_scheme,
        )

    def _open_command_palette(self) -> None:
        """Open Ctrl+K command palette dialog (Issue #21)."""
        if self._active_palette and self._active_palette.winfo_exists():
            self._active_palette.focus_set()
            return

        self._active_palette = CommandPalette(
            self,
            controller=self.controller,
            on_select_setting=self._nav_to_setting,
            on_select_category=self._on_category_selected,
            on_create_scheme=self._open_create_scheme,
            on_open_export=self._open_export,
            on_open_compare=self._open_compare,
            on_open_visibility=self._open_visibility,
        )

    def _nav_to_setting(self, subgroup_guid: str, setting_guid: str) -> None:
        """Navigate to and display a specific setting."""
        self.controller.state.selected_category = subgroup_guid
        self.controller.state.search_query = ""
        self.sidebar.refresh()
        self._render_setting_cards()

    def _undo(self) -> None:
        """Execute single-level undo (Issue #27, REQ-11.1)."""
        success = self.controller.undo()
        if success:
            self.status_bar.show_toast("Undone previous setting change")
            self._render_setting_cards()

    def _refresh(self) -> None:
        """Refresh current view."""
        self.status_bar.set_status("Refreshing...", is_busy=True)
        self.controller.refresh(full=True)

    def _toggle_modified(self) -> None:
        """Toggle modified-only filter on Ctrl+M."""
        new_val = not self.controller.state.show_modified_only
        if new_val:
            self.search_bar.mod_switch.select()
        else:
            self.search_bar.mod_switch.deselect()
        self._on_modified_toggle(new_val)

    def _open_compare(self) -> None:
        """Open Compare Schemes view."""
        self.status_bar.set_status("Compare Schemes view")

    def _open_visibility(self) -> None:
        """Open Control Panel Visibility view."""
        self.status_bar.set_status("Control Panel Visibility view")

    def _open_restore_defaults(self) -> None:
        """Open Restore Defaults confirmation flow."""
        def on_proceed_elevation():
            try:
                self.controller.pm.restore_default_schemes()
                self.controller.refresh(full=True)
                self.status_bar.show_toast("Power scheme defaults restored")
            except Exception as exc:
                self.status_bar.set_status(f"Restore failed: {exc}")

        def on_confirm_restore():
            ElevationDialog(
                self,
                title="Restore Windows Power Defaults",
                action_name="PowerRestoreDefaultPowerSchemes",
                description="This will restore all built-in Windows power schemes to factory defaults and remove custom schemes.",
                on_proceed=on_proceed_elevation,
            )

        ConfirmDialog(
            self,
            title="Restore Default Power Schemes",
            message="Are you sure you want to restore all power schemes to Windows defaults?\nAll custom changes and profiles will be lost.",
            confirm_text="Restore Defaults",
            is_destructive=True,
            required_phrase="RESTORE",
            on_confirm=on_confirm_restore,
        )

    def _open_log_folder(self) -> None:
        """Open application log directory (F1)."""
        log_dir = get_data_directory() / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(log_dir))
        except Exception:
            pass

    def _on_close(self) -> None:
        """Handle window shutdown, save ui-state.json, and release resources."""
        try:
            # Capture geometry
            geom = self.geometry()  # e.g. '1150x720+100+100'
            parts = geom.replace("+", "x").split("x")
            if len(parts) >= 4:
                w, h, x, y = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                self.ui_state["window"] = {
                    "width": w,
                    "height": h,
                    "x": x,
                    "y": y,
                    "maximized": (self.state() == "zoomed"),
                }

            self.ui_state["appearance_mode"] = self.controller.state.appearance_mode
            self.ui_state["last_selected_scheme_guid"] = self.controller.state.selected_scheme_guid
            self.ui_state["last_selected_category"] = self.controller.state.selected_category
            self.ui_state["show_modified_only"] = self.controller.state.show_modified_only
            self.ui_state["favorites"] = [
                [sub, set_g] for sub, set_g in self.controller.state.favorites
            ]

            save_ui_state(self.ui_state)
        except Exception as exc:
            logger.warning(f"Failed saving ui-state: {exc}")

        try:
            self.controller.shutdown()
        except Exception:
            pass

        self.destroy()


# Compatibility aliases
App = PowerExplorerApp
