"""Process-local fail-closed stop switch with stale-resume protection."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class CaptureLatch:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._commit_lock = threading.Lock()
        self._paused = True
        self._generation = 0
        self._draining = False

    def pause(self) -> None:
        with self._lock:
            self._paused = True
            self._generation += 1
            self._draining = True

    def generation(self) -> int:
        with self._lock:
            return self._generation

    def resume_if_unchanged(self, generation: int) -> bool:
        with self._lock:
            if type(generation) is not int or generation != self._generation or self._draining:
                return False
            self._paused = False
            return True

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def ticket(self) -> int | None:
        with self._lock:
            return None if self._paused else self._generation

    def allows(self, ticket: object) -> bool:
        with self._lock:
            return type(ticket) is int and not self._paused and ticket == self._generation

    @contextmanager
    def commit_window(self) -> Iterator[None]:
        with self._commit_lock:
            yield

    def drain(self, timeout: float | None = None) -> bool:
        with self._lock:
            generation = self._generation
        acquired = self._commit_lock.acquire() if timeout is None else self._commit_lock.acquire(timeout=timeout)
        if not acquired:
            return False
        try:
            with self._lock:
                if self._generation != generation:
                    return False
                self._draining = False
                return True
        finally:
            self._commit_lock.release()
