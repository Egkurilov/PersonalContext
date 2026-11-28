import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import pystray
import uvicorn
import win32api
import win32con
import win32event
import winerror
from PIL import Image, ImageDraw

from personalcontext.app import create_app
from personalcontext.network.loopback.config import loopback_server_config
from personalcontext.windows.lifecycle import mutex_name, request_shutdown
from personalcontext.windows.pause_capture import PauseCapture
from personalcontext.windows.setup_owner import OwnerSetupWindow


def main() -> int:
    if sys.argv[1:] == ["--check-timezones"]:
        from personalcontext.ingest.visit.timezone_probe import verify_timezone_runtime

        return 0 if verify_timezone_runtime() else 1
    if len(sys.argv) > 1 and sys.argv[1] == "--restore":
        from personalcontext.storage.restore import main as restore_main

        sys.argv.pop(1)
        restore_main()
        return 0
    demo = "--demo" in sys.argv[1:]
    data_dir = Path(os.environ["LOCALAPPDATA"]) / "PersonalContext" / ("demo" if demo else "data")
    if "--shutdown" in sys.argv[1:]:
        return request_shutdown(data_dir)
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        win32api.MessageBox(0, "Не удалось открыть каталог данных PersonalContext.", "PersonalContext", win32con.MB_ICONERROR)
        return 1
    name = mutex_name(data_dir)
    mutex = win32event.CreateMutex(None, False, name)  # type: ignore[arg-type]  # Default security attributes are supported by pywin32.
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        mutex.Close()
        webbrowser.open("http://127.0.0.1:17890/")
        return 0
    stop_event = win32event.CreateEvent(None, True, False, name + "-stop")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 17890))
        listener.listen(128)
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        web_root = root / "frontend" / "dist"
        app = create_app(data_dir / "context.db", web_root, demo=demo)
        server = uvicorn.Server(loopback_server_config(app))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not server.started:
            server.should_exit = True
            thread.join(timeout=5)
            win32api.MessageBox(0, "Не удалось запустить PersonalContext. Проверьте доступ к каталогу данных.", "PersonalContext", win32con.MB_ICONERROR)
            return 1
        image = Image.new("RGB", (64, 64), "#111820")
        ImageDraw.Draw(image).ellipse((12, 12, 52, 52), fill="#91cdb2")
        owner_setup = OwnerSetupWindow(app)
        pause_capture = PauseCapture(app)
        icon = pystray.Icon("PersonalContext", image, "PersonalContext", menu=pystray.Menu(
            pystray.MenuItem("Открыть", lambda: webbrowser.open("http://127.0.0.1:17890/"), default=True),
            pystray.MenuItem("Настроить владельца", lambda: owner_setup.open()),
            pystray.MenuItem("Приостановить сбор", lambda: pause_capture.open()),
            pystray.MenuItem("Выход", lambda icon: icon.stop()),
        ))
        def watch_shutdown() -> None:
            win32event.WaitForSingleObject(stop_event, win32event.INFINITE)
            icon.stop()

        watcher = threading.Thread(target=watch_shutdown, daemon=True)
        def setup_tray(tray: pystray.Icon) -> None:
            tray.visible = True
            watcher.start()

        try:
            icon.run(setup=setup_tray)
        finally:
            win32event.SetEvent(stop_event)
            if watcher.is_alive():
                watcher.join(timeout=5)
            server.should_exit = True
            thread.join(timeout=10)
        return 0
    except OSError:
        win32api.MessageBox(0, "Не удалось открыть локальный порт или каталог данных.", "PersonalContext", win32con.MB_ICONERROR)
        return 1
    finally:
        listener.close()
        win32api.CloseHandle(stop_event)
        mutex.Close()


if __name__ == "__main__":
    raise SystemExit(main())
