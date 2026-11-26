import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == "win32", "Windows named objects required")
class ShutdownTests(unittest.TestCase):
    def test_absent_instance_and_incomplete_startup(self):
        import win32api
        import win32event

        from personalcontext.windows.lifecycle import mutex_name, request_shutdown

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.assertEqual(request_shutdown(path), 0)
            mutex = win32event.CreateMutex(None, False, mutex_name(path))
            try:
                self.assertEqual(request_shutdown(path), 1)
            finally:
                win32api.CloseHandle(mutex)

    def test_shutdown_signals_and_waits_for_instance(self):
        import win32api
        import win32event

        from personalcontext.windows.lifecycle import mutex_name, request_shutdown

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            name = mutex_name(path)
            mutex = win32event.CreateMutex(None, False, name)
            event = win32event.CreateEvent(None, True, False, name + "-stop")
            results = []
            def instance():
                results.append(win32event.WaitForSingleObject(event, 5000))
                time.sleep(0.2)
                win32api.CloseHandle(mutex)

            worker = threading.Thread(target=instance)
            worker.start()
            try:
                self.assertEqual(request_shutdown(path), 0)
            finally:
                worker.join(timeout=6)
                win32api.CloseHandle(event)
            self.assertFalse(worker.is_alive())
            self.assertEqual(results, [win32event.WAIT_OBJECT_0])
