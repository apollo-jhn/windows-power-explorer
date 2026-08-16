"""Live read-only Win32 integration tests against the host operating system."""

import sys
import unittest

from core.catalog import build_catalog
from core.models import PowerScheme, SettingCatalog
from core.power_manager import PowerManager
from core.values import assemble_power_scheme, load_scheme_values
from core.win32_bindings import GUID, is_elevated, parse_guid


@unittest.skipUnless(sys.platform == "win32", "Live Win32 integration tests require Windows")
class TestLiveIntegration(unittest.TestCase):

    def setUp(self):
        self.pm = PowerManager()

    def test_get_active_scheme_live(self):
        """Live PowerGetActiveScheme returns a valid canonical GUID."""
        active = self.pm.get_active_scheme_guid()
        self.assertIsInstance(active, str)
        parsed = parse_guid(active)
        self.assertEqual(parsed.to_string(), active.lower())

    def test_enumerate_schemes_live(self):
        """Live PowerEnumerate(ACCESS_SCHEME) discovers at least one active scheme."""
        schemes = list(self.pm.iter_schemes())
        self.assertGreater(len(schemes), 0)
        active_found = any(is_active for _, _, _, is_active, _ in schemes)
        self.assertTrue(active_found, "At least one scheme must be marked active")

    def test_two_phase_catalog_and_values_live(self):
        """Live test of Two-Phase Load: building catalog and loading values."""
        catalog = build_catalog(self.pm)
        self.assertIsInstance(catalog, SettingCatalog)
        self.assertGreater(len(catalog.subgroups), 0)

        total_settings = sum(len(sub.settings) for sub in catalog.subgroups)
        self.assertGreater(total_settings, 10, "Should discover power settings across subgroups")

        active_guid = self.pm.get_active_scheme_guid()
        values = load_scheme_values(active_guid, catalog, self.pm)
        self.assertEqual(values.scheme_guid.lower(), active_guid.lower())

        scheme = assemble_power_scheme(
            scheme_guid=active_guid,
            friendly_name="Active Plan",
            description="",
            is_active=True,
            is_base_default=False,
            catalog=catalog,
            values=values,
        )
        self.assertIsInstance(scheme, PowerScheme)
        self.assertTrue(scheme.is_active)


if __name__ == "__main__":
    unittest.main()
