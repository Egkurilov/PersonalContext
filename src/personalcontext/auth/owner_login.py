"""Internal owner login; HTTP origin, cookie and transport checks are separate."""

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from personalcontext.auth.owner_sessions import (
    SessionSecrets,
    create_session,
    revoke_authorized_session,
)
from personalcontext.auth.owner_store import find_owner_hash
from personalcontext.auth.password_executor import PasswordExecutor
from personalcontext.auth.password_hash import is_supported_hash
from personalcontext.auth.rate_limit import consume_attempt
from personalcontext.jobs.writer import Writer


@dataclass(frozen=True)
class LoginResult:
    status: Literal["ok", "invalid", "limited", "unavailable"]
    session: SessionSecrets | None = field(default=None, repr=False)
    retry_after: int | None = None


class OwnerLogin:
    def __init__(self, writer: Writer, executor: PasswordExecutor, dummy_hash: str,
                 clock: Callable[[], int] | None = None) -> None:
        if not is_supported_hash(dummy_hash):
            raise ValueError("Invalid verifier configuration")
        self._writer = writer
        self._executor = executor
        self._dummy_hash = dummy_hash
        self._clock = clock or (lambda: int(time.time()))

    @classmethod
    async def create(cls, writer: Writer, executor: PasswordExecutor,
                     clock: Callable[[], int] | None = None) -> "OwnerLogin":
        dummy_hash = await executor.hash(secrets.token_urlsafe(32))
        return cls(writer, executor, dummy_hash, clock)

    async def authenticate(self, password: str, *, now: int | None = None) -> LoginResult:
        clock = self._clock if now is None else lambda: now
        decision = await self._writer.submit(lambda connection: consume_attempt(connection, action="owner_login", now=clock()))
        if not decision.allowed:
            return LoginResult("limited", retry_after=decision.retry_after)
        stored = await self._writer.submit(find_owner_hash)
        valid_hash = is_supported_hash(stored)
        target = stored if valid_hash and stored is not None else self._dummy_hash
        try:
            matched = await self._executor.verify(target, password)
        except RuntimeError:
            return LoginResult("unavailable")
        if not valid_hash or stored is None or not matched:
            return LoginResult("invalid")
        session = await self._writer.submit(lambda connection: create_session(connection, expected_hash=stored, now=clock()))
        return LoginResult("ok", session=session) if session is not None else LoginResult("unavailable")

    async def logout(self, token: object, csrf: object, *, now: int | None = None) -> bool:
        clock = self._clock if now is None else lambda: now
        return await self._writer.submit(
            lambda connection: revoke_authorized_session(connection, token=token, csrf=csrf, now=clock()),
        )
