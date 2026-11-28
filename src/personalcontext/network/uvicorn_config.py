"""Build a private TLS server configuration without binding or starting it."""

import ssl
from collections.abc import Callable
from pathlib import Path

import uvicorn
from starlette.types import ASGIApp

from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.material.paths import validated_tls_material
from personalcontext.network.tls import vault_server_context
from personalcontext.network.transport import ScopedTransport


def private_server_config(app: ASGIApp, boundary: PrivateBoundary, cert: Path, key: Path,
                          protected: bytes) -> uvicorn.Config:
    """Verify TLS; caller must validate the firewall and use the app's event loop."""
    if not isinstance(boundary, PrivateBoundary):
        raise TypeError("Invalid private TLS configuration")
    if cert.parent != key.parent:
        raise ValueError("Invalid private TLS configuration")
    with validated_tls_material(cert.parent, cert.name, key.name) as (checked_cert, checked_key):
        context = vault_server_context(checked_cert, checked_key, boundary.hostname, protected)
    if (not isinstance(context, ssl.SSLContext) or context.protocol != ssl.PROTOCOL_TLS_SERVER
            or context.minimum_version < ssl.TLSVersion.TLSv1_2):
        raise ValueError("Invalid private TLS configuration")

    def tls_factory(_config: uvicorn.Config, _default: Callable[[], ssl.SSLContext]) -> ssl.SSLContext:
        return context

    return uvicorn.Config(ScopedTransport(app, boundary), host=boundary.address, port=boundary.port,
                          lifespan="off", workers=1, proxy_headers=False, access_log=False, ws="none",
                          log_level="warning", ssl_context_factory=tls_factory)
