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

An internal ASGI transport wrapper can attach the server-selected private
boundary to the shared application; request headers cannot select it. Under
that boundary owner mutations require the matching HTTPS Origin and owner
cookies carry `Secure`, `HttpOnly` and `SameSite=Strict`. Bootstrap completion
is still local only. ASGI tests cover remote login, rotation, Origin, rejected
peers and plaintext. They simulate transport scope and do not prove a real TLS
listener, peer network, firewall or browser installation.

An internal Uvicorn configuration builds a verified TLS 1.2+ server context
from the certificate, encrypted key and DPAPI-protected passphrase, joins it to
the scoped transport, disables proxy headers and request access logs, and
leaves the shared application's lifecycle to its existing event loop. It does
not bind or start a socket. A synthetic test runs it on loopback: a real TLS
connection with a synthetic certificate succeeds cryptographically but is denied as an unlisted peer even
with a forged forwarding header; plaintext HTTP is not accepted. This is not a
LAN acceptance test. Before any actual start the caller must validate the
effective firewall, bind the selected interface and arrange
safe lifecycle and failure handling.

An offline TLS helper loads a certificate and matching private key into a server
context and performs a bounded in-memory TLS handshake against Python's default
trust configuration. It requires certificate hostname verification via SAN and
TLS 1.2 or newer; it accepts a key passphrase supplied by its caller. Synthetic
tests cover trusted and untrusted certificates, hostname and key mismatches, and
an encrypted test key. The helper does not open a socket. Python's default trust
may depend on environment configuration, and the remote client's trust may differ.
The Windows-only TLS vault helper uses user-bound DPAPI with a dedicated purpose
and no UI to protect the key passphrase; its loader accepts encrypted PKCS#8 PEM
keys and supplies the recovered passphrase to the offline verifier. Real DPAPI
round-trip, tampering and encrypted synthetic-key tests run on Windows. This is
not protection against malware running as the same user; Python cannot guarantee
erasure of a passphrase from process memory.

The owner-only local `GET/POST /api/v1/network/private/config` API prepares and
stores a **disabled candidate**, never starts the listener. POST requires Origin,
CSRF, owner session and an expected revision; it rechecks authorization after
preflight. The owner places an encrypted PKCS#8 key and certificate chain as
separate `.pem` files under `%LOCALAPPDATA%/PersonalContext/data/tls`; the API
accepts their simple filenames, a private address, hostname, port, peer CIDRs,
and a passphrase of 16–1024 UTF-8 bytes. Preparation requires a local fixed
NTFS volume, files resolving inside that directory, matching trusted TLS and an
encrypted key. Only the DPAPI-protected passphrase is saved. GET returns settings
without the passphrase; both methods are forbidden on a private transport.
The preflight is bounded and happens outside the SQLite writer. File ACL
verification, listener activation and a settings UI remain unimplemented. Check
the files and certificate again at actual startup: they can change after save.

Migration `0012` adds the candidate and a payload-free audit category. Restore
deletes the candidate and its protected passphrase along with other access state;
the owner must configure it again. Downgrade refuses to discard a candidate or
its audit events; restore a verified earlier backup to roll back.

Private access is not wired to a listener or settings and is not available yet.
Before enabling it, implement and verify certificate and key storage, client
trust, selected local interface binding, firewall restrictions, HTTPS
session cookies, owner opt-in, lifecycle and real LAN/VPN negative tests. Never
use this request filter as a substitute for TLS, firewall or authentication.
