import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class CloneDiagnosticsTests(unittest.TestCase):
    def test_failure_reports_safe_category_without_raw_output(self):
        scripts = str(Path(__file__).resolve().parent.parent / "scripts")
        with patch.object(sys, "path", [scripts, *sys.path]):
            from smoke_clone_repro import run

        with tempfile.TemporaryDirectory() as directory:
            code = "import sys; print('not found in the cache; synthetic private path', file=sys.stderr); sys.exit(3)"
            with self.assertRaises(RuntimeError) as failure:
                run("Python setup", [sys.executable, "-c", code], Path(directory), os.environ.copy())
        self.assertIn("offline dependency cache incomplete", str(failure.exception))
        self.assertNotIn("synthetic private path", str(failure.exception))
