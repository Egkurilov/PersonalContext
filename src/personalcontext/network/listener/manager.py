"""Explicitly start and stop one private HTTPS server on the host event loop."""

import asyncio
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from personalcontext.jobs.writer import Writer
from personalcontext.network.firewall.status import firewall_status
from personalcontext.network.listener.bind import bind_listener
from personalcontext.network.listener.cancel import StartCancelled, preflight
from personalcontext.network.listener.monitor import monitor_listener
from personalcontext.network.listener.read import (
    audit_attempt,
    authorized_candidate,
)
from personalcontext.network.listener.shutdown import stop_listener, stop_locked
from personalcontext.network.uvicorn_config import private_server_config


class PrivateServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        """The primary host owns process signals and application lifespan."""
        yield


class PrivateListener:
    def __init__(self, app: FastAPI, writer: Writer, tls_dir: Path) -> None:
        self.app, self.writer, self.tls_dir = app, writer, tls_dir
        self.lock = asyncio.Lock()
        self.server: uvicorn.Server | None = None
        self.task: asyncio.Task[None] | None = None
        self.monitor: asyncio.Task[None] | None = None
        self.socket: socket.socket | None = None
        self.generation = 0
        self.cancel_start: asyncio.Event | None = None

    def active(self) -> bool:
        return bool(self.server is not None and self.server.started and self.task is not None and not self.task.done())

    def healthy(self) -> bool:
        state = self.app.state
        return bool(getattr(state, "ready", False) and not self.writer.closed and not self.writer.safety_failed.is_set()
                    and not state.scheduler.task.done() and not state.audit_housekeeping.task.done())

    async def start(self, token: object, csrf: object, revision: object) -> str:
        generation = self.generation
        async with self.lock:
            if generation != self.generation:
                return "conflict"
            if self.server is not None:
                return "conflict"
            if not self.healthy():
                return "unavailable"
            cancel = self.cancel_start = asyncio.Event()
            try:
                status, saved = await self.writer.submit(lambda c: authorized_candidate(c, token, csrf, revision))
                if status != "ok" or saved is None:
                    return status
                candidate = saved.candidate
                if await preflight(cancel, firewall_status, candidate.boundary, sys.executable) != "restricted":
                    return "unavailable"
                config = await preflight(cancel, private_server_config, self.app, candidate.boundary,
                                         self.tls_dir / candidate.cert_name, self.tls_dir / candidate.key_name,
                                         candidate.protected)
                if await preflight(cancel, firewall_status, candidate.boundary, sys.executable) != "restricted":
                    return "unavailable"
                status, current = await self.writer.submit(lambda c: authorized_candidate(c, token, csrf, revision))
                if status != "ok":
                    return status
                if current != saved or cancel.is_set():
                    return "conflict"
                if not self.healthy():
                    return "unavailable"
                listener = bind_listener(candidate.boundary)
            except StartCancelled:
                return "conflict"
            except Exception:  # noqa: BLE001 - never leak TLS paths or firewall details
                return "unavailable"
            try:
                status = await self.writer.submit(lambda c: audit_attempt(c, token, csrf, revision, saved))
                if status != "ok" or cancel.is_set():
                    listener.close()
                    return "conflict" if cancel.is_set() else status
                self.socket = listener
                self.server = PrivateServer(config)
                self.task = asyncio.create_task(self.server.serve(sockets=[listener]))
                async with asyncio.timeout(10):
                    while not self.server.started and not self.task.done() and not cancel.is_set():
                        await asyncio.sleep(0.02)
                if cancel.is_set():
                    await stop_locked(self)
                    return "conflict"
                if not self.active():
                    await stop_locked(self)
                    return "unavailable"
                self.monitor = asyncio.create_task(monitor_listener(self, candidate.boundary))
                return "ok"
            except Exception:  # noqa: BLE001 - close the socket on any startup failure
                listener.close()
                await stop_locked(self)
                return "unavailable"
            except BaseException:
                listener.close()
                await stop_locked(self)
                raise

    async def stop(self) -> None:
        await stop_listener(self)
