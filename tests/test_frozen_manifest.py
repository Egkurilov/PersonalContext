import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("smoke_frozen_repro", Path(__file__).resolve().parent.parent / "scripts/smoke_frozen_repro.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FrozenManifestTests(unittest.TestCase):
    def test_detects_changed_files_and_empty_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.bin").write_bytes(b"synthetic")
            original = module.manifest(root)
            (root / "empty").mkdir()
            self.assertNotEqual(original, module.manifest(root))
            (root / "sample.bin").write_bytes(b"changed")
            self.assertNotEqual(original["sample.bin"], module.manifest(root)["sample.bin"])
