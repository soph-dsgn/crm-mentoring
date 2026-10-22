from argon2 import PasswordHasher

from app.modules.auth.passwords import (
    LoginFormatError,
    PasswordManager,
    generate_temporary_password,
    normalize_login,
)


def test_password_hashing_verification_and_rehash() -> None:
    old_hasher = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    manager = PasswordManager(time_cost=2, memory_cost=1024, parallelism=1)
    old_hash = old_hasher.hash("correct horse battery staple")

    assert manager.verify("correct horse battery staple", old_hash) is True
    assert manager.verify("wrong password", old_hash) is False

    replacement = manager.verify_and_update("correct horse battery staple", old_hash)
    assert replacement is not None
    assert replacement != old_hash
    assert replacement.startswith("$argon2id$")
    assert manager.verify("correct horse battery staple", replacement) is True


def test_password_hash_uses_argon2id() -> None:
    manager = PasswordManager(time_cost=1, memory_cost=1024, parallelism=1)
    password_hash = manager.hash("a sufficiently long password")

    assert password_hash.startswith("$argon2id$")
    assert "m=1024,t=1,p=1" in password_hash
    assert "a sufficiently long password" not in password_hash

    try:
        manager.hash("too short")
    except ValueError:
        pass
    else:
        raise AssertionError("short permanent password should be rejected")


def test_login_normalization_and_validation() -> None:
    assert normalize_login("  Curator.Name  ") == "curator.name"
    assert normalize_login("ＣＵＲＡＴＯＲ") == "curator"
    assert normalize_login("Straße") == "strasse"

    for invalid_login in (
        "ab",
        "bad login",
        "кириллица",
        "сurator",
        "name@example.com",
        "-leading",
    ):
        try:
            normalize_login(invalid_login)
        except LoginFormatError:
            continue
        raise AssertionError(f"login should be rejected: {invalid_login}")


def test_temporary_password_is_long_and_has_no_ambiguous_characters() -> None:
    temporary_password = generate_temporary_password()

    assert len(temporary_password) >= 20
    assert set(temporary_password).isdisjoint({"0", "O", "I", "l"})
