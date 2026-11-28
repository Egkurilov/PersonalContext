"""Synthetic extension pairing against an already running frozen application."""

import json
from urllib.error import HTTPError
from urllib.request import Request

EXTENSION = "chrome-extension://" + "a" * 32


def check_extension(opener, base, csrf):
    def send(path, body, origin, bearer=None):
        headers = {"Origin": origin, "Content-Type": "application/json"}
        if origin == base:
            headers["X-CSRF-Token"] = csrf
        if bearer:
            headers["Authorization"] = "Bearer " + bearer
        return opener.open(Request(base + path, data=json.dumps(body).encode(), headers=headers, method="POST"), timeout=5)

    with send("/api/v1/devices/pairing-codes/extension", {"scopes": "heartbeat", "origin": EXTENSION}, base) as response:
        code = json.load(response)["code"]
    preflight = Request(base + "/api/v1/devices/enroll", method="OPTIONS", headers={
        "Origin": EXTENSION, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type",
    })
    with opener.open(preflight, timeout=5) as response:
        assert response.status == 200 and response.headers["Access-Control-Allow-Origin"] == EXTENSION
        assert response.headers.get("Access-Control-Allow-Credentials") is None
    with send("/api/v1/devices/enroll", {"code": code}, EXTENSION) as response:
        device = json.load(response)
        assert response.headers["Access-Control-Allow-Origin"] == EXTENSION
    with send("/api/v1/device/heartbeat", {"device_id": device["device_id"]}, EXTENSION, device["token"]) as response:
        assert response.status == 204
    with send("/api/v1/devices/" + device["device_id"] + "/revoke", {}, base) as response:
        assert response.status == 204
    try:
        send("/api/v1/device/heartbeat", {"device_id": device["device_id"]}, EXTENSION, device["token"])
    except HTTPError as error:
        assert error.code in (401, 403)
    else:
        raise AssertionError("Revoked extension remains authorized")
