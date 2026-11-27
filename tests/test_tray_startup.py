import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Windows tray entrypoint required")
class TrayStartupTests(unittest.TestCase):
    def test_setup_displays_icon_and_starts_shutdown_watcher(self):
        from personalcontext.__main__ import main

        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "frontend/dist/assets").mkdir(parents=True)
            with (patch.dict(os.environ, {"LOCALAPPDATA": directory}),
                  patch("sys.argv", ["personalcontext"]),
                  patch("sys._MEIPASS", directory, create=True),
                  patch("personalcontext.__main__.pystray.Icon") as icon):
                instance = icon.return_value
                instance.visible = False

                def run(*, setup):
                    setup(instance)
                    self.assertTrue(instance.visible)

                instance.run.side_effect = run
                self.assertEqual(main(), 0)
                instance.stop.assert_called_once()
