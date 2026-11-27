import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("repro_report", Path(__file__).resolve().parent.parent / "scripts/repro_report.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReproReportTests(unittest.TestCase):
    def test_contains_only_revision_relative_entries_and_hashes(self):
        report = module.build_report("a" * 40, {"folder": None, "folder/file.bin": b"\x12" * 32}, b"\x34" * 32)
        self.assertEqual(report["revision"], "a" * 40)
        self.assertEqual(report["bundle"]["folder/file.bin"], "12" * 32)
        self.assertIsNone(report["bundle"]["folder"])
        self.assertEqual(report["installer_sha256"], "34" * 32)

    def test_rejects_unsafe_paths_or_invalid_hashes(self):
        for name in ("../secret", "C:/outside", "/absolute", "folder\\file", "bad\nname"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                module.build_report("a" * 40, {name: b"\x12" * 32}, b"\x34" * 32)
        with self.assertRaises(ValueError):
            module.build_report("not-a-revision", {}, b"\x34" * 32)
        with self.assertRaises(ValueError):
            module.build_report("a" * 40, {"file": b"short"}, b"\x34" * 32)
