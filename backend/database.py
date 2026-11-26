"""Engine, session factory and declarative base."""
from __future__ import annotations

from typing import Generator

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

IS_SQLITE = DATABASE_URL.startswith("sqlite")


def _build_engine(url: str) -> Engine:
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # PostgreSQL: a pool sized for a small web deployment. Tune for the
        # number of uvicorn workers you actually run.
        kwargs.update(pool_size=10, max_overflow=20, pool_recycle=1800)
    return create_engine(url, **kwargs)


engine = _build_engine(DATABASE_URL)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record):  # pragma: no cover
    """WAL + foreign keys on SQLite: concurrent reads, enforced integrity."""
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reconfigure_engine(url: str | None = None) -> None:
    """Re-point the global engine (used after restoring a SQLite backup)."""
    global engine
    engine.dispose()
    engine = _build_engine(url or DATABASE_URL)
    SessionLocal.configure(bind=engine)
