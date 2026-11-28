# PC-002: browser extension origin binding

`POST /api/v1/devices/pairing-codes/extension` binds a single canonical
`chrome-extension://` origin (32 characters in `a`–`p`) to a short-lived
pairing code issued by an authenticated owner with CSRF protection. Its JSON
body contains `scopes` (the existing comma-separated scope list) and `origin`.
A mismatched or missing origin cannot consume the code or receive a credential.
A successful enrollment binds that origin to the new device and its separately
scoped, revocable bearer token.

The request boundary must still validate the server-selected transport, peer,
Host and forwarding headers. Only the bound origin may use the narrowly scoped
enrollment, device configuration and heartbeat routes, including their CORS
preflights. Owner, settings and other routes must remain inaccessible to that
origin. CORS responses must never allow credentials or wildcard origins. An
origin match is not authentication: each device request must also verify its
bearer token, device ID, scope, revocation and bound origin in the same
authoritative operation. Native device credentials retain their existing
behavior; a browser-bound token cannot be used without its bound origin.

Owner revocation takes effect immediately. Expired and consumed pairing codes
cannot allow enrollment or extend a temporary preflight grant. Restoring a
backup removes pending grants and revokes devices. Migration `0013` stores
origin bindings; downgrade refuses to discard them, so rollback requires a
verified earlier backup. Existing native device credentials remain usable.
Synthetic HTTP tests exercise the contract. On Windows, the manual command
`python scripts/smoke_browser_extension.py` also ran a temporary synthetic MV3
extension in the installed Edge against the packaged app: pairing and heartbeat
succeeded, an invalid bearer was denied, and the owner route was inaccessible.
This requires the packaged app, installed Edge and Git's OpenSSL at the paths
specified by the script, and a free loopback port. It does not validate a
production extension, Chrome, private HTTPS or remote browser behavior. The
extension implementation and capture remain separate future work.
