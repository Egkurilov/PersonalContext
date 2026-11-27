"""Validate owner-supplied private TLS material before saving a disabled candidate."""

import os
import sys
import threading
from pathlib import Path

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.private_settings import PrivateCandidate, valid_candidate
from personalcontext.network.tls import vault_server_context
from personalcontext.network.tls_vault import seal_passphrase

_FIELDS = frozenset({"revision", "address", "hostname", "port", "peers", "cert", "key", "passphrase"})
_GATE = threading.BoundedSemaphore(2)


def prepare_candidate(root: Path, body: dict[str, object]) -> PrivateCandidate:
    """Use a local NTFS directory and return only DPAPI-protected credentials."""
    if not _GATE.acquire(blocking=False):
        raise ValueError("Private TLS settings unavailable")
    try:
        return _prepare_candidate(root, body)
    finally:
        _GATE.release()


def _prepare_candidate(root: Path, body: dict[str, object]) -> PrivateCandidate:
    try:
        if (body.keys() != _FIELDS or type(body["revision"]) is not int or not 0 <= body["revision"] < 2**53 - 1
                or not isinstance(body["peers"], list)):
            raise ValueError("Invalid settings")
        address, hostname, port = body["address"], body["hostname"], body["port"]
        cert_name, key_name, phrase = body["cert"], body["key"], body["passphrase"]
        if not all(isinstance(item, str) for item in (address, hostname, cert_name, key_name, phrase)) or type(port) is not int:
            raise ValueError("Invalid settings")
        assert isinstance(address, str) and isinstance(hostname, str) and isinstance(cert_name, str)
        assert isinstance(key_name, str) and isinstance(phrase, str)
        phrase_bytes = phrase.encode("utf-8")
        if not 16 <= len(phrase_bytes) <= 1024:
            raise ValueError("Invalid settings")
        boundary = PrivateBoundary.create(address, hostname, port, body["peers"])
        candidate = PrivateCandidate(boundary, cert_name, key_name, b"x")
        if not valid_candidate(candidate) or sys.platform != "win32":
            raise ValueError("Invalid settings")
        import win32api
        import win32file

        base = root.absolute()
        drive, _ = os.path.splitdrive(str(base))
        if (len(drive) != 2 or drive[1] != ":" or win32file.GetDriveType(drive + "\\") != win32file.DRIVE_FIXED
                or win32api.GetVolumeInformation(drive + "\\")[4].upper() != "NTFS"):
            raise ValueError("Invalid storage")
        resolved = base.resolve(strict=True)
        if resolved != base or not resolved.is_dir():
            raise ValueError("Invalid storage")
        cert, key = (resolved / cert_name).resolve(strict=True), (resolved / key_name).resolve(strict=True)
        if (cert.parent != resolved or key.parent != resolved or not cert.is_file() or not key.is_file()
                or not 0 < cert.stat().st_size <= 1048576 or not 0 < key.stat().st_size <= 1048576):
            raise ValueError("Invalid storage")
        protected = seal_passphrase(phrase_bytes)
        vault_server_context(cert, key, hostname, protected)
        return PrivateCandidate(boundary, cert_name, key_name, protected)
    except Exception:  # noqa: BLE001 - never return certificate paths or secrets in errors
        raise ValueError("Private TLS settings unavailable") from None
