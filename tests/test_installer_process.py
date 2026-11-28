"""Installer child processes must not retain the CI runner's output pipe."""

import importlib.util
import os
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

    def test_descendant_does_not_hold_parent_output_pipe(self):
        scripts = str(Path(__file__).resolve().parents[1] / "scripts")
        child = "import subprocess,sys; subprocess.Popen([sys.executable,'-c','import time; time.sleep(8)'])"
        wrapper = ("import sys; sys.path.insert(0," + repr(scripts) + "); "
                   "from installer_process import run_installer; "
                   "run_installer([sys.executable,'-c'," + repr(child) + "],check=True)")
        result = subprocess.run([sys.executable, "-c", wrapper], capture_output=True, timeout=5, check=True)
        self.assertEqual(result.returncode, 0)

    def test_synthetic_environment_is_passed(self):
        from scripts.installer_process import run_installer

        env = os.environ.copy()
        env["PC_SYNTHETIC_INSTALLER_TEST"] = "yes"
        command = [sys.executable, "-c", "import os,sys; sys.exit(os.getenv('PC_SYNTHETIC_INSTALLER_TEST') != 'yes')"]
        self.assertEqual(run_installer(command, check=True, env=env).returncode, 0)
