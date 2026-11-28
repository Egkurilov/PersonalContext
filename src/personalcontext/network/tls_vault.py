"""User-bound DPAPI protection for a TLS private-key passphrase."""

_ENTROPY = b"PersonalContext TLS passphrase v1"
_DESCRIPTION = "PersonalContext TLS passphrase v1"


def seal_passphrase(value: object) -> bytes:
    if type(value) is not bytes or not 1 <= len(value) <= 1024:
        raise ValueError("TLS secret unavailable")
    try:
        import win32crypt

        sealed = win32crypt.CryptProtectData(value, _DESCRIPTION, _ENTROPY, None, None, 1)
        if type(sealed) is not bytes or not 1 <= len(sealed) <= 8192:
            raise ValueError("Invalid protected value")
        return sealed
    except Exception:  # noqa: BLE001 - DPAPI errors are deliberately sanitized
        raise ValueError("TLS secret unavailable") from None


def open_passphrase(value: object) -> bytes:
    if type(value) is not bytes or not 1 <= len(value) <= 8192:
        raise ValueError("TLS secret unavailable")
    try:
        import win32crypt

        description, secret = win32crypt.CryptUnprotectData(value, _ENTROPY, None, None, 1)
        if description != _DESCRIPTION or type(secret) is not bytes or not 1 <= len(secret) <= 1024:
            raise ValueError("Invalid protected value")
        return secret
    except Exception:  # noqa: BLE001 - DPAPI errors are deliberately sanitized
        raise ValueError("TLS secret unavailable") from None
