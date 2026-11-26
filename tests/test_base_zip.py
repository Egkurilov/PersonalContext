import importlib.util
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("normalize_base_zip", Path(__file__).resolve().parent.parent / "scripts/normalize_base_zip.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BaseZipTests(unittest.TestCase):
    def test_sorts_entries_without_changing_payloads(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.zip", Path(directory) / "second.zip"
            for path, names in ((first, ("b.pyc", "a.pyc")), (second, ("a.pyc", "b.pyc"))):
                with zipfile.ZipFile(path, "w") as archive:
                    for name in names:
                        archive.writestr(zipfile.ZipInfo(name), f"synthetic-{name}".encode())
            self.assertNotEqual(first.read_bytes(), second.read_bytes())
            module.normalize(first)
            module.normalize(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), ["a.pyc", "b.pyc"])
                self.assertEqual(archive.read("b.pyc"), b"synthetic-b.pyc")

    def test_rejects_duplicate_names_without_modifying_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.zip"
            with warnings.catch_warnings(), zipfile.ZipFile(path, "w") as archive:
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr("same.pyc", b"first")
                archive.writestr("same.pyc", b"second")
            original = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "duplicate"):
                module.normalize(path)
            self.assertEqual(path.read_bytes(), original)
