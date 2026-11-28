"""Device-bound heartbeat, authorized in the same transaction as the write."""

import sqlite3

from personalcontext.devices.scopes import HEARTBEAT, authorize_device


def record_heartbeat(connection: sqlite3.Connection, token: object, device_id: object, now: int,
                     origin: object = None) -> bool:
    if type(now) is not int or not 0 <= now <= 2**53 - 300:
        return False
    connection.execute("BEGIN IMMEDIATE")
    if not authorize_device(connection, token, device_id, HEARTBEAT, origin):
        return False
    return connection.execute(
        "UPDATE devices SET last_seen=? WHERE device_id=? AND created_at <= ? AND (last_seen IS NULL OR last_seen <= ?)",
        (now, device_id, now, now),
    ).rowcount == 1
