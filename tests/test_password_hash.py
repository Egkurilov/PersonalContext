import unittest

from personalcontext.auth.password_hash import hash_password, verify_password


class PasswordHashTests(unittest.TestCase):
    def test_argon2id_uses_random_salt_and_verifies(self):
        candidate = "synthetic " + "пароль for test"
        first = hash_password(candidate)
        second = hash_password(candidate)
        self.assertTrue(first.startswith("$argon2id$v=19$m=19456,t=2,p=1$"))
        self.assertNotEqual(first, second)
        self.assertNotIn(candidate, first)
        self.assertTrue(verify_password(first, candidate))
        self.assertFalse(verify_password(first, "incorrect synthetic input"))

    def test_invalid_hashes_fail_closed(self):
        candidate = "synthetic " + "passphrase for test"
        encoded = hash_password(candidate)
        cases = ("", "not-a-hash", encoded.replace("$argon2id$", "$argon2i$"),
                 encoded.replace("m=19456", "m=1073741824"), encoded + "extra")
        for value in cases:
            with self.subTest(case=value[:12]):
                self.assertFalse(verify_password(value, candidate))

    def test_invalid_password_is_rejected_without_echo(self):
        for value in ("short", "a" * 1025, "a" * 12 + "\ud800"):
            with self.subTest(size=len(value)):
                with self.assertRaises(ValueError) as error:
                    hash_password(value)
                self.assertEqual(str(error.exception), "Invalid password")
                self.assertFalse(verify_password("invalid", value))
