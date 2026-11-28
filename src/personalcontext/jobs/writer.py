import asyncio
import queue
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


class Writer:
    def __init__(self, path: Path, capacity: int = 32, *, on_storage_failure: Callable[[], None] | None = None) -> None:
        self.path = path
        self.on_storage_failure = on_storage_failure
        self.safety_failed = threading.Event()
        self.queue: queue.Queue[tuple[Callable[[sqlite3.Connection], Any], Future[Any]] | None] = queue.Queue(maxsize=capacity)
        self.closed = False
        self.lock = threading.Lock()
        self.ready: Future[None] = Future()
        self.thread = threading.Thread(target=self._run, name="sqlite-writer", daemon=True)
        self.thread.start()

    def _fail_closed(self) -> None:
        if self.on_storage_failure is not None:
            try:
                self.on_storage_failure()
            except Exception:  # noqa: BLE001 - stop the writer if fail-closed signalling fails
                self.safety_failed.set()

    def _run(self) -> None:
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=5)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
        except Exception as error:  # noqa: BLE001 - propagate failures to the submitting task
            self._fail_closed()
            if connection is not None:
                connection.close()
            with self.lock:
                self.closed = True
            self.ready.set_exception(error)
            return
        self.ready.set_result(None)
        try:
            while True:
                item = self.queue.get()
                try:
                    if item is None:
                        return
                    operation, future = item
                    if not future.set_running_or_notify_cancel():
                        continue
                    try:
                        result = operation(connection)
                        if self.safety_failed.is_set():
                            raise RuntimeError("Writer safety unavailable")
                        connection.commit()
                    except Exception as error:  # noqa: BLE001 - propagate failures to the submitting task
                        if isinstance(error, sqlite3.Error):
                            self._fail_closed()
                        try:
                            connection.rollback()
                        except sqlite3.Error as rollback_error:
                            future.set_exception(rollback_error)
                            return
                        future.set_exception(error)
                        if self.safety_failed.is_set():
                            return
                    else:
                        future.set_result(result)
                finally:
                    self.queue.task_done()
        finally:
            with self.lock:
                self.closed = True
                while True:
                    try:
                        item = self.queue.get_nowait()
                    except queue.Empty:
                        break
                    if item is not None and not item[1].done():
                        item[1].set_exception(RuntimeError("Writer stopped"))
                    self.queue.task_done()
            connection.close()

    async def start(self) -> None:
        await asyncio.wrap_future(self.ready)

    async def submit(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        future: Future[T] = Future()
        with self.lock:
            if self.safety_failed.is_set():
                raise RuntimeError("Writer safety unavailable")
            if self.closed:
                self._fail_closed()
                raise RuntimeError("Writer is closed")
            try:
                self.queue.put_nowait((operation, future))
            except queue.Full as error:
                self._fail_closed()
                raise RuntimeError("Writer queue is full") from error
        return await asyncio.wrap_future(future)

    async def close(self) -> None:
        with self.lock:
            should_stop = not self.closed
            self.closed = True
        if should_stop and self.thread.is_alive():
            await asyncio.to_thread(self.queue.put, None)
        await asyncio.to_thread(self.thread.join)
