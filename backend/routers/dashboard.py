"""Dashboard aggregates — every number comes from an indexed COUNT/GROUP BY,
never from loading rows into the application."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import ActivityLog, Attendance, Course, Department, Faculty, Student, User
from ..schemas import ActivityOut, DashboardStats
from ..security import get_current_user
from .students import _out as student_out

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _month_bucket(column, dialect: str):
    if dialect == "postgresql":
        return func.to_char(column, "YYYY-MM")
    return func.strftime("%Y-%m", column)


@router.get("/stats", response_model=DashboardStats)
def stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    total_students = int(db.scalar(select(func.count(Student.id))) or 0)
    total_faculty = int(db.scalar(select(func.count(Faculty.id))) or 0)
    total_departments = int(db.scalar(select(func.count(Department.id))) or 0)
    total_courses = int(db.scalar(select(func.count(Course.id))) or 0)
    active_students = int(
        db.scalar(select(func.count(Student.id)).where(Student.academic_status == "active")) or 0
    )

    today = date.today()
    marked_today = int(
        db.scalar(select(func.count(Attendance.id)).where(Attendance.date == today)) or 0
    )
    present_today = int(
        db.scalar(
            select(func.count(Attendance.id)).where(
                Attendance.date == today, Attendance.status.in_(("present", "late"))
            )
        )
        or 0
    )
    today_pct = round(present_today * 100 / marked_today, 1) if marked_today else None
    absent_today = int(
        db.scalar(
            select(func.count(Attendance.id)).where(
                Attendance.date == today, Attendance.status == "absent"
            )
        )
        or 0
    )

    recent_students = db.scalars(
        select(Student)
        .options(joinedload(Student.department), joinedload(Student.course))
        .order_by(Student.created_at.desc())
        .limit(5)
    ).unique().all()

    recently_updated_students = db.scalars(
        select(Student)
        .options(joinedload(Student.department))
        .order_by(Student.updated_at.desc())
        .limit(6)
    ).unique().all()
    recently_updated_faculty = db.scalars(
        select(Faculty)
        .options(joinedload(Faculty.department))
        .order_by(Faculty.updated_at.desc())
        .limit(6)
    ).unique().all()

    recent_updates = sorted(
        [
            {
                "entity": "student",
                "id": s.id,
                "code": s.student_id,
                "label": s.full_name,
                "detail": " · ".join(
                    part for part in (s.department.name if s.department else None, f"Sem {s.semester}") if part
                ),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in recently_updated_students
        ]
        + [
            {
                "entity": "faculty",
                "id": f.id,
                "code": f.faculty_id,
                "label": f.full_name,
                "detail": " · ".join(
                    part for part in (f.department.name if f.department else None, f.subject) if part
                ),
                "updated_at": f.updated_at.isoformat(),
            }
            for f in recently_updated_faculty
        ],
        key=lambda row: row["updated_at"],
        reverse=True,
    )[:6]

    recent_activity = db.scalars(
        select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(8)
    ).all()

    students_by_department = [
        {"department": name or "Unassigned", "code": code or "—", "students": int(count)}
        for name, code, count in db.execute(
            select(Department.name, Department.code, func.count(Student.id))
            .join(Student, Student.department_id == Department.id, isouter=True)
            .group_by(Department.name, Department.code)
            .order_by(func.count(Student.id).desc())
        ).all()
    ]

    faculty_by_department = [
        {"department": name or "Unassigned", "code": code or "—", "faculty": int(count)}
        for name, code, count in db.execute(
            select(Department.name, Department.code, func.count(Faculty.id))
            .join(Faculty, Faculty.department_id == Department.id, isouter=True)
            .group_by(Department.name, Department.code)
            .order_by(func.count(Faculty.id).desc())
        ).all()
    ]

    dialect = db.bind.dialect.name if db.bind else "sqlite"
    bucket = _month_bucket(Student.admission_date, dialect)
    start = date(today.year - 1, today.month, 1)
    admissions = db.execute(
        select(bucket.label("bucket"), func.count(Student.id))
        .where(Student.admission_date.is_not(None), Student.admission_date >= start)
        .group_by("bucket")
        .order_by("bucket")
    ).all()
    admissions_by_month = [{"month": b, "students": int(c)} for b, c in admissions]

    gender_split = [
        {"gender": (g or "unknown"), "count": int(c)}
        for g, c in db.execute(
            select(Student.gender, func.count(Student.id)).group_by(Student.gender)
        ).all()
    ]

    semester_split = [
        {"semester": int(s or 0), "count": int(c)}
        for s, c in db.execute(
            select(Student.semester, func.count(Student.id))
            .group_by(Student.semester)
            .order_by(Student.semester)
        ).all()
    ]

    trend_start = today - timedelta(days=13)
    trend_rows = db.execute(
        select(
            Attendance.date,
            func.count(Attendance.id),
            func.sum(case((Attendance.status.in_(("present", "late")), 1), else_=0)),
        )
        .where(Attendance.date >= trend_start)
        .group_by(Attendance.date)
        .order_by(Attendance.date)
    ).all()
    attendance_trend = [
        {
            "date": d.isoformat(),
            "total": int(t or 0),
            "present": int(p or 0),
            "percentage": round(int(p or 0) * 100 / int(t or 1), 1),
        }
        for d, t, p in trend_rows
    ]

    return DashboardStats(
        total_students=total_students,
        total_faculty=total_faculty,
        total_departments=total_departments,
        total_courses=total_courses,
        active_students=active_students,
        today_attendance_percentage=today_pct,
        attendance_marked_today=marked_today,
        today_present=present_today,
        today_absent=absent_today,
        recent_students=[student_out(s) for s in recent_students],
        recent_updates=recent_updates,
        recent_activity=[ActivityOut.model_validate(a) for a in recent_activity],
        students_by_department=students_by_department,
        faculty_by_department=faculty_by_department,
        admissions_by_month=admissions_by_month,
        gender_split=gender_split,
        semester_split=semester_split,
        attendance_trend=attendance_trend,
    )
