from __future__ import annotations

import re
import secrets
import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

LOGIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
TEMPORARY_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


class LoginFormatError(ValueError):
    pass


def canonicalize_login(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def normalize_login(value: str) -> str:
    normalized = canonicalize_login(value)
    if not LOGIN_PATTERN.fullmatch(normalized):
        raise LoginFormatError(
            "Login must contain 3-64 ASCII letters, digits, dots, underscores or hyphens"
        )
    return normalized


class PasswordManager:
    def __init__(
        self,
        *,
        time_cost: int,
        memory_cost: int,
        parallelism: int,
        minimum_length: int = 12,
    ) -> None:
        self._hasher = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
        )
        self._minimum_length = minimum_length
        self._dummy_hash = self._hash_unchecked(secrets.token_urlsafe(32))

    def hash(self, password: str) -> str:
        if len(password) < self._minimum_length:
            raise ValueError(f"Password must be at least {self._minimum_length} characters")
        return self._hash_unchecked(password)

    def _hash_unchecked(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False

    def verify_and_update(self, password: str, password_hash: str) -> str | None:
        if not self.verify(password, password_hash):
            return None
        if self._hasher.check_needs_rehash(password_hash):
            return self._hash_unchecked(password)
        return password_hash

    def consume_dummy_verification(self, password: str) -> None:
        self.verify(password, self._dummy_hash)


def generate_temporary_password(length: int = 20) -> str:
    if length < 12:
        raise ValueError("Temporary password length must be at least 12")
    return "".join(secrets.choice(TEMPORARY_PASSWORD_ALPHABET) for _ in range(length))
