"""Footer Status Bar Component (REQ-7.1, NFR-1)."""

from typing import Any

import customtkinter as ctk

from core.controller import AppController
from ui.theme import (
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_SURFACE_CARD,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_BODY,
    FONT_SMALL,
)


class StatusBar(ctk.CTkFrame):
    """Footer status bar presenting active scheme, power mode overlay, and system status."""

    def __init__(self, master: Any, controller: AppController, **kwargs: Any) -> None:
        super().__init__(
            master,
            fg_color=COLOR_SURFACE_CARD,
            border_color=COLOR_BORDER,
            border_width=1,
            corner_radius=0,
            height=32,
            **kwargs,
        )
        self.controller = controller
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # Left: Active scheme info & overlay
        active_scheme_name = (
            self.controller.state.active_scheme.friendly_name
            if self.controller.state.active_scheme
            else "Windows Default"
        )
        overlay_text = f" · Power Mode: {self.controller.state.overlay.friendly_name}" if self.controller.state.overlay else ""

        self.left_label = ctk.CTkLabel(
            self,
            text=f"Active Scheme: {active_scheme_name}{overlay_text}",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        )
        self.left_label.grid(row=0, column=0, padx=16, pady=4, sticky="w")

        # Right: System Status
        self.status_label = ctk.CTkLabel(
            self,
            text="● System Ready",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
            anchor="e",
        )
        self.status_label.grid(row=0, column=1, padx=16, pady=4, sticky="e")

    def set_status(self, message: str, is_busy: bool = False) -> None:
        """Update transient status text."""
        self.status_label.configure(
            text=f"● {message}",
            text_color=COLOR_PRIMARY if is_busy else COLOR_TEXT_MUTED,
        )

    def refresh(self) -> None:
        """Update active scheme and overlay text from state."""
        active_scheme_name = (
            self.controller.state.active_scheme.friendly_name
            if self.controller.state.active_scheme
            else "Windows Default"
        )
        overlay_text = f" · Power Mode: {self.controller.state.overlay.friendly_name}" if self.controller.state.overlay else ""
        self.left_label.configure(text=f"Active Scheme: {active_scheme_name}{overlay_text}")
