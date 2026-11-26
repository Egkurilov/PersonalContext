import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("smoke_frozen_repro", Path(__file__).resolve().parent.parent / "scripts/smoke_frozen_repro.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FrozenManifestTests(unittest.TestCase):
    def test_zip_diagnostic_identifies_order_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first.zip", Path(directory) / "second.zip"
            for path, names in ((first, ("a", "b")), (second, ("b", "a"))):
                with zipfile.ZipFile(path, "w") as archive:
                    for name in names:
                        archive.writestr(zipfile.ZipInfo(name), b"synthetic")
            detail = module.zip_diagnostic(module.zip_entries(first), module.zip_entries(second))
            self.assertEqual(detail, "zip_metadata_equal=True; zip_order_equal=False")

    def test_detects_changed_files_and_empty_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.bin").write_bytes(b"synthetic")
            original = module.manifest(root)
            (root / "empty").mkdir()
            self.assertNotEqual(original, module.manifest(root))
            (root / "sample.bin").write_bytes(b"changed")
            self.assertNotEqual(original["sample.bin"], module.manifest(root)["sample.bin"])
