import io
import unittest

from scripts.setup_diagnostics import observe_setup


class SetupDiagnosticsTests(unittest.TestCase):
    def test_keeps_only_known_stage_and_error_category(self):
        stream = io.BytesIO(
            b"PersonalContext: installing frontend dependencies\n"
            b"npm error code ENOTCACHED\n"
            b"synthetic private diagnostic content\n"
        )
        state = {"stage": "not started", "reason": "unspecified"}
        observe_setup(stream, state)
        self.assertEqual(state, {
            "stage": "PersonalContext: installing frontend dependencies",
            "reason": "offline dependency cache incomplete",
        })
