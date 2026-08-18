"""Sidebar Navigation Component for Schemes and Categories (REQ-5.2, REQ-10.3, REQ-10.4)."""

from typing import Any, Callable

import customtkinter as ctk

from core.controller import AppController
from ui.theme import (
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


class SidebarNav(ctk.CTkScrollableFrame):
    """Navigation sidebar hosting Power Schemes, Categories, and Tools."""

    def __init__(
        self,
        master: Any,
        controller: AppController,
        on_scheme_selected: Callable[[str], None],
        on_category_selected: Callable[[str], None],
        on_open_compare: Callable[[], None] | None = None,
        on_open_visibility: Callable[[], None] | None = None,
        on_restore_defaults: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLOR_SURFACE_CARD,
            border_color=COLOR_BORDER,
            border_width=1,
            corner_radius=0,
            width=240,
            **kwargs,
        )
        self.controller = controller
        self.on_scheme_selected = on_scheme_selected
        self.on_category_selected = on_category_selected
        self.on_open_compare = on_open_compare
        self.on_open_visibility = on_open_visibility
        self.on_restore_defaults = on_restore_defaults

        self._render_navigation()

    def refresh(self) -> None:
        """Re-render sidebar items to reflect state changes."""
        self._render_navigation()

    def _render_navigation(self) -> None:
        """Construct sidebar content."""
        for widget in self.winfo_children():
            widget.destroy()

        self.grid_columnconfigure(0, weight=1)

        # 1. Power Schemes Section
        self._build_header("POWER SCHEMES")
        for scheme in self.controller.state.schemes:
            is_active = (scheme.guid.lower() == (self.controller.state.active_scheme_guid or "").lower())
            is_selected = (scheme.guid.lower() == (self.controller.state.selected_scheme_guid or "").lower())

            prefix = "🟢 " if is_active else "   "
            custom_tag = " (Custom)" if not scheme.is_base_default else ""
            label_text = f"{prefix}{scheme.friendly_name}{custom_tag}"

            btn = ctk.CTkButton(
                self,
                text=label_text,
                anchor="w",
                font=FONT_BODY_BOLD if is_selected else FONT_BODY,
                fg_color=COLOR_SURFACE_HOVER if is_selected else "transparent",
                text_color=COLOR_PRIMARY if is_selected else COLOR_TEXT_PRIMARY,
                hover_color=COLOR_SURFACE_HOVER,
                height=32,
                command=lambda g=scheme.guid: self.on_scheme_selected(g),
            )
            btn.pack(fill="x", padx=6, pady=1)

        # 2. Categories Section
        self._build_header("CATEGORIES")

        # Favorites
        fav_active = (self.controller.state.selected_category == "favorites")
        fav_btn = ctk.CTkButton(
            self,
            text="★ Favorites",
            anchor="w",
            font=FONT_BODY_BOLD if fav_active else FONT_BODY,
            fg_color=COLOR_SURFACE_HOVER if fav_active else "transparent",
            text_color=COLOR_PRIMARY if fav_active else COLOR_TEXT_PRIMARY,
            hover_color=COLOR_SURFACE_HOVER,
            height=30,
            command=lambda: self.on_category_selected("favorites"),
        )
        fav_btn.pack(fill="x", padx=6, pady=1)

        # Essentials
        ess_active = (self.controller.state.selected_category == "essentials")
        ess_btn = ctk.CTkButton(
            self,
            text="✦ Essentials",
            anchor="w",
            font=FONT_BODY_BOLD if ess_active else FONT_BODY,
            fg_color=COLOR_SURFACE_HOVER if ess_active else "transparent",
            text_color=COLOR_PRIMARY if ess_active else COLOR_TEXT_PRIMARY,
            hover_color=COLOR_SURFACE_HOVER,
            height=30,
            command=lambda: self.on_category_selected("essentials"),
        )
        ess_btn.pack(fill="x", padx=6, pady=1)

        # All Settings
        all_active = (self.controller.state.selected_category == "all")
        all_btn = ctk.CTkButton(
            self,
            text="☰ All Settings",
            anchor="w",
            font=FONT_BODY_BOLD if all_active else FONT_BODY,
            fg_color=COLOR_SURFACE_HOVER if all_active else "transparent",
            text_color=COLOR_PRIMARY if all_active else COLOR_TEXT_PRIMARY,
            hover_color=COLOR_SURFACE_HOVER,
            height=30,
            command=lambda: self.on_category_selected("all"),
        )
        all_btn.pack(fill="x", padx=6, pady=1)

        # Subgroups from Catalog
        if self.controller.state.catalog:
            for sub in self.controller.state.catalog.subgroups:
                sub_active = (self.controller.state.selected_category.lower() == sub.guid.lower())
                sub_btn = ctk.CTkButton(
                    self,
                    text=f"  {sub.friendly_name}",
                    anchor="w",
                    font=FONT_BODY_BOLD if sub_active else FONT_BODY,
                    fg_color=COLOR_SURFACE_HOVER if sub_active else "transparent",
                    text_color=COLOR_PRIMARY if sub_active else COLOR_TEXT_SECONDARY,
                    hover_color=COLOR_SURFACE_HOVER,
                    height=28,
                    command=lambda g=sub.guid: self.on_category_selected(g),
                )
                sub_btn.pack(fill="x", padx=6, pady=1)

        # 3. Tools Section
        self._build_header("TOOLS")

        if self.on_open_compare:
            cmp_btn = ctk.CTkButton(
                self,
                text="⇄ Compare Schemes",
                anchor="w",
                font=FONT_BODY,
                fg_color="transparent",
                text_color=COLOR_TEXT_PRIMARY,
                hover_color=COLOR_SURFACE_HOVER,
                height=30,
                command=self.on_open_compare,
            )
            cmp_btn.pack(fill="x", padx=6, pady=1)

        if self.on_open_visibility:
            vis_btn = ctk.CTkButton(
                self,
                text="👁 Visibility Manager",
                anchor="w",
                font=FONT_BODY,
                fg_color="transparent",
                text_color=COLOR_TEXT_PRIMARY,
                hover_color=COLOR_SURFACE_HOVER,
                height=30,
                command=self.on_open_visibility,
            )
            vis_btn.pack(fill="x", padx=6, pady=1)

        if self.on_restore_defaults:
            res_btn = ctk.CTkButton(
                self,
                text="♻ Restore Defaults",
                anchor="w",
                font=FONT_BODY,
                fg_color="transparent",
                text_color=COLOR_TEXT_PRIMARY,
                hover_color=COLOR_SURFACE_HOVER,
                height=30,
                command=self.on_restore_defaults,
            )
            res_btn.pack(fill="x", padx=6, pady=1)

    def _build_header(self, title: str) -> None:
        header = ctk.CTkLabel(
            self,
            text=title,
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
            anchor="w",
        )
        header.pack(fill="x", padx=10, pady=(16, 4))
