"""Create Custom Power Scheme Modal Dialog (REQ-1.1, REQ-1.2, REQ-1.4, Issue #23).

Offers live schemes on the current machine to clone from, enforces naming,
and configures the power plan personality matching the base template.
"""

from typing import Any, Callable

import customtkinter as ctk

from core.controller import AppController
from ui.dialogs.base import BaseDialog
from ui.theme import (
    COLOR_APP_BG,
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_SURFACE_CARD,
    COLOR_SURFACE_HOVER,
    COLOR_SURFACE_SECONDARY,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SMALL,
    FONT_SUBTITLE,
)


class CreateSchemeDialog(BaseDialog):
    """Modal dialog for creating a custom power scheme by cloning an existing one."""

    def __init__(
        self,
        parent: Any,
        controller: AppController,
        on_created: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, title="Create Custom Scheme", width=520, height=360, **kwargs)
        self.controller = controller
        self.on_created = on_created

        # Map display label -> scheme GUID
        self.scheme_map: dict[str, str] = {}
        for s in self.controller.state.schemes:
            custom_tag = " (Custom)" if not s.is_base_default else ""
            label = f"{s.friendly_name}{custom_tag}"
            self.scheme_map[label] = s.guid

        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # Header Title
        ctk.CTkLabel(
            self,
            text="Create Custom Power Scheme",
            font=FONT_SUBTITLE,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(padx=24, pady=(18, 4), fill="x")

        ctk.CTkLabel(
            self,
            text="Clone an existing power scheme into a new customizable profile.",
            font=FONT_BODY,
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        ).pack(padx=24, pady=(0, 14), fill="x")

        # 1. Base Scheme Dropdown (REQ-1.1: live pass from current machine)
        ctk.CTkLabel(
            self,
            text="Base Scheme to Clone:",
            font=FONT_BODY_BOLD,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(padx=24, pady=(0, 4), fill="x")

        options = list(self.scheme_map.keys()) or ["Balanced"]
        self.selected_scheme_var = ctk.StringVar(value=options[0])

        self.scheme_menu = ctk.CTkOptionMenu(
            self,
            values=options,
            variable=self.selected_scheme_var,
            font=FONT_BODY,
            height=34,
            command=self._on_base_changed,
        )
        self.scheme_menu.pack(padx=24, pady=(0, 12), fill="x")

        # 2. Scheme Name Entry
        ctk.CTkLabel(
            self,
            text="New Scheme Name:",
            font=FONT_BODY_BOLD,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(padx=24, pady=(0, 4), fill="x")

        default_name = f"Custom - {options[0].replace(' (Custom)', '')}"
        self.name_entry = ctk.CTkEntry(self, font=FONT_BODY, height=34)
        self.name_entry.insert(0, default_name)
        self.name_entry.pack(padx=24, pady=(0, 12), fill="x")

        # 3. Optional Description
        ctk.CTkLabel(
            self,
            text="Description (Optional):",
            font=FONT_BODY,
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w",
        ).pack(padx=24, pady=(0, 4), fill="x")

        self.desc_entry = ctk.CTkEntry(self, font=FONT_BODY, height=34)
        self.desc_entry.insert(0, "User-defined custom power profile.")
        self.desc_entry.pack(padx=24, pady=(0, 16), fill="x")

        # 4. Action Buttons
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

        self.create_btn = ctk.CTkButton(
            btn_box,
            text="Create Scheme",
            font=FONT_BODY_BOLD,
            fg_color=COLOR_PRIMARY,
            command=self._on_create,
            width=120,
        )
        self.create_btn.pack(side="right")

        # Initial focus on safe Cancel button
        cancel_btn.focus_set()

    def _on_base_changed(self, choice: str) -> None:
        base_name = choice.replace(" (Custom)", "")
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, f"Custom - {base_name}")

    def _on_create(self) -> None:
        selected_label = self.selected_scheme_var.get()
        source_guid = self.scheme_map.get(selected_label)
        if not source_guid and self.controller.state.schemes:
            source_guid = self.controller.state.schemes[0].guid

        name = self.name_entry.get().strip() or "Custom Power Scheme"
        description = self.desc_entry.get().strip()

        self.destroy()
        if source_guid:
            new_guid = self.controller.create_scheme(
                source_scheme_guid=source_guid,
                new_name=name,
                description=description,
            )
            if self.on_created and new_guid:
                self.on_created(new_guid)
