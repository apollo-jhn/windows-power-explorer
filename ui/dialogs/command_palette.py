"""Command Palette Modal Dialog for fuzzy jump & keyboard navigation (Issue #21, REQ-10.1).

Features:
- Global Ctrl+K trigger
- Ranked search across Settings, Schemes, Categories, and App Commands
- 100% Keyboard-navigable: Up/Down to navigate, Enter to execute, Escape to cancel
- Scrollable list in CTkScrollableFrame
"""

from dataclasses import dataclass
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


@dataclass
class PaletteItem:
    """Single navigable command palette item."""

    category: str  # "Setting" | "Scheme" | "Category" | "Command"
    title: str
    subtitle: str
    action: Callable[[], None]


class CommandPalette(BaseDialog):
    """Fuzzy jump command palette dialog."""

    def __init__(
        self,
        parent: Any,
        controller: AppController,
        on_select_setting: Callable[[str, str], None] | None = None,
        on_select_category: Callable[[str], None] | None = None,
        on_create_scheme: Callable[[], None] | None = None,
        on_open_compare: Callable[[], None] | None = None,
        on_open_visibility: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, title="Command Palette", width=580, height=420, **kwargs)
        self.controller = controller
        self.on_select_setting = on_select_setting
        self.on_select_category = on_select_category
        self.on_create_scheme = on_create_scheme
        self.on_open_compare = on_open_compare
        self.on_open_visibility = on_open_visibility

        self.all_items: list[PaletteItem] = []
        self.filtered_items: list[PaletteItem] = []
        self.selected_index: int = 0
        self.row_buttons: list[ctk.CTkButton] = []

        self._build_items()
        self._build_ui()
        self._filter_items("")

    def _build_items(self) -> None:
        """Construct the searchable items list from controller state."""
        # 1. Commands
        if self.on_create_scheme:
            self.all_items.append(PaletteItem("Command", "Create Custom Power Scheme", "Clone an existing scheme to a new profile (Ctrl+N)", self.on_create_scheme))
        if self.on_open_compare:
            self.all_items.append(PaletteItem("Command", "Compare Schemes", "Side-by-side comparison of two power schemes (Ctrl+D)", self.on_open_compare))
        if self.on_open_visibility:
            self.all_items.append(PaletteItem("Command", "Control Panel Visibility Manager", "Manage setting visibility in powercfg.cpl", self.on_open_visibility))

        self.all_items.append(PaletteItem("Command", "Refresh State", "Re-read per-scheme values from OS (Ctrl+R)", lambda: self.controller.refresh(full=False)))
        self.all_items.append(PaletteItem("Command", "Undo Last Value Change", "Restore previous setting value (Ctrl+Z)", lambda: self.controller.undo()))

        # 2. Categories
        self.all_items.append(PaletteItem("Category", "All Settings", "View all power settings", lambda: self._nav_category("all")))
        self.all_items.append(PaletteItem("Category", "Favorites", "View pinned favorite settings", lambda: self._nav_category("favorites")))
        self.all_items.append(PaletteItem("Category", "Essentials", "View curated starter settings", lambda: self._nav_category("essentials")))

        if self.controller.state.catalog:
            for sub in self.controller.state.catalog.subgroups:
                s_guid = sub.guid
                self.all_items.append(PaletteItem(
                    "Category",
                    f"Category: {sub.friendly_name}",
                    f"Subgroup GUID: {sub.guid}",
                    lambda g=s_guid: self._nav_category(g),
                ))

        # 3. Schemes
        for s in self.controller.state.schemes:
            s_guid = s.guid
            self.all_items.append(PaletteItem(
                "Scheme",
                f"Switch to Scheme: {s.friendly_name}",
                f"{'Active · ' if s.is_active else ''}GUID: {s.guid}",
                lambda g=s_guid: self.controller.select_scheme(g),
            ))

        # 4. Settings
        if self.controller.state.catalog:
            for sub in self.controller.state.catalog.subgroups:
                for set_entry in sub.settings:
                    name = set_entry.friendly_name or f"Unknown setting ({set_entry.guid[:8]}...)"
                    sub_g = sub.guid
                    set_g = set_entry.guid
                    choices_hint = f" ({', '.join(c.friendly_name for c in set_entry.choices[:3])})" if set_entry.choices else ""
                    self.all_items.append(PaletteItem(
                        "Setting",
                        f"{name}{choices_hint}",
                        f"{sub.friendly_name} · {set_entry.guid}",
                        lambda sg=sub_g, st=set_g: self._nav_setting(sg, st),
                    ))

    def _nav_category(self, cat: str) -> None:
        if self.on_select_category:
            self.on_select_category(cat)

    def _nav_setting(self, subgroup_guid: str, setting_guid: str) -> None:
        if self.on_select_setting:
            self.on_select_setting(subgroup_guid, setting_guid)

    def _build_ui(self) -> None:
        """Construct dialog widgets."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header Search Box
        search_box = ctk.CTkFrame(self, fg_color="transparent")
        search_box.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        search_box.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            search_box,
            placeholder_text="Type a setting, category, scheme, or command...",
            font=FONT_BODY,
            height=36,
        )
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.focus_set()

        # Bindings for keyboard navigation (REQ-10.1)
        self.entry.bind("<KeyRelease>", self._on_type)
        self.entry.bind("<Up>", self._on_arrow_up)
        self.entry.bind("<Down>", self._on_arrow_down)
        self.entry.bind("<Return>", self._on_enter)
        self.bind("<Up>", self._on_arrow_up)
        self.bind("<Down>", self._on_arrow_down)
        self.bind("<Return>", self._on_enter)

        # Results Scrollable Frame
        self.results_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            corner_radius=6,
        )
        self.results_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self.results_frame.grid_columnconfigure(0, weight=1)

        # Footer Hint
        hint_lbl = ctk.CTkLabel(
            self,
            text="↑/↓ to navigate · Enter to select · Esc to close",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_MUTED,
        )
        hint_lbl.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 10))

    def _filter_items(self, query: str) -> None:
        """Filter and render top matching items."""
        q = query.strip().lower()
        if not q:
            self.filtered_items = self.all_items[:40]
        else:
            # Score items: exact prefix matches rank higher
            matched = []
            for it in self.all_items:
                title_low = it.title.lower()
                sub_low = it.subtitle.lower()
                if q in title_low or q in sub_low or q in it.category.lower():
                    # Rank score
                    score = 0
                    if title_low.startswith(q):
                        score += 3
                    elif q in title_low:
                        score += 2
                    elif q in sub_low:
                        score += 1
                    matched.append((score, it))

            matched.sort(key=lambda x: x[0], reverse=True)
            self.filtered_items = [it for score, it in matched[:40]]

        self.selected_index = 0
        self._render_results()

    def _render_results(self) -> None:
        """Render result buttons inside scrollable area."""
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        self.row_buttons = []
        if not self.filtered_items:
            empty_lbl = ctk.CTkLabel(
                self.results_frame,
                text="No matching commands or settings.",
                font=FONT_BODY,
                text_color=COLOR_TEXT_MUTED,
            )
            empty_lbl.pack(pady=20)
            return

        for idx, item in enumerate(self.filtered_items):
            is_active = (idx == self.selected_index)
            btn = ctk.CTkButton(
                self.results_frame,
                text=f"[{item.category.upper()}]  {item.title}\n{item.subtitle}",
                anchor="w",
                font=FONT_BODY,
                height=44,
                fg_color=COLOR_SURFACE_HOVER if is_active else COLOR_SURFACE_CARD,
                text_color=COLOR_TEXT_PRIMARY,
                hover_color=COLOR_SURFACE_HOVER,
                border_color=COLOR_PRIMARY if is_active else COLOR_BORDER,
                border_width=1 if is_active else 0,
                command=lambda i=item: self._execute_item(i),
            )
            btn.pack(fill="x", pady=2)
            self.row_buttons.append(btn)

    def _on_type(self, event: Any) -> None:
        if event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        self._filter_items(self.entry.get())

    def _on_arrow_down(self, _: Any) -> str:
        if not self.filtered_items:
            return "break"
        self.selected_index = min(len(self.filtered_items) - 1, self.selected_index + 1)
        self._update_highlight()
        return "break"

    def _on_arrow_up(self, _: Any) -> str:
        if not self.filtered_items:
            return "break"
        self.selected_index = max(0, self.selected_index - 1)
        self._update_highlight()
        return "break"

    def _update_highlight(self) -> None:
        for idx, btn in enumerate(self.row_buttons):
            is_active = (idx == self.selected_index)
            btn.configure(
                fg_color=COLOR_SURFACE_HOVER if is_active else COLOR_SURFACE_CARD,
                border_width=1 if is_active else 0,
                border_color=COLOR_PRIMARY if is_active else COLOR_BORDER,
            )

    def _on_enter(self, _: Any) -> str:
        if self.filtered_items and 0 <= self.selected_index < len(self.filtered_items):
            self._execute_item(self.filtered_items[self.selected_index])
        return "break"

    def _execute_item(self, item: PaletteItem) -> None:
        """Execute selected item action and dismiss palette."""
        self.destroy()
        try:
            item.action()
        except Exception:
            pass
