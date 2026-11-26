import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class FrozenPythonTests(unittest.TestCase):
    def test_matching_and_different_runtime_files(self):
        root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            bundled = Path(directory) / "bundled.dll"
            runtime = Path(directory) / "runtime.dll"
            bundled.write_bytes(b"synthetic runtime")
            runtime.write_bytes(b"synthetic runtime")
            code = "from check_frozen_python import compare_runtime; import sys; from pathlib import Path; compare_runtime(Path(sys.argv[1]), Path(sys.argv[2]))"
            command = [sys.executable, "-c", code, str(bundled), str(runtime)]
            environment = {"PYTHONPATH": str(root / "scripts")}
            result = subprocess.run(command, env=os.environ | environment, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0)
            runtime.write_bytes(b"different synthetic runtime")
            result = subprocess.run(command, env=os.environ | environment, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
