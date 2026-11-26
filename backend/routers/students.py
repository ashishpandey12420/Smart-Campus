"""Student module: CRUD, search, import/export, profile."""
from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..config import EXPORT_ROW_LIMIT
from ..database import get_db
from ..models import Attendance, Course, Department, Student, User
from ..schemas import StudentCreate, StudentOut, StudentUpdate
from ..security import get_current_user, require_roles
from ..services.audit import log_activity
from ..services.export import to_csv, to_pdf, to_xlsx
from .common import count_rows, page_params, paginated

router = APIRouter(prefix="/students", tags=["students"])

SORTABLE = {
    "student_id": Student.student_id,
    "full_name": Student.full_name,
    "email": Student.email,
    "semester": Student.semester,
    "admission_date": Student.admission_date,
    "academic_status": Student.academic_status,
    "created_at": Student.created_at,
    "updated_at": Student.updated_at,
    "department": Department.name,
    "course": Course.name,
}

EXPORT_HEADERS = [
    "Student ID", "Full Name", "Father's Name", "Mother's Name", "Date of Birth",
    "Gender", "Email", "Mobile", "Address", "Department", "Course", "Semester",
    "Admission Date", "Enrollment No", "Academic Status",
]
CSV_TEMPLATE_HEADERS = [
    "student_id", "full_name", "father_name", "mother_name", "date_of_birth", "gender",
    "email", "mobile", "address", "department_code", "course_code", "semester",
    "admission_date", "enrollment_no", "academic_status",
]
HEADER_ALIASES = {
    "student id": "student_id", "studentid": "student_id", "roll": "student_id",
    "name": "full_name", "full name": "full_name", "student name": "full_name",
    "father": "father_name", "father's name": "father_name", "father name": "father_name",
    "mother": "mother_name", "mother's name": "mother_name", "mother name": "mother_name",
    "dob": "date_of_birth", "date of birth": "date_of_birth", "birth date": "date_of_birth",
    "department": "department_code", "dept": "department_code", "department code": "department_code",
    "course": "course_code", "course code": "course_code",
    "enrollment": "enrollment_no", "enrollment no": "enrollment_no", "enrollment number": "enrollment_no",
    "status": "academic_status", "academic status": "academic_status",
    "admission": "admission_date", "admission date": "admission_date",
}


def _filters(
    q: str | None = None,
    department_id: int | None = None,
    course_id: int | None = None,
    semester: int | None = None,
    gender: str | None = None,
    academic_status: str | None = None,
    admission_from: date | None = None,
    admission_to: date | None = None,
) -> list:
    conds: list = []
    if q:
        like = f"%{q.strip()}%"
        conds.append(
            or_(
                Student.student_id.ilike(like),
                Student.full_name.ilike(like),
                Student.email.ilike(like),
                Student.mobile.ilike(like),
                Student.enrollment_no.ilike(like),
                Student.father_name.ilike(like),
            )
        )
    if department_id:
        conds.append(Student.department_id == department_id)
    if course_id:
        conds.append(Student.course_id == course_id)
    if semester:
        conds.append(Student.semester == semester)
    if gender:
        conds.append(Student.gender == gender)
    if academic_status:
        conds.append(Student.academic_status == academic_status)
    if admission_from:
        conds.append(Student.admission_date >= admission_from)
    if admission_to:
        conds.append(Student.admission_date <= admission_to)
    return conds


def _out(s: Student) -> StudentOut:
    item = StudentOut.model_validate(s)
    item.department_name = s.department.name if s.department else None
    item.course_name = s.course.name if s.course else None
    return item


def _export_rows(students: list[Student]) -> list[list]:
    return [
        [
            s.student_id, s.full_name, s.father_name, s.mother_name,
            s.date_of_birth.isoformat() if s.date_of_birth else None,
            s.gender, s.email, s.mobile, s.address,
            s.department.name if s.department else None,
            s.course.name if s.course else None,
            s.semester,
            s.admission_date.isoformat() if s.admission_date else None,
            s.enrollment_no, s.academic_status,
        ]
        for s in students
    ]


def _load_export(db: Session, conds: list, sort: str, order: str) -> list[Student]:
    stmt = (
        select(Student)
        .options(joinedload(Student.department), joinedload(Student.course))
        .where(*conds)
    )
    col = SORTABLE.get(sort, Student.created_at)
    stmt = stmt.order_by(col.desc() if order.lower() == "desc" else col.asc())
    return list(db.scalars(stmt.limit(EXPORT_ROW_LIMIT)).unique().all())


@router.get("")
def list_students(
    q: str | None = None,
    department_id: int | None = None,
    course_id: int | None = None,
    semester: int | None = None,
    gender: str | None = None,
    academic_status: str | None = None,
    admission_from: date | None = None,
    admission_to: date | None = None,
    sort: str = "created_at",
    order: str = "desc",
    paging: tuple[int, int] = Depends(page_params),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    page, page_size = paging
    conds = _filters(q, department_id, course_id, semester, gender, academic_status, admission_from, admission_to)
    total = int(db.scalar(select(func.count(Student.id)).where(*conds)) or 0)
    col = SORTABLE.get(sort, Student.created_at)
    stmt = (
        select(Student)
        .options(joinedload(Student.department), joinedload(Student.course))
        .where(*conds)
        .order_by(col.desc() if order.lower() == "desc" else col.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = db.scalars(stmt).unique().all()
    return paginated([_out(s) for s in rows], total, page, page_size)


@router.get("/export")
def export_students(
    request: Request,
    format: str = Query("csv", pattern="^(csv|xlsx|pdf)$"),
    q: str | None = None,
    department_id: int | None = None,
    course_id: int | None = None,
    semester: int | None = None,
    gender: str | None = None,
    academic_status: str | None = None,
    sort: str = "created_at",
    order: str = "desc",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conds = _filters(q, department_id, course_id, semester, gender, academic_status)
    students = _load_export(db, conds, sort, order)
    rows = _export_rows(students)
    stamp = date.today().isoformat()
    log_activity(db, user, "export", "student", None, f"{format.upper()}, {len(rows)} rows", request)
    db.commit()

    if format == "xlsx":
        data = to_xlsx("Students", EXPORT_HEADERS, rows)
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="students-{stamp}.xlsx"'},
        )
    if format == "pdf":
        data = to_pdf("Student Register", EXPORT_HEADERS, rows)
        return Response(
            data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="students-{stamp}.pdf"'},
        )
    data = to_csv(EXPORT_HEADERS, rows)
    return Response(
        data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="students-{stamp}.csv"'},
    )


@router.get("/import/template")
def import_template(user: User = Depends(get_current_user)):
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"
    ws.append(CSV_TEMPLATE_HEADERS)
    ws.append([
        "SC2026001", "Aarav Sharma", "Rajesh Sharma", "Sunita Sharma", "2005-04-18",
        "male", "aarav.sharma@example.com", "9876543210", "12 MG Road, Pune",
        "CSE", "BTECH-CSE", 3, "2023-07-01", "ENR2026001", "active",
    ])
    ref = wb.create_sheet("Reference")
    ref.append(["department_code", "course_code", "note"])
    ref.append(["CSE", "BTECH-CSE", "Department and course codes must already exist in the system"])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="student-import-template.xlsx"'},
    )


def _read_table(filename: str, raw: bytes) -> list[dict]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        text = raw.decode("utf-8-sig")
        return [dict(r) for r in csv.DictReader(io.StringIO(text))]
    if lower.endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h).strip() if h is not None else "" for h in rows[0]]
        out = []
        for r in rows[1:]:
            if all(v is None or str(v).strip() == "" for v in r):
                continue
            out.append({headers[i]: r[i] for i in range(min(len(headers), len(r)))})
        return out
    raise HTTPException(400, "Upload a .csv or .xlsx file")


@router.post("/import")
async def import_students(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "File is larger than 20 MB")
    records = _read_table(file.filename or "", raw)
    if len(records) > 10000:
        raise HTTPException(400, "Import at most 10,000 rows per file")

    depts = {d.code.upper(): d.id for d in db.scalars(select(Department)).all()}
    courses = {c.code.upper(): c.id for c in db.scalars(select(Course)).all()}
    existing_ids = set(db.scalars(select(Student.student_id)).all())
    existing_emails = set(db.scalars(select(Student.email)).all())
    existing_enroll = set(db.scalars(select(Student.enrollment_no)).all())

    inserted, errors = 0, []
    seen_ids: set[str] = set()

    for index, raw_row in enumerate(records, start=2):
        row = {}
        for key, value in raw_row.items():
            clean = str(key).strip().lower() if key is not None else ""
            row[HEADER_ALIASES.get(clean, clean.replace(" ", "_"))] = value
        try:
            payload = dict(row)
            dept_code = str(payload.pop("department_code", "") or "").strip().upper()
            course_code = str(payload.pop("course_code", "") or "").strip().upper()
            if dept_code not in depts:
                raise ValueError(f"Unknown department code '{dept_code}'")
            payload["department_id"] = depts[dept_code]
            payload["course_id"] = courses.get(course_code) if course_code else None
            for key in ("date_of_birth", "admission_date"):
                val = payload.get(key)
                if isinstance(val, date):
                    payload[key] = val.isoformat()
            # Blank cells must fall back to the schema default/optional, not to None.
            payload = {
                key: value
                for key, value in payload.items()
                if value not in (None, "") or key in ("father_name", "mother_name", "mobile", "address", "course_id")
            }
            payload["father_name"] = payload.get("father_name") or None
            payload["mother_name"] = payload.get("mother_name") or None
            payload["mobile"] = payload.get("mobile") or None
            payload["address"] = payload.get("address") or None
            data = StudentCreate.model_validate(payload)
            if data.student_id in existing_ids or data.student_id in seen_ids:
                raise ValueError(f"Duplicate Student ID '{data.student_id}'")
            if data.email in existing_emails:
                raise ValueError(f"Duplicate email '{data.email}'")
            if data.enrollment_no in existing_enroll:
                raise ValueError(f"Duplicate enrollment number '{data.enrollment_no}'")
            with db.begin_nested():
                db.add(Student(**data.model_dump()))
                db.flush()
            seen_ids.add(data.student_id)
            existing_emails.add(data.email)
            existing_enroll.add(data.enrollment_no)
            inserted += 1
        except Exception as exc:  # noqa: BLE001 - per-row report, never abort the file
            message = str(exc)
            if hasattr(exc, "errors"):
                try:
                    message = "; ".join(
                        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()  # type: ignore[attr-defined]
                    )
                except Exception:  # pragma: no cover
                    pass
            errors.append({"row": index, "error": message})

    log_activity(db, user, "import", "student", None, f"{inserted} inserted, {len(errors)} failed", request)
    db.commit()
    return {"inserted": inserted, "failed": len(errors), "errors": errors[:200]}


@router.get("/{record_id}", response_model=StudentOut)
def get_student(record_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    student = db.scalar(
        select(Student)
        .options(joinedload(Student.department), joinedload(Student.course))
        .where(Student.id == record_id)
    )
    if not student:
        raise HTTPException(404, "Student not found")
    out = _out(student)
    total = db.scalar(select(func.count(Attendance.id)).where(Attendance.student_id == record_id)) or 0
    present = (
        db.scalar(
            select(func.count(Attendance.id)).where(
                Attendance.student_id == record_id, Attendance.status.in_(("present", "late"))
            )
        )
        or 0
    )
    out.attendance_percentage = round(present * 100 / total, 1) if total else None
    return out


@router.post("", response_model=StudentOut, status_code=201)
def create_student(
    payload: StudentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    if not db.get(Department, payload.department_id):
        raise HTTPException(400, "Department does not exist")
    if payload.course_id and not db.get(Course, payload.course_id):
        raise HTTPException(400, "Course does not exist")
    student = Student(**payload.model_dump())
    db.add(student)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _duplicate_message(str(exc.orig)))
    log_activity(db, user, "create", "student", student.id, f"{student.student_id} {student.full_name}", request)
    db.commit()
    db.refresh(student)
    return _out(student)


def _duplicate_message(raw: str) -> str:
    low = raw.lower()
    if "student_id" in low:
        return "This Student ID already exists"
    if "enrollment_no" in low:
        return "This enrollment number already exists"
    if "email" in low:
        return "This email is already registered"
    return "A student with these unique details already exists"


@router.put("/{record_id}", response_model=StudentOut)
def update_student(
    record_id: int,
    payload: StudentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    student = db.get(Student, record_id)
    if not student:
        raise HTTPException(404, "Student not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("department_id") and not db.get(Department, data["department_id"]):
        raise HTTPException(400, "Department does not exist")
    if data.get("course_id") and not db.get(Course, data["course_id"]):
        raise HTTPException(400, "Course does not exist")
    changed = []
    for key, value in data.items():
        if getattr(student, key) != value:
            changed.append(key)
            setattr(student, key, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _duplicate_message(str(exc.orig)))
    log_activity(db, user, "update", "student", student.id, f"{student.student_id}: {', '.join(changed) or 'no field changed'}", request)
    db.commit()
    db.refresh(student)
    return _out(student)


@router.delete("/{record_id}")
def delete_student(
    record_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "staff")),
):
    student = db.get(Student, record_id)
    if not student:
        raise HTTPException(404, "Student not found")
    label = f"{student.student_id} {student.full_name}"
    db.execute(Attendance.__table__.delete().where(Attendance.student_id == record_id))
    db.delete(student)
    log_activity(db, user, "delete", "student", record_id, label, request)
    db.commit()
    return {"detail": f"Student {label} deleted"}
