"""Hold TLS files against replacement while checking conservative Windows ACLs."""

import sys
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, cast


@contextmanager
def locked_tls_material(root: Path, cert: Path, key: Path) -> Iterator[None]:
    """Only owner, SYSTEM and administrators may have allowed ACEs."""
    stack = ExitStack()
    try:
        if sys.platform != "win32":
            raise ValueError("Unsupported platform")
        import win32api
        import win32con
        import win32file
        import win32security

        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        stack.callback(cast(Any, token).Close)
        owner = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        trusted = {win32security.ConvertSidToStringSid(owner), "S-1-5-18", "S-1-5-32-544", "S-1-3-4"}
        for path, is_directory in ((root, True), (cert, False), (key, False)):
            flags = win32file.FILE_FLAG_OPEN_REPARSE_POINT
            if is_directory:
                flags |= win32file.FILE_FLAG_BACKUP_SEMANTICS
            handle = win32file.CreateFile(str(path), win32con.GENERIC_READ | win32con.READ_CONTROL,
                                          win32con.FILE_SHARE_READ, None, win32con.OPEN_EXISTING, flags, None)
            stack.callback(handle.Close)
            attributes = win32file.GetFileInformationByHandle(int(handle))[0]
            if (attributes & win32con.FILE_ATTRIBUTE_REPARSE_POINT
                    or bool(attributes & win32con.FILE_ATTRIBUTE_DIRECTORY) != is_directory):
                raise ValueError("Invalid TLS material")
            security = win32security.GetSecurityInfo(int(handle), win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION)
            if security.GetSecurityDescriptorOwner() != owner:
                raise ValueError("Invalid owner")
            acl = security.GetSecurityDescriptorDacl()
            if acl is None:
                raise ValueError("Missing DACL")
            for index in range(acl.GetAceCount()):
                ace = acl.GetAce(index)
                kind = ace[0][0]
                if kind not in (win32security.ACCESS_ALLOWED_ACE_TYPE, win32security.ACCESS_DENIED_ACE_TYPE):
                    raise ValueError("Unsupported ACE")
                if kind == win32security.ACCESS_ALLOWED_ACE_TYPE and win32security.ConvertSidToStringSid(ace[2]) not in trusted:
                    raise ValueError("Untrusted ACE")
    except Exception:  # noqa: BLE001 - do not disclose paths or security descriptors
        stack.close()
        raise ValueError("TLS file permissions unavailable") from None
    try:
        yield
    finally:
        stack.close()
