import unittest

from personalcontext.privacy.url_normalize import normalize_url


class UrlNormalizeTests(unittest.TestCase):
    def test_strips_userinfo_query_and_fragment(self):
        self.assertEqual(
            normalize_url("HTTPS://" + "synthetic:" + "synthetic@Example.COM:443/article?token=synthetic#part"),
            "https://example.com/article",
        )

    def test_normalizes_idna_ipv6_and_ports(self):
        cases = {
            "http://ПРИМЕР.РФ:80": "http://xn--e1afmkfd.xn--p1ai/",
            "https://[2001:DB8::1]:443/x": "https://[2001:db8::1]/x",
            "https://example.org:8443/x": "https://example.org:8443/x",
            "http://127.0.0.1:8080/x": "http://127.0.0.1:8080/x",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_url(raw), expected)

    def test_rejects_invalid_values_without_echoing_input(self):
        cases = (
            "file:///synthetic", "https://", "https://bad_host/synthetic",
            "https://example.org:0/synthetic", "https://example.org:/synthetic",
            "https://example.org:99999/synthetic",
            "https://example.org\\@attacker.example/synthetic", "https://example.org/has\nnewline",
            "https://[fe80::1%25zone]/synthetic", "http://127.1/synthetic",
            "https://[2001:db8::1]attacker.example/synthetic",
        )
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError) as failure:
                    normalize_url(raw)
                self.assertEqual(str(failure.exception), "Invalid URL")
