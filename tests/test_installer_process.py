"""Installer child processes must not retain the CI runner's output pipe."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_nonzero_exit_preserves_check_semantics(self):
        from scripts.installer_process import run_installer

        command = [sys.executable, "-c", "raise SystemExit(7)"]
        self.assertEqual(run_installer(command, check=False).returncode, 7)
        with self.assertRaises(subprocess.CalledProcessError):
            run_installer(command, check=True)

    @unittest.skipUnless(sys.platform == "win32", "Windows process-tree behavior")
    def test_tree_cleanup_failure_is_reported(self):
        from scripts.installer_process import run_installer

        command = [sys.executable, "-c", "import time; time.sleep(10)"]
        with (patch("scripts.installer_process.subprocess.run", side_effect=OSError("synthetic")),
              self.assertRaisesRegex(RuntimeError, "Unable to stop installer process tree")):
            run_installer(command, check=True, timeout=0.2)

    @unittest.skipUnless(sys.platform == "win32", "Windows process-tree behavior")
    def test_timeout_terminates_synthetic_descendant(self):
        from scripts.installer_process import run_installer

        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "synthetic.txt"
            ready = Path(directory) / "ready.txt"
            child = ("import pathlib,sys,time; pathlib.Path(sys.argv[2]).write_text('ready'); "
                     "time.sleep(3); pathlib.Path(sys.argv[1]).write_text('synthetic')")
            parent = ("import subprocess,sys,time; "
                      "subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2],sys.argv[3]],"
                      "creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)); time.sleep(10)")
            with self.assertRaises(subprocess.TimeoutExpired):
                run_installer([sys.executable, "-c", parent, child, str(marker), str(ready)], check=True, timeout=1.5)
            time.sleep(3)
            self.assertTrue(ready.exists())
            self.assertFalse(marker.exists())
