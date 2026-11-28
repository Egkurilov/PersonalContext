"""Restart a synthetic frozen profile and verify the process-local capture latch."""

import json
import subprocess
import time
from urllib.error import URLError


def restart_and_check(process, executable, env, opener, origin):
    process.terminate()
    process.wait(timeout=10)
    restarted = subprocess.Popen([str(executable)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while True:
            if restarted.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Restarted application did not become ready")
            try:
                with opener.open(origin + "/readyz", timeout=1) as response:
                    if response.status == 200:
                        break
            except URLError:
                time.sleep(0.25)
        with opener.open(origin + "/api/v1/privacy/policy", timeout=5) as response:
            policy = json.load(response)
            assert policy["paused"] is False
            assert policy["local_paused"] is True and policy["effective_paused"] is True
        print("Frozen synthetic policy restart smoke passed")
        return restarted
    except BaseException:
        if restarted.poll() is None:
            restarted.terminate()
            restarted.wait(timeout=10)
        raise
