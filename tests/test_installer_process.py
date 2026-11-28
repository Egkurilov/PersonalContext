"""Synthetic installers with descendants must not make timeout handling hang."""

import importlib.util
import subprocess
import sys
import time
import unittest
from pathlib import Path


class InstallerProcessTests(unittest.TestCase):
    def test_timeout_remains_bounded_with_inherited_output_handles(self):
        path = Path(__file__).resolve().parent.parent / "scripts/installer_process.py"
        spec = importlib.util.spec_from_file_location("installer_process", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        executable = getattr(sys, "_base_executable", sys.executable)
        child = "import time; time.sleep(5)"
        parent = ("import subprocess,sys,time; "
                  "subprocess.Popen([sys.executable,'-c',sys.argv[1]]); time.sleep(10)")
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            module.run_installer([executable, "-c", parent, child], check=True, timeout=0.5)
        self.assertLess(time.monotonic() - started, 3)
