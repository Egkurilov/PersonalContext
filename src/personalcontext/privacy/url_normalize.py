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
