"""Owner-managed sanitizer allow/deny rules must be versioned and fail closed."""

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import test_device_http as fixture

PATH = "/api/v1/privacy/filters"


class FilterRulesHttpTests(unittest.TestCase):
    setUp = fixture.DeviceHttpTests.setUp
    tearDown = fixture.DeviceHttpTests.tearDown

    def draft(self):
        return {"version": 1, "allowed_domains": ["example.org"], "denied_domains": ["private.example.org"],
                "allowed_apps": ["reader.exe"], "denied_apps": ["messenger.exe"]}

    def test_owner_update_pauses_and_versions_rules_without_audit_payload(self):
        empty = self.client.get(PATH)
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json(), {"version": 1, "allowed_domains": [], "denied_domains": [],
                                        "allowed_apps": [], "denied_apps": []})
        self.assertEqual(self.client.patch(PATH, json=self.draft(), headers=self.headers).status_code, 403)
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        result = self.client.patch(PATH, json=self.draft(), headers=owner)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {"version": 2, "paused": True})
        self.assertEqual(self.client.get(PATH).json(), {**self.draft(), "version": 2})
        self.assertEqual(self.client.patch(PATH, json=self.draft(), headers=owner).status_code, 409)
        policy = self.client.get("/api/v1/privacy/policy").json()
        self.assertTrue(policy["effective_paused"])
        self.assertEqual(policy["version"], 2)
        audit = self.client.get("/api/v1/audit").text
        self.assertNotIn("example.org", audit)
        self.assertNotIn("reader.exe", audit)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(PATH).status_code, 401)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM privacy_filter_rules").fetchone()[0], 4)

    def test_invalid_or_duplicate_rules_are_rejected_without_mutation(self):
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        changes = ({"allowed_domains": ["example.org", "example.org"]}, {"allowed_domains": ["https://example.org/"]},
                   {"allowed_domains": ["EXAMPLE.ORG"]}, {"allowed_apps": ["C:\\private.exe"]},
                   {"denied_apps": ["reader.exe", 1]}, {"version": True}, {"extra": "synthetic"})
        for change in changes:
            with self.subTest(field=tuple(change)):
                self.assertEqual(self.client.patch(PATH, json={**self.draft(), **change}, headers=owner).status_code, 400)
        self.assertEqual(self.client.get(PATH).json()["version"], 1)

    def test_audit_failure_rolls_back_rules_and_keeps_local_pause(self):
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        with patch("personalcontext.privacy.filters.store.record_audit", side_effect=sqlite3.OperationalError("synthetic")):
            self.assertEqual(self.client.patch(PATH, json=self.draft(), headers=owner).status_code, 503)
        self.assertTrue(self.client.app.state.capture_latch.is_paused())
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM privacy_filter_rules").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT version FROM capture_policy").fetchone()[0], 1)

    def test_corrupt_stored_rules_fail_closed(self):
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("INSERT INTO privacy_filter_rules(kind, value) VALUES ('invalid', 'synthetic')")
            connection.commit()
        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        self.assertEqual(self.client.get(PATH).status_code, 503)
        self.assertEqual(self.client.patch(PATH, json=self.draft(), headers=owner).status_code, 503)
        self.assertTrue(self.client.app.state.capture_latch.is_paused())

    def test_revoked_session_cannot_commit_filters_after_preflight(self):
        from personalcontext.privacy.filters.store import save_filters

        def revoke_then_save(connection, *args):
            with closing(sqlite3.connect(self.path)) as other:
                other.execute("DELETE FROM owner_sessions")
                other.commit()
            return save_filters(connection, *args)

        owner = {**self.headers, "X-CSRF-Token": self.csrf}
        with patch("personalcontext.privacy.filters.http.save_filters", side_effect=revoke_then_save):
            self.assertEqual(self.client.patch(PATH, json=self.draft(), headers=owner).status_code, 403)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM privacy_filter_rules").fetchone()[0], 0)
