import asyncio
import queue
import sqlite3
import threading
from concurrent.futures import Future
from pathlib import Path


class Writer:
    def __init__(self, path: Path, capacity: int = 32):
        self.path = path
        self.queue = queue.Queue(maxsize=capacity)
        self.closed = False
        self.lock = threading.Lock()
        self.ready = Future()
        self.thread = threading.Thread(target=self._run, name="sqlite-writer", daemon=True)
        self.thread.start()

    def _run(self):
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=5)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
        except Exception as error:  # noqa: BLE001 - propagate failures to the submitting task
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
                        connection.commit()
                    except Exception as error:  # noqa: BLE001 - propagate failures to the submitting task
                        try:
                            connection.rollback()
                        except sqlite3.Error as rollback_error:
                            future.set_exception(rollback_error)
                            return
                        future.set_exception(error)
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

    async def start(self):
        await asyncio.wrap_future(self.ready)

    async def submit(self, operation):
        future = Future()
        with self.lock:
            if self.closed:
                raise RuntimeError("Writer is closed")
            try:
                self.queue.put_nowait((operation, future))
            except queue.Full as error:
                raise RuntimeError("Writer queue is full") from error
        return await asyncio.wrap_future(future)

    async def close(self):
        with self.lock:
            should_stop = not self.closed
            self.closed = True
        if should_stop and self.thread.is_alive():
            await asyncio.to_thread(self.queue.put, None)
        await asyncio.to_thread(self.thread.join)
