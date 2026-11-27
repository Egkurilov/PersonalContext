import json
import unittest
from pathlib import Path

from personalcontext.privacy.sanitizer.rules import SanitizerContext
from personalcontext.privacy.sanitizer.web import sanitize_web


class SanitizerFixtureTests(unittest.TestCase):
    def test_shared_synthetic_web_cases(self):
        path = Path(__file__).parent / "fixtures" / "sanitizer-web.json"
        cases = json.loads(path.read_text(encoding="utf8"))
        for case in cases:
            with self.subTest(case=case["case"]):
                context = SanitizerContext(allowed_domains=frozenset({case.get("domain", "example.org")}),
                                           private=case.get("private", False), sensitivity="ordinary")
                result = sanitize_web({"url": case["url"]}, context)
                self.assertEqual(None if result is None else result.url, case["expected"])
