import sqlite3
import tempfile
import unittest
from contextlib import closing
from functools import partial
from pathlib import Path
from unittest.mock import patch

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.devices.pairing import enroll, issue_pairing, revoke_device
from personalcontext.jobs.writer import Writer
from personalcontext.privacy.policy_pause import pause_local
from personalcontext.privacy.policy_store import PolicyDraft, save_policy
from personalcontext.storage.initialize import initialize_database


class SecurityAuditTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        self.writer = Writer(self.path)
        await self.writer.start()
        bootstrap = await self.writer.submit(partial(issue_bootstrap, now=1000))
        self.bootstrap = bootstrap
        encoded = hash_password("synthetic audit owner")
        await self.writer.submit(partial(consume_bootstrap, candidate=bootstrap, encoded=encoded, now=1001))
        self.owner = await self.writer.submit(partial(create_session, expected_hash=encoded, now=1002))

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def test_successful_security_actions_are_audited_without_payload(self):
        code = await self.writer.submit(partial(issue_pairing, token=self.owner.token, csrf=self.owner.csrf, mask=1, now=1003))
        device = await self.writer.submit(partial(enroll, code=code, now=1004))
        draft = PolicyDraft(False, 600, frozenset({"synthetic-private-source"}), frozenset(),
                            frozenset({("synthetic-private-source", "metadata")}))
        await self.writer.submit(partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                                         expected_version=1, draft=draft, now=1005))
        await self.writer.submit(partial(pause_local, now=1006))
        await self.writer.submit(partial(revoke_device, token=self.owner.token, csrf=self.owner.csrf,
                                         device_id=device.device_id, now=1007))
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute("SELECT event_type,actor,status,occurred_at,correlation_id FROM security_audit ORDER BY id").fetchall()
        self.assertEqual([row[0] for row in rows], ["owner_bootstrap", "owner_login", "pairing_issue", "device_enroll",
                                                   "policy_update", "policy_pause", "device_revoke"])
        visible = repr(rows)
        if any(item in visible for item in (self.bootstrap, self.owner.token, self.owner.csrf, code, device.token,
                                            device.device_id, "synthetic-private-source")):
            self.fail("Sensitive value appeared in audit")

    async def test_policy_and_audit_roll_back_together(self):
        draft = PolicyDraft(False, 600, frozenset({"synthetic-source"}), frozenset(),
                            frozenset({("synthetic-source", "metadata")}))
        with closing(sqlite3.connect(self.path)) as connection:
            before = connection.execute("SELECT count(*) FROM security_audit").fetchone()[0]
            self.assertEqual(save_policy(connection, self.owner.token, self.owner.csrf, 1, draft, 1003).status, "ok")
            connection.rollback()
            self.assertEqual(connection.execute("SELECT count(*) FROM security_audit").fetchone()[0], before)
            self.assertEqual(connection.execute("SELECT version FROM capture_policy").fetchone()[0], 1)

    async def test_audit_write_failure_rolls_back_policy_change(self):
        draft = PolicyDraft(False, 600, frozenset({"synthetic-source"}), frozenset(),
                            frozenset({("synthetic-source", "metadata")}))
        operation = partial(save_policy, token=self.owner.token, csrf=self.owner.csrf,
                            expected_version=1, draft=draft, now=1003)
        with (patch("personalcontext.privacy.policy_store.record_audit", side_effect=sqlite3.OperationalError("synthetic failure")),
              self.assertRaises(sqlite3.OperationalError)):
            await self.writer.submit(operation)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT version FROM capture_policy").fetchone()[0], 1)
