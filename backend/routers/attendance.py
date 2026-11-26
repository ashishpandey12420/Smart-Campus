"""Attendance: daily sheet, bulk marking, monthly reports and percentages."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from ..config import EXPORT_ROW_LIMIT, MAX_PAGE_SIZE
from ..database import get_db
from ..models import Attendance, Department, Faculty, Student, User
from ..schemas import AttendanceBulkRequest, AttendanceOut, MonthlyAttendanceRow
from ..security import get_current_user, require_roles
from ..services.audit import log_activity
from ..services.export import to_csv, to_pdf, to_xlsx
from .common import page_params, paginated

router = APIRouter(prefix="/attendance", tags=["attendance"])

STATUSES = ("present", "absent", "late", "excused")


@router.get("/sheet")
def attendance_sheet(
    person_type: str = Query("student", pattern="^(student|faculty)$"),
    on_date: date = Query(default_factory=date.today, alias="date"),
    department_id: int | None = None,
    semester: int | None = None,
    course_id: int | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """People plus their status for one day — what the marking screen renders."""
    if person_type == "student":
        stmt = (
            select(Student)
            .options(joinedload(Student.department), joinedload(Student.course))
            .where(Student.academic_status == "active")
        )
        if department_id:
            stmt = stmt.where(Student.department_id == department_id)
        if semester:
            stmt = stmt.where(Student.semester == semester)
        if course_id:
            stmt = stmt.where(Student.course_id == course_id)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(Student.full_name.ilike(like) | Student.student_id.ilike(like))
        people = db.scalars(stmt.order_by(Student.full_name).limit(2000)).unique().all()
        marks = {
            a.student_id: a.status
            for a in db.scalars(
                select(Attendance).where(
                    Attendance.person_type == "student", Attendance.date == on_date
                )
            ).all()
        }
        items = [
            {
                "id": p.id,
                "code": p.student_id,
                "name": p.full_name,
                "department": p.department.name if p.department else None,
                "semester": p.semester,
                "status": marks.get(p.id, None),
            }
            for p in people
        ]
    else:
        stmt = select(Faculty).options(joinedload(Faculty.department)).where(
            Faculty.employment_status == "active"
        )
        if department_id:
            stmt = stmt.where(Faculty.department_id == department_id)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(Faculty.full_name.ilike(like) | Faculty.faculty_id.ilike(like))
        people = db.scalars(stmt.order_by(Faculty.full_name).limit(2000)).unique().all()
        marks = {
            a.faculty_id: a.status
            for a in db.scalars(
                select(Attendance).where(
                    Attendance.person_type == "faculty", Attendance.date == on_date
                )
            ).all()
        }
        items = [
            {
                "id": p.id,
                "code": p.faculty_id,
                "name": p.full_name,
                "department": p.department.name if p.department else None,
                "semester": None,
                "status": marks.get(p.id, None),
            }
            for p in people
        ]

    marked = sum(1 for i in items if i["status"])
    return {
        "date": on_date.isoformat(),
        "person_type": person_type,
        "items": items,
        "total_people": len(items),
        "marked": marked,
    }


@router.post("/bulk")
def mark_attendance(
    payload: AttendanceBulkRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff", "faculty")),
):
    ids = [r.person_id for r in payload.records]
    if payload.person_type == "student":
        existing = {
            a.student_id: a
            for a in db.scalars(
                select(Attendance).where(
                    Attendance.date == payload.date, Attendance.student_id.in_(ids)
                )
            ).all()
        }
        valid_ids = set(
            db.scalars(select(Student.id).where(Student.id.in_(ids))).all()
        )
    else:
        existing = {
            a.faculty_id: a
            for a in db.scalars(
                select(Attendance).where(
                    Attendance.date == payload.date, Attendance.faculty_id.in_(ids)
                )
            ).all()
        }
        valid_ids = set(db.scalars(select(Faculty.id).where(Faculty.id.in_(ids))).all())

    created = updated = skipped = 0
    for record in payload.records:
        if record.person_id not in valid_ids:
            skipped += 1
            continue
        row = existing.get(record.person_id)
        if row:
            row.status = record.status
            row.marked_by = user.id
            updated += 1
        else:
            row = Attendance(
                person_type=payload.person_type,
                student_id=record.person_id if payload.person_type == "student" else None,
                faculty_id=record.person_id if payload.person_type == "faculty" else None,
                date=payload.date,
                status=record.status,
                marked_by=user.id,
            )
            db.add(row)
            created += 1

    log_activity(
        db, user, "attendance", payload.person_type, payload.date.isoformat(),
        f"{created} added, {updated} updated, {skipped} skipped", request,
    )
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


@router.get("")
def list_attendance(
    on_date: date | None = Query(None, alias="date"),
    person_type: str | None = Query(None, pattern="^(student|faculty)$"),
    status_filter: str | None = Query(None, alias="status"),
    department_id: int | None = None,
    paging: tuple[int, int] = Depends(page_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    page, page_size = paging
    conds: list = []
    if on_date:
        conds.append(Attendance.date == on_date)
    if person_type:
        conds.append(Attendance.person_type == person_type)
    if status_filter:
        conds.append(Attendance.status == status_filter)
    if department_id:
        conds.append(
            Attendance.student_id.in_(
                select(Student.id).where(Student.department_id == department_id)
            )
            | Attendance.faculty_id.in_(
                select(Faculty.id).where(Faculty.department_id == department_id)
            )
        )

    total = int(db.scalar(select(func.count(Attendance.id)).where(*conds)) or 0)
    stmt = (
        select(Attendance)
        .options(joinedload(Attendance.student), joinedload(Attendance.faculty))
        .where(*conds)
        .order_by(Attendance.date.desc(), Attendance.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for a in db.scalars(stmt).unique().all():
        out = AttendanceOut.model_validate(a)
        if a.student:
            out.person_name, out.person_code = a.student.full_name, a.student.student_id
        elif a.faculty:
            out.person_name, out.person_code = a.faculty.full_name, a.faculty.faculty_id
        items.append(out)
    return paginated(items, total, page, page_size)


PRESENT = func.sum(case((Attendance.status.in_(("present", "late")), 1), else_=0))
ABSENT = func.sum(case((Attendance.status == "absent", 1), else_=0))
LATE = func.sum(case((Attendance.status == "late", 1), else_=0))
EXCUSED = func.sum(case((Attendance.status == "excused", 1), else_=0))
TOTAL = func.count(Attendance.id)
RATIO = (func.coalesce(PRESENT, 0) * 1.0) / func.nullif(TOTAL, 0)

EXPORT_HEADERS = [
    "Code", "Name", "Department", "Present", "Absent", "Late", "Excused", "Days", "Percentage",
]


def _monthly(person_type, first, last, department_id, semester, person_id, sort, order,
             limit=None, offset=0, db=None):
    """One query builder for both the on-screen report and its export."""
    entity = Student if person_type == "student" else Faculty
    link = Attendance.student_id if person_type == "student" else Attendance.faculty_id
    code_col = Student.student_id if person_type == "student" else Faculty.faculty_id

    stmt = (
        select(
            entity.id, code_col, entity.full_name, Department.name,
            PRESENT.label("present"), ABSENT.label("absent"), LATE.label("late"),
            EXCUSED.label("excused"), TOTAL.label("total"),
        )
        .join(Attendance, link == entity.id)
        .join(Department, Department.id == entity.department_id, isouter=True)
        .where(Attendance.date.between(first, last))
        .group_by(entity.id, code_col, entity.full_name, Department.name)
    )
    count_stmt = (
        select(func.count(func.distinct(entity.id)))
        .select_from(entity)
        .join(Attendance, link == entity.id)
        .where(Attendance.date.between(first, last))
    )
    if department_id:
        stmt = stmt.where(entity.department_id == department_id)
        count_stmt = count_stmt.where(entity.department_id == department_id)
    if semester and person_type == "student":
        stmt = stmt.where(Student.semester == semester)
        count_stmt = count_stmt.where(Student.semester == semester)
    if person_id:
        stmt = stmt.where(entity.id == person_id)
        count_stmt = count_stmt.where(entity.id == person_id)

    name_col = entity.full_name
    if sort == "percentage":
        stmt = stmt.order_by(RATIO.desc() if order.lower() == "desc" else RATIO.asc(), name_col)
    elif sort == "code":
        stmt = stmt.order_by(code_col.desc() if order.lower() == "desc" else code_col.asc())
    else:
        stmt = stmt.order_by(name_col.desc() if order.lower() == "desc" else name_col.asc())

    if limit:
        stmt = stmt.limit(limit).offset(offset)

    rows = db.execute(stmt).all()
    total = int(db.scalar(count_stmt) or 0)
    items = [
        MonthlyAttendanceRow(
            person_id=r[0], person_code=r[1], person_name=r[2], department=r[3],
            present=int(r[4] or 0), absent=int(r[5] or 0), late=int(r[6] or 0),
            excused=int(r[7] or 0), total=int(r[8] or 0),
            percentage=round(int(r[4] or 0) * 100 / int(r[8] or 1), 1),
        )
        for r in rows
    ]
    return items, total


@router.get("/monthly")
def monthly_report(
    person_type: str = Query("student", pattern="^(student|faculty)$"),
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    department_id: int | None = None,
    semester: int | None = None,
    person_id: int | None = None,
    sort: str = Query("name", pattern="^(name|percentage|code)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    paging: tuple[int, int] = Depends(page_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    page, page_size = paging
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    items, total = _monthly(
        person_type, first, last, department_id, semester, person_id, sort, order,
        limit=page_size, offset=(page - 1) * page_size, db=db,
    )
    return paginated(items, total, page, page_size)


@router.get("/monthly/export")
def export_monthly(
    request: Request,
    format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    person_type: str = Query("student", pattern="^(student|faculty)$"),
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    department_id: int | None = None,
    semester: int | None = None,
    sort: str = Query("name", pattern="^(name|percentage|code)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    items, total = _monthly(
        person_type, first, last, department_id, semester, None, sort, order,
        limit=EXPORT_ROW_LIMIT, db=db,
    )
    rows = [
        [i.person_code, i.person_name, i.department, i.present, i.absent, i.late, i.excused, i.total, f"{i.percentage}%"]
        for i in items
    ]
    title = f"{person_type.title()} attendance — {calendar.month_name[month]} {year}"
    stamp = f"{year}-{month:02d}"
    log_activity(db, user, "export", "attendance", stamp, f"{format.upper()}, {len(rows)} rows", request)
    db.commit()

    if format == "xlsx":
        return Response(
            to_xlsx("Attendance", EXPORT_HEADERS, rows),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="attendance-{person_type}-{stamp}.xlsx"'},
        )
    if format == "pdf":
        return Response(
            to_pdf(title, EXPORT_HEADERS, rows, subtitle=f"{total} people with records in this month"),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="attendance-{person_type}-{stamp}.pdf"'},
        )
    return Response(
        to_csv(EXPORT_HEADERS, rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="attendance-{person_type}-{stamp}.csv"'},
    )


@router.get("/person/{person_type}/{person_id}/calendar")
def person_calendar(
    person_type: str,
    person_id: int,
    year: int = Query(default_factory=lambda: date.today().year),
    month: int = Query(default_factory=lambda: date.today().month),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if person_type not in ("student", "faculty"):
        raise HTTPException(400, "person_type must be student or faculty")
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    column = Attendance.student_id if person_type == "student" else Attendance.faculty_id
    rows = db.scalars(
        select(Attendance)
        .where(column == person_id, Attendance.date.between(first, last))
        .order_by(Attendance.date)
    ).all()
    return [
        {"date": a.date.isoformat(), "status": a.status, "note": a.note} for a in rows
    ]


@router.get("/summary")
def attendance_summary(
    on_date: date = Query(default_factory=date.today, alias="date"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = db.execute(
        select(Attendance.person_type, Attendance.status, func.count())
        .where(Attendance.date == on_date)
        .group_by(Attendance.person_type, Attendance.status)
    ).all()
    out: dict = {"date": on_date.isoformat(), "student": {}, "faculty": {}}
    for person_type, status_value, count in rows:
        out[person_type][status_value] = count
    for kind in ("student", "faculty"):
        total = sum(out[kind].values())
        present = out[kind].get("present", 0) + out[kind].get("late", 0)
        out[kind]["total"] = total
        out[kind]["percentage"] = round(present * 100 / total, 1) if total else None
    return out


@router.get("/trend")
def attendance_trend(days: int = Query(30, ge=7, le=365), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    start = date.today() - timedelta(days=days - 1)
    rows = db.execute(
        select(
            Attendance.date,
            func.count(Attendance.id),
            func.sum(case((Attendance.status.in_(("present", "late")), 1), else_=0)),
        )
        .where(Attendance.date >= start)
        .group_by(Attendance.date)
        .order_by(Attendance.date)
    ).all()
    return [
        {
            "date": r[0].isoformat(),
            "total": int(r[1] or 0),
            "present": int(r[2] or 0),
            "percentage": round(int(r[2] or 0) * 100 / int(r[1] or 1), 1),
        }
        for r in rows
    ]
