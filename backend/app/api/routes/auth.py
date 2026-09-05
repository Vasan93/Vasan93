"""Signup, login and profile."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RateLimit, get_current_user
from app.core.db import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models import RatingHistory, User
from app.schemas.user import (
    SUPPORTED_LANGUAGES,
    LoginRequest,
    ProfileUpdate,
    SignupRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

signup_limit = RateLimit(limit=10, window_seconds=3600, name="signup")
login_limit = RateLimit(limit=20, window_seconds=300, name="login")


@router.get("/languages", response_model=list[str])
def languages() -> list[str]:
    return SUPPORTED_LANGUAGES


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db), _: None = Depends(signup_limit)) -> TokenResponse:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        preferred_language=payload.preferred_language,
        goal=payload.goal.strip(),
        current_rating_estimate=1000,
    )
    db.add(user)
    db.flush()
    # A starting point on the trajectory chart, replaced once assessment finishes.
    db.add(RatingHistory(user_id=user.id, rating=user.current_rating_estimate, source="signup"))
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db), _: None = Depends(login_limit)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        # Same message either way: do not reveal which accounts exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    return TokenResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> UserOut:
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.preferred_language is not None:
        user.preferred_language = payload.preferred_language
    if payload.goal is not None:
        user.goal = payload.goal.strip()
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
