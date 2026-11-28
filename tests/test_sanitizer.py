import unittest
from dataclasses import replace
from unittest.mock import patch

from personalcontext.privacy.sanitizer.app import sanitize_app
from personalcontext.privacy.sanitizer.rules import SanitizerContext
from personalcontext.privacy.sanitizer.text import sanitize_text
from personalcontext.privacy.sanitizer.web import sanitize_web


class SanitizerTests(unittest.TestCase):
    def setUp(self):
        self.context = SanitizerContext(
            allowed_domains=frozenset({"example.org"}), denied_domains=frozenset(),
            allowed_apps=frozenset({"reader.exe"}), denied_apps=frozenset(),
            private=False, sensitivity="ordinary",
        )

    def test_web_normalizes_and_discards_credentials_query_and_fragment(self):
        url = "https://" + "user:" + "pass@" + "EXAMPLE.org:443/articles/python?token=synthetic#part"
        value = {"url": url,
                 "title": "Синтетическая статья"}
        result = sanitize_web(value, self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.url, "https://example.org/articles/python")
        self.assertEqual(result.title, "Синтетическая статья")
        self.assertNotIn("Синтетическая статья", repr(result))

    def test_unknown_private_denied_domains_and_sensitive_paths_fail_closed(self):
        for context in (replace(self.context, private=True), replace(self.context, private=None),
                        replace(self.context, sensitivity="unknown"),
                        replace(self.context, denied_domains=frozenset({"example.org"}))):
            self.assertIsNone(sanitize_web({"url": "https://example.org/article"}, context))
        for url in ("https://other.example/article", "https://example.org/login",
                    "https://example.org/%6cogin", "https://example.org/%256cogin",
                    "https://example.org/oauth", "https://example.org/credentials",
                    "https://example.org/%D0%B1%D0%B0%D0%BD%D0%BA",
                    "https://example.org/%D0%BF%D0%BB%D0%B0%D1%82%D1%91%D0%B6",
                    "https://example.org/article/%00", "https://example.org/article/%ZZ",
                    "file:///C:/private", "https://example.org/a/../account"):
            with self.subTest(kind="url"):
                self.assertIsNone(sanitize_web({"url": url}, self.context))

    def test_secret_path_title_unknown_fields_and_untrusted_context_are_dropped(self):
        candidate = "synthetic" + "_" + "aB3x" * 12
        self.assertIsNone(sanitize_web({"url": "https://example.org/article/" + candidate}, self.context))
        canary = "api" + "_key=" + "synthetic-value"
        self.assertIsNone(sanitize_web({"url": "https://example.org/article", "title": canary}, self.context))
        self.assertIsNone(sanitize_web({"url": "https://example.org/article", "title": "synthetic%0Asecond"}, self.context))
        self.assertIsNone(sanitize_web({"url": "https://example.org/article", "form": "synthetic"}, self.context))
        self.assertIsNone(sanitize_web({"url": "https://example.org/article"}, {"private": False}))
        domain = "a" * 40 + ".example.org"
        context = replace(self.context, allowed_domains=frozenset({domain}))
        self.assertIsNone(sanitize_web({"url": "https://" + domain + "/article"}, context))

    def test_application_requires_explicit_allow_and_hard_deny_takes_precedence(self):
        result = sanitize_app({"app": "READER.EXE", "title": "Синтетическая книга"}, self.context)
        self.assertIsNotNone(result)
        self.assertEqual(result.app, "reader.exe")
        self.assertIsNone(sanitize_app({"app": "C:\\Users\\example\\reader.exe"}, self.context))
        self.assertIsNone(sanitize_app({"app": "unknown.exe"}, self.context))
        self.assertIsNone(sanitize_app({"app": "reader.exe"}, replace(self.context, denied_apps=frozenset({"reader.exe"}))))
        denied = replace(self.context, allowed_apps=frozenset({"password-manager.exe"}))
        self.assertIsNone(sanitize_app({"app": "password-manager.exe"}, denied))

    def test_text_rejects_secret_pii_markup_and_oversized_content(self):
        self.assertEqual(sanitize_text("Синтетический пример текста", 16384), "Синтетический пример текста")
        for text in ("Contact synthetic@example.org", "пользователь@пример.рф", "+7 (999) 111-22-33",
                     "192.0.2.1", "2001:db8::1", "<form>synthetic</form>", "synthetic <input value=example",
                     "Bearer " + "x" * 40, "api" + "_key=" + "synthetic-value", "пароль" + ": пример",
                     "api%255Fkey%253Dsynthetic", "x" * 32, "x" * 16385):
            self.assertIsNone(sanitize_text(text, 16384))
        self.assertIsNone(sanitize_text("synthetic", True))

    def test_deny_suffix_and_sensitive_domain_cannot_be_overridden_by_allow(self):
        context = replace(self.context, allowed_domains=frozenset({"sub.example.org", "bank.example.org"}),
                          denied_domains=frozenset({"example.org"}))
        self.assertIsNone(sanitize_web({"url": "https://sub.example.org/article"}, context))
        context = replace(context, denied_domains=frozenset())
        self.assertIsNone(sanitize_web({"url": "https://bank.example.org/article"}, context))
        domain = "банк.рф".encode("idna").decode("ascii")
        context = replace(context, allowed_domains=frozenset({domain}))
        self.assertIsNone(sanitize_web({"url": "https://банк.рф/article"}, context))

    def test_malformed_input_and_source_context_never_log_payload(self):
        candidate = "api" + "_key=" + "synthetic-value"
        with patch("logging.Logger._log") as logger:
            for raw in (None, [], 3, {"url": None}, {"url": "https://example.org/", "title": candidate}):
                self.assertIsNone(sanitize_web(raw, self.context))
            for context in (replace(self.context, private=0), replace(self.context, allowed_domains=frozenset({"EXAMPLE.org"})),
                            replace(self.context, sensitivity=None)):
                self.assertIsNone(sanitize_web({"url": "https://example.org/article"}, context))
            logger.assert_not_called()
