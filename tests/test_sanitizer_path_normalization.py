"""Unicode and entity normalization must not introduce unsafe path structure."""

import unittest

from personalcontext.privacy.sanitizer.rules import SanitizerContext
from personalcontext.privacy.sanitizer.web import sanitize_web


class PathNormalizationTests(unittest.TestCase):
    def test_normalized_traversal_and_separators_are_rejected(self):
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}),
                                   private=False, sensitivity="ordinary")
        for path in ("/．/article", "/．．/article", "/a／／article",
                     "/%EF%BC%8E%EF%BC%8E/article", "/%26%2346%3B%26%2346%3B/article",
                     "/a＼article", "/a/%26%2337%3B2e%26%2337%3B2e/article"):
            with self.subTest(path=path):
                self.assertIsNone(sanitize_web({"url": "https://example.org" + path}, context))

    def test_safe_unicode_path_remains_available(self):
        context = SanitizerContext(allowed_domains=frozenset({"example.org"}),
                                   private=False, sensitivity="ordinary")
        result = sanitize_web({"url": "https://example.org/статья"}, context)
        self.assertIsNotNone(result)
        self.assertEqual(result.url, "https://example.org/%D1%81%D1%82%D0%B0%D1%82%D1%8C%D1%8F")


if __name__ == "__main__":
    unittest.main()
