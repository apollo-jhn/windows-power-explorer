"""Base Modal Dialog Components (ADR-011).

Provides accessible, focus-trapping modal dialogs with keyboard support (Escape/Enter).
"""

from typing import Any, Callable

import customtkinter as ctk

from ui.theme import (
    COLOR_APP_BG,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SURFACE_CARD,
    COLOR_SURFACE_HOVER,
    COLOR_SURFACE_SECONDARY,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_SUBTITLE,
)


class BaseDialog(ctk.CTkToplevel):
    """Base modal toplevel handling centering, focus trapping, and Escape closing."""

    def __init__(
        self,
        parent: Any,
        title: str = "",
        width: int = 480,
        height: int = 240,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, fg_color=COLOR_APP_BG, **kwargs)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)

        # Center on parent
        self.transient(parent)
        self.after(10, self._center_on_parent, parent, width, height)

        # Modal grab
        self.grab_set()
        self.bind("<Escape>", lambda _: self.destroy())

    def _center_on_parent(self, parent: Any, width: int, height: int) -> None:
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + max(0, (pw - width) // 2)
            y = py + max(0, (ph - height) // 2)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass


class ConfirmDialog(BaseDialog):
    """Confirmation modal dialog with typed phrase support (ADR-011)."""

    def __init__(
        self,
        parent: Any,
        title: str,
        message: str,
        on_confirm: Callable[[], None],
        confirm_text: str = "Confirm",
        is_destructive: bool = False,
        required_phrase: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, title=title, width=440, height=220, **kwargs)
        self.on_confirm = on_confirm
        self.required_phrase = required_phrase

        self._build_ui(title, message, confirm_text, is_destructive)

    def _build_ui(self, title: str, message: str, confirm_text: str, is_destructive: bool) -> None:
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=title,
            font=FONT_SUBTITLE,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(padx=20, pady=(16, 8), fill="x")

        ctk.CTkLabel(
            self,
            text=message,
            font=FONT_BODY,
            text_color=COLOR_TEXT_SECONDARY,
            wraplength=400,
            justify="left",
            anchor="w",
        ).pack(padx=20, pady=(0, 12), fill="x")

        self.phrase_entry = None
        if self.required_phrase:
            ctk.CTkLabel(
                self,
                text=f"Type '{self.required_phrase}' to confirm:",
                font=FONT_BODY,
                text_color=COLOR_TEXT_PRIMARY,
            ).pack(padx=20, pady=(0, 4), anchor="w")

            self.phrase_entry = ctk.CTkEntry(self, font=FONT_BODY)
            self.phrase_entry.pack(padx=20, pady=(0, 12), fill="x")
            self.phrase_entry.bind("<KeyRelease>", self._on_phrase_type)

        btn_box = ctk.CTkFrame(self, fg_color="transparent")
        btn_box.pack(padx=20, pady=(8, 16), fill="x")

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

        btn_color = COLOR_DANGER if is_destructive else COLOR_PRIMARY
        self.confirm_btn = ctk.CTkButton(
            btn_box,
            text=confirm_text,
            font=FONT_BODY_BOLD,
            fg_color=btn_color,
            command=self._confirm,
            width=100,
            state="disabled" if self.required_phrase else "normal",
        )
        self.confirm_btn.pack(side="right")

        # Initial focus on safe Cancel action
        cancel_btn.focus_set()

    def _on_phrase_type(self, _: Any) -> None:
        if self.phrase_entry and self.required_phrase:
            typed = self.phrase_entry.get().strip()
            self.confirm_btn.configure(
                state="normal" if typed == self.required_phrase else "disabled"
            )

    def _confirm(self) -> None:
        self.destroy()
        self.on_confirm()
