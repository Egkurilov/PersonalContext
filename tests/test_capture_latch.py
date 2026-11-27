import threading
import unittest

from personalcontext.privacy.runtime.latch import CaptureLatch


class CaptureLatchTests(unittest.TestCase):
    def test_default_pause_and_explicit_resume(self):
        latch = CaptureLatch()
        self.assertTrue(latch.is_paused())
        self.assertIsNone(latch.ticket())
        revision = latch.generation()
        self.assertTrue(latch.resume_if_unchanged(revision))
        ticket = latch.ticket()
        self.assertIsNotNone(ticket)
        self.assertTrue(latch.allows(ticket))
        latch.pause()
        self.assertFalse(latch.allows(ticket))
        self.assertTrue(latch.is_paused())
        self.assertFalse(latch.resume_if_unchanged(latch.generation()))
        self.assertTrue(latch.drain())
        self.assertTrue(latch.resume_if_unchanged(latch.generation()))

    def test_pause_invalidates_inflight_resume_even_if_database_write_finishes_later(self):
        latch = CaptureLatch()
        ticket = latch.generation()
        started, done = threading.Event(), threading.Event()
        result = []

        def resume():
            started.set()
            done.wait(timeout=2)
            result.append(latch.resume_if_unchanged(ticket))

        worker = threading.Thread(target=resume)
        worker.start()
        self.assertTrue(started.wait(timeout=2))
        latch.pause()
        done.set()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [False])
        self.assertTrue(latch.is_paused())

    def test_new_process_starts_paused(self):
        previous = CaptureLatch()
        self.assertTrue(previous.resume_if_unchanged(previous.generation()))
        previous.pause()
        self.assertTrue(CaptureLatch().is_paused())
