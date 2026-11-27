# PC-002 network boundaries

The running listener is still exactly `127.0.0.1:17890` over HTTP. Its request
boundary checks the actual ASGI peer, HTTP scheme, exact Host and optional
Origin and rejects forwarding headers. Uvicorn proxy-header interpretation is
disabled. Existing CSRF and authentication checks remain separate.

The same boundary module validates a prospective private HTTPS request against
an explicit private bind address, canonical lower-case DNS hostname, port and
up to 16 explicitly configured private peer networks. Allowed network ranges
are RFC 1918, IPv6 ULA and shared VPN address space `100.64.0.0/10`. Wildcards,
public networks, malformed/ambiguous addresses, unlisted peers, HTTP, foreign
Host/Origin and forwarding headers are rejected. These checks are unit tested;
they do not establish TLS or change firewall rules.

An offline TLS helper loads a certificate and matching private key into a server
context and performs a bounded in-memory TLS handshake against Python's default
trust configuration. It requires certificate hostname verification via SAN and
TLS 1.2 or newer; it accepts a key passphrase supplied by its caller. Synthetic
tests cover trusted and untrusted certificates, hostname and key mismatches, and
an encrypted test key. The helper does not open a socket. Python's default trust
may depend on environment configuration, and the remote client's trust may differ.
No certificate/key storage or owner-facing TLS configuration is implemented.

Private access is not wired to a listener or settings and is not available yet.
Before enabling it, implement and verify certificate identity and trust, private
key protection, selected local interface binding, firewall restrictions, HTTPS
session cookies, owner opt-in, lifecycle and real LAN/VPN negative tests. Never
use this request filter as a substitute for TLS, firewall or authentication.
