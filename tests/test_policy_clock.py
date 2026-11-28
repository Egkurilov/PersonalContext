"""The local capture latch rejects wall-clock rollback while the process runs."""

import unittest
from unittest.mock import patch

from personalcontext.privacy.runtime.latch import CaptureLatch


class PolicyClockTests(unittest.TestCase):
    def test_clock_progress_is_compared_with_monotonic_time(self):
        latch = CaptureLatch()
        with patch("personalcontext.privacy.runtime.latch.time.monotonic", side_effect=[100, 110]):
            self.assertTrue(latch.observe_time(1000))
            self.assertTrue(latch.resume_if_unchanged(latch.generation()))
            self.assertFalse(latch.observe_time(1005))
        self.assertTrue(latch.is_paused())

    def test_high_water_mark_and_invalid_values_fail_closed(self):
        for invalid in (True, -1, float("nan"), float("inf"), "100", 10**1000):
            with self.subTest(value=repr(invalid)):
                latch = CaptureLatch()
                self.assertFalse(latch.observe_time(invalid))
                self.assertTrue(latch.is_paused())
        latch = CaptureLatch()
        with patch("personalcontext.privacy.runtime.latch.time.monotonic", side_effect=[1, 2, 3]):
            self.assertTrue(latch.observe_time(1000))
            self.assertTrue(latch.observe_time(1100))
            self.assertFalse(latch.observe_time(1090))
