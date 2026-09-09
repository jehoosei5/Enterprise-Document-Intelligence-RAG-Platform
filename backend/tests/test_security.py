import time

import jwt
import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings


def test_hash_password_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("wrong-password", hashed) is False


def test_access_token_roundtrip():
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"


def test_tampered_token_is_rejected():
    token = create_access_token("user-123")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token + "x")


def test_garbage_token_is_rejected():
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt-at-all")


def test_expired_token_is_rejected():
    settings = get_settings()
    payload = {"sub": "user-123", "iat": time.time() - 120, "exp": time.time() - 60}
    expired_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidTokenError):
        decode_access_token(expired_token)


def test_token_signed_with_wrong_secret_is_rejected():
    token = jwt.encode({"sub": "user-123"}, "a-completely-different-secret", algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)
