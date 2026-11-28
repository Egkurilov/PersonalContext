# PC-002 URL Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize HTTP(S) URLs without userinfo, query or fragment, rejecting malformed input.

**Architecture:** A pure, unconnected URL-normalization leaf raises a generic error on invalid input. It does not replace consent, deny rules or sensitive-path filtering and does not collect, persist or transmit data.

**Tech Stack:** Python 3.12 standard library and unittest.

---

### Task 1: Canonical URL component

**Files:**
- Create: `src/personalcontext/privacy/url_normalize.py`
- Test: `tests/test_url_normalize.py`

- [x] Write tests for IDNA, IPv6, default/non-default ports, stripping credentials/query/fragment and rejecting invalid hosts, controls, backslashes and non-HTTP schemes. Verify exceptions never echo the input.
- [x] Run `.venv/Scripts/python -m unittest discover -s tests -p test_url_normalize.py -v`; expect import failure before implementation.
- [x] Implement `normalize_url(value: str) -> str` with `urllib.parse.urlsplit`/`urlunsplit`, explicit host and port validation, `ipaddress` for IP literals and IDNA for DNS names; raise `ValueError("Invalid URL")` without chaining on invalid input. Preserve the path as untrusted content for later policy/sensitive-data filtering.
- [x] Run the focused tests, `.venv/Scripts/ruff check src tests`, `.venv/Scripts/mypy src/personalcontext`, and the native project tests.

PC-002 also requires bootstrap, sessions/CSRF, device pairing/revoke, policy and sanitizer integration, audit, rate limiting and optional private HTTPS. This leaf is not evidence that those requirements are complete.

## Reference implementation

```python
"""URL structure normalization; policy and sensitive-path checks remain mandatory."""

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def _host(value: str) -> str:
    if "%" in value:
        raise ValueError
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        if all(character in "0123456789." for character in value):
            raise ValueError from None
        encoded = value.removesuffix(".").encode("idna").decode("ascii").lower()
        if len(encoded) > 253 or any(not _LABEL.fullmatch(label) for label in encoded.split(".")):
            raise ValueError from None
        return encoded
    return f"[{address.compressed}]" if address.version == 6 else str(address)


def normalize_url(value: str) -> str:
    """Strip authority credentials, query and fragment; do not trust the path."""
    try:
        if not isinstance(value, str) or not value or len(value) > 8192:
            raise ValueError
        if any(character.isspace() or ord(character) < 32 or ord(character) == 127 or character == "\\" for character in value):
            raise ValueError
        parts = urlsplit(value)
        scheme = parts.scheme.lower()
        if scheme not in {"http", "https"} or not parts.hostname or parts.netloc.rsplit("@", 1)[-1].endswith(":"):
            raise ValueError
        hostname = _host(parts.hostname)
        port = parts.port
        if port == 0:
            raise ValueError
        suffix = f":{port}" if port is not None and port != {"http": 80, "https": 443}[scheme] else ""
        return urlunsplit((scheme, hostname + suffix, parts.path or "/", "", ""))
    except (ValueError, UnicodeError):
        raise ValueError("Invalid URL") from None
```
## Regression cases

```python
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
```
