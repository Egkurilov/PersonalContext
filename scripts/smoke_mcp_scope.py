"""Synthetic local MCP credential scope and revocation against a frozen host."""

import json
from urllib.error import HTTPError
from urllib.request import Request


def check_mcp(opener, base, csrf):
    owner = {"Origin": base, "Content-Type": "application/json", "X-CSRF-Token": csrf}
    issue = Request(base + "/api/v1/mcp/credentials", data=b'{"scope":"status:read"}', headers=owner, method="POST")
    with opener.open(issue, timeout=5) as response:
        credential = json.load(response)
        assert credential["scope"] == "status:read" and credential["expires_in"] == 900
    status = Request(base + "/api/v1/mcp/status", headers={"Authorization": "Bearer " + credential["token"]})
    with opener.open(status, timeout=5) as response:
        assert json.load(response) == {"scope": "status:read", "status": "ready"}
    revoke = Request(base + "/api/v1/mcp/credentials/" + credential["id"] + "/revoke", data=b"{}", headers=owner, method="POST")
    with opener.open(revoke, timeout=5) as response:
        assert response.status == 204
    try:
        opener.open(status, timeout=5)
    except HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError("Revoked MCP credential remains authorized")
