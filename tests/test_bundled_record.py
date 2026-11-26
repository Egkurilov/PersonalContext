import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("prune_alembic_record", Path(__file__).resolve().parent.parent / "scripts/prune_alembic_record.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BundledRecordTests(unittest.TestCase):
    def test_only_unshipped_launcher_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "RECORD"
            path.write_bytes(b"alembic/module.py,sha256=synthetic,1\n../../Scripts/alembic.exe,sha256=path-specific,2\n")
            module.prune(path)
            self.assertEqual(path.read_bytes(), b"alembic/module.py,sha256=synthetic,1\n")

    def test_unexpected_metadata_is_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "RECORD"
            for original in (b"alembic/module.py,sha256=synthetic,1\n",
                             b"../../Scripts/alembic.exe,sha256=a,1\n" * 2):
                path.write_bytes(original)
                with self.assertRaisesRegex(ValueError, "launcher"):
                    module.prune(path)
                self.assertEqual(path.read_bytes(), original)
