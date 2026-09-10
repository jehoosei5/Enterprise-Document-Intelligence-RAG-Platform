import time

import jwt
import pytest

from app.core.security import (
    GoogleIdentityAction,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    resolve_google_identity_action,
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


def test_reset_token_hash_is_deterministic_and_not_reversible():
    token = generate_reset_token()
    assert hash_reset_token(token) == hash_reset_token(token)
    assert hash_reset_token(token) != token


def test_reset_tokens_are_unique():
    assert generate_reset_token() != generate_reset_token()


def test_google_identity_uses_existing_account_when_sub_matches():
    action = resolve_google_identity_action(
        found_by_sub=True, email="a@example.com", email_verified=True, found_by_email=True
    )
    assert action == GoogleIdentityAction.USE_EXISTING


def test_google_identity_links_verified_email_to_password_account():
    action = resolve_google_identity_action(
        found_by_sub=False, email="a@example.com", email_verified=True, found_by_email=True
    )
    assert action == GoogleIdentityAction.LINK


def test_google_identity_creates_new_account_for_unseen_verified_email():
    action = resolve_google_identity_action(
        found_by_sub=False, email="new@example.com", email_verified=True, found_by_email=False
    )
    assert action == GoogleIdentityAction.CREATE


def test_google_identity_rejects_unverified_email():
    action = resolve_google_identity_action(
        found_by_sub=False, email="a@example.com", email_verified=False, found_by_email=True
    )
    assert action == GoogleIdentityAction.REJECT


def test_google_identity_rejects_missing_email():
    action = resolve_google_identity_action(
        found_by_sub=False, email=None, email_verified=False, found_by_email=False
    )
    assert action == GoogleIdentityAction.REJECT
