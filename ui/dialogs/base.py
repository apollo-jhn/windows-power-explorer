"""Base Modal Dialog Components (ADR-011, Issue #23).

Provides accessible, focus-trapping modal dialogs with keyboard support (Escape/Enter),
destructive styling, optional typed-phrase gating, and fallback startup error handling.
"""

import sys
import tkinter.messagebox
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
        self.minsize(width, height)
        self.resizable(False, False)

        # Center on parent window or display
        self.transient(parent)
        self.after(10, self._center_on_parent, parent, width, height)

        # Modal grab
        try:
            self.grab_set()
        except Exception:
            pass

        # Keyboard and window close bindings
        self.bind("<Escape>", lambda _: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _center_on_parent(self, parent: Any, width: int, height: int) -> None:
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()

            x = max(0, min(screen_w - width, px + max(0, (pw - width) // 2)))
            y = max(0, min(screen_h - height, py + max(0, (ph - height) // 2)))
            self.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass


class ConfirmDialog(BaseDialog):
    """Confirmation modal dialog with typed phrase support and safe default focus (ADR-011)."""

    def __init__(
        self,
        parent: Any,
        title: str,
        message: str,
        on_confirm: Callable[[], None],
        confirm_text: str = "Confirm",
        cancel_text: str = "Cancel",
        is_destructive: bool = False,
        required_phrase: str | None = None,
        secondary_text: str | None = None,
        on_secondary: Callable[[], None] | None = None,
        **kwargs: Any,
    ) -> None:
        height = 260 if required_phrase else 220
        super().__init__(parent, title=title, width=460, height=height, **kwargs)
        self.on_confirm = on_confirm
        self.required_phrase = required_phrase
        self.on_secondary = on_secondary

        self._build_ui(title, message, confirm_text, cancel_text, is_destructive, secondary_text)

    def _build_ui(
        self,
        title: str,
        message: str,
        confirm_text: str,
        cancel_text: str,
        is_destructive: bool,
        secondary_text: str | None,
    ) -> None:
        self.grid_columnconfigure(0, weight=1)

        # Title Label
        ctk.CTkLabel(
            self,
            text=title,
            font=FONT_SUBTITLE,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
        ).pack(padx=20, pady=(16, 6), fill="x")

        # Message Label
        ctk.CTkLabel(
            self,
            text=message,
            font=FONT_BODY,
            text_color=COLOR_TEXT_SECONDARY,
            wraplength=420,
            justify="left",
            anchor="w",
        ).pack(padx=20, pady=(0, 10), fill="x")

        # Optional Typed-Phrase Confirmation Gate (for high-risk / destructive actions)
        self.phrase_entry = None
        if self.required_phrase:
            ctk.CTkLabel(
                self,
                text=f"Type '{self.required_phrase}' to enable confirmation:",
                font=FONT_BODY,
                text_color=COLOR_TEXT_PRIMARY,
                anchor="w",
            ).pack(padx=20, pady=(0, 4), fill="x")

            self.phrase_entry = ctk.CTkEntry(self, font=FONT_BODY)
            self.phrase_entry.pack(padx=20, pady=(0, 10), fill="x")
            self.phrase_entry.bind("<KeyRelease>", self._on_phrase_type)

        # Button Container
        btn_box = ctk.CTkFrame(self, fg_color="transparent")
        btn_box.pack(padx=20, pady=(6, 16), fill="x")

        # 1. Safe Action: Cancel Button (holds initial focus)
        cancel_btn = ctk.CTkButton(
            btn_box,
            text=cancel_text,
            font=FONT_BODY,
            fg_color=COLOR_SURFACE_SECONDARY,
            text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_SURFACE_HOVER,
            command=self.destroy,
            width=90,
        )
        cancel_btn.pack(side="right", padx=(8, 0))

        # 2. Confirm Action Button
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
        self.confirm_btn.pack(side="right", padx=(8, 0))

        # 3. Optional Secondary Action (e.g. "Export first")
        if secondary_text and self.on_secondary:
            sec_btn = ctk.CTkButton(
                btn_box,
                text=secondary_text,
                font=FONT_BODY,
                fg_color=COLOR_SURFACE_SECONDARY,
                text_color=COLOR_PRIMARY,
                hover_color=COLOR_SURFACE_HOVER,
                command=self._secondary,
                width=110,
            )
            sec_btn.pack(side="left")

        # Ensure safe Cancel button holds initial focus
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

    def _secondary(self) -> None:
        if self.on_secondary:
            self.on_secondary()


def show_startup_error(title: str, message: str) -> None:
    """Display startup failure dialog using native tkinter.messagebox (ADR-011).

    Used during early binding verification before CustomTkinter initializes.
    Ensures screen-reader accessibility and zero dependency on CTk stack.
    """
    try:
        tkinter.messagebox.showerror(title, message)
    except Exception:
        # Fallback to standard error stream if display server unavailable
        print(f"[{title}] {message}", file=sys.stderr)
