"""Faculty module: CRUD, search, export."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..config import EXPORT_ROW_LIMIT
from ..database import get_db
from ..models import Attendance, Department, Faculty, Student, User
from ..schemas import FacultyCreate, FacultyOut, FacultyUpdate
from ..security import get_current_user, require_roles
from ..services.audit import log_activity
from ..services.export import to_csv, to_pdf, to_xlsx
from .common import page_params, paginated

router = APIRouter(prefix="/faculty", tags=["faculty"])

SORTABLE = {
    "faculty_id": Faculty.faculty_id,
    "full_name": Faculty.full_name,
    "email": Faculty.email,
    "subject": Faculty.subject,
    "experience_years": Faculty.experience_years,
    "joining_date": Faculty.joining_date,
    "employment_status": Faculty.employment_status,
    "created_at": Faculty.created_at,
    "updated_at": Faculty.updated_at,
    "department": Department.name,
}

EXPORT_HEADERS = [
    "Faculty ID", "Full Name", "Email", "Phone", "Department", "Subject",
    "Qualification", "Joining Date", "Experience (years)", "Employment Status",
]


def _out(f: Faculty) -> FacultyOut:
    item = FacultyOut.model_validate(f)
    item.department_name = f.department.name if f.department else None
    return item


def _conds(q, department_id, employment_status, subject) -> list:
    conds: list = []
    if q:
        like = f"%{q.strip()}%"
        conds.append(
            or_(
                Faculty.faculty_id.ilike(like),
                Faculty.full_name.ilike(like),
                Faculty.email.ilike(like),
                Faculty.phone.ilike(like),
                Faculty.subject.ilike(like),
                Faculty.qualification.ilike(like),
            )
        )
    if department_id:
        conds.append(Faculty.department_id == department_id)
    if employment_status:
        conds.append(Faculty.employment_status == employment_status)
    if subject:
        conds.append(Faculty.subject.ilike(f"%{subject}%"))
    return conds


@router.get("")
def list_faculty(
    q: str | None = None,
    department_id: int | None = None,
    employment_status: str | None = None,
    subject: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    paging: tuple[int, int] = Depends(page_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    page, page_size = paging
    conds = _conds(q, department_id, employment_status, subject)
    total = int(db.scalar(select(func.count(Faculty.id)).where(*conds)) or 0)
    col = SORTABLE.get(sort, Faculty.created_at)
    stmt = (
        select(Faculty)
        .options(joinedload(Faculty.department))
        .where(*conds)
        .order_by(col.desc() if order.lower() == "desc" else col.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = db.scalars(stmt).unique().all()
    return paginated([_out(f) for f in rows], total, page, page_size)


@router.get("/export")
def export_faculty(
    request: Request,
    format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    q: str | None = None,
    department_id: int | None = None,
    employment_status: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conds = _conds(q, department_id, employment_status, None)
    col = SORTABLE.get(sort, Faculty.created_at)
    stmt = (
        select(Faculty)
        .options(joinedload(Faculty.department))
        .where(*conds)
        .order_by(col.desc() if order.lower() == "desc" else col.asc())
        .limit(EXPORT_ROW_LIMIT)
    )
    rows = [
        [
            f.faculty_id, f.full_name, f.email, f.phone,
            f.department.name if f.department else None,
            f.subject, f.qualification,
            f.joining_date.isoformat() if f.joining_date else None,
            f.experience_years, f.employment_status,
        ]
        for f in db.scalars(stmt).unique().all()
    ]
    stamp = date.today().isoformat()
    log_activity(db, user, "export", "faculty", None, f"{format.upper()}, {len(rows)} rows", request)
    db.commit()
    if format == "xlsx":
        return Response(
            to_xlsx("Faculty", EXPORT_HEADERS, rows),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="faculty-{stamp}.xlsx"'},
        )
    if format == "pdf":
        return Response(
            to_pdf("Faculty Register", EXPORT_HEADERS, rows),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="faculty-{stamp}.pdf"'},
        )
    return Response(
        to_csv(EXPORT_HEADERS, rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="faculty-{stamp}.csv"'},
    )


@router.get("/{record_id}", response_model=FacultyOut)
def get_faculty(record_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    fac = db.scalar(
        select(Faculty).options(joinedload(Faculty.department)).where(Faculty.id == record_id)
    )
    if not fac:
        raise HTTPException(404, "Faculty member not found")
    return _out(fac)


@router.post("", response_model=FacultyOut, status_code=201)
def create_faculty(
    payload: FacultyCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    if not db.get(Department, payload.department_id):
        raise HTTPException(400, "Department does not exist")
    fac = Faculty(**payload.model_dump())
    db.add(fac)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _dup(str(exc.orig)))
    log_activity(db, user, "create", "faculty", fac.id, f"{fac.faculty_id} {fac.full_name}", request)
    db.commit()
    db.refresh(fac)
    return _out(fac)


def _dup(raw: str) -> str:
    low = raw.lower()
    if "faculty_id" in low:
        return "This Faculty ID already exists"
    if "email" in low:
        return "This email is already registered"
    return "A faculty member with these unique details already exists"


@router.put("/{record_id}", response_model=FacultyOut)
def update_faculty(
    record_id: int,
    payload: FacultyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    fac = db.get(Faculty, record_id)
    if not fac:
        raise HTTPException(404, "Faculty member not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("department_id") and not db.get(Department, data["department_id"]):
        raise HTTPException(400, "Department does not exist")
    changed = []
    for key, value in data.items():
        if getattr(fac, key) != value:
            changed.append(key)
            setattr(fac, key, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _dup(str(exc.orig)))
    log_activity(db, user, "update", "faculty", fac.id, f"{fac.faculty_id}: {', '.join(changed) or 'no field changed'}", request)
    db.commit()
    db.refresh(fac)
    return _out(fac)


@router.delete("/{record_id}")
def delete_faculty(
    record_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    fac = db.get(Faculty, record_id)
    if not fac:
        raise HTTPException(404, "Faculty member not found")
    label = f"{fac.faculty_id} {fac.full_name}"
    db.execute(Attendance.__table__.delete().where(Attendance.faculty_id == record_id))
    db.delete(fac)
    log_activity(db, user, "delete", "faculty", record_id, label, request)
    db.commit()
    return {"detail": f"Faculty member {label} deleted"}
