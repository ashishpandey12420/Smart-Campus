"""Authentication: login, refresh, profile, password change."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import ChangePasswordRequest, LoginRequest, TokenResponse, UserOut
from ..security import (
    check_login_allowed,
    clear_login_attempts,
    client_ip,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    record_failed_login,
    verify_password,
)
from ..services.audit import log_activity

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshRequest(BaseModel):
    refresh_token: str


def _issue(user: User) -> TokenResponse:
    access, expires_in = create_access_token(user)
    return TokenResponse(
        access_token=access,
        refresh_token=create_refresh_token(user),
        expires_in=expires_in,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    ident = payload.username.strip()
    check_login_allowed(ident, ip)

    user = db.scalar(
        select(User).where(
            or_(User.username == ident.lower(), User.email == ident.lower())
        )
    )
    if not user or not verify_password(payload.password, user.password_hash):
        record_failed_login(ident, ip)
        if user:
            log_activity(db, user, "login_failed", "user", user.id, "Wrong password", request)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")

    clear_login_attempts(ident, ip)
    user.last_login = datetime.utcnow()
    log_activity(db, user, "login", "user", user.id, "Signed in", request)
    db.commit()
    db.refresh(user)
    return _issue(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    data = decode_token(payload.refresh_token, "refresh")
    user = db.get(User, int(data["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is inactive")
    return _issue(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    log_activity(db, user, "password_change", "user", user.id, None, request)
    db.commit()
    return {"detail": "Password updated"}
