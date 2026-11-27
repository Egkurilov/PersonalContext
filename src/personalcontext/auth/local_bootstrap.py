"""Complete owner bootstrap from an explicitly invoked native UI only."""

import time
from collections.abc import Callable

from personalcontext.auth.bootstrap_store import issue_bootstrap
from personalcontext.auth.owner_bootstrap import BootstrapResult, OwnerBootstrap
from personalcontext.jobs.writer import Writer


async def setup_local_owner(writer: Writer, bootstrap: OwnerBootstrap, password: str,
                            clock: Callable[[], int] | None = None) -> BootstrapResult:
    current_time = clock or (lambda: int(time.time()))
    try:
        code = await writer.submit(lambda connection: issue_bootstrap(connection, now=current_time()))
    except RuntimeError:
        return BootstrapResult("unavailable")
    return await bootstrap.complete(code, password)
