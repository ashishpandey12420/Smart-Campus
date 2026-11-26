"""System: backups, restore, project download, environment info."""
from __future__ import annotations

import io
import os
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import (
    APP_NAME,
    APP_VERSION,
    BACKUP_DIR,
    DATABASE_URL,
    ROOT_DIR,
)
from ..database import Base, engine, get_db, reconfigure_engine
from ..models import Course, Department, Faculty, Student, User
from ..schemas import BackupOut
from ..security import require_roles
from ..services.audit import log_activity

router = APIRouter(prefix="/system", tags=["system"])

EXCLUDE_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git", ".pytest_cache", ".mypy_cache", "backups", "app-build", "downloads"}


def _db_path() -> Path | None:
    if not DATABASE_URL.startswith("sqlite"):
        return None
    raw = DATABASE_URL.replace("sqlite:///C:/Users/Ashish Pandey/AppData/Local/SmartCampus/", "", 1).replace("sqlite://", "", 1)
    return Path(raw).expanduser().resolve()


def _backup_files() -> list[Path]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        [p for p in BACKUP_DIR.glob("smartcampus-*") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


@router.get("/info")
def info(db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "database": engine.dialect.name,
        "database_url_masked": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else engine.dialect.name,
        "students": int(db.scalar(select(func.count(Student.id))) or 0),
        "faculty": int(db.scalar(select(func.count(Faculty.id))) or 0),
        "departments": int(db.scalar(select(func.count(Department.id))) or 0),
        "courses": int(db.scalar(select(func.count(Course.id))) or 0),
        "backup_dir": str(BACKUP_DIR),
    }


@router.post("/backup", response_model=BackupOut, status_code=201)
def create_backup(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    db_path = _db_path()

    if db_path:
        target = BACKUP_DIR / f"smartcampus-{stamp}.db"
        # Merge the WAL into the main file before copying so the backup is complete.
        con = sqlite3.connect(db_path)
        try:
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            con.close()
        db.commit()
        shutil.copy2(db_path, target)
    else:
        target = BACKUP_DIR / f"smartcampus-{stamp}.sql"
        url = DATABASE_URL
        env = os.environ.copy()
        try:
            import subprocess

            subprocess.run(["pg_dump", "--no-owner", "--file", str(target), url], check=True, env=env, timeout=300)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, f"pg_dump failed: {exc}")

    log_activity(db, user, "backup", "system", target.name, f"{target.stat().st_size} bytes", request)
    db.commit()
    return BackupOut(
        name=target.name,
        size=target.stat().st_size,
        created_at=datetime.fromtimestamp(target.stat().st_mtime),
    )


@router.get("/backups", response_model=list[BackupOut])
def list_backups(user: User = Depends(require_roles("admin"))):
    return [
        BackupOut(
            name=p.name,
            size=p.stat().st_size,
            created_at=datetime.fromtimestamp(p.stat().st_mtime),
        )
        for p in _backup_files()
    ]


@router.get("/backups/{name}")
def download_backup(name: str, user: User = Depends(require_roles("admin"))):
    target = (BACKUP_DIR / name).resolve()
    if not str(target).startswith(str(BACKUP_DIR.resolve())) or not target.is_file():
        raise HTTPException(404, "Backup not found")
    return FileResponse(target, filename=target.name, media_type="application/octet-stream")


class RestoreRequest(BaseModel):
    name: str
    confirm: bool = False


@router.post("/restore")
def restore_backup(
    payload: RestoreRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    if not payload.confirm:
        raise HTTPException(400, "Restore must be confirmed")
    source = (BACKUP_DIR / payload.name).resolve()
    if not str(source).startswith(str(BACKUP_DIR.resolve())) or not source.is_file():
        raise HTTPException(404, "Backup not found")

    db_path = _db_path()
    if not db_path:
        raise HTTPException(
            400,
            "Live restore is only automated for SQLite. Restore PostgreSQL with psql/\
pg_restore against the server, then restart the app.",
        )
    log_activity(db, user, "restore", "system", source.name, "Database restored from backup", request)
    db.commit()
    db.close()
    engine.dispose()

    shutil.copy2(source, db_path)
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.exists():
            side.unlink()
    reconfigure_engine()
    with engine.connect() as conn:
        Base.metadata.create_all(bind=conn)
    return {"detail": f"Database restored from {source.name}. You may need to refresh the page."}


@router.get("/source.zip")
def download_source(user: User = Depends(require_roles("admin"))):
    """The whole project as a zip, so it can be moved to another machine
    without going through chat attachments."""
    buf = io.BytesIO()
    root = ROOT_DIR.resolve()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in root.rglob("*"):
            rel = path.relative_to(root)
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            if path.is_dir():
                continue
            if path.suffix in {".db", ".db-wal", ".db-shm", ".pyc"}:
                continue
            if path.name.endswith(".zip") and "SmartCampus" in path.name:
                continue
            try:
                zf.write(path, arcname=str(Path("SmartCampus") / rel))
            except OSError:
                continue
    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="SmartCampus-source-{stamp}.zip"'},
    )


APP_BUILD = ROOT_DIR / "app-build" / "SmartCampus-Windows.zip"


@router.get("/app-available")
def app_build_available():
    """Lets the UI show the download card only where a build exists."""
    if not APP_BUILD.exists():
        return {"available": False, "size_mb": None}
    return {"available": True, "size_mb": round(APP_BUILD.stat().st_size / (1024 * 1024))}


@router.get("/app-download")
def download_app_build():
    """The ready-to-run Windows app (portable, no Python install needed).

    Deliberately unauthenticated: the archive holds only the program, no data.
    """
    if not APP_BUILD.exists():
        raise HTTPException(404, "Windows app build not available on this server.")
    return FileResponse(
        APP_BUILD,
        media_type="application/zip",
        filename="Smart Campus App.zip",
    )
