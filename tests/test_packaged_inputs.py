import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("check_packaged_inputs", Path(__file__).resolve().parent.parent / "scripts/check_packaged_inputs.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackagedInputTests(unittest.TestCase):
    def test_migrations_match_source_and_reject_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, bundled = root / "source", root / "bundled"
            (source / "versions").mkdir(parents=True)
            (bundled / "versions").mkdir(parents=True)
            for path in (source, bundled):
                (path / "env.py").write_bytes(b"synthetic")
                (path / "versions/0001.py").write_bytes(b"synthetic version")
            (source / "__pycache__").mkdir()
            (source / "__pycache__/env.pyc").write_bytes(b"generated")
            module.verify_migrations(source, bundled)
            (bundled / "env.pyc").write_bytes(b"generated")
            with self.assertRaisesRegex(ValueError, "migration"):
                module.verify_migrations(source, bundled)
            (bundled / "env.pyc").unlink()
            (bundled / "env.py").write_bytes(b"different")
            with self.assertRaisesRegex(ValueError, "migration"):
                module.verify_migrations(source, bundled)

    def test_rejects_application_local_windows_system_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "VCRUNTIME140.dll").write_bytes(b"synthetic")
            module.verify_system_runtime(root)
            for name in ("ucrtbase.dll", "api-ms-win-crt-runtime-l1-1-0.dll", "api-ms-win-core-file-l1-1-0.dll"):
                path = root / name
                path.write_bytes(b"synthetic")
                with self.assertRaisesRegex(ValueError, "system runtime"):
                    module.verify_system_runtime(root)
                path.unlink()
