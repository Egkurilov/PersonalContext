"""Domain metadata must normalize without accepting URL authority syntax."""

import unittest

from pydantic import ValidationError

from personalcontext.ingest.visit.model import WebPayload


class WebVisitDomainTests(unittest.TestCase):
    def test_idna_and_case_normalization(self):
        value = WebPayload.model_validate({"domain": "ПРИМЕР.РФ", "url": "https://пример.рф/article"})
        self.assertEqual(value.domain, "xn--e1afmkfd.xn--p1ai")

    def test_authority_components_are_not_domains(self):
        for domain in ("user@example.org", "example.org:443", "example.org/path", "example.org?synthetic"):
            with self.subTest(kind="invalid"), self.assertRaises(ValidationError):
                WebPayload.model_validate({"domain": domain, "url": "https://example.org/article"})
