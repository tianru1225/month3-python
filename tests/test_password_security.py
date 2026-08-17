from app.core.security import hash_password, verify_password


def test_password_is_stored_as_salted_argon2id_hash() -> None:
    password = "correct horse battery staple"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash.startswith("$argon2id$")
    assert password not in first_hash
    assert first_hash != second_hash
    assert verify_password(password, first_hash) is True
    assert verify_password(password, second_hash) is True


def test_password_verification_rejects_wrong_password_and_invalid_hash() -> None:
    password_hash = hash_password("correct password")

    assert verify_password("wrong password", password_hash) is False
    assert verify_password("any password", "!legacy-user-without-password") is False