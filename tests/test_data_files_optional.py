"""Tests for Presentational Data Files (Issue #32, REQ-10.3, REQ-10.6, REQ-10.7)."""

import json
from pathlib import Path
import tempfile
import unittest

from core.presentational_data import (
    load_doc_links,
    load_essentials,
    load_essentials_guids,
    load_reboot_required,
)


class TestPresentationalData(unittest.TestCase):

    def test_data_files_optional(self):
        """Missing or malformed data files degrade gracefully without throwing exceptions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # 1. Non-existent files
            self.assertEqual(load_essentials(tmp_path), [])
            self.assertEqual(load_essentials_guids(tmp_path), set())
            self.assertEqual(load_reboot_required(tmp_path), set())
            self.assertEqual(load_doc_links(tmp_path), {})

            # 2. Malformed / Invalid JSON files
            bad_json_file = tmp_path / "essentials.json"
            bad_json_file.write_text("{ corrupt json data ...", encoding="utf-8")
            self.assertEqual(load_essentials(tmp_path), [])

            bad_reboot = tmp_path / "reboot_required.json"
            bad_reboot.write_text("not even a dict", encoding="utf-8")
            self.assertEqual(load_reboot_required(tmp_path), set())

            bad_doc = tmp_path / "doc_links.json"
            bad_doc.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(load_doc_links(tmp_path), {})

    def test_live_data_files_integrity(self):
        """Repository presentational data files load correctly with valid structures."""
        essentials = load_essentials()
        self.assertIsInstance(essentials, list)
        self.assertGreater(len(essentials), 0)

        ess_guids = load_essentials_guids()
        self.assertIn("be337238-0d82-4146-a960-4f3749d470c7".lower(), ess_guids)

        reboot_guids = load_reboot_required()
        self.assertIsInstance(reboot_guids, set)
        self.assertIn("ee12f906-d277-404b-b6da-e5fa1a576df5".lower(), reboot_guids)

        doc_links = load_doc_links()
        self.assertIsInstance(doc_links, dict)
        self.assertIn("be337238-0d82-4146-a960-4f3749d470c7".lower(), doc_links)
        self.assertTrue(doc_links["be337238-0d82-4146-a960-4f3749d470c7".lower()].startswith("https://learn.microsoft.com"))


if __name__ == "__main__":
    unittest.main()
