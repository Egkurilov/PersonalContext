import time
import uuid


def enqueue(connection, kind, key):
    connection.execute("BEGIN IMMEDIATE")
    previous = connection.execute("SELECT kind FROM jobs WHERE idempotency_key=?", (key,)).fetchone()
    if previous:
        if previous[0] != kind:
            raise ValueError("Idempotency key is already in use")
        return False
    connection.execute("INSERT INTO jobs(idempotency_key,kind,status) VALUES (?,?,'pending')", (key, kind))
    return True


def claim(connection, kinds, lease_seconds):
    if not kinds:
        return None
    now = time.time()
    connection.execute("BEGIN IMMEDIATE")
    placeholders = ",".join("?" for _ in kinds)
    row = connection.execute(
        f"SELECT idempotency_key,kind,attempts FROM jobs WHERE kind IN ({placeholders}) "
        "AND ((status='pending' AND retry_at<=?) OR (status='running' AND lease_until<=?)) "
        "ORDER BY retry_at,idempotency_key LIMIT 1", (*kinds, now, now),
    ).fetchone()
    if row is None:
        return None
    key, kind, attempts = row
    if attempts >= 5:
        connection.execute(
            "UPDATE jobs SET status='failed',lease_until=NULL,lease_token=NULL WHERE idempotency_key=?",
            (key,),
        )
        return None
    token = uuid.uuid4().hex
    connection.execute(
        "UPDATE jobs SET status='running',attempts=?,lease_until=?,lease_token=? WHERE idempotency_key=?",
        (attempts + 1, now + lease_seconds, token, key),
    )
    return key, kind, attempts + 1, token


def finish(connection, key, token, attempts, succeeded):
    connection.execute("BEGIN IMMEDIATE")
    status = "done" if succeeded else "failed" if attempts >= 5 else "pending"
    retry_at = 0 if succeeded else time.time() + min(1800, 2 ** attempts)
    connection.execute(
        "UPDATE jobs SET status=?,retry_at=?,lease_until=NULL,lease_token=NULL "
        "WHERE idempotency_key=? AND status='running' AND lease_token=?",
        (status, retry_at, key, token),
    )
