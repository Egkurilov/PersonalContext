"""Owner-facing policy status and bounded error responses."""

import time

from fastapi.responses import JSONResponse

from personalcontext.auth.http_routes import error
from personalcontext.privacy.capture_policy import CapturePolicy
from personalcontext.privacy.policy_store import PolicyResult
from personalcontext.privacy.runtime.clock import policy_time_valid
from personalcontext.privacy.runtime.latch import CaptureLatch


def policy_response(policy: CapturePolicy, latch: CaptureLatch) -> JSONResponse:
    assert policy.issued_at is not None and policy.expires_at is not None
    now = int(time.time())
    issued, expires = int(policy.issued_at.timestamp()), int(policy.expires_at.timestamp())
    valid_time = policy_time_valid(latch, policy, now)
    local_paused = latch.is_paused()
    return JSONResponse({"version": policy.version, "issued_at": issued,
                         "expires_at": expires, "paused": policy.paused,
                         "effective_paused": local_paused or policy.paused or not valid_time,
                         "local_paused": local_paused,
                         "allowed": sorted(policy.allowed_sources), "denied": sorted(policy.denied_sources),
                         "grants": [{"source": source, "scope": scope} for source, scope in sorted(policy.grants)]},
                        headers={"Cache-Control": "no-store"})


def failure(result: PolicyResult) -> JSONResponse:
    status = {"invalid": 400, "forbidden": 403, "conflict": 409, "unavailable": 503}.get(result.status, 503)
    return error(status, result.status)
