"""Password hashing (raw bcrypt — passlib[bcrypt] is broken against the
installed bcrypt 5.x, see plan notes), JWT access tokens, Google ID-token
verification, and password-reset tokens.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from enum import Enum

import bcrypt
import jwt
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


class InvalidTokenError(Exception):
    pass


def decode_access_token(token: str) -> str:
    """Returns the user_id ("sub") encoded in the token, or raises
    InvalidTokenError for anything invalid/expired/tampered.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise InvalidTokenError(str(e)) from e

    user_id = payload.get("sub")
    if not user_id:
        raise InvalidTokenError("Token missing 'sub' claim")
    return user_id


# Cached across calls — reuses one HTTP connection for Google's public-key
# fetches instead of opening a fresh one per verification.
_google_auth_request = google_requests.Request()


def verify_google_id_token(id_token: str) -> dict:
    """Verifies a Google Identity Services ID token (signature, audience,
    expiry) and returns its claims dict, or raises InvalidTokenError.
    """
    settings = get_settings()
    try:
        return google_id_token.verify_oauth2_token(
            id_token, _google_auth_request, settings.google_client_id
        )
    except (ValueError, google_auth_exceptions.GoogleAuthError) as e:
        raise InvalidTokenError(str(e)) from e


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class GoogleIdentityAction(str, Enum):
    USE_EXISTING = "use_existing"  # google_sub already on file — just log in
    LINK = "link"  # verified email matches an existing password-only account
    CREATE = "create"  # no account at all yet
    REJECT = "reject"  # no usable, verified identity to act on


def resolve_google_identity_action(
    *, found_by_sub: bool, email: str | None, email_verified: bool, found_by_email: bool
) -> GoogleIdentityAction:
    """Pure decision logic for /auth/google's user lookup/link/create step,
    kept separate from DB I/O (app/api/auth.py) so it's unit-testable with
    plain booleans/claims instead of a real database and a real
    Google-signed token.
    """
    if found_by_sub:
        return GoogleIdentityAction.USE_EXISTING
    if email and email_verified:
        return GoogleIdentityAction.LINK if found_by_email else GoogleIdentityAction.CREATE
    return GoogleIdentityAction.REJECT
