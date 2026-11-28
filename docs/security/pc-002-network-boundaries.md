# PC-002 network boundaries

The default listener is exactly `127.0.0.1:17890` over HTTP. Its request
boundary checks the actual ASGI peer, HTTP scheme, exact Host and optional
Origin and rejects forwarding headers. Uvicorn proxy-header interpretation is
disabled. Existing CSRF and authentication checks remain separate.
WebSockets have no supported contract and are disabled in Uvicorn and rejected
at the ASGI boundary on both local and prospective private transports. Synthetic
route tests demonstrate that adding a WebSocket route cannot bypass the HTTP
peer, Host, Origin and authentication boundary; any future WebSocket support
requires a separately reviewed security contract.

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
leaves the shared application's lifecycle to its existing event loop. Configuration
creation revalidates local fixed NTFS storage, file and ancestor ACLs, certificate
trust and hostname, and encrypted key while holding the checked files against
write/delete sharing. Windows tests reject altered ACLs and certificates. The
resulting TLS context is kept in memory; this is a preparation check, not a
firewall or lifecycle guarantee. It does not bind or start a socket. A synthetic test runs it on loopback: a real TLS
connection with a synthetic certificate succeeds cryptographically but is denied as an unlisted peer even
with a forged forwarding header; plaintext HTTP is not accepted. This is not a
LAN acceptance test. The explicit owner start path described in the listener
lifecycle notes uses this configuration after checking the firewall and binds
the selected private interface.

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
encrypted key. The TLS directory and both files must be owned by the current
user, SYSTEM or Administrators and have a non-null DACL with no allow ACE for principals other than that
user, SYSTEM, Administrators and the Windows owner-rights SID. Unsupported ACE
types fail closed. Handles are held without write/delete sharing during TLS
preflight, preventing replacement of the checked files during that operation.
Only the DPAPI-protected passphrase is saved. GET returns settings
without the passphrase; both methods are forbidden on a private transport.
The preflight is bounded and happens outside the SQLite writer. Ancestor
directories are checked for untrusted ownership and ACEs that permit deletion,
replacement or changing ownership/DACL; read-only access to ancestors is allowed.
Reparse-point ancestors, null DACLs and unsupported effective ACE types are
rejected. These conservative checks may reject otherwise safe ACLs; they do not
defeat administrators or prevent a trusted owner from changing files after
preflight. Listener activation is available through the local owner API, but a
settings UI and real LAN acceptance remain unimplemented. See Microsoft's
[DACL guidance](https://learn.microsoft.com/en-us/windows/win32/secauthz/dacls-and-aces)
and [null DACL behavior](https://learn.microsoft.com/en-us/windows/win32/secauthz/null-dacls-and-empty-dacls).

Migration `0012` adds the candidate and a payload-free audit category. Restore
deletes the candidate and its protected passphrase along with other access state;
the owner must configure it again. Downgrade refuses to discard a candidate or
its audit events; restore a verified earlier backup to roll back.

The local owner-only `POST /api/v1/network/private/firewall/check` performs a
bounded, read-only inspection of the selected interface's Windows firewall
profile and active inbound allow rules. It requires Origin, CSRF and the owner
session, repeats authorization and candidate revision checks after inspection,
and returns only `restricted`, `not_restricted` or `unavailable`; it never
enables the listener. The conservative assessment rejects disabled/non-blocking
profiles, broad or ambiguous overlapping allows, edge traversal, and missing
explicit executable/port/peer coverage. The effective policy can change during
or after inspection, and Windows Filtering Platform can include policy outside
these high-level rules. Therefore `restricted` is diagnostic evidence, not a
durable permission to start or keep a listener running. Rule details are not
logged or returned. See Microsoft's [active policy store description](https://learn.microsoft.com/en-us/powershell/module/netsecurity/get-netfirewallrule)
and [Windows Filtering Platform overview](https://learn.microsoft.com/en-us/windows/win32/fwp/about-windows-filtering-platform).

The separately opted-in private listener is experimental and off by default.
Its [lifecycle notes](pc-002-listener-lifecycle.md) describe its owner controls,
monitoring gaps, WFP permission limit and remaining LAN/VPN acceptance tests.
Never treat the request filter as a substitute for TLS, firewall or authentication.

The Windows frozen smoke `scripts/smoke_frozen_network.py` inspects the
application process tree twice during startup with synthetic local data. It
requires exactly one TCP listener on loopback port 17890 and no UDP endpoints;
an independent test checks that an additional loopback listener is rejected.
These snapshots do not prove later network behavior or firewall enforcement.

`test_private_owner_socket.py` exercises owner login, Secure/HttpOnly/Strict
cookie attributes, Origin, CSRF, logout and denied bootstrap through a real TLS
socket bound to an eligible private address on the same machine. It uses a
synthetic pinned certificate and mocks TLS material/vault validation; the peer
allowlist contains only that machine's address. The test skips when no eligible
interface exists. It does not exercise listener activation, effective firewall
filtering, a separate device, real certificate trust or LAN/VPN connectivity.
