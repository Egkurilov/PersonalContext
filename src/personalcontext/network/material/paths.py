"""Validate and hold the Windows TLS directory and material for a caller."""

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from personalcontext.network.private_settings import valid_material_names
from personalcontext.network.tls_file_acl import locked_tls_material


@contextmanager
def validated_tls_material(root: Path, cert_name: str, key_name: str) -> Iterator[tuple[Path, Path]]:
    if sys.platform != "win32" or not valid_material_names(cert_name, key_name):
        raise ValueError("Invalid TLS storage")
    import win32api
    import win32con
    import win32file

    base = root.absolute()
    if win32file.GetFileAttributes(str(base)) & win32con.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError("Invalid TLS storage")
    resolved = base.resolve(strict=True)
    drive, _ = os.path.splitdrive(str(resolved))
    if (len(drive) != 2 or drive[1] != ":" or win32file.GetDriveType(drive + "\\") != win32file.DRIVE_FIXED
            or win32api.GetVolumeInformation(drive + "\\")[4].upper() != "NTFS" or not resolved.is_dir()):
        raise ValueError("Invalid TLS storage")
    cert, key = (resolved / cert_name).resolve(strict=True), (resolved / key_name).resolve(strict=True)
    if (cert.parent != resolved or key.parent != resolved or not cert.is_file() or not key.is_file()
            or not 0 < cert.stat().st_size <= 1048576 or not 0 < key.stat().st_size <= 1048576):
        raise ValueError("Invalid TLS storage")
    with locked_tls_material(resolved, cert, key):
        yield cert, key
