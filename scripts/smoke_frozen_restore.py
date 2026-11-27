"""Check frozen restore revokes synthetic credentials and pauses consent."""

import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

from personalcontext.auth.bootstrap_store import consume_bootstrap, issue_bootstrap
from personalcontext.auth.owner_sessions import create_session, session_active
from personalcontext.auth.owner_store import find_owner_hash
from personalcontext.auth.password_hash import hash_password
from personalcontext.devices.pairing import enroll, issue_pairing
from personalcontext.devices.scopes import authorize_device
from personalcontext.network.boundary import PrivateBoundary
from personalcontext.network.private_settings import PrivateCandidate, save_candidate
from personalcontext.network.tls_vault import seal_passphrase
from personalcontext.privacy.policy_store import PolicyDraft, load_policy, save_policy
from personalcontext.sources.registry import create_source, set_source_pause
from personalcontext.storage.backup import backup_database
from personalcontext.storage.initialize import initialize_database


def main():
    executable = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/PersonalContext/PersonalContext.exe").resolve()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "context.db"
        initialize_database(path)
        with closing(sqlite3.connect(path)) as connection:
            encoded = hash_password("synthetic frozen restore")
            bootstrap = issue_bootstrap(connection, 1000)
            connection.commit()
            assert consume_bootstrap(connection, bootstrap, encoded, 1001)
            connection.commit()
            owner = create_session(connection, encoded, 1002)
            connection.commit()
            code = issue_pairing(connection, owner.token, owner.csrf, 1, 1003)
            connection.commit()
            device = enroll(connection, code, 1004)
            connection.commit()
            source = create_source(connection, owner.token, owner.csrf, device.device_id, "browser", 1004)
            assert source.status == "ok"
            connection.commit()
            assert set_source_pause(connection, owner.token, owner.csrf, source.source_id, 1, False, 1005).status == "ok"
            connection.commit()
            boundary = PrivateBoundary.create("192.168.7.2", "pc.example.test", 18443, ["192.168.7.0/24"])
            candidate = PrivateCandidate(boundary, "cert.pem", "key.pem", seal_passphrase(b"synthetic-passphrase"))
            assert save_candidate(connection, owner.token, owner.csrf, 0, candidate, 1005).status == "ok"
            connection.commit()
            code = issue_pairing(connection, owner.token, owner.csrf, 1, 1005)
            connection.commit()
            draft = PolicyDraft(False, 600, frozenset({"synthetic-source"}), frozenset(),
                                frozenset({("synthetic-source", "metadata")}))
            assert save_policy(connection, owner.token, owner.csrf, 1, draft, 1006).status == "ok"
            connection.commit()
            backup = backup_database(connection, path)
        restored = Path(directory) / "restored.db"
        env = os.environ.copy()
        env["LOCALAPPDATA"] = directory
        subprocess.run([str(executable), "--restore", str(backup), str(restored)], env=env, check=True,
                       capture_output=True, timeout=20)
        with closing(sqlite3.connect(restored)) as connection:
            assert find_owner_hash(connection) is None
            assert not session_active(connection, owner.token, 1007)
            assert not authorize_device(connection, device.token, device.device_id, 1)
            assert enroll(connection, code, 1007) is None
            connection.rollback()
            assert load_policy(connection).paused
            assert connection.execute("SELECT count(*) FROM private_network_candidate").fetchone() == (0,)
            assert connection.execute("SELECT paused FROM sources WHERE source_id=?", (source.source_id,)).fetchone() == (1,)
            assert connection.execute("SELECT count(*) FROM security_audit WHERE event_type='restore'").fetchone()[0] == 1
        print("Frozen synthetic restore safety smoke passed")


if __name__ == "__main__":
    main()
