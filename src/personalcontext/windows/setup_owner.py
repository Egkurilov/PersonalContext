"""Explicit native owner setup; secrets never travel through the web page."""

import asyncio
import threading
from concurrent.futures import TimeoutError
from typing import Any

from personalcontext.auth.local_bootstrap import setup_local_owner


class OwnerSetupWindow:
    def __init__(self, app: Any) -> None:
        self._app = app
        self._lock = threading.Lock()

    def open(self) -> None:
        if self._lock.acquire(blocking=False):
            try:
                threading.Thread(target=self._run, name="owner-setup", daemon=True).start()
            except BaseException:
                self._lock.release()
                raise

    def _run(self) -> None:
        try:
            self._dialog()
        except Exception:  # noqa: BLE001 - avoid displaying or logging sensitive exception details
            import win32api
            import win32con

            win32api.MessageBox(0, "Не удалось открыть настройку владельца.", "PersonalContext", win32con.MB_ICONERROR)
        finally:
            self._lock.release()

    def _dialog(self) -> None:
        import tkinter as tk
        from tkinter import messagebox, simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        title = "PersonalContext — настройка владельца"
        try:
            first = simpledialog.askstring(title, "Введите пароль владельца (не менее 12 символов):",
                                           show="*", parent=root)
            if first is None:
                return
            second = simpledialog.askstring(title, "Повторите пароль:", show="*", parent=root)
            if second is None:
                return
            if first != second:
                messagebox.showerror(title, "Пароли не совпадают.", parent=root)
                return
            operation = setup_local_owner(self._app.state.scheduler.writer, self._app.state.owner_bootstrap, first)
            try:
                future = asyncio.run_coroutine_threadsafe(operation, self._app.state.loop)
            except RuntimeError:
                operation.close()
                messagebox.showerror(title, "Приложение недоступно.", parent=root)
                return
            try:
                result = future.result(timeout=30)
            except TimeoutError:
                messagebox.showerror(title, "Результат не подтверждён. Проверьте вход перед повтором.", parent=root)
                return
            except Exception:  # noqa: BLE001 - do not expose errors containing sensitive input
                messagebox.showerror(title, "Не удалось настроить владельца.", parent=root)
                return
            if result.status == "ok":
                messagebox.showinfo(title, "Владелец настроен. Теперь можно войти в приложение.", parent=root)
            else:
                messagebox.showerror(title, "Настройка не выполнена: проверьте пароль и повторите позже. "
                                     "Возможно, владелец уже настроен.", parent=root)
        finally:
            root.destroy()
