import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "scripts/check_python.py"
spec = importlib.util.spec_from_file_location("check_python", path)
assert spec and spec.loader
check_python = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_python)


class PythonPinTests(unittest.TestCase):
    def test_accepts_exact_version_and_rejects_mismatch_or_invalid_pin(self):
        check_python.require_pinned_version("3.12.16", (3, 12, 16))
        for pin, actual in (("3.12.16", (3, 12, 10)), ("3.12", (3, 12, 16)),
                            ("3.13.0", (3, 13, 0)), ("3.12.16\nextra", (3, 12, 16))):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                check_python.require_pinned_version(pin, actual)
