"""Read-only probe for WFP filter change subscription permission on Windows."""

import ctypes
import sys
from ctypes import wintypes


def check_subscription() -> bool:
    if sys.platform != "win32":
        return False

    class Guid(ctypes.Structure):
        _fields_ = [("data1", wintypes.DWORD), ("data2", wintypes.WORD),
                    ("data3", wintypes.WORD), ("data4", ctypes.c_ubyte * 8)]

    class Subscription(ctypes.Structure):
        _fields_ = [("template", ctypes.c_void_p), ("flags", wintypes.DWORD), ("session", Guid)]

    callback_type = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
    callback = callback_type(lambda _context, _change: None)
    engine, subscription = wintypes.HANDLE(), wintypes.HANDLE()
    try:
        api = ctypes.WinDLL("fwpuclnt.dll")
        api.FwpmEngineOpen0.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p,
                                        ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
        api.FwpmEngineOpen0.restype = wintypes.DWORD
        api.FwpmFilterSubscribeChanges0.argtypes = [wintypes.HANDLE, ctypes.POINTER(Subscription), callback_type,
                                                     ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
        api.FwpmFilterSubscribeChanges0.restype = wintypes.DWORD
        api.FwpmFilterUnsubscribeChanges0.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        api.FwpmFilterUnsubscribeChanges0.restype = wintypes.DWORD
        api.FwpmEngineClose0.argtypes = [wintypes.HANDLE]
        api.FwpmEngineClose0.restype = wintypes.DWORD
        if api.FwpmEngineOpen0(None, 10, None, None, ctypes.byref(engine)) != 0:
            return False
        try:
            spec = Subscription(None, 3, Guid())  # all filters, additions and deletions
            if api.FwpmFilterSubscribeChanges0(engine, ctypes.byref(spec), callback, None, ctypes.byref(subscription)) != 0:
                return False
            return api.FwpmFilterUnsubscribeChanges0(engine, subscription) == 0
        finally:
            api.FwpmEngineClose0(engine)
    except (AttributeError, OSError, ValueError):
        return False


if __name__ == "__main__":
    available = check_subscription()
    print("WFP filter change subscription: " + ("available" if available else "unavailable"))
    sys.exit(0 if available else 1)
