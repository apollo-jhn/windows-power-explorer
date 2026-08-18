"""Search and Filter Header Component (Issue #21, REQ-5.1, REQ-10.2).

Provides:
- Live search query input with 120ms debounce (TDD §7)
- "Modified only" toggle switch (REQ-9.4)
- Clear search action on Escape / Clear button
"""

from typing import Any, Callable

import customtkinter as ctk

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
    FONT_SMALL,
    FONT_SUBTITLE,
)


class SearchBar(ctk.CTkFrame):
    """Header search and filter bar with debounced live querying."""

    def __init__(
        self,
        master: Any,
        on_query_changed: Callable[[str], None],
        on_modified_toggle: Callable[[bool], None],
        on_create_scheme: Callable[[], None] | None = None,
        debounce_ms: int = 120,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master,
            fg_color=COLOR_SURFACE_CARD,
            border_color=COLOR_BORDER,
            border_width=1,
            corner_radius=0,
            height=56,
            **kwargs,
        )
        self.on_query_changed = on_query_changed
        self.on_modified_toggle = on_modified_toggle
        self.on_create_scheme = on_create_scheme
        self.debounce_ms = debounce_ms

        self._after_job: Any = None
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct header elements."""
        self.grid_columnconfigure(1, weight=1)

        # 1. App Title / Logo
        title_box = ctk.CTkFrame(self, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=(16, 12), pady=12, sticky="w")

        title_lbl = ctk.CTkLabel(
            title_box,
            text="⚡ Windows Power Explorer",
            font=FONT_SUBTITLE,
            text_color=COLOR_TEXT_PRIMARY,
        )
        title_lbl.pack(side="left")

        # 2. Search Entry Box
        search_box = ctk.CTkFrame(self, fg_color="transparent")
        search_box.grid(row=0, column=1, padx=8, pady=12, sticky="ew")
        search_box.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            search_box,
            placeholder_text="Search settings, descriptions, GUIDs, choices... (Ctrl+F)",
            font=FONT_BODY,
            height=34,
            border_color=COLOR_BORDER,
            corner_radius=6,
        )
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<Escape>", lambda _: self.clear())

        # 3. "Modified only" toggle switch (REQ-9.4)
        self.mod_switch = ctk.CTkSwitch(
            self,
            text="Modified only",
            font=FONT_SMALL,
            command=self._on_switch_toggle,
        )
        self.mod_switch.grid(row=0, column=2, padx=(8, 12), pady=12, sticky="e")

        # 4. "+ New Scheme" button (REQ-1.1)
        if self.on_create_scheme:
            self.new_btn = ctk.CTkButton(
                self,
                text="+ New Scheme",
                font=FONT_BODY,
                fg_color=COLOR_PRIMARY,
                height=32,
                width=110,
                corner_radius=6,
                command=self.on_create_scheme,
            )
            self.new_btn.grid(row=0, column=3, padx=(0, 16), pady=12, sticky="e")

    def _on_key_release(self, event: Any) -> None:
        """Debounce keystroke query dispatch (TDD §7)."""
        if event.keysym in ("Escape", "Return", "Up", "Down", "Left", "Right"):
            return

        if self._after_job is not None:
            self.after_cancel(self._after_job)

        self._after_job = self.after(self.debounce_ms, self._dispatch_query)

    def _dispatch_query(self) -> None:
        """Send search query to controller callback."""
        self._after_job = None
        query = self.entry.get()
        self.on_query_changed(query)

    def _on_switch_toggle(self) -> None:
        """Send modified-only toggle state to controller callback."""
        is_mod = bool(self.mod_switch.get())
        self.on_modified_toggle(is_mod)

    def clear(self) -> None:
        """Clear search input and dispatch update."""
        self.entry.delete(0, "end")
        self._dispatch_query()

    def focus(self) -> None:
        """Focus the search input widget."""
        self.entry.focus_set()
