"""Verify server credentials against Python's default trust configuration offline."""

import ssl
from pathlib import Path

from personalcontext.network.tls_vault import open_passphrase


def _handshake(server: ssl.SSLContext, client: ssl.SSLContext, hostname: str) -> None:
    if client.verify_mode != ssl.CERT_REQUIRED or not client.check_hostname:
        raise ValueError("TLS verification required")
    server_in, server_out, client_in, client_out = (ssl.MemoryBIO() for _ in range(4))
    server_socket = server.wrap_bio(server_in, server_out, server_side=True)
    client_socket = client.wrap_bio(client_in, client_out, server_side=False, server_hostname=hostname)
    server_done = client_done = False
    for _ in range(32):
        if not client_done:
            try:
                client_socket.do_handshake()
                client_done = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
        if client_out.pending:
            server_in.write(client_out.read())
        if not server_done:
            try:
                server_socket.do_handshake()
                server_done = True
            except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                pass
        if server_out.pending:
            client_in.write(server_out.read())
        if client_done and server_done:
            return
    raise ValueError("TLS handshake did not complete")


def trusted_server_context(cert: Path, key: Path, hostname: str, password: bytes | None = None) -> ssl.SSLContext:
    """Load a matching key and verify its hostname against the default trust roots."""
    try:
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.minimum_version = ssl.TLSVersion.TLSv1_2
        server.load_cert_chain(cert, key, password=password if password is not None else b"")
        client = ssl.create_default_context()
        client.minimum_version = ssl.TLSVersion.TLSv1_2
        client.hostname_checks_common_name = False
        _handshake(server, client, hostname)
        return server
    except (ssl.SSLError, OSError, ValueError, TypeError):
        raise ValueError("TLS configuration unavailable") from None


def vault_server_context(cert: Path, key: Path, hostname: str, protected: bytes) -> ssl.SSLContext:
    """Open a user-bound passphrase only for loading the encrypted TLS key."""
    try:
        with key.open("rb") as source:
            if source.readline(80).strip() != b"-----BEGIN ENCRYPTED PRIVATE KEY-----":
                raise ValueError("Invalid encrypted key")
    except (OSError, ValueError):
        raise ValueError("TLS configuration unavailable") from None
    return trusted_server_context(cert, key, hostname, open_passphrase(protected))
