"""Activity log and user administration (admin only)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ActivityLog, User
from ..schemas import ActivityOut, UserCreate, UserOut, UserUpdate
from ..security import get_current_user, hash_password, require_roles
from ..services.audit import log_activity
from .common import page_params, paginated

router = APIRouter(tags=["admin"])


@router.get("/activity")
def list_activity(
    q: str | None = None,
    action: str | None = None,
    entity: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    paging: tuple[int, int] = Depends(page_params),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    page, page_size = paging
    conds: list = []
    if q:
        like = f"%{q.strip()}%"
        conds.append(
            or_(
                ActivityLog.user_email.ilike(like),
                ActivityLog.detail.ilike(like),
                ActivityLog.entity.ilike(like),
                ActivityLog.entity_id.ilike(like),
            )
        )
    if action:
        conds.append(ActivityLog.action == action)
    if entity:
        conds.append(ActivityLog.entity == entity)
    if date_from:
        conds.append(func.date(ActivityLog.created_at) >= date_from)
    if date_to:
        conds.append(func.date(ActivityLog.created_at) <= date_to)

    total = int(db.scalar(select(func.count(ActivityLog.id)).where(*conds)) or 0)
    rows = db.scalars(
        select(ActivityLog)
        .where(*conds)
        .order_by(ActivityLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return paginated([ActivityOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return [UserOut.model_validate(u) for u in db.scalars(select(User).order_by(User.created_at)).all()]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    account = User(
        email=str(payload.email).lower(),
        username=payload.username.lower(),
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
        faculty_id=payload.faculty_id,
        password_hash=hash_password(payload.password),
        must_change_password=True,
    )
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email is already taken")
    log_activity(db, user, "create", "user", account.id, f"{account.username} ({account.role})", request)
    db.commit()
    db.refresh(account)
    return UserOut.model_validate(account)


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    account = db.get(User, user_id)
    if not account:
        raise HTTPException(404, "User not found")
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    if account.id == user.id and data.get("role") and data["role"] != "admin":
        raise HTTPException(400, "You cannot remove your own administrator role")
    for key, value in data.items():
        if key == "email" and value:
            value = str(value).lower()
        setattr(account, key, value)
    if password:
        account.password_hash = hash_password(password)
        account.must_change_password = True
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email is already taken")
    log_activity(db, user, "update", "user", account.id, account.username, request)
    db.commit()
    db.refresh(account)
    return UserOut.model_validate(account)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    if user_id == user.id:
        raise HTTPException(400, "You cannot delete your own account")
    account = db.get(User, user_id)
    if not account:
        raise HTTPException(404, "User not found")
    if account.role == "admin":
        admins = db.scalar(select(func.count(User.id)).where(User.role == "admin")) or 0
        if admins <= 1:
            raise HTTPException(400, "At least one administrator must remain")
    label = account.username
    log_activity(db, user, "delete", "user", user_id, label, request)
    db.delete(account)
    db.commit()
    return {"detail": f"User {label} deleted"}
