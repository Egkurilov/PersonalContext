import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from personalcontext.auth.owner_bootstrap import OwnerBootstrap
from personalcontext.auth.owner_store import find_owner_hash
from personalcontext.auth.password_executor import PasswordExecutor
from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database
from personalcontext.windows.setup_owner import OwnerSetupWindow


@unittest.skipUnless(sys.platform == "win32", "Windows native setup")
class OwnerSetupWindowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = Path(self.directory.name) / "context.db"
        initialize_database(path)
        self.writer = Writer(path)
        await self.writer.start()
        self.executor = PasswordExecutor()
        state = SimpleNamespace(scheduler=SimpleNamespace(writer=self.writer),
                                owner_bootstrap=OwnerBootstrap(self.writer, self.executor),
                                loop=asyncio.get_running_loop())
        self.window = OwnerSetupWindow(SimpleNamespace(state=state))

    async def asyncTearDown(self):
        await self.executor.close()
        await self.writer.close()
        self.directory.cleanup()

    async def test_confirmed_native_dialog_creates_owner_without_displaying_code(self):
        candidate = "synthetic dialog owner"
        with patch("tkinter.Tk"), patch("tkinter.simpledialog.askstring", side_effect=[candidate, candidate]), \
             patch("tkinter.messagebox.showinfo") as notice, patch("tkinter.messagebox.showerror") as error:
            await asyncio.to_thread(self.window._dialog)
        self.assertIsNotNone(await self.writer.submit(find_owner_hash))
        self.assertEqual(notice.call_count, 1)
        self.assertEqual(error.call_count, 0)
        self.assertNotIn(candidate, repr(notice.call_args))

    async def test_cancel_or_mismatched_password_does_not_create_owner(self):
        for replies in ([None], ["synthetic first", "synthetic second"]):
            with patch("tkinter.Tk"), patch("tkinter.simpledialog.askstring", side_effect=replies), \
                 patch("tkinter.messagebox.showerror"):
                await asyncio.to_thread(self.window._dialog)
            self.assertIsNone(await self.writer.submit(find_owner_hash))

    async def test_short_password_explains_requirement_before_bootstrap(self):
        with (patch("tkinter.Tk"), patch("tkinter.simpledialog.askstring", return_value="short") as ask,
              patch("tkinter.messagebox.showerror") as error,
              patch("personalcontext.windows.setup_owner.setup_local_owner") as setup):
            await asyncio.to_thread(self.window._dialog)
        self.assertEqual(ask.call_count, 1)
        self.assertIn("не менее 12 символов", error.call_args.args[1])
        self.assertNotIn("short", repr(error.call_args))
        setup.assert_not_called()
        self.assertIsNone(await self.writer.submit(find_owner_hash))
