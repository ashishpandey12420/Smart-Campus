"""Password hashing, JWT handling and role-based access control."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    BCRYPT_ROUNDS,
    JWT_ALGORITHM,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_SECONDS,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
)
from .database import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def _pw_bytes(password: str) -> bytes:
    # bcrypt ignores everything past 72 bytes; truncate deterministically.
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(password), hashed.encode())
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
def create_access_token(user: User) -> tuple[str, int]:
    expires_in = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM), expires_in


def create_refresh_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please sign in again")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid authentication token")
    if payload.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
    return payload


# --------------------------------------------------------------------------- #
# Brute-force protection (in-process, per user+IP)
# --------------------------------------------------------------------------- #
_attempts: dict[str, list[float]] = {}
_lock = threading.Lock()


def _attempt_key(username: str, ip: str) -> str:
    return f"{username.lower()}|{ip}"


def check_login_allowed(username: str, ip: str) -> None:
    now = time.time()
    with _lock:
        hits = [t for t in _attempts.get(_attempt_key(username, ip), []) if now - t < LOGIN_WINDOW_SECONDS]
        _attempts[_attempt_key(username, ip)] = hits
        if len(hits) >= LOGIN_MAX_ATTEMPTS:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Too many failed attempts. Try again in {LOGIN_WINDOW_SECONDS // 60} minutes.",
            )


def record_failed_login(username: str, ip: str) -> None:
    with _lock:
        _attempts.setdefault(_attempt_key(username, ip), []).append(time.time())


def clear_login_attempts(username: str, ip: str) -> None:
    with _lock:
        _attempts.pop(_attempt_key(username, ip), None)


# --------------------------------------------------------------------------- #
# Current user + RBAC
# --------------------------------------------------------------------------- #
def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else None
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token, "access")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is inactive")
    request.state.user = user
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    """Dependency factory: only the listed roles may call the endpoint."""

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Requires role: {' or '.join(roles)}. You are {user.role}.",
            )
        return user

    return _dep


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
