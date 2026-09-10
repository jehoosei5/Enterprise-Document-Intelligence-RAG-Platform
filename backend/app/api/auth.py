from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.email import send_password_reset_email
from app.core.security import (
    GoogleIdentityAction,
    InvalidTokenError,
    create_access_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    resolve_google_identity_action,
    verify_google_id_token,
    verify_password,
)
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GoogleSignInRequest,
    LoginRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _utcnow() -> datetime:
    """Naive UTC now, matching MySQL's DateTime column (no tz storage)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.post("/register", response_model=UserOut, status_code=201)
def register(request: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.query(User).filter(User.email == request.email).first() is not None:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    user = User(email=request.email, hashed_password=hash_password(request.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> Token:
    user = db.query(User).filter(User.email == request.email).first()
    # A Google-only account (no password set) fails the same generic way as
    # a wrong password — never reveal that the account has no password.
    if user is None or user.hashed_password is None or not verify_password(
        request.password, user.hashed_password
    ):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    return Token(access_token=create_access_token(user.id))


@router.post("/google", response_model=Token)
def google_sign_in(request: GoogleSignInRequest, db: Session = Depends(get_db)) -> Token:
    try:
        claims = verify_google_id_token(request.id_token)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid Google sign-in token")

    google_sub = claims["sub"]
    email = claims.get("email")
    email_verified = claims.get("email_verified", False)

    user_by_sub = db.query(User).filter(User.google_sub == google_sub).first()
    user_by_email = db.query(User).filter(User.email == email).first() if email else None

    action = resolve_google_identity_action(
        found_by_sub=user_by_sub is not None,
        email=email,
        email_verified=email_verified,
        found_by_email=user_by_email is not None,
    )

    if action == GoogleIdentityAction.USE_EXISTING:
        user = user_by_sub
    elif action == GoogleIdentityAction.LINK:
        user = user_by_email
        user.google_sub = google_sub
        db.commit()
    elif action == GoogleIdentityAction.CREATE:
        user = User(email=email, hashed_password=None, google_sub=google_sub)
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        raise HTTPException(status_code=401, detail="Unable to sign in with this Google account")

    return Token(access_token=create_access_token(user.id))


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)) -> ForgotPasswordResponse:
    settings = get_settings()
    user = db.query(User).filter(User.email == request.email).first()

    # Always the same response, whether or not the account exists (or has
    # a password to reset) — avoids leaking account existence.
    if user is not None and user.hashed_password is not None:
        token = generate_reset_token()
        user.reset_token_hash = hash_reset_token(token)
        user.reset_token_expires_at = _utcnow() + timedelta(
            minutes=settings.password_reset_expire_minutes
        )
        db.commit()

        reset_link = f"{settings.frontend_base_url}/reset-password?token={token}"
        send_password_reset_email(user.email, reset_link)

    return ForgotPasswordResponse()


@router.post("/reset-password", response_model=ForgotPasswordResponse)
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)) -> ForgotPasswordResponse:
    token_hash = hash_reset_token(request.token)
    user = db.query(User).filter(User.reset_token_hash == token_hash).first()

    if (
        user is None
        or user.reset_token_expires_at is None
        or user.reset_token_expires_at < _utcnow()
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.hashed_password = hash_password(request.new_password)
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    db.commit()

    return ForgotPasswordResponse(message="Password has been reset successfully.")


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
