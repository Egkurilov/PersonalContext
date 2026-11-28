"""Internal owner credential storage; caller must authorize bootstrap first."""

import sqlite3

from personalcontext.auth.password_hash import is_supported_hash


def insert_owner_hash(connection: sqlite3.Connection, encoded: str) -> bool:
    if not is_supported_hash(encoded):
        raise ValueError("Invalid password hash")
    connection.execute("BEGIN IMMEDIATE")
    return insert_owner_hash_in_transaction(connection, encoded)


def insert_owner_hash_in_transaction(connection: sqlite3.Connection, encoded: str) -> bool:
    if not connection.in_transaction or not is_supported_hash(encoded):
        raise ValueError("Invalid password hash or transaction")
    result = connection.execute(
        "INSERT INTO owner_credentials(singleton, password_hash) VALUES (1, ?) "
        "ON CONFLICT(singleton) DO NOTHING",
        (encoded,),
    )
    return result.rowcount == 1


def find_owner_hash(connection: sqlite3.Connection) -> str | None:
    row = connection.execute("SELECT password_hash FROM owner_credentials WHERE singleton=1").fetchone()
    return str(row[0]) if row else None
