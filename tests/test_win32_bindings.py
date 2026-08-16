"""Tests for core/win32_bindings.py."""

import ctypes
from ctypes import wintypes
import unittest
from unittest.mock import MagicMock, patch
import uuid

from core.errors import PowerApiError
from core.win32_bindings import (
    ERROR_MORE_DATA,
    ERROR_SUCCESS,
    GUID,
    LPGUID,
    encode_name,
    out_guid,
    parse_guid,
    read_sized_string,
    verify_bindings,
)


class TestWin32Bindings(unittest.TestCase):

    def test_guid_roundtrip_with_high_bytes(self):
        """Data4 must be c_ubyte. With signed c_byte, bytes() raises on >= 0x80."""
        guids = [
            "381b4222-f694-41f0-9685-ff5bb260df2e",
            "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",  # 0xa6, 0xe2 in Data4
            "ffffffff-ffff-ffff-ffff-ffffffffffff",  # every byte high
            "00000000-0000-0000-0000-000000000000",
            "a1841308-3541-4fab-bc81-f71556f20b4a",
        ]
        for raw in guids:
            guid_obj = GUID.from_string(raw)
            self.assertEqual(guid_obj.to_string(), raw.lower())

    def test_guid_data4_matches_bytes_le(self):
        """Guards against reconstructing Data4 from uuid.UUID.fields incorrectly."""
        raw = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
        guid_obj = GUID.from_string(raw)
        self.assertEqual(bytes(guid_obj.Data4), uuid.UUID(raw).bytes_le[8:])

    def test_guid_rejects_noncanonical(self):
        """parse_guid must strictly enforce canonical hyphenated format."""
        invalid = [
            "{8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c}",
            "urn:uuid:8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
            "8c5e7fdae8bf4a969a85a6e23a8c635c",
            "not-a-guid",
            "",
            12345,
        ]
        for bad in invalid:
            with self.assertRaises(ValueError):
                parse_guid(bad)

    def test_guid_equality_and_hash(self):
        """GUID structures with identical bytes compare equal and hash identically."""
        raw = "381b4222-f694-41f0-9685-ff5bb260df2e"
        g1 = GUID.from_string(raw)
        g2 = GUID.from_string(raw)
        g3 = GUID.from_string("8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c")

        self.assertEqual(g1, g2)
        self.assertNotEqual(g1, g3)
        self.assertNotEqual(g1, "381b4222-f694-41f0-9685-ff5bb260df2e")
        self.assertEqual(hash(g1), hash(g2))
        self.assertNotEqual(hash(g1), hash(g3))

    def test_localfree_called_once(self):
        """out_guid context manager must call kernel32.LocalFree exactly once on exit."""
        with patch("core.win32_bindings.kernel32") as mock_kernel:
            dummy_guid = GUID.from_string("381b4222-f694-41f0-9685-ff5bb260df2e")
            mock_kernel.LocalFree = MagicMock()

            # Success path
            with out_guid() as ptr:
                ptr._obj.contents = dummy_guid
            mock_kernel.LocalFree.assert_called_once()

            # Exception path
            mock_kernel.LocalFree.reset_mock()
            with self.assertRaises(RuntimeError):
                with out_guid() as ptr:
                    ptr._obj.contents = dummy_guid
                    raise RuntimeError("Boom")
            mock_kernel.LocalFree.assert_called_once()

    def test_read_sized_string(self):
        """Test buffer protocol string read with UTF-16LE decoding."""
        expected_str = "Balanced Power Plan"
        encoded_bytes = (expected_str + "\x00").encode("utf-16-le")

        FUNCTYPE = ctypes.WINFUNCTYPE(
            wintypes.DWORD,
            wintypes.HANDLE,
            LPGUID,
            LPGUID,
            LPGUID,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(wintypes.DWORD),
        )

        def mock_impl(c_root, c_scheme, c_sub, c_set, buf, size_ptr):
            if not buf:
                size_ptr.contents.value = len(encoded_bytes)
                return ERROR_SUCCESS
            ctypes.memmove(buf, encoded_bytes, len(encoded_bytes))
            size_ptr.contents.value = len(encoded_bytes)
            return ERROR_SUCCESS

        c_fn = FUNCTYPE(mock_impl)
        result = read_sized_string(c_fn, None, None, None, None)
        self.assertEqual(result, expected_str)

    def test_read_sized_string_empty(self):
        """Zero size returned must result in empty string without allocation."""
        FUNCTYPE = ctypes.WINFUNCTYPE(
            wintypes.DWORD,
            wintypes.HANDLE,
            LPGUID,
            LPGUID,
            LPGUID,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(wintypes.DWORD),
        )

        def mock_impl(c_root, c_scheme, c_sub, c_set, buf, size_ptr):
            size_ptr.contents.value = 0
            return ERROR_SUCCESS

        c_fn = FUNCTYPE(mock_impl)
        result = read_sized_string(c_fn, None, None, None, None)
        self.assertEqual(result, "")

    def test_read_sized_string_error(self):
        """Non-zero status on second call must raise PowerApiError."""
        FUNCTYPE = ctypes.WINFUNCTYPE(
            wintypes.DWORD,
            wintypes.HANDLE,
            LPGUID,
            LPGUID,
            LPGUID,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(wintypes.DWORD),
        )

        def mock_impl(c_root, c_scheme, c_sub, c_set, buf, size_ptr):
            if not buf:
                size_ptr.contents.value = 16
                return ERROR_SUCCESS
            return 2  # ERROR_FILE_NOT_FOUND

        c_fn = FUNCTYPE(mock_impl)
        with self.assertRaises(PowerApiError):
            read_sized_string(c_fn, None, None, None, None)

    def test_encode_name(self):
        """encode_name converts string to UTF-16LE with NUL terminator and rejects embedded NUL."""
        ptr, size, buf = encode_name("Test Plan")
        self.assertEqual(size.value, len(("Test Plan\x00").encode("utf-16-le")))
        self.assertEqual(buf.raw.decode("utf-16-le").rstrip("\x00"), "Test Plan")

        with self.assertRaises(ValueError):
            encode_name("Bad\x00Name")

    def test_verify_bindings(self):
        """verify_bindings executes without error on Windows."""
        self.assertTrue(verify_bindings())


if __name__ == "__main__":
    unittest.main()
