"""Elevation Explanation Modal Dialog (ADR-008, ADR-011, Issue #23).

Explains to the user why Administrator privileges are required for system-wide operations
(such as modifying Control Panel visibility attributes or restoring default power schemes)
before triggering the Windows User Account Control (UAC) prompt.
"""

from typing import Any, Callable

import customtkinter as ctk

from ui.dialogs.base import BaseDialog
from ui.theme import (
    COLOR_APP_BG,
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_SURFACE_HOVER,
    COLOR_SURFACE_SECONDARY,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SUBTITLE,
)


class ElevationDialog(BaseDialog):
    """Modal dialog explaining the need for Administrator privileges prior to UAC prompt."""

    def __init__(
        self,
        parent: Any,
        title: str = "Administrator Privileges Required",
        action_name: str = "System-wide Modification",
        description: str = "This operation modifies system-wide power settings in the Windows Registry that apply to all user accounts.",
        on_proceed: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, title=title, width=480, height=270, **kwargs)
        self.action_name = action_name
        self.description = description
        self.on_proceed = on_proceed

        self._build_ui(title)

    def _build_ui(self, title: str) -> None:
        self.grid_columnconfigure(0, weight=1)

        # Header with Warning / Shield indicator
        ctk.CTkLabel(
            self,
            text=f"🛡️ {title}",
            font=FONT_SUBTITLE,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(padx=24, pady=(18, 6), fill="x")

        # Action Summary
        ctk.CTkLabel(
            self,
            text=f"Operation: {self.action_name}",
            font=FONT_BODY_BOLD,
            text_color=COLOR_WARNING,
            anchor="w",
        ).pack(padx=24, pady=(0, 8), fill="x")

        # Description Body
        ctk.CTkLabel(
            self,
            text=self.description,
            font=FONT_BODY,
            text_color=COLOR_TEXT_SECONDARY,
            wraplength=430,
            justify="left",
            anchor="w",
        ).pack(padx=24, pady=(0, 10), fill="x")

        ctk.CTkLabel(
            self,
            text="A standard Windows User Account Control (UAC) prompt will appear when you continue.",
            font=FONT_BODY,
            text_color=COLOR_TEXT_SECONDARY,
            wraplength=430,
            justify="left",
            anchor="w",
        ).pack(padx=24, pady=(0, 16), fill="x")

        # Action Buttons
        btn_box = ctk.CTkFrame(self, fg_color="transparent")
        btn_box.pack(padx=24, pady=(0, 18), fill="x")

        cancel_btn = ctk.CTkButton(
            btn_box,
            text="Cancel",
            font=FONT_BODY,
            fg_color=COLOR_SURFACE_SECONDARY,
            text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_SURFACE_HOVER,
            command=self.destroy,
            width=90,
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        continue_btn = ctk.CTkButton(
            btn_box,
            text="Continue",
            font=FONT_BODY_BOLD,
            fg_color=COLOR_PRIMARY,
            command=self._proceed,
            width=100,
        )
        continue_btn.pack(side="right")

        # Initial focus on safe Cancel action
        cancel_btn.focus_set()

    def _proceed(self) -> None:
        self.destroy()
        if self.on_proceed:
            self.on_proceed()
