# PC-002 threat model and security review

## Boundaries and assets

The owner controls one Windows user session and explicitly approves sources.
Owner passwords, session cookies, CSRF tokens, pairing codes, device tokens,
consent rules and any future activity are sensitive. Local processes and web
pages are not trusted merely because the app listens on loopback. Device tokens
are distinct from owner sessions; source identifiers alone are not credentials.
Database encryption at rest is not provided by SQLite or by DPAPI backup.

## Threats and current controls

| Threat | Control and evidence | Remaining boundary |
| --- | --- | --- |
| DNS rebinding, hostile LAN, forged proxy headers | Exact loopback bind and peer, scheme, Host and Origin checks; proxy header interpretation disabled and forwarding headers rejected; WebSocket upgrades are disabled and rejected at ASGI boundaries; `test_app.py`, `test_proxy_headers.py`, `test_websocket_boundary.py`, frozen smoke. | Private HTTPS is experimental, explicitly enabled and periodically monitors firewall snapshots; live LAN/VPN acceptance and firewall monitoring gaps remain. Do not expose it directly to the internet or add a reverse proxy. |
| Cross-site request and session theft | Origin and CSRF on owner mutations; HttpOnly, Strict cookie on exact loopback HTTP; no wildcard CORS; `test_auth_http.py`. | Same-user malware or a compromised owner browser can still act as the owner. HTTPS Secure cookies need the remote implementation. |
| Guessing passwords or enrollment codes | Argon2id, bounded password executor, persistent attempt limits, one-time expiring high-entropy codes; hashes in SQLite; auth and device tests. | Global throttling permits temporary denial of service; access to the Windows user account remains a trust boundary. |
| Device impersonation or overprivilege | Hashed bearer bound to device and individual scopes; owner-authorized revoke; source bound to one device; device and source tests. | A stolen bearer acts within its scopes until revoked; no real ingestion or extension storage exists yet. |
| Private or sensitive activity reaching storage | Default-deny versioned policy, TTL, pause latch and conservative sanitizer helpers with synthetic negative tests. | No trusted collector classification or ingestion enforcement exists; sanitizer heuristics cannot prove privacy. Collection remains disabled. |
| Sensitive information in security audit | Fixed event/actor categories, no payload, source or device identifiers, IPs or credentials, bounded retention and owner-only access. | Audit is not a full record of every failed request; OS and third-party logs are outside this guarantee. |
| Restoring old permissions or credentials | Restore invalidates owner sessions and codes, revokes devices and pauses policy and sources. Synthetic frozen restore smoke and migration tests cover supported revisions. | Owner must bootstrap and pair again; unknown security schemas fail closed. |

Security review must be repeated when new network transports, adapters, data
flows or privileges are introduced. Remote HTTPS needs explicit private
interface selection, trusted certificate validation, firewall restrictions,
HTTPS-only peer/Host/Origin checks and Secure cookies before it can be enabled.
Device and owner checks do not substitute for those requirements. The model
server and database must not expose network listeners. Physical compromise,
malware with the owner's privileges, backups already exported, and filesystem
forensics are not solved by these controls.
