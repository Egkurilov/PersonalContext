"""Exercise HTTP-managed credentials against the internal synthetic event writer."""

import sqlite3
import unittest
import uuid
from contextlib import closing
from datetime import UTC, datetime
from functools import partial

import test_sources_http as fixture
from test_web_visit_ledger import synthetic_event

from personalcontext.ingest.visit.service import submit_web_visit
from personalcontext.privacy.sanitizer.rules import SanitizerContext


class HttpInternalIngestTests(unittest.TestCase):
    setUp = fixture.SourcesHttpTests.setUp
    tearDown = fixture.SourcesHttpTests.tearDown
    create = fixture.SourcesHttpTests.create

    def test_http_consent_device_binding_and_revoke_reach_internal_writer(self):
        first, other = self.devices
        source = self.create(first).json()["source_id"]
        event = synthetic_event(first["device_id"], source)
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        event.update(started_at=now, observed_at=now)
        app = self.client.app
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}), private=False, sensitivity="ordinary")

        def submit(device, value):
            call = partial(submit_web_visit, app.state.scheduler.writer, app.state.capture_latch,
                           device["token"], device["device_id"], value, context)
            return self.client.portal.call(call)

        self.assertEqual(submit(first, event), "rejected")
        filters = {"version": 1, "allowed_domains": ["example.org"], "denied_domains": [],
                   "allowed_apps": [], "denied_apps": []}
        self.assertEqual(self.client.patch("/api/v1/privacy/filters", json=filters, headers=self.owner_headers).status_code, 200)
        self.assertEqual(self.client.patch(f"/api/v1/sources/{source}", json={"revision": 1, "paused": False},
                                           headers=self.owner_headers).status_code, 200)
        policy = {"version": 2, "paused": False, "ttl": 600, "allowed": [source], "denied": [],
                  "grants": [{"source": source, "scope": "metadata"}]}
        self.assertEqual(self.client.patch("/api/v1/privacy/policy", json=policy, headers=self.owner_headers).status_code, 200)
        event["policy_version"] = 3
        self.assertEqual(submit(other, event | {"device_id": other["device_id"]}), "rejected")
        self.assertEqual(submit(first, event), "accepted")
        self.assertEqual(submit(first, event), "duplicate")
        self.assertEqual(self.client.post(f"/api/v1/devices/{first['device_id']}/revoke",
                                          headers=self.owner_headers).status_code, 204)
        retry = event | {"event_id": str(uuid.uuid4()), "source_event_key": "after-revoke"}
        self.assertEqual(submit(first, retry), "rejected")
        with closing(sqlite3.connect(app.state.scheduler.writer.path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
