import os
import sys
import tempfile
import unittest
from pathlib import Path

from personalcontext.network.tls_file_acl import locked_tls_material, trusted_file_owner


def protect_fixture(*paths):
    import win32api
    import win32con
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    owner = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    token.Close()
    system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    admins = win32security.CreateWellKnownSid(win32security.WinBuiltinAdministratorsSid, None)
    for path in paths:
        acl = win32security.ACL()
        for sid in (owner, system, admins):
            acl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_ALL, sid)
        win32security.SetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, acl, None)


@unittest.skipUnless(sys.platform == "win32", "Windows ACLs required")
class TlsFileAclTests(unittest.TestCase):
    def test_owner_rights_pseudoprincipal_is_not_a_valid_file_owner(self):
        trusted = {"synthetic-owner", "S-1-5-18", "S-1-5-32-544", "S-1-3-4"}
        self.assertTrue(trusted_file_owner("synthetic-owner", trusted))
        self.assertTrue(trusted_file_owner("S-1-5-18", trusted))
        self.assertTrue(trusted_file_owner("S-1-5-32-544", trusted))
        self.assertFalse(trusted_file_owner("S-1-3-4", trusted))
        self.assertFalse(trusted_file_owner("S-1-1-0", trusted))

    def test_owner_acl_is_accepted_and_world_access_rejected(self):
        import win32api
        import win32con
        import win32security

        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        owner = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        token.Close()
        system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
        admins = win32security.CreateWellKnownSid(win32security.WinBuiltinAdministratorsSid, None)
        everyone = win32security.CreateWellKnownSid(win32security.WinWorldSid, None)

        def set_acl(path, *, world=False):
            acl = win32security.ACL()
            for sid in (owner, system, admins):
                acl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_ALL, sid)
            if world:
                acl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_READ, everyone)
            win32security.SetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
                None, None, acl, None)

        with tempfile.TemporaryDirectory(dir=os.environ["LOCALAPPDATA"]) as directory:
            root = Path(directory) / "tls"
            root.mkdir()
            cert, key = root / "cert.pem", root / "key.pem"
            cert.write_text("synthetic")
            key.write_text("synthetic")
            protect_fixture(Path(directory))
            for path in (root, cert, key):
                set_acl(path)
            with locked_tls_material(root, cert, key):
                self.assertTrue(key.exists())
                with self.assertRaises(PermissionError):
                    key.write_text("changed")
            for path in (root, cert, key):
                with self.subTest(kind=path.name):
                    set_acl(path, world=True)
                    with self.assertRaisesRegex(ValueError, "TLS file permissions unavailable"), locked_tls_material(root, cert, key):
                        self.fail("World-readable TLS material was accepted")
                    set_acl(path)
            win32security.SetNamedSecurityInfo(str(key), win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
                None, None, None, None)
            try:
                with self.assertRaisesRegex(ValueError, "TLS file permissions unavailable"), locked_tls_material(root, cert, key):
                    self.fail("Null DACL was accepted")
            finally:
                set_acl(key)

    def test_parent_delete_child_permission_is_rejected(self):
        import win32con
        import win32security

        with tempfile.TemporaryDirectory(dir=os.environ["LOCALAPPDATA"]) as directory:
            parent = Path(directory)
            root = parent / "tls"
            root.mkdir()
            cert, key = root / "cert.pem", root / "key.pem"
            cert.write_text("synthetic")
            key.write_text("synthetic")
            protect_fixture(parent, root, cert, key)
            descriptor = win32security.GetNamedSecurityInfo(str(parent), win32security.SE_FILE_OBJECT,
                                                            win32security.DACL_SECURITY_INFORMATION)
            acl = descriptor.GetSecurityDescriptorDacl()
            everyone = win32security.CreateWellKnownSid(win32security.WinWorldSid, None)
            acl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_READ, everyone)
            win32security.SetNamedSecurityInfo(str(parent), win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION, None, None, acl, None)
            with locked_tls_material(root, cert, key):
                self.assertTrue(key.exists())
            acl.AddAccessAllowedAce(win32security.ACL_REVISION, 0x40, everyone)  # FILE_DELETE_CHILD
            win32security.SetNamedSecurityInfo(str(parent), win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION, None, None, acl, None)
            with self.assertRaisesRegex(ValueError, "TLS file permissions unavailable"), locked_tls_material(root, cert, key):
                self.fail("Replaceable TLS parent was accepted")
