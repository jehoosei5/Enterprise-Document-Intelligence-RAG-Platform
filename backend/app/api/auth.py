from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, Token, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


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
    if user is None or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
