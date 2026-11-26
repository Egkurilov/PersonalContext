import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from personalcontext.build_tools.node_archive import extract_verified


class NodeArchiveTests(unittest.TestCase):
    def test_rejects_wrong_hash_and_unsafe_member(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "fixture.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("fixture/../../escape.txt", "synthetic")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "checksum"):
                extract_verified(archive, root / "output", "fixture", "0" * 64)
            with self.assertRaisesRegex(ValueError, "archive"):
                extract_verified(archive, root / "output", "fixture", digest)
            self.assertFalse((root / "escape.txt").exists())

    def test_extracts_verified_safe_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "fixture.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("fixture/node.exe", "synthetic executable")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            extract_verified(archive, root / "output", "fixture", digest)
            self.assertEqual((root / "output/fixture/node.exe").read_text(), "synthetic executable")
