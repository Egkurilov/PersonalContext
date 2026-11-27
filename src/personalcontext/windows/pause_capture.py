"""Owner-initiated native pause; no activity collection is started here."""

import asyncio
import threading
import time
from typing import Any

from personalcontext.privacy.policy_pause import pause_local


class PauseCapture:
    def __init__(self, app: Any) -> None:
        self._app = app
        self._lock = threading.Lock()

    def open(self) -> None:
        if self._lock.acquire(blocking=False):
            try:
                threading.Thread(target=self._run, name="capture-pause", daemon=True).start()
            except BaseException:
                self._lock.release()
                raise

    def _run(self) -> None:
        import win32api
        import win32con

        try:
            operation = self._app.state.scheduler.writer.submit(
                lambda connection: pause_local(connection, now=int(time.time())),
            )
            try:
                future = asyncio.run_coroutine_threadsafe(operation, self._app.state.loop)
            except RuntimeError:
                operation.close()
                raise
            result = future.result(timeout=10)
            if result.status != "ok":
                raise RuntimeError("Pause unavailable")
            message = ("Политика приостановлена. Отключённые устройства могут следовать своей политике до её истечения. "
                       "Возобновление требует нового разрешения.")
            flags = win32con.MB_ICONINFORMATION
        except Exception:  # noqa: BLE001 - do not disclose details from the database or runtime
            message = "Не удалось подтвердить паузу. Проверьте состояние приложения."
            flags = win32con.MB_ICONERROR
        finally:
            self._lock.release()
        win32api.MessageBox(0, message, "PersonalContext", flags | win32con.MB_TOPMOST | win32con.MB_SETFOREGROUND)
