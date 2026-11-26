"""Shared pagination / ordering helpers."""
from __future__ import annotations

from typing import Any, Sequence

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..config import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


def page_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> tuple[int, int]:
    return page, page_size


def count_rows(db: Session, stmt: Select) -> int:
    sub = stmt.order_by(None).subquery()
    return int(db.scalar(select(func.count()).select_from(sub)) or 0)


def apply_order(stmt: Select, column: Any, order: str) -> Select:
    return stmt.order_by(column.desc() if order.lower() == "desc" else column.asc())


def paginated(items: Sequence[Any], total: int, page: int, page_size: int) -> dict:
    return {
        "items": list(items),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }
