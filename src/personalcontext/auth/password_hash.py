"""Argon2id password hashing; not an authentication or rate-limit endpoint."""

from argon2 import PasswordHasher, Type, extract_parameters
from argon2.exceptions import HashingError, InvalidHashError, VerificationError

_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16, type=Type.ID)
_PREFIX = "$argon2id$v=19$m=19456,t=2,p=1$"


def _password_bytes(value: object, minimum: int) -> bytes:
    if not isinstance(value, str) or len(value) < minimum or len(value) > 1024:
        raise ValueError("Invalid password")
    try:
        data = value.encode("utf-8")
    except UnicodeError:
        raise ValueError("Invalid password") from None
    if len(data) > 1024:
        raise ValueError("Invalid password")
    return data


def hash_password(password: str) -> str:
    data = _password_bytes(password, 12)
    try:
        return _HASHER.hash(data)
    except HashingError:
        raise RuntimeError("Password hashing unavailable") from None


def verify_password(encoded: str, password: str) -> bool:
    try:
        data = _password_bytes(password, 1)
        if not isinstance(encoded, str) or len(encoded) > 256 or not encoded.startswith(_PREFIX):
            return False
        parameters = extract_parameters(encoded)
        if (parameters.type != Type.ID or parameters.version != 19 or parameters.memory_cost != 19456
                or parameters.time_cost != 2 or parameters.parallelism != 1
                or parameters.salt_len != 16 or parameters.hash_len != 32):
            return False
        return _HASHER.verify(encoded, data)
    except (ValueError, UnicodeError, InvalidHashError, VerificationError, OverflowError):
        return False
