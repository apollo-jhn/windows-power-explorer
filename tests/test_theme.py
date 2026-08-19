"""Tests for Theme System and WCAG AA Contrast Compliance (Issue #22, REQ-13.1, REQ-13.2)."""

import unittest
from unittest.mock import patch

from ui.theme import (
    APPEARANCE_MODES,
    COLOR_APP_BG,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_MODIFIED_BADGE,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_SURFACE_CARD,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    apply_appearance_mode,
    calculate_contrast_ratio,
    is_wcag_aa_compliant,
    relative_luminance,
    resolve_effective_mode,
)


class TestThemeSystem(unittest.TestCase):

    def test_appearance_mode_validation(self):
        """APPEARANCE_MODES defines valid modes Light, Dark, System."""
        self.assertIn("Light", APPEARANCE_MODES)
        self.assertIn("Dark", APPEARANCE_MODES)
        self.assertIn("System", APPEARANCE_MODES)

    def test_resolve_effective_mode(self):
        """resolve_effective_mode resolves 'System' via darkdetect or returns explicit mode."""
        self.assertEqual(resolve_effective_mode("Light"), "Light")
        self.assertEqual(resolve_effective_mode("Dark"), "Dark")

        with patch("darkdetect.isDark", return_value=True):
            self.assertEqual(resolve_effective_mode("System"), "Dark")

        with patch("darkdetect.isDark", return_value=False):
            self.assertEqual(resolve_effective_mode("System"), "Light")

    def test_relative_luminance_known_values(self):
        """Relative luminance of pure white is 1.0, pure black is 0.0."""
        self.assertAlmostEqual(relative_luminance("#FFFFFF"), 1.0, places=3)
        self.assertAlmostEqual(relative_luminance("#000000"), 0.0, places=3)

    def test_wcag_aa_contrast_all_palette_pairs(self):
        """All primary text and surface color pairs must meet WCAG AA contrast ratio (REQ-13.2).

        Standard body text requires >= 4.5:1.
        Large text / UI badges / components require >= 3.0:1.
        """
        # Light mode checks
        light_bg = COLOR_APP_BG[0]         # #F8FAFC
        light_card = COLOR_SURFACE_CARD[0] # #FFFFFF
        light_text_p = COLOR_TEXT_PRIMARY[0]   # #0F172A
        light_text_s = COLOR_TEXT_SECONDARY[0] # #475569
        light_primary = COLOR_PRIMARY[0]       # #0891B2
        light_warning = COLOR_WARNING[0]       # #B45309
        light_danger = COLOR_DANGER[0]         # #DC2626
        light_badge = COLOR_MODIFIED_BADGE[0]  # #7C3AED

        # Primary text on Card surface (Light)
        ratio = calculate_contrast_ratio(light_text_p, light_card)
        self.assertGreaterEqual(ratio, 4.5, f"Light primary text contrast {ratio:.2f} < 4.5:1")

        # Secondary text on Card surface (Light)
        ratio = calculate_contrast_ratio(light_text_s, light_card)
        self.assertGreaterEqual(ratio, 4.5, f"Light secondary text contrast {ratio:.2f} < 4.5:1")

        # Primary text on App Background (Light)
        ratio = calculate_contrast_ratio(light_text_p, light_bg)
        self.assertGreaterEqual(ratio, 4.5, f"Light primary on App Bg contrast {ratio:.2f} < 4.5:1")

        # UI Badges / Accent elements on Card surface (Light) - threshold 3.0:1
        self.assertTrue(is_wcag_aa_compliant(light_primary, light_card, is_large_text=True))
        self.assertTrue(is_wcag_aa_compliant(light_warning, light_card, is_large_text=True))
        self.assertTrue(is_wcag_aa_compliant(light_danger, light_card, is_large_text=True))
        self.assertTrue(is_wcag_aa_compliant(light_badge, light_card, is_large_text=True))

        # Dark mode checks
        dark_bg = COLOR_APP_BG[1]         # #1A1B26
        dark_card = COLOR_SURFACE_CARD[1] # #24283B
        dark_text_p = COLOR_TEXT_PRIMARY[1]   # #FFFFFF
        dark_text_s = COLOR_TEXT_SECONDARY[1] # #9CA3AF
        dark_primary = COLOR_PRIMARY[1]       # #06B6D4
        dark_warning = COLOR_WARNING[1]       # #F59E0B
        dark_danger = COLOR_DANGER[1]         # #EF4444
        dark_badge = COLOR_MODIFIED_BADGE[1]  # #A78BFA

        # Primary text on Card surface (Dark)
        ratio = calculate_contrast_ratio(dark_text_p, dark_card)
        self.assertGreaterEqual(ratio, 4.5, f"Dark primary text contrast {ratio:.2f} < 4.5:1")

        # Secondary text on Card surface (Dark)
        ratio = calculate_contrast_ratio(dark_text_s, dark_card)
        self.assertGreaterEqual(ratio, 4.5, f"Dark secondary text contrast {ratio:.2f} < 4.5:1")

        # Primary text on App Background (Dark)
        ratio = calculate_contrast_ratio(dark_text_p, dark_bg)
        self.assertGreaterEqual(ratio, 4.5, f"Dark primary on App Bg contrast {ratio:.2f} < 4.5:1")

        # UI Badges / Accent elements on Card surface (Dark) - threshold 3.0:1
        self.assertTrue(is_wcag_aa_compliant(dark_primary, dark_card, is_large_text=True))
        self.assertTrue(is_wcag_aa_compliant(dark_warning, dark_card, is_large_text=True))
        self.assertTrue(is_wcag_aa_compliant(dark_danger, dark_card, is_large_text=True))
        self.assertTrue(is_wcag_aa_compliant(dark_badge, dark_card, is_large_text=True))


if __name__ == "__main__":
    unittest.main()
