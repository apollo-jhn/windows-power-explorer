"""Sidebar Navigation Component for Schemes, Categories, and Tools (REQ-1.3, REQ-5.2, REQ-10.3, REQ-10.4, Issue #19).

Features:
- Live list of power schemes with active indicator (🟢) and selection highlight
- Clear visual distinction for custom vs built-in schemes (REQ-1.3)
- Built-in schemes locked against deletion (REQ-1.3)
- Custom scheme deletion workflow with confirmation
- Categories: Favorites (★), Essentials (✦), All Settings (☰), and dynamic catalog subgroups
- Tools: Compare Schemes (⇄), Control Panel Visibility (👁), Restore Defaults (♻)
"""

from typing import Any, Callable

import customtkinter as ctk

from core.controller import AppController
from ui.dialogs.base import ConfirmDialog
from ui.theme import (
    COLOR_BORDER,
    COLOR_DANGER,
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
        on_delete_scheme: Callable[[str], None] | None = None,
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
        self.on_delete_scheme = on_delete_scheme

        self._render_navigation()

    def refresh(self) -> None:
        """Re-render sidebar items to reflect state changes."""
        self._render_navigation()

    def _render_navigation(self) -> None:
        """Construct sidebar content."""
        for widget in self.winfo_children():
            widget.destroy()

        self.grid_columnconfigure(0, weight=1)

        # 1. Power Schemes Section (REQ-1.3)
        self._build_header("POWER SCHEMES")
        for scheme in self.controller.state.schemes:
            is_active = (scheme.guid.lower() == (self.controller.state.active_scheme_guid or "").lower())
            is_selected = (scheme.guid.lower() == (self.controller.state.selected_scheme_guid or "").lower())

            prefix = "🟢 " if is_active else "   "
            custom_tag = " (Custom)" if not scheme.is_base_default else ""
            label_text = f"{prefix}{scheme.friendly_name}{custom_tag}"

            row_frame = ctk.CTkFrame(self, fg_color=COLOR_SURFACE_HOVER if is_selected else "transparent")
            row_frame.pack(fill="x", padx=6, pady=1)
            row_frame.grid_columnconfigure(0, weight=1)

            btn = ctk.CTkButton(
                row_frame,
                text=label_text,
                anchor="w",
                font=FONT_BODY_BOLD if is_selected else FONT_BODY,
                fg_color="transparent",
                text_color=COLOR_PRIMARY if is_selected else COLOR_TEXT_PRIMARY,
                hover_color=COLOR_SURFACE_HOVER,
                height=32,
                command=lambda g=scheme.guid: self.on_scheme_selected(g),
            )
            btn.grid(row=0, column=0, sticky="ew")

            # Built-in schemes have NO delete control (REQ-1.3)
            # Custom schemes offer delete action if not currently active
            if not scheme.is_base_default and not is_active:
                del_btn = ctk.CTkButton(
                    row_frame,
                    text="✕",
                    font=FONT_SMALL,
                    fg_color="transparent",
                    text_color=COLOR_TEXT_MUTED,
                    hover_color=COLOR_SURFACE_SECONDARY,
                    width=24,
                    height=24,
                    command=lambda s=scheme: self._confirm_delete_scheme(s),
                )
                del_btn.grid(row=0, column=1, padx=(2, 4))

        # 2. Categories Section
        self._build_header("CATEGORIES")

        # Favorites (REQ-10.4)
        fav_active = (self.controller.state.selected_category == "favorites")
        fav_count = len(self.controller.state.favorites)
        fav_count_tag = f" ({fav_count})" if fav_count > 0 else ""
        fav_btn = ctk.CTkButton(
            self,
            text=f"★ Favorites{fav_count_tag}",
            anchor="w",
            font=FONT_BODY_BOLD if fav_active else FONT_BODY,
            fg_color=COLOR_SURFACE_HOVER if fav_active else "transparent",
            text_color=COLOR_PRIMARY if fav_active else COLOR_TEXT_PRIMARY,
            hover_color=COLOR_SURFACE_HOVER,
            height=30,
            command=lambda: self.on_category_selected("favorites"),
        )
        fav_btn.pack(fill="x", padx=6, pady=1)

        # Essentials (REQ-10.3)
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

    def _confirm_delete_scheme(self, scheme: Any) -> None:
        """Prompt confirmation before deleting custom scheme."""
        ConfirmDialog(
            self,
            title="Delete Custom Scheme",
            message=f"Are you sure you want to delete '{scheme.friendly_name}'?\nThis action cannot be undone.",
            confirm_text="Delete Scheme",
            is_destructive=True,
            on_confirm=lambda: self._delete_scheme(scheme.guid),
        )

    def _delete_scheme(self, scheme_guid: str) -> None:
        if self.on_delete_scheme:
            self.on_delete_scheme(scheme_guid)
        else:
            self.controller.delete_scheme(scheme_guid)
