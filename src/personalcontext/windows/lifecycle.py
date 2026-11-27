import hashlib
import time
from pathlib import Path

import pywintypes
import win32api
import win32event
import winerror


def mutex_name(data_dir: Path) -> str:
    name = hashlib.sha256(str(data_dir.resolve()).casefold().encode()).hexdigest()
    return "Local\\PersonalContext-" + name


def request_shutdown(data_dir: Path) -> int:
    name = mutex_name(data_dir)
    try:
        event = win32event.OpenEvent(win32event.EVENT_MODIFY_STATE, False, name + "-stop")
    except pywintypes.error as error:
        if error.winerror != winerror.ERROR_FILE_NOT_FOUND:
            raise
        try:
            mutex = win32event.OpenMutex(win32event.SYNCHRONIZE, False, name)
        except pywintypes.error as mutex_error:
            if mutex_error.winerror == winerror.ERROR_FILE_NOT_FOUND:
                return 0
            raise
        win32api.CloseHandle(mutex)
        return 1
    try:
        win32event.SetEvent(event)
    finally:
        win32api.CloseHandle(event)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            mutex = win32event.OpenMutex(win32event.SYNCHRONIZE, False, name)
        except pywintypes.error as error:
            if error.winerror == winerror.ERROR_FILE_NOT_FOUND:
                return 0
            raise
        win32api.CloseHandle(mutex)
        time.sleep(0.1)
    return 1
