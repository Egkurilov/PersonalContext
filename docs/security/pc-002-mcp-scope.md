# PC-002: separate local MCP credential

The local owner may explicitly issue a short-lived credential through
`POST /api/v1/mcp/credentials` with the exact scope `status:read`, an owner
session, Origin and CSRF. The response returns the random bearer token once,
with `Cache-Control: no-store`; it expires after 900 seconds and at most eight
unexpired credentials may exist. The server stores only a SHA-256 verifier and
non-secret metadata. The caller must protect the returned token and must not
place it in URLs, web pages, logs or a checked-in configuration. There is no
automatic credential or access on installation.

`GET /api/v1/mcp/status` requires that token and exposes only readiness and the
`status:read` scope; it provides no activity, search, file access, mutations or
execution. It rejects owner cookies and device tokens as credentials. MCP
tokens likewise cannot authorize owner or device endpoints. Both MCP management
and status endpoints are loopback-only and reject the prospective private
transport. The owner may revoke by credential ID using the CSRF-protected local
API; revocation takes effect on the next request. Observed expiry and clock
rollback cannot revive a token. Normal process restart retains an unexpired
credential; restoring a backup deletes all MCP credentials.

Migration `0014` adds verifiers and fixed audit categories without token or
payload content. Downgrade refuses to discard credential records or their audit
history; restore a verified earlier backup instead. Tests use synthetic data.
This is not the MCP stdio server or authorization for personal context; PC-021
must implement its own explicitly approved per-client/source/time/field scope,
privacy filtering and actual read-only tools before exposing such data.
