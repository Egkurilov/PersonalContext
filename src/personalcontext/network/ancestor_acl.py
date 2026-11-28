"""Conservatively reject replaceable ancestors of the TLS directory on Windows."""

from pathlib import Path

_TRUSTED_INSTALLER = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
_REPLACEMENT_RIGHTS = 0x40 | 0x10000 | 0x40000 | 0x80000 | 0x10000000 | 0x40000000
_FILE_READ_ATTRIBUTES = 0x80


def check_ancestors(root: Path, trusted: set[str]) -> None:
    """Reject untrusted ownership or rights to delete/replace any existing ancestor."""
    import win32con
    import win32file
    import win32security

    allowed = trusted | {_TRUSTED_INSTALLER}
    allowed_owners = allowed - {"S-1-3-4"}
    for path in root.parents:
        handle = win32file.CreateFile(str(path), win32con.READ_CONTROL | _FILE_READ_ATTRIBUTES,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None, win32con.OPEN_EXISTING,
            win32file.FILE_FLAG_BACKUP_SEMANTICS | win32file.FILE_FLAG_OPEN_REPARSE_POINT, None)
        try:
            attributes = win32file.GetFileInformationByHandle(int(handle))[0]
            if attributes & win32con.FILE_ATTRIBUTE_REPARSE_POINT or not attributes & win32con.FILE_ATTRIBUTE_DIRECTORY:
                raise ValueError("Invalid ancestor")
            security = win32security.GetSecurityInfo(int(handle), win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION)
            if win32security.ConvertSidToStringSid(security.GetSecurityDescriptorOwner()) not in allowed_owners:
                raise ValueError("Invalid ancestor owner")
            acl = security.GetSecurityDescriptorDacl()
            if acl is None:
                raise ValueError("Missing ancestor DACL")
            for index in range(acl.GetAceCount()):
                ace = acl.GetAce(index)
                kind, flags = ace[0]
                if flags & win32con.INHERIT_ONLY_ACE:
                    continue
                if kind not in (win32security.ACCESS_ALLOWED_ACE_TYPE, win32security.ACCESS_DENIED_ACE_TYPE):
                    raise ValueError("Unsupported ancestor ACE")
                if (kind == win32security.ACCESS_ALLOWED_ACE_TYPE and ace[1] & _REPLACEMENT_RIGHTS
                        and win32security.ConvertSidToStringSid(ace[2]) not in allowed):
                    raise ValueError("Replaceable ancestor")
        finally:
            handle.Close()
