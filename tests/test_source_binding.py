import sqlite3
import tempfile
import unittest
from contextlib import closing
from functools import partial
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session
from personalcontext.auth.password_hash import hash_password
from personalcontext.devices.pairing import enroll, issue_pairing, revoke_device
from personalcontext.jobs.writer import Writer
from personalcontext.sources.registry import (
    create_source,
    owns_source,
    set_source_pause,
)
from personalcontext.storage.initialize import initialize_database


class SourceBindingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "context.db"
        initialize_database(self.path)
        self.writer = Writer(self.path)
        await self.writer.start()
        encoded = hash_password("synthetic source owner")
        bootstrap = await self.writer.submit(partial(issue_bootstrap, now=1000))
        await self.writer.submit(partial(consume_bootstrap, candidate=bootstrap, encoded=encoded, now=1001))
        self.owner = await self.writer.submit(partial(create_session, expected_hash=encoded, now=1002))
        self.devices = []
        for now in (1003, 1005):
            code = await self.writer.submit(partial(issue_pairing, token=self.owner.token, csrf=self.owner.csrf, mask=7, now=now))
            self.devices.append(await self.writer.submit(partial(enroll, code=code, now=now + 1)))

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def test_source_is_paused_by_default_and_bound_to_one_device(self):
        created = await self.writer.submit(partial(create_source, token=self.owner.token, csrf=self.owner.csrf,
                                                   device_id=self.devices[0].device_id, kind="browser", now=1010))
        self.assertEqual(created.status, "ok")
        source_id = created.source_id
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute("SELECT device_id,kind,paused,revision FROM sources WHERE source_id=?", (source_id,)).fetchone()
        self.assertEqual(row, (self.devices[0].device_id, "browser", 1, 1))
        self.assertTrue(await self.writer.submit(partial(owns_source, token=self.devices[0].token,
                                                         device_id=self.devices[0].device_id, source_id=source_id)))
        self.assertFalse(await self.writer.submit(partial(owns_source, token=self.devices[1].token,
                                                          device_id=self.devices[1].device_id, source_id=source_id)))
        self.assertFalse(await self.writer.submit(partial(owns_source, token=self.devices[0].token,
                                                          device_id=self.devices[1].device_id, source_id=source_id)))

    async def test_owner_auth_cas_and_revocation_are_enforced(self):
        denied = await self.writer.submit(partial(create_source, token=self.owner.token, csrf="invalid",
                                                  device_id=self.devices[0].device_id, kind="browser", now=1010))
        self.assertEqual(denied.status, "forbidden")
        created = await self.writer.submit(partial(create_source, token=self.owner.token, csrf=self.owner.csrf,
                                                   device_id=self.devices[0].device_id, kind="windows", now=1010))
        source = created.source_id
        self.assertEqual((await self.writer.submit(partial(set_source_pause, token=self.owner.token, csrf=self.owner.csrf,
                                                           source_id=source, expected_revision=1, paused=False, now=1011))).status, "ok")
        self.assertEqual((await self.writer.submit(partial(set_source_pause, token=self.owner.token, csrf=self.owner.csrf,
                                                           source_id=source, expected_revision=1, paused=True, now=1012))).status, "conflict")
        await self.writer.submit(partial(revoke_device, token=self.owner.token, csrf=self.owner.csrf,
                                         device_id=self.devices[0].device_id, now=1013))
        self.assertFalse(await self.writer.submit(partial(owns_source, token=self.devices[0].token,
                                                          device_id=self.devices[0].device_id, source_id=source)))
        denied = await self.writer.submit(partial(create_source, token=self.owner.token, csrf=self.owner.csrf,
                                                  device_id=self.devices[0].device_id, kind="browser", now=1014))
        self.assertNotEqual(denied.status, "ok")

    async def test_invalid_inputs_and_unknown_kind_fail_without_side_effects(self):
        for kind in ("ios", "macos", "safari", "unknown", ""):
            result = await self.writer.submit(partial(create_source, token=self.owner.token, csrf=self.owner.csrf,
                                                      device_id=self.devices[0].device_id, kind=kind, now=1010))
            self.assertEqual(result.status, "invalid")
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM sources").fetchone()[0], 0)

    async def test_source_and_audit_write_roll_back_together(self):
        with closing(sqlite3.connect(self.path)) as connection:
            count = connection.execute("SELECT count(*) FROM security_audit").fetchone()[0]
            result = create_source(connection, self.owner.token, self.owner.csrf, self.devices[0].device_id, "browser", 1010)
            self.assertEqual(result.status, "ok")
            connection.rollback()
            self.assertEqual(connection.execute("SELECT count(*) FROM sources").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM security_audit").fetchone()[0], count)

    async def test_audit_never_contains_device_or_source_ids(self):
        result = await self.writer.submit(partial(create_source, token=self.owner.token, csrf=self.owner.csrf,
                                                  device_id=self.devices[0].device_id, kind="browser", now=1010))
        with closing(sqlite3.connect(self.path)) as connection:
            audit = repr(connection.execute("SELECT event_type,actor,status,correlation_id FROM security_audit").fetchall())
        self.assertIn("source_create", audit)
        if result.source_id in audit or self.devices[0].device_id in audit or self.devices[0].token in audit:
            self.fail("Source identity or secret appeared in audit")
