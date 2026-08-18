"""Main Graphical User Interface Shell (customtkinter) for Windows Power Explorer.

Orchestrates:
- 2-Column responsive split layout (Sidebar + Content + Header + Footer)
- Subgroup pagination / container card rendering (Spike #41)
- Live search bar with 120ms debounce (Issue #21)
- Fuzzy jump command palette on Ctrl+K (Issue #21)
- SettingCardWidget with AC/DC controls, badges, reset, link, and context actions (Issue #20, #26, #28)
- Single-level undo on Ctrl+Z (Issue #27)
- Presentational data integration (Issue #32)
"""

import logging
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
from ui.components.setting_card import SettingCardWidget
from ui.dialogs.command_palette import CommandPalette
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
)

logger = logging.getLogger(__name__)


class App(ctk.CTk):
    """Main Application Window."""

    def __init__(self, controller: AppController | None = None) -> None:
        super().__init__()

        self.title("Windows Power Explorer")
        self.geometry("1150x720")
        self.minsize(920, 600)
        self.configure(fg_color=COLOR_APP_BG)

        # Set default appearance mode
        ctk.set_appearance_mode("System")

        # Initialize Controller with GUI schedulers
        self.controller = controller or AppController(
            scheduler=self.after,
            canceler=self.after_cancel,
        )
        self.controller.add_listener(self._on_controller_event)

        # Load presentational metadata (safely degraded if missing)
        self.essentials_guids = load_essentials_guids()
        self.reboot_guids = load_reboot_required()
        self.doc_links = load_doc_links()

        self._active_palette: CommandPalette | None = None

        self._build_shell()
        self._bind_shortcuts()

        # Start initial data discovery
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self.controller.load_initial_data)

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

        # 2. Sidebar Navigation
        self.sidebar = SidebarNav(
            self,
            controller=self.controller,
            on_scheme_selected=self._on_scheme_selected,
            on_category_selected=self._on_category_selected,
            on_open_compare=self._open_compare,
            on_open_visibility=self._open_visibility,
            on_restore_defaults=self._open_restore_defaults,
        )
        self.sidebar.grid(row=1, column=0, sticky="nsew")

        # 3. Main Content Container
        self.content_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=0,
        )
        self.content_frame.grid(row=1, column=1, sticky="nsew", padx=16, pady=12)
        self.content_frame.grid_columnconfigure(0, weight=1)

        # 4. Status Bar
        self.status_bar = StatusBar(self, controller=self.controller)
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")

    def _bind_shortcuts(self) -> None:
        """Register global keyboard shortcuts (CLI and UX spec §1.4)."""
        self.bind("<Control-f>", lambda _: self.search_bar.focus())
        self.bind("<Control-k>", lambda _: self._open_command_palette())
        self.bind("<Control-z>", lambda _: self._undo())
        self.bind("<Control-r>", lambda _: self._refresh())
        self.bind("<Control-m>", lambda _: self._toggle_modified())
        self.bind("<Escape>", lambda _: self.search_bar.clear())

    def _on_controller_event(self, event_name: str, payload: Any) -> None:
        """Handle notifications from AppController on the main thread."""
        if event_name in ("catalog_loaded", "values_loaded", "schemes_loaded", "scheme_selected", "value_changed"):
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
            loading_lbl = ctk.CTkLabel(
                self.content_frame,
                text="Loading power catalog from Windows...",
                font=FONT_SUBTITLE,
                text_color=COLOR_TEXT_MUTED,
            )
            loading_lbl.pack(pady=40)
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

        # Render cards sequentially
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
            self.status_bar.set_status("Undone previous setting change")
            self._render_setting_cards()

    def _refresh(self) -> None:
        """Refresh current view."""
        self.status_bar.set_status("Refreshing...", is_busy=True)
        self.controller.refresh(full=False)

    def _toggle_modified(self) -> None:
        """Toggle modified-only filter on Ctrl+M."""
        new_val = not self.controller.state.show_modified_only
        self.search_bar.mod_switch.select() if new_val else self.search_bar.mod_switch.deselect()
        self._on_modified_toggle(new_val)

    def _open_create_scheme(self) -> None:
        """Open create custom scheme modal."""
        self.status_bar.set_status("Create Scheme dialog")

    def _open_compare(self) -> None:
        """Open Compare Schemes view."""
        self.status_bar.set_status("Compare Schemes view")

    def _open_visibility(self) -> None:
        """Open Control Panel Visibility view."""
        self.status_bar.set_status("Control Panel Visibility view")

    def _open_restore_defaults(self) -> None:
        """Open Restore Defaults flow."""
        self.status_bar.set_status("Restore Defaults dialog")

    def _on_close(self) -> None:
        """Handle window shutdown."""
        try:
            self.controller.shutdown()
        except Exception:
            pass
        self.destroy()


# Compatibility alias for main.py
PowerExplorerApp = App
