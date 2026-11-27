import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("normalize_packaged_text", Path(__file__).resolve().parent.parent / "scripts/normalize_packaged_text.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackagedTextTests(unittest.TestCase):
    def test_normalizes_crlf_and_preserves_other_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.py"
            path.write_bytes(b"first\r\nsecond\nthird\r\n")
            module.normalize(path)
            self.assertEqual(path.read_bytes(), b"first\nsecond\nthird\n")

    def test_rejects_invalid_utf8_without_modifying_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.py"
            original = b"\xff\r\n"
            path.write_bytes(original)
            with self.assertRaises(UnicodeDecodeError):
                module.normalize(path)
            self.assertEqual(path.read_bytes(), original)
