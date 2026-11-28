"""Validate owner-supplied private TLS material before saving a disabled candidate."""

import sys
import threading
from pathlib import Path

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.lan.networks import lan_ranges_allowed
from personalcontext.network.material.paths import validated_tls_material
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
        if not lan_ranges_allowed(boundary.address, boundary.peers):
            raise ValueError("Invalid settings")
        candidate = PrivateCandidate(boundary, cert_name, key_name, b"x")
        if not valid_candidate(candidate) or sys.platform != "win32":
            raise ValueError("Invalid settings")
        with validated_tls_material(root, cert_name, key_name) as (cert, key):
            protected = seal_passphrase(phrase_bytes)
            vault_server_context(cert, key, hostname, protected)
        return PrivateCandidate(boundary, cert_name, key_name, protected)
    except Exception:  # noqa: BLE001 - never return certificate paths or secrets in errors
        raise ValueError("Private TLS settings unavailable") from None
