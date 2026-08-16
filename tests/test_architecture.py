"""Architecture and structural invariant assertions."""

import ast
from pathlib import Path
import unittest


class TestArchitecture(unittest.TestCase):

    def test_core_never_imports_ui(self):
        """core/ must never import from ui/ (strict layered architecture)."""
        core_dir = Path(__file__).resolve().parent.parent / "core"
        for py_file in core_dir.rglob("*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(
                            alias.name.startswith("ui"),
                            f"{py_file} illegally imports {alias.name}",
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self.assertFalse(
                            node.module.startswith("ui"),
                            f"{py_file} illegally imports from {node.module}",
                        )

    def test_no_network_imports(self):
        """core/ must remain completely offline with no network or telemetry libraries."""
        prohibited = {
            "socket",
            "urllib.request",
            "http.client",
            "requests",
            "aiohttp",
            "httpx",
            "urllib3",
            "ftplib",
            "poplib",
            "imaplib",
            "smtplib",
        }
        core_dir = Path(__file__).resolve().parent.parent / "core"
        for py_file in core_dir.rglob("*.py"):
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_pkg = alias.name.split(".")[0]
                        self.assertNotIn(
                            alias.name,
                            prohibited,
                            f"{py_file} contains prohibited network import: {alias.name}",
                        )
                        self.assertNotIn(
                            root_pkg,
                            prohibited,
                            f"{py_file} contains prohibited network import: {alias.name}",
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        root_pkg = node.module.split(".")[0]
                        self.assertNotIn(
                            node.module,
                            prohibited,
                            f"{py_file} contains prohibited network import: {node.module}",
                        )
                        self.assertNotIn(
                            root_pkg,
                            prohibited,
                            f"{py_file} contains prohibited network import: {node.module}",
                        )


if __name__ == "__main__":
    unittest.main()
