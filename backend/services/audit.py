"""Audit trail helper — every write goes through this."""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from ..models import ActivityLog, User


def log_activity(
    db: Session,
    user: User | None,
    action: str,
    entity: str,
    entity_id: str | int | None = None,
    detail: str | None = None,
    request: Request | None = None,
) -> None:
    ip = None
    if request is not None:
        forwarded = request.headers.get("x-forwarded-for")
        ip = forwarded.split(",")[0].strip() if forwarded else (
            request.client.host if request.client else None
        )
    db.add(
        ActivityLog(
            user_id=user.id if user else None,
            user_email=user.email if user else None,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=detail,
            ip=ip,
        )
    )
