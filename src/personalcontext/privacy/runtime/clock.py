"""Fail closed when a policy expires or the process observes clock rollback."""

from datetime import datetime

from personalcontext.privacy.capture_policy import CapturePolicy
from personalcontext.privacy.runtime.latch import CaptureLatch


def policy_time_valid(latch: CaptureLatch, policy: CapturePolicy, now: object) -> bool:
    try:
        if isinstance(now, datetime):
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("Naive clock")
            wall = now.timestamp()
        elif isinstance(now, (int, float)) and not isinstance(now, bool):
            wall = float(now)
        else:
            raise TypeError("Invalid clock")
        if not latch.observe_time(wall):
            return False
        if policy.issued_at is None or policy.expires_at is None:
            raise ValueError("Missing policy time")
        valid = policy.issued_at.timestamp() <= wall < policy.expires_at.timestamp()
        if not valid and policy.paused is False and not latch.is_paused():
            latch.pause()
        return valid
    except (ValueError, TypeError, OverflowError, OSError):
        latch.pause()
        return False
