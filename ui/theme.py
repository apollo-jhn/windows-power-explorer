"""Centralized UI Theme and WCAG AA Palettes for Windows Power Explorer (REQ-13.1, REQ-13.2, Issue #22).

Defines:
- Three-mode appearance system (Light / Dark / System)
- System default appearance via darkdetect (REQ-13.1)
- Centralized (light, dark) CustomTkinter color tuples per CLI/UX Spec §1.1
- Relative luminance and WCAG AA contrast ratio compliance helpers (REQ-13.2)
- Segoe UI typography hierarchy
"""

from typing import Tuple

import customtkinter as ctk

# WCAG AA Compliant (light, dark) Color Tuples (CLI/UX Spec §1.1)
COLOR_APP_BG = ("#F8FAFC", "#1A1B26")
COLOR_SURFACE_CARD = ("#FFFFFF", "#24283B")
COLOR_SURFACE_HOVER = ("#F1F5F9", "#2E334D")
COLOR_SURFACE_SECONDARY = ("#F1F5F9", "#1E2233")

COLOR_PRIMARY = ("#0891B2", "#06B6D4")
COLOR_PRIMARY_HOVER = ("#0E7490", "#0891B2")

COLOR_SUCCESS = ("#059669", "#10B981")
COLOR_WARNING = ("#B45309", "#F59E0B")
COLOR_DANGER = ("#DC2626", "#EF4444")
COLOR_DANGER_HOVER = ("#B91C1C", "#DC2626")

COLOR_TEXT_PRIMARY = ("#0F172A", "#FFFFFF")
COLOR_TEXT_SECONDARY = ("#475569", "#9CA3AF")
COLOR_TEXT_MUTED = ("#64748B", "#6B7280")

COLOR_BORDER = ("#E2E8F0", "#374151")
COLOR_MODIFIED_BADGE = ("#7C3AED", "#A78BFA")
COLOR_MODIFIED_BG = ("#EDE9FE", "#2E1065")

# Typography
FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 16, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 13, "bold")
FONT_BODY = (FONT_FAMILY, 12, "normal")
FONT_BODY_BOLD = (FONT_FAMILY, 12, "bold")
FONT_SMALL = (FONT_FAMILY, 10, "normal")
FONT_BADGE = (FONT_FAMILY, 10, "bold")

# Valid appearance modes
APPEARANCE_MODES = ("Light", "Dark", "System")


def apply_appearance_mode(mode: str) -> None:
    """Set CustomTkinter appearance mode with validation (REQ-13.1)."""
    norm = mode.strip().capitalize()
    if norm not in APPEARANCE_MODES:
        norm = "System"
    ctk.set_appearance_mode(norm)


def get_appearance_mode() -> str:
    """Return currently active CustomTkinter appearance mode."""
    return ctk.get_appearance_mode()


def resolve_effective_mode(mode: str = "System") -> str:
    """Resolve 'System' mode into effective 'Dark' or 'Light' using darkdetect (REQ-13.1)."""
    norm = mode.strip().capitalize()
    if norm in ("Light", "Dark"):
        return norm

    try:
        import darkdetect
        if darkdetect.isDark():
            return "Dark"
        return "Light"
    except Exception:
        return "Light"


def relative_luminance(hex_color: str) -> float:
    """Calculate the relative luminance of an sRGB color per WCAG 2.1 specifications."""
    hex_clean = hex_color.lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join(c * 2 for c in hex_clean)
    r = int(hex_clean[0:2], 16) / 255.0
    g = int(hex_clean[2:4], 16) / 255.0
    b = int(hex_clean[4:6], 16) / 255.0

    def adjust(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r_lin = adjust(r)
    g_lin = adjust(g)
    b_lin = adjust(b)

    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def calculate_contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate the contrast ratio between two hex colors per WCAG 2.1 specifications.

    Returns a value between 1.0 and 21.0.
    """
    l1 = relative_luminance(hex1)
    l2 = relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def is_wcag_aa_compliant(text_hex: str, bg_hex: str, is_large_text: bool = False) -> bool:
    """Verify if a text/background pair meets WCAG AA contrast requirements (REQ-13.2).

    Requires >= 4.5:1 for standard body text, or >= 3.0:1 for large text/UI badges.
    """
    threshold = 3.0 if is_large_text else 4.5
    return calculate_contrast_ratio(text_hex, bg_hex) >= threshold
