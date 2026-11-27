import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from functools import partial
from pathlib import Path

from personalcontext.auth.owner_store import find_owner_hash, insert_owner_hash
from personalcontext.auth.password_hash import hash_password, verify_password
from personalcontext.jobs.writer import Writer
from personalcontext.storage.initialize import initialize_database


class OwnerStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_create_is_singleton_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            first = "synthetic first candidate"
            second = "synthetic second candidate"
            digests = [hash_password(first), hash_password(second)]
            writer = Writer(path)
            await writer.start()
            try:
                outcomes = await asyncio.gather(*(writer.submit(partial(insert_owner_hash, encoded=x)) for x in digests))
                self.assertEqual(sorted(outcomes), [False, True])
                stored = await writer.submit(find_owner_hash)
            finally:
                await writer.close()
            self.assertEqual(stored, digests[outcomes.index(True)])
            with closing(sqlite3.connect(path)) as connection:
                persisted = find_owner_hash(connection)
                self.assertEqual(persisted, stored)
                self.assertTrue(verify_password(persisted, [first, second][outcomes.index(True)]))
            self.assertNotIn(first.encode(), path.read_bytes())
            self.assertNotIn(second.encode(), path.read_bytes())

    async def test_plaintext_and_malformed_hash_are_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            writer = Writer(path)
            await writer.start()
            try:
                with self.assertRaisesRegex(ValueError, "Invalid password hash"):
                    await writer.submit(partial(insert_owner_hash, encoded="synthetic plaintext"))
                self.assertIsNone(await writer.submit(find_owner_hash))
            finally:
                await writer.close()

    async def test_uncommitted_insert_can_be_rolled_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.db"
            initialize_database(path)
            digest = hash_password("synthetic rollback candidate")
            with closing(sqlite3.connect(path)) as connection:
                self.assertTrue(insert_owner_hash(connection, digest))
                connection.rollback()
                self.assertIsNone(find_owner_hash(connection))
                self.assertTrue(insert_owner_hash(connection, digest))
                connection.commit()
                self.assertEqual(find_owner_hash(connection), digest)
