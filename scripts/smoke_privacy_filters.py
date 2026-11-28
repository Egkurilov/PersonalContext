"""Verify owner filter settings on the packaged synthetic instance."""

import json
from urllib.request import Request


def check_filters(opener, origin, csrf):
    path = origin + "/api/v1/privacy/filters"
    with opener.open(path, timeout=5) as response:
        rules = json.load(response)
    assert rules == {"version": 1, "allowed_domains": [], "denied_domains": [],
                     "allowed_apps": [], "denied_apps": []}
    rules["allowed_domains"] = ["example.org"]
    request = Request(path, data=json.dumps(rules).encode(), method="PATCH",
                      headers={"Origin": origin, "Content-Type": "application/json", "X-CSRF-Token": csrf})
    with opener.open(request, timeout=5) as response:
        assert json.load(response) == {"version": 2, "paused": True}
    with opener.open(path, timeout=5) as response:
        assert json.load(response) == {**rules, "version": 2}
