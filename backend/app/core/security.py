"""Password hashing (raw bcrypt — passlib[bcrypt] is broken against the
installed bcrypt 5.x, see plan notes) and JWT access tokens.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

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
