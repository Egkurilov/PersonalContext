"""Internal bootstrap completion; local issuance and transport are separate."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from personalcontext.auth.bootstrap_store import consume_bootstrap
from personalcontext.auth.password_executor import PasswordExecutor
from personalcontext.auth.rate_limit import consume_attempt
from personalcontext.jobs.writer import Writer


@dataclass(frozen=True)
class BootstrapResult:
    status: Literal["ok", "invalid", "limited", "unavailable"]
    retry_after: int | None = None


class OwnerBootstrap:
    def __init__(self, writer: Writer, executor: PasswordExecutor, clock: Callable[[], int] | None = None) -> None:
        self._writer = writer
        self._executor = executor
        self._clock = clock or (lambda: int(time.time()))

    async def complete(self, code: object, password: str) -> BootstrapResult:
        decision = await self._writer.submit(
            lambda connection: consume_attempt(connection, action="owner_bootstrap", now=self._clock()),
        )
        if not decision.allowed:
            return BootstrapResult("limited", decision.retry_after)
        try:
            encoded = await self._executor.hash(password)
        except ValueError:
            return BootstrapResult("invalid")
        except RuntimeError:
            return BootstrapResult("unavailable")
        created = await self._writer.submit(
            lambda connection: consume_bootstrap(connection, candidate=code, encoded=encoded, now=self._clock()),
        )
        return BootstrapResult("ok" if created else "invalid")
